from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from config import config
from database.db import Database


class UserMiddleware(BaseMiddleware):
    """Register users on first interaction and inject db into handler data."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        db: Database = data.get("db")
        user = None

        if hasattr(event, "from_user") and event.from_user:
            tg_user = event.from_user
            if db:
                user = await db.get_or_create_user(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                )

        data["user"] = user
        data["is_admin"] = (
            user is not None
            and (bool(user.is_admin) or user.telegram_id in config.ADMIN_IDS)
        )

        return await handler(event, data)
