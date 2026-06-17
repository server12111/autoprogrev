import logging
import os
import sys


def setup_logging(level: int = logging.INFO) -> None:
    os.makedirs("data/logs", exist_ok=True)

    fmt = "%(asctime)s | %(levelname)-8s | %(name)s: %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt=date_fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("data/logs/bot.log", encoding="utf-8"),
        ],
    )

    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.WARNING)
