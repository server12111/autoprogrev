import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import config
from database.db import Database
from handlers import setup_routers
from middlewares.user import UserMiddleware
from services.botohub import BotohubClient
from services.piarflow import PiarFlowClient
from services.warmup import WarmupService
from userbot.manager import UserbotManager
from utils.logger import setup_logging

logger = logging.getLogger(__name__)


def _handle_exception(loop, context):
    exc = context.get("exception")
    msg = context.get("message", "Unknown error")
    if isinstance(exc, asyncio.CancelledError):
        return  # normal shutdown
    logger.error("Unhandled asyncio exception: %s | %s", msg, exc, exc_info=exc)


async def main():
    setup_logging()
    logger.info("Starting AutoProgrev bot... Python %s", sys.version.split()[0])

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(_handle_exception)

    db = Database(config.DATABASE_PATH)
    await db.connect()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    userbot = UserbotManager(config.SESSIONS_PATH)
    botohub = BotohubClient(config.BOTOHUB_TOKEN)
    piarflow = PiarFlowClient(config.PIARFLOW_API_KEY)
    warmup = WarmupService(db, userbot, piarflow, bot=bot)

    # Dependency injection
    dp["db"] = db
    dp["userbot"] = userbot
    dp["botohub"] = botohub
    dp["piarflow"] = piarflow
    dp["warmup"] = warmup

    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    dp.include_router(setup_routers())

    # Register bot in PiarFlow
    if config.PIARFLOW_API_KEY and config.ADMIN_IDS:
        result = await piarflow.register_bot(
            bot_token=config.BOT_TOKEN,
            owner_chat_id=config.ADMIN_IDS[0],
        )
        if result:
            logger.info("PiarFlow: bot registered/confirmed OK")
        else:
            logger.warning("PiarFlow: registration failed — check API key")

    # Resume active warmups after restart
    await warmup.start()

    logger.info("Bot is polling...")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            # Auto-reconnect on network errors — default behaviour in aiogram 3
        )
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception:
        logger.critical("Polling stopped unexpectedly", exc_info=True)
    finally:
        logger.info("Shutting down...")
        await warmup.stop()
        try:
            await botohub.close()
        except Exception:
            pass
        try:
            await piarflow.close()
        except Exception:
            pass
        try:
            await db.close()
        except Exception:
            pass
        try:
            await bot.session.close()
        except Exception:
            pass
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
