from aiogram import Router
from aiogram.types import CallbackQuery

from config import config
from database.db import Database
from keyboards.inline import profile_keyboard
from services.warmup import calculate_trust_index, make_progress_bar

router = Router()

ACTION_LABELS = {
    "join_channel": "📢 Подписка на канал",
    "read_messages": "👁 Просмотр сообщений",
    "online_status": "🟢 Обновление статуса",
    "simulate_online": "⏱ Онлайн-сессия",
    "account_banned": "🚫 Аккаунт заблокирован",
}


@router.callback_query(lambda c: c.data and c.data.startswith("profile:"))
async def cb_profile(callback: CallbackQuery, db: Database):
    account_id = int(callback.data.split(":")[1])
    account = await db.get_warming_account(account_id)
    profile = await db.get_warming_profile(account_id)

    if not account or not profile:
        await callback.answer("Данные не найдены.", show_alert=True)
        return

    level = profile.warming_level
    level_cfg = config.WARMING_LEVELS.get(level, {})
    trust = profile.trust_index
    bar = make_progress_bar(trust)

    hours, mins = divmod(profile.online_time_minutes, 60)

    last_action = profile.last_action_at or "—"
    if last_action != "—":
        last_action = last_action[:16].replace("T", " ")

    lines = [
        f"📋 <b>Профиль прогрева</b>",
        f"📱 <b>{account.phone}</b>",
        "",
        f"🏆 <b>Уровень:</b> {level_cfg.get('emoji', '')} {level_cfg.get('name', '')} ({level}/5)",
        f"🔐 <b>Индекс доверия:</b> {bar}",
        "",
        "📊 <b>Статистика:</b>",
        f"  📅 Возраст аккаунта: <b>{profile.account_age_days}</b> дн.",
        f"  📢 Подписок всего: <b>{profile.total_subscriptions}</b>",
        f"  📢 Подписок сегодня: <b>{profile.daily_subscriptions}</b>",
        f"  💬 Диалогов: <b>{profile.dialog_count}</b>",
        f"  ✉️ Исходящих сообщений: <b>{profile.outgoing_messages}</b>",
        f"  ⏱ Время онлайн: <b>{hours}ч {mins}мин</b>",
        f"  📥 Вступлений в каналы: <b>{profile.channel_joins}</b>",
        "",
        f"⏰ <b>Последнее действие:</b> {last_action}",
    ]

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=profile_keyboard(account_id),
        parse_mode="HTML",
    )
