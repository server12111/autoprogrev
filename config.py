import os
from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids() -> list[int]:
    raw = os.getenv("ADMIN_IDS", "")
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: list[int] = _parse_admin_ids()

    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/bot.db")
    SESSIONS_PATH: str = os.getenv("SESSIONS_PATH", "data/sessions")

    PIARFLOW_API_KEY: str = os.getenv("PIARFLOW_API_KEY", "")
    PIARFLOW_BASE_URL: str = "https://api.piarflow.com"

    BOTOHUB_TOKEN: str = os.getenv("BOTOHUB_TOKEN", "")
    BOTOHUB_BASE_URL: str = "https://botohub.me"

    API_ID: int = 17251237
    API_HASH: str = "ea6f31223cf729d2ba4793cdeb017437"

    MAX_WARMING_ACCOUNTS: int = 5

    WARMING_LEVELS: dict = {
        1: {
            "name": "Новый аккаунт",
            "emoji": "🌱",
            "min_trust": 0,
            "max_trust": 20,
            "daily_actions": 3,
            "action_delay_min": 1800,
            "action_delay_max": 3600,
        },
        2: {
            "name": "Базовый прогрев",
            "emoji": "🔥",
            "min_trust": 21,
            "max_trust": 40,
            "daily_actions": 7,
            "action_delay_min": 900,
            "action_delay_max": 2700,
        },
        3: {
            "name": "Средний прогрев",
            "emoji": "🔥🔥",
            "min_trust": 41,
            "max_trust": 60,
            "daily_actions": 12,
            "action_delay_min": 600,
            "action_delay_max": 1800,
        },
        4: {
            "name": "Высокий прогрев",
            "emoji": "🔥🔥🔥",
            "min_trust": 61,
            "max_trust": 80,
            "daily_actions": 18,
            "action_delay_min": 300,
            "action_delay_max": 1200,
        },
        5: {
            "name": "Полностью прогрет",
            "emoji": "⭐",
            "min_trust": 81,
            "max_trust": 100,
            "daily_actions": 25,
            "action_delay_min": 180,
            "action_delay_max": 900,
        },
    }


config = Config()

# Validate critical settings at import time
if not config.BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in .env — bot cannot start")
if not config.ADMIN_IDS:
    raise RuntimeError("ADMIN_IDS is not set in .env — bot cannot start")
