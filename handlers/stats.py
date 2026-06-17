from aiogram import Router
from aiogram.types import CallbackQuery

from database.db import Database
from keyboards.inline import stats_keyboard
from services.warmup import WarmupService

router = Router()


@router.callback_query(lambda c: c.data == "stats_menu")
async def cb_stats(callback: CallbackQuery, db: Database, warmup: WarmupService, user):
    global_stats = await db.get_global_stats()
    user_accounts = await db.get_user_warming_accounts(user.id)

    active_user = sum(1 for a in user_accounts if a.status == "active")
    total_user_subs = 0
    for acc in user_accounts:
        profile = await db.get_warming_profile(acc.id)
        if profile:
            total_user_subs += profile.total_subscriptions

    lines = [
        "📊 <b>Статистика</b>\n",
        "👤 <b>Ваши аккаунты:</b>",
        f"  Всего: <b>{len(user_accounts)}</b>",
        f"  Активных: <b>{active_user}</b>",
        f"  Подписок выполнено: <b>{total_user_subs}</b>",
        "",
        "🌐 <b>Общая статистика:</b>",
        f"  Пользователей: <b>{global_stats['total_users']}</b>",
        f"  Аккаунтов в системе: <b>{global_stats['total_accounts']}</b>",
        f"  Активных прогревов: <b>{global_stats['active_accounts']}/{warmup.get_active_count()}</b>",
        f"  Действий всего: <b>{global_stats['total_actions']}</b>",
        f"  Действий сегодня: <b>{global_stats['today_actions']}</b>",
        f"  Успешных: <b>{global_stats['successful_actions']}</b>",
    ]

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=stats_keyboard(),
        parse_mode="HTML",
    )
