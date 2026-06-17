import logging

from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import config
from database.db import Database
from keyboards.inline import (
    _back_btn,
    _pf_link,
    _pf_title,
    admin_keyboard,
    main_menu_keyboard,
    subscription_check_keyboard,
)
from services.botohub import BotohubClient
from services.piarflow import PiarFlowClient

logger = logging.getLogger(__name__)
router = Router()

_tg = lambda eid, ch: f'<tg-emoji emoji-id="{eid}">{ch}</tg-emoji>'

WELCOME_TEXT = (
    f'{_tg("6030400221232501136", "🤖")} <b>Добро пожаловать в AutoProgrev!</b>\n\n'
    f'{_tg("5963103826075456248", "⬆")} Бот для автоматического прогрева Telegram-аккаунтов.\n\n'
    "Выберите раздел:"
)

HOW_IT_WORKS_TEXT = (
    f'{_tg("6028435952299413210", "ℹ")} <b>Как работает прогрев аккаунта</b>\n\n'
    "Прогрев — это постепенное наращивание активности аккаунта, чтобы Telegram не воспринимал его как спам-аккаунт "
    "и не ограничивал его возможности.\n\n"
    "━━━━━━━━━━━━━━━━━━\n"
    f'{_tg("5870930636742595124", "📊")} <b>5 уровней прогрева:</b>\n'
    "🌱 Уровень 1 (0–20%) — 3 действия/день, задержка 30–60 мин\n"
    "Уровень 2 (21–40%) — 7 действий/день, задержка 15–45 мин\n"
    "Уровень 3 (41–60%) — 12 действий/день, задержка 10–30 мин\n"
    "Уровень 4 (61–80%) — 18 действий/день, задержка 5–20 мин\n"
    f'{_tg("6041731551845159060", "🎉")} Уровень 5 (81–100%) — 25 действий/день, задержка 3–15 мин\n\n'
    "━━━━━━━━━━━━━━━━━━\n"
    f'{_tg("6030400221232501136", "🤖")} <b>Что делает бот с аккаунтом:</b>\n'
    f'• {_tg("5769289093221454192", "🔗")} Вступает в каналы из пула (накапливает подписки)\n'
    f'• {_tg("6037397706505195857", "👁")} Читает сообщения в каналах (имитация просмотра)\n'
    f'• {_tg("5983150113483134607", "⏰")} Обновляет статус онлайн\n'
    f'• {_tg("5345906554510012647", "🔄")} Проводит онлайн-сессии для накопления времени активности\n\n'
    "━━━━━━━━━━━━━━━━━━\n"
    f'{_tg("5870921681735781843", "📊")} <b>Индекс доверия</b> растёт на основе:\n'
    "возраст аккаунта · подписки · диалоги · "
    "сообщения · время онлайн · вступления в каналы\n\n"
    "Чем выше уровень — тем больше действий в день и тем активнее аккаунт."
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_pf_sponsors(piarflow: PiarFlowClient, user_id: int) -> list:
    """Получить список спонсоров из PiarFlow для пользователя."""
    if not piarflow.api_key:
        return []
    try:
        return await piarflow.get_sponsors(user_id=user_id, chat_id=user_id)
    except Exception as exc:
        logger.warning("PiarFlow get_sponsors failed for %s: %s", user_id, exc)
        return []


async def _get_unsubscribed_mandatory(bot: Bot, user_id: int, db: Database) -> list:
    """Вернуть обязательные DB-каналы, на которые пользователь не подписан."""
    channels = await db.get_mandatory_channels()
    result = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch.channel_id, user_id=user_id)
            if member.status in ("left", "kicked", "banned"):
                result.append(ch)
        except Exception:
            result.append(ch)
    return result


async def _verify_pf_sponsors(piarflow: PiarFlowClient, user_id: int, sponsors: list) -> list:
    """Проверить через PiarFlow check_completion — вернуть неподтверждённых спонсоров."""
    if not sponsors:
        return []
    links = [_pf_link(s) for s in sponsors if _pf_link(s)]
    if not links:
        return []
    try:
        result = await piarflow.check_completion(user_id, links)
        return [s for s in sponsors if result.get(_pf_link(s), "unsubscribed") != "subscribed"]
    except Exception as exc:
        logger.warning("PiarFlow check_completion failed: %s", exc)
        return sponsors  # при ошибке считаем все непроверенными


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, piarflow: PiarFlowClient, botohub: BotohubClient):
    user_id = message.from_user.id

    # Отправляем рекламу пользователю через BotoHub Views (hi=True для /start)
    await botohub.send_ad(chat_id=user_id, hi=True)

    pf_sponsors = await _get_pf_sponsors(piarflow, user_id)
    not_subscribed_mandatory = await _get_unsubscribed_mandatory(message.bot, user_id, db)

    if pf_sponsors or not_subscribed_mandatory:
        total = len(pf_sponsors) + len(not_subscribed_mandatory)
        await message.answer(
            f'{_tg("6030400221232501136", "🤖")} <b>Добро пожаловать в AutoProgrev!</b>\n\n'
            f'{_tg("6037249452824072506", "🔒")} Для доступа подпишитесь на <b>{total}</b> канал(а).\n'
            f'После подписки нажмите кнопку ниже.',
            reply_markup=subscription_check_keyboard(
                pf_sponsors, not_subscribed_mandatory, check_cb="check_sub_start"
            ),
            parse_mode="HTML",
        )
    else:
        await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard(), parse_mode="HTML")


@router.callback_query(lambda c: c.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        WELCOME_TEXT, reply_markup=main_menu_keyboard(), parse_mode="HTML"
    )


# ─── Subscription check (after /start) ───────────────────────────────────────

@router.callback_query(lambda c: c.data == "check_sub_start")
async def cb_check_sub_start(callback: CallbackQuery, db: Database, piarflow: PiarFlowClient):
    """Проверка подписок после /start — при успехе открывает главное меню."""
    user_id = callback.from_user.id

    # Сначала получаем актуальный список PiarFlow-задач
    pf_sponsors = await _get_pf_sponsors(piarflow, user_id)
    # Проверяем выполнение через API
    pf_remaining = await _verify_pf_sponsors(piarflow, user_id, pf_sponsors)
    # Проверяем обязательные каналы из БД
    not_subscribed_mandatory = await _get_unsubscribed_mandatory(callback.bot, user_id, db)

    if pf_remaining or not_subscribed_mandatory:
        total = len(pf_remaining) + len(not_subscribed_mandatory)
        await callback.answer(
            f"Осталось подписаться на {total} канал(а).", show_alert=True
        )
        await callback.message.edit_reply_markup(
            reply_markup=subscription_check_keyboard(
                pf_remaining, not_subscribed_mandatory, check_cb="check_sub_start"
            )
        )
        return

    await callback.answer("✅ Подписки подтверждены!", show_alert=True)
    await callback.message.edit_text(
        WELCOME_TEXT, reply_markup=main_menu_keyboard(), parse_mode="HTML"
    )


# ─── Warmup gate (only mandatory channels) ────────────────────────────────────

@router.callback_query(lambda c: c.data == "warmup_menu")
async def cb_warmup_menu_gate(callback: CallbackQuery, db: Database):
    """Проверяет обязательные подписки перед показом меню прогрева."""
    not_subscribed = await _get_unsubscribed_mandatory(callback.bot, callback.from_user.id, db)
    if not_subscribed:
        await callback.message.edit_text(
            f'{_tg("6037249452824072506", "🔒")} <b>Для доступа к прогреву подпишитесь на каналы:</b>',
            reply_markup=subscription_check_keyboard(
                [], not_subscribed, check_cb="check_sub_warmup"
            ),
            parse_mode="HTML",
        )
        return
    from handlers.accounts import _show_warmup_menu
    await _show_warmup_menu(callback, db)


@router.callback_query(lambda c: c.data == "check_sub_warmup")
async def cb_check_sub_warmup(callback: CallbackQuery, db: Database):
    """Проверка подписок после gate перед прогревом — при успехе открывает warmup_menu."""
    not_subscribed = await _get_unsubscribed_mandatory(callback.bot, callback.from_user.id, db)
    if not_subscribed:
        await callback.answer("❌ Вы ещё не подписались на все каналы.", show_alert=True)
        await callback.message.edit_reply_markup(
            reply_markup=subscription_check_keyboard(
                [], not_subscribed, check_cb="check_sub_warmup"
            )
        )
        return
    await callback.answer("✅ Подписки подтверждены!", show_alert=True)
    from handlers.accounts import _show_warmup_menu
    await _show_warmup_menu(callback, db)


# ─── Info / how it works ──────────────────────────────────────────────────────

@router.callback_query(lambda c: c.data == "how_it_works")
async def cb_how_it_works(callback: CallbackQuery):
    b = InlineKeyboardBuilder()
    b.row(_back_btn("main_menu"))
    await callback.message.edit_text(
        HOW_IT_WORKS_TEXT, reply_markup=b.as_markup(), parse_mode="HTML"
    )


# ─── Admin entry ──────────────────────────────────────────────────────────────

@router.message(lambda m: m.text and m.text.startswith("/admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        await message.answer("⛔ Недостаточно прав.")
        return
    await message.answer(
        "🛠 <b>Панель администратора</b>",
        reply_markup=admin_keyboard(),
        parse_mode="HTML",
    )
