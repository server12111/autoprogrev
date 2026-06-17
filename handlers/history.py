import json

from aiogram import Router
from aiogram.types import CallbackQuery

from database.db import Database
from keyboards.inline import history_keyboard

router = Router()

PAGE_SIZE = 10

ACTION_LABELS = {
    "join_channel": "📢 Подписка",
    "read_messages": "👁 Просмотр",
    "online_status": "🟢 Статус",
    "simulate_online": "⏱ Онлайн",
    "account_banned": "🚫 Бан",
}

STATUS_EMOJI = {"success": "✅", "failed": "❌"}


@router.callback_query(lambda c: c.data and c.data.startswith("history:"))
async def cb_history(callback: CallbackQuery, db: Database):
    _, acc_id_str, offset_str = callback.data.split(":")
    account_id = int(acc_id_str)
    offset = int(offset_str)

    account = await db.get_warming_account(account_id)
    if not account:
        await callback.answer("Аккаунт не найден.", show_alert=True)
        return

    total = await db.count_account_actions(account_id)
    actions = await db.get_account_actions(account_id, limit=PAGE_SIZE, offset=offset)

    lines = [
        f"📜 <b>История действий</b>",
        f"📱 {account.phone}",
        f"Всего: <b>{total}</b> | Страница {offset // PAGE_SIZE + 1}/{max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)}",
        "",
    ]

    if not actions:
        lines.append("История пуста.")
    else:
        for action in actions:
            label = ACTION_LABELS.get(action.action_type, action.action_type)
            status_ico = STATUS_EMOJI.get(action.status, "")
            ts = action.created_at[:16].replace("T", " ")
            detail = ""
            if action.details:
                try:
                    d = json.loads(action.details)
                    channel = d.get("channel", "")
                    if channel:
                        detail = f" — <code>{channel[:30]}</code>"
                except Exception:
                    pass
            lines.append(f"{status_ico} {ts} | {label}{detail}")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=history_keyboard(account_id, offset, total, PAGE_SIZE),
        parse_mode="HTML",
    )
