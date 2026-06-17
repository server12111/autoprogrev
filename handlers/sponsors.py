from aiogram import Router
from aiogram.types import CallbackQuery

from database.db import Database
from keyboards.inline import sponsors_keyboard
from services.piarflow import PiarFlowClient

router = Router()

PAGE_SIZE = 10

SOURCE_LABELS = {"botohub": "BotoHub", "piarflow": "PiarFlow", "manual": "Вручную"}


@router.callback_query(lambda c: c.data == "sponsors_menu" or (c.data and c.data.startswith("sponsors:")))
async def cb_sponsors(callback: CallbackQuery, db: Database, piarflow: PiarFlowClient):
    offset = 0
    if callback.data and callback.data.startswith("sponsors:"):
        offset = int(callback.data.split(":")[1])

    # Sync fresh sponsors from PiarFlow on first page load
    if offset == 0 and piarflow.api_key:
        sponsors_raw = await piarflow.get_sponsors()
        for s in sponsors_raw:
            link = s.get("link") or s.get("channel_link") or s.get("url", "")
            title = s.get("title") or s.get("name", "")
            if link:
                await db.add_sponsor_channel("piarflow", link, title)

    total = await db.count_sponsor_channels()
    channels = await db.get_sponsor_channels(limit=PAGE_SIZE, offset=offset)

    lines = [
        "🎯 <b>Спонсорские каналы</b>",
        f"Всего: <b>{total}</b>\n",
    ]

    if not channels:
        lines.append("Список спонсорских каналов пуст.")
        lines.append("\nОни появятся автоматически после выполнения первых заданий.")
    else:
        for ch in channels:
            src = SOURCE_LABELS.get(ch.source, ch.source)
            title = ch.channel_title or "—"
            lines.append(f"• <a href='{ch.channel_link}'>{title}</a> [{src}]")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=sponsors_keyboard(offset, total, PAGE_SIZE),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
