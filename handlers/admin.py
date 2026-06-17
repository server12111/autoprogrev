import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import config
from database.db import Database
from keyboards.inline import (
    _back_btn,
    admin_keyboard,
    admin_limits_keyboard,
    admin_mandatory_keyboard,
    cancel_keyboard,
)
from services.piarflow import PiarFlowClient
from services.warmup import WarmupService

logger = logging.getLogger(__name__)
router = Router()

_tg = lambda eid, ch: f'<tg-emoji emoji-id="{eid}">{ch}</tg-emoji>'


class IsAdmin(Filter):
    """Проверяет напрямую по ADMIN_IDS — не зависит от middleware."""
    async def __call__(self, event) -> bool:
        from_user = getattr(event, "from_user", None)
        if from_user is None:
            return False
        return from_user.id in config.ADMIN_IDS


class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_channel = State()


# ─── Admin panel ──────────────────────────────────────────────────────────────

@router.callback_query(IsAdmin(), F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        f'{_tg("5870982283724328568", "⚙️")} <b>Панель администратора</b>',
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(IsAdmin(), F.data == "admin_stats")
async def cb_admin_stats(
    callback: CallbackQuery, db: Database, warmup: WarmupService, piarflow: PiarFlowClient
):
    stats = await db.get_global_stats()
    lines = [
        f'{_tg("5870921681735781843", "📊")} <b>Общая статистика</b>\n',
        f'{_tg("5870772616305839506", "👥")} Пользователей: <b>{stats["total_users"]}</b>',
        f'{_tg("5870994129244131212", "👤")} Аккаунтов: <b>{stats["total_accounts"]}</b>',
        f'{_tg("5870633910337015697", "✅")} Активных прогревов: <b>{stats["active_accounts"]}</b> (в памяти: {warmup.get_active_count()})',
        f'{_tg("5870528606328852614", "📁")} Действий всего: <b>{stats["total_actions"]}</b>',
        f'{_tg("5890937706803894250", "📅")} Действий сегодня: <b>{stats["today_actions"]}</b>',
        f'{_tg("5870633910337015697", "✅")} Успешных: <b>{stats["successful_actions"]}</b>',
        f'\n{_tg("5870982283724328568", "⚙️")} Лимит одновременных аккаунтов: <b>{config.MAX_WARMING_ACCOUNTS}</b>',
    ]

    if piarflow.api_key:
        pf_info = await piarflow.get_bot_info()
        pf_today = await piarflow.get_bot_stats()
        if pf_info or pf_today:
            lines.append(f'\n{_tg("5769289093221454192", "🔗")} <b>PiarFlow:</b>')
        if pf_info:
            lines.append(f'  Пользователей в боте: <b>{pf_info.get("total_users", "—")}</b>')
        if pf_today:
            lines.append(f'  Подписок сегодня: <b>{pf_today.get("subscriptions", "—")}</b>')

    b = InlineKeyboardBuilder()
    b.row(_back_btn("admin_menu"))
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=b.as_markup(), parse_mode="HTML"
    )


@router.callback_query(IsAdmin(), F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery, db: Database):
    users = await db.get_all_users()
    lines = [f'{_tg("5870772616305839506", "👥")} <b>Пользователи ({len(users)}):</b>\n']
    for u in users[:30]:
        uname = f"@{u.username}" if u.username else u.first_name or "—"
        admin_mark = f' {_tg("5870676941614354370", "🖋")}' if (u.is_admin or u.telegram_id in config.ADMIN_IDS) else ""
        lines.append(f"• <code>{u.telegram_id}</code> {uname}{admin_mark}")
    if len(users) > 30:
        lines.append(f"\n…и ещё {len(users) - 30}")

    b = InlineKeyboardBuilder()
    b.row(_back_btn("admin_menu"))
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=b.as_markup(), parse_mode="HTML"
    )


@router.callback_query(IsAdmin(), F.data == "admin_accounts")
async def cb_admin_accounts(callback: CallbackQuery, db: Database):
    accounts = await db.get_all_warming_accounts()
    status_emoji = {
        "active": "🟢", "paused": "⏸", "pending": "⏳",
        "banned": "🚫", "error": "❌",
    }
    lines = [f'{_tg("5870994129244131212", "👤")} <b>Все аккаунты ({len(accounts)}):</b>\n']
    for acc in accounts[:30]:
        ico = status_emoji.get(acc.status, "❓")
        lines.append(f"• {ico} <code>{acc.phone}</code> (user {acc.user_id})")
    if len(accounts) > 30:
        lines.append(f"\n…и ещё {len(accounts) - 30}")

    b = InlineKeyboardBuilder()
    b.row(_back_btn("admin_menu"))
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=b.as_markup(), parse_mode="HTML"
    )


# ─── Limits ───────────────────────────────────────────────────────────────────

@router.callback_query(IsAdmin(), F.data == "admin_limits")
async def cb_admin_limits(callback: CallbackQuery):
    lines = [
        f'{_tg("5870982283724328568", "⚙️")} <b>Лимиты прогрева</b>\n',
        f'{_tg("5870994129244131212", "👤")} Макс. одновременных аккаунтов (на юзера): <b>{config.MAX_WARMING_ACCOUNTS}</b>',
    ]
    for lvl, cfg in config.WARMING_LEVELS.items():
        lines.append(
            f"\n{cfg['emoji']} <b>Уровень {lvl}</b> — {cfg['name']}:"
            f"\n  • Действий/день: {cfg['daily_actions']}"
            f"\n  • Задержка: {cfg['action_delay_min']//60}–{cfg['action_delay_max']//60} мин"
        )
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=admin_limits_keyboard(), parse_mode="HTML"
    )


# ─── Broadcast ────────────────────────────────────────────────────────────────

@router.callback_query(IsAdmin(), F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.message.edit_text(
        f'{_tg("6039422865189638057", "📣")} <b>Рассылка</b>\n\nВведите текст для отправки всем пользователям:',
        reply_markup=cancel_keyboard("admin_menu"),
        parse_mode="HTML",
    )


@router.message(IsAdmin(), AdminStates.waiting_broadcast)
async def fsm_broadcast(message: Message, state: FSMContext, db: Database):
    text = message.text or ""
    if not text:
        await message.answer("❌ Пустое сообщение.")
        return

    users = await db.get_all_users()
    sent = failed = 0
    await message.answer(f"⏳ Рассылка для {len(users)} пользователей...")

    for i, user in enumerate(users):
        try:
            await message.bot.send_message(user.telegram_id, text, parse_mode="HTML")
            sent += 1
        except Exception as exc:
            logger.warning("Broadcast failed for %s: %s", user.telegram_id, exc)
            failed += 1
        # Throttle: пауза каждые 25 сообщений чтобы не превысить лимит Telegram
        if (i + 1) % 25 == 0:
            await asyncio.sleep(1)

    await state.clear()
    await message.answer(
        f'{_tg("5870633910337015697", "✅")} <b>Рассылка завершена!</b>\n'
        f'{_tg("5870633910337015697", "✅")} Доставлено: {sent}\n'
        f'{_tg("5870657884844462243", "❌")} Ошибок: {failed}',
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )


# ─── Mandatory channels ───────────────────────────────────────────────────────

@router.callback_query(IsAdmin(), F.data == "admin_mandatory")
async def cb_admin_mandatory(callback: CallbackQuery, db: Database):
    channels = await db.get_mandatory_channels()
    count = len(channels)
    text = (
        f'{_tg("6037249452824072506", "🔒")} <b>Обязательные подписки ({count})</b>\n\n'
        "Пользователи должны подписаться на эти каналы перед использованием бота.\n"
    )
    if not channels:
        text += f'\n{_tg("6028435952299413210", "ℹ")} Список пуст. Добавьте каналы кнопкой ниже.'
    await callback.message.edit_text(
        text,
        reply_markup=admin_mandatory_keyboard(channels),
        parse_mode="HTML",
    )


@router.callback_query(IsAdmin(), F.data == "mandatory_add")
async def cb_mandatory_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_channel)
    await callback.message.edit_text(
        f'{_tg("5963103826075456248", "⬆")} <b>Добавить обязательный канал</b>\n\n'
        f'Отправьте username канала или числовой ID:\n'
        f'Примеры: <code>@mychannel</code> · <code>-1001234567890</code>',
        reply_markup=cancel_keyboard("admin_mandatory"),
        parse_mode="HTML",
    )


@router.message(IsAdmin(), AdminStates.waiting_channel)
async def fsm_add_channel(message: Message, state: FSMContext, db: Database):
    raw = message.text.strip() if message.text else ""
    if not raw:
        await message.answer("❌ Пустой ввод.")
        return

    # Нормализация: @username → @username, числовой ID оставляем как есть
    channel_id = raw if raw.startswith(("-", "@")) else f"@{raw}"

    # Пробуем получить название канала через бот
    channel_title = None
    try:
        chat = await message.bot.get_chat(channel_id)
        channel_title = chat.title or chat.username
        channel_id = str(chat.id)  # сохраняем числовой ID для надёжности
    except Exception as exc:
        logger.warning("Cannot get chat info for %s: %s", channel_id, exc)
        await message.answer(
            f"⚠️ Не удалось получить данные канала. Убедитесь что бот добавлен в канал как администратор.\n"
            f"Сохраняю как: <code>{channel_id}</code>",
            parse_mode="HTML",
        )

    ok = await db.add_mandatory_channel(channel_id, channel_title)
    await state.clear()

    if ok:
        title_str = f" ({channel_title})" if channel_title else ""
        await message.answer(
            f"✅ Канал <code>{channel_id}</code>{title_str} добавлен в обязательные подписки.",
            parse_mode="HTML",
        )
    else:
        await message.answer("⚠️ Канал уже в списке или ошибка сохранения.")

    channels = await db.get_mandatory_channels()
    await message.answer(
        f"🔒 <b>Обязательные подписки ({len(channels)})</b>",
        reply_markup=admin_mandatory_keyboard(channels),
        parse_mode="HTML",
    )


@router.callback_query(IsAdmin(), F.data.startswith("mandatory_remove:"))
async def cb_mandatory_remove(callback: CallbackQuery, db: Database):
    channel_id = callback.data.split(":", 1)[1]
    if not channel_id:
        await callback.answer("Ошибка: ID канала пустой.", show_alert=True)
        return
    await db.remove_mandatory_channel(channel_id)
    await callback.answer("🗑 Канал удалён.", show_alert=True)
    channels = await db.get_mandatory_channels()
    await callback.message.edit_text(
        f"🔒 <b>Обязательные подписки ({len(channels)})</b>",
        reply_markup=admin_mandatory_keyboard(channels),
        parse_mode="HTML",
    )


@router.callback_query(IsAdmin(), F.data.startswith("mandatory_info:"))
async def cb_mandatory_info(callback: CallbackQuery):
    await callback.answer("Нажмите 🗑 чтобы удалить канал.", show_alert=False)
