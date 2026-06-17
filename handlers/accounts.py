import logging

from aiogram import F, Router

_tg = lambda eid, ch: f'<tg-emoji emoji-id="{eid}">{ch}</tg-emoji>'
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from telethon.errors import PhoneCodeExpiredError, PhoneCodeInvalidError, SessionPasswordNeededError

from config import config
from database.db import Database
from keyboards.inline import (
    account_detail_keyboard,
    cancel_keyboard,
    confirm_delete_keyboard,
    warmup_menu_keyboard,
)
from services.warmup import WarmupService
from userbot.manager import UserbotManager

logger = logging.getLogger(__name__)
router = Router()


class AddAccountStates(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()


# ─── Shared helper ────────────────────────────────────────────────────────────

async def _show_warmup_menu(callback: CallbackQuery, db: Database):
    user = await db.get_user(callback.from_user.id)
    accounts = await db.get_user_warming_accounts(user.id)
    active_ids = {a.id for a in accounts if a.status == "active"}
    text = f'{_tg("5963103826075456248", "⬆")} <b>Прогрев аккаунтов</b>\n\n'
    if accounts:
        text += f"У вас <b>{len(accounts)}</b> аккаунт(ов). Нажмите для управления:"
    else:
        text += f'У вас пока нет аккаунтов для прогрева.\nНажмите <b>Добавить аккаунт</b>.'
    await callback.message.edit_text(
        text,
        reply_markup=warmup_menu_keyboard(accounts, active_ids),
        parse_mode="HTML",
    )


# ─── Account detail ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("account_detail:"))
async def cb_account_detail(callback: CallbackQuery, db: Database):
    account_id = int(callback.data.split(":")[1])
    account = await db.get_warming_account(account_id)
    if not account:
        await callback.answer("Аккаунт не найден.", show_alert=True)
        return

    profile = await db.get_warming_profile(account_id)
    status_names = {
        "active": "🟢 Активен",
        "paused": "⏸ Пауза",
        "pending": "⏳ Ожидание",
        "banned": "🚫 Заблокирован",
        "error": "❌ Ошибка",
    }
    level_cfg = {}
    if profile:
        level_cfg = config.WARMING_LEVELS.get(profile.warming_level, {})

    lines = [
        f'{_tg("5870994129244131212", "👤")} <b>Аккаунт:</b> {account.phone}',
        f'{_tg("6037397706505195857", "👁")} <b>Статус:</b> {status_names.get(account.status, account.status)}',
    ]
    if profile:
        lines += [
            "",
            f'{_tg("5870930636742595124", "📊")} <b>Уровень:</b> {level_cfg.get("name", "")} ({profile.warming_level}/5)',
            f'{_tg("6037249452824072506", "🔒")} <b>Доверие:</b> {profile.trust_index:.1f}%',
        ]
    if account.error_message:
        lines.append(f'\n{_tg("5870657884844462243", "❌")} {account.error_message}')

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=account_detail_keyboard(account_id, account.status),
        parse_mode="HTML",
    )


# ─── Add account FSM ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "add_account")
async def cb_add_account(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddAccountStates.waiting_phone)
    await callback.message.edit_text(
        f'{_tg("5870994129244131212", "👤")} <b>Добавление аккаунта</b>\n\n'
        f'Введите <b>номер телефона</b> (например: +79991234567):',
        reply_markup=cancel_keyboard("warmup_menu"),
        parse_mode="HTML",
    )


@router.message(AddAccountStates.waiting_phone)
async def fsm_phone(message: Message, state: FSMContext, db: Database, user, userbot: UserbotManager):
    phone = message.text.strip() if message.text else ""
    if not phone.startswith("+"):
        await message.answer("❌ Номер должен начинаться с +. Попробуйте снова:")
        return

    await message.answer("⏳ Отправляю код подтверждения...")
    try:
        await userbot.start_login(phone, config.API_ID, config.API_HASH)
    except Exception as exc:
        logger.error("start_login error: %s", exc)
        await message.answer(f"❌ Ошибка: {exc}\nПроверьте номер телефона.")
        await state.clear()
        return

    account = await db.create_warming_account(user.id, phone, config.API_ID, config.API_HASH)
    await state.update_data(phone=phone, account_id=account.id)
    await state.set_state(AddAccountStates.waiting_code)
    await message.answer(
        "Введите <b>код из Telegram</b>:",
        reply_markup=cancel_keyboard("warmup_menu"),
        parse_mode="HTML",
    )


@router.message(AddAccountStates.waiting_code)
async def fsm_code(message: Message, state: FSMContext, db: Database, userbot: UserbotManager):
    code = message.text.strip() if message.text else ""
    data = await state.get_data()
    phone = data["phone"]
    account_id = data["account_id"]

    try:
        await userbot.complete_login(phone, code)
    except SessionPasswordNeededError:
        await state.set_state(AddAccountStates.waiting_password)
        await message.answer(
            "🔐 Требуется пароль двухфакторной аутентификации. Введите его:",
            reply_markup=cancel_keyboard("warmup_menu"),
        )
        return
    except PhoneCodeExpiredError:
        try:
            await userbot.resend_code(phone)
            await message.answer(
                "⏱ Код истёк. Отправил новый — введите его:",
                reply_markup=cancel_keyboard("warmup_menu"),
            )
        except Exception as exc:
            logger.error("resend_code error: %s", exc)
            await message.answer(f"❌ Не удалось переотправить код: {exc}")
            await db.update_warming_account_status(account_id, "error", str(exc))
            await state.clear()
        return
    except PhoneCodeInvalidError:
        await message.answer("❌ Неверный код. Попробуйте снова:")
        return
    except Exception as exc:
        logger.error("complete_login error: %s", exc)
        await message.answer(f"❌ Ошибка: {exc}")
        await db.update_warming_account_status(account_id, "error", str(exc))
        await state.clear()
        return

    await _finalize_account(message, state, db, userbot, account_id, phone)


@router.message(AddAccountStates.waiting_password)
async def fsm_password(message: Message, state: FSMContext, db: Database, userbot: UserbotManager):
    password = message.text.strip() if message.text else ""
    data = await state.get_data()
    phone = data["phone"]
    account_id = data["account_id"]

    try:
        await userbot.complete_2fa(phone, password)
    except Exception as exc:
        logger.error("complete_2fa error: %s", exc)
        await message.answer(f"❌ Неверный пароль: {exc}")
        return

    await _finalize_account(message, state, db, userbot, account_id, phone)


async def _finalize_account(
    message: Message,
    state: FSMContext,
    db: Database,
    userbot: UserbotManager,
    account_id: int,
    phone: str,
):
    session_name = f"acc_{account_id}"
    try:
        telegram_id = await userbot.finalize_login(
            phone, account_id, session_name, config.API_ID, config.API_HASH
        )
    except Exception as exc:
        logger.error("finalize_login error: %s", exc)
        await message.answer(f"❌ Ошибка сохранения сессии: {exc}")
        await db.update_warming_account_status(account_id, "error", str(exc))
        await state.clear()
        return

    if telegram_id is None:
        await message.answer("❌ Не удалось авторизоваться. Попробуйте снова.")
        await db.update_warming_account_status(account_id, "error", "Authorization failed")
        await state.clear()
        return

    await db.update_warming_account_session(account_id, session_name, telegram_id)
    await db.update_warming_account_status(account_id, "paused")
    await state.clear()

    await message.answer(
        f'{_tg("5870633910337015697", "✅")} <b>Аккаунт {phone} успешно добавлен!</b>\n\n'
        f'Нажмите <b>Запустить прогрев</b>, чтобы начать.',
        reply_markup=account_detail_keyboard(account_id, "paused"),
        parse_mode="HTML",
    )


# ─── Warmup controls ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("warmup_start:"))
async def cb_warmup_start(callback: CallbackQuery, db: Database, warmup: WarmupService):
    account_id = int(callback.data.split(":")[1])
    ok = await warmup.start_warming(account_id)
    if ok:
        await callback.answer("✅ Прогрев запущен!", show_alert=True)
    else:
        user = await db.get_user(callback.from_user.id)
        active = await db.count_active_warming_accounts(user_id=user.id)
        await callback.answer(
            f"❌ Лимит: у вас {active}/{config.MAX_WARMING_ACCOUNTS} активных аккаунтов.",
            show_alert=True,
        )
    account = await db.get_warming_account(account_id)
    if account:
        await callback.message.edit_reply_markup(
            reply_markup=account_detail_keyboard(account_id, account.status)
        )


@router.callback_query(F.data.startswith("warmup_stop:"))
async def cb_warmup_stop(callback: CallbackQuery, warmup: WarmupService, db: Database):
    account_id = int(callback.data.split(":")[1])
    await warmup.stop_warming(account_id)
    await callback.answer("⏸ Прогрев остановлен.", show_alert=True)
    await callback.message.edit_reply_markup(
        reply_markup=account_detail_keyboard(account_id, "paused")
    )


# ─── Delete ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("account_delete_confirm:"))
async def cb_delete_confirm(callback: CallbackQuery):
    account_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        "⚠️ <b>Удалить аккаунт?</b>\n\nВся история прогрева будет удалена.",
        reply_markup=confirm_delete_keyboard(account_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("account_delete:"))
async def cb_delete(callback: CallbackQuery, db: Database, warmup: WarmupService, userbot: UserbotManager):
    account_id = int(callback.data.split(":")[1])
    account = await db.get_warming_account(account_id)
    if account and account.status == "active":
        await warmup.stop_warming(account_id)
    await userbot.disconnect_account(account_id)
    await db.delete_warming_account(account_id)
    await callback.answer("🗑 Аккаунт удалён.", show_alert=True)
    await _show_warmup_menu(callback, db)
