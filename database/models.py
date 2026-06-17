from dataclasses import dataclass
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS warming_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    phone TEXT NOT NULL,
    api_id INTEGER,
    api_hash TEXT,
    session_name TEXT,
    telegram_id INTEGER,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS warming_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER UNIQUE NOT NULL,
    account_age_days INTEGER DEFAULT 0,
    total_subscriptions INTEGER DEFAULT 0,
    daily_subscriptions INTEGER DEFAULT 0,
    dialog_count INTEGER DEFAULT 0,
    outgoing_messages INTEGER DEFAULT 0,
    online_time_minutes INTEGER DEFAULT 0,
    channel_joins INTEGER DEFAULT 0,
    trust_index REAL DEFAULT 0.0,
    warming_level INTEGER DEFAULT 1,
    last_reset_date TEXT,
    last_action_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES warming_accounts(id)
);

CREATE TABLE IF NOT EXISTS warming_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    details TEXT,
    status TEXT DEFAULT 'success',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES warming_accounts(id)
);

CREATE TABLE IF NOT EXISTS sponsor_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    channel_link TEXT NOT NULL UNIQUE,
    channel_title TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mandatory_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL UNIQUE,
    channel_title TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass
class User:
    id: int
    telegram_id: int
    username: Optional[str]
    first_name: Optional[str]
    is_admin: int
    created_at: str


@dataclass
class WarmingAccount:
    id: int
    user_id: int
    phone: str
    api_id: Optional[int]
    api_hash: Optional[str]
    session_name: Optional[str]
    telegram_id: Optional[int]
    status: str
    error_message: Optional[str]
    created_at: str


@dataclass
class WarmingProfile:
    id: int
    account_id: int
    account_age_days: int
    total_subscriptions: int
    daily_subscriptions: int
    dialog_count: int
    outgoing_messages: int
    online_time_minutes: int
    channel_joins: int
    trust_index: float
    warming_level: int
    last_reset_date: Optional[str]
    last_action_at: Optional[str]
    updated_at: str


@dataclass
class WarmingAction:
    id: int
    account_id: int
    action_type: str
    details: Optional[str]
    status: str
    created_at: str


@dataclass
class SponsorChannel:
    id: int
    source: str
    channel_link: str
    channel_title: Optional[str]
    is_active: int
    created_at: str


@dataclass
class MandatoryChannel:
    id: int
    channel_id: str
    channel_title: Optional[str]
    added_at: str
