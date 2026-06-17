import aiosqlite
import json
import os
from datetime import date, datetime
from typing import Optional, List

from .models import SCHEMA, User, WarmingAccount, WarmingProfile, WarmingAction, SponsorChannel, MandatoryChannel


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    # ─── Users ───────────────────────────────────────────────────────────────

    async def get_or_create_user(
        self, telegram_id: int, username: str = None, first_name: str = None
    ) -> User:
        async with self._conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()

        if row:
            await self._conn.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
                (username, first_name, telegram_id),
            )
            await self._conn.commit()
            async with self._conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ) as cur:
                row = await cur.fetchone()
            return User(**dict(row))

        await self._conn.execute(
            "INSERT INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (telegram_id, username, first_name),
        )
        await self._conn.commit()
        async with self._conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
        return User(**dict(row))

    async def get_user(self, telegram_id: int) -> Optional[User]:
        async with self._conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
        return User(**dict(row)) if row else None

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        async with self._conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return User(**dict(row)) if row else None

    async def get_all_users(self) -> List[User]:
        async with self._conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
        return [User(**dict(r)) for r in rows]

    async def set_admin(self, telegram_id: int, is_admin: bool):
        await self._conn.execute(
            "UPDATE users SET is_admin = ? WHERE telegram_id = ?",
            (1 if is_admin else 0, telegram_id),
        )
        await self._conn.commit()

    # ─── Warming Accounts ─────────────────────────────────────────────────────

    async def create_warming_account(
        self, user_id: int, phone: str, api_id: int = None, api_hash: str = None
    ) -> WarmingAccount:
        await self._conn.execute(
            "INSERT INTO warming_accounts (user_id, phone, api_id, api_hash) VALUES (?, ?, ?, ?)",
            (user_id, phone, api_id, api_hash),
        )
        await self._conn.commit()

        async with self._conn.execute(
            "SELECT * FROM warming_accounts WHERE user_id = ? AND phone = ? ORDER BY id DESC LIMIT 1",
            (user_id, phone),
        ) as cur:
            row = await cur.fetchone()
        account = WarmingAccount(**dict(row))

        await self._create_warming_profile(account.id)
        return account

    async def _create_warming_profile(self, account_id: int):
        today = date.today().isoformat()
        await self._conn.execute(
            "INSERT OR IGNORE INTO warming_profiles (account_id, last_reset_date) VALUES (?, ?)",
            (account_id, today),
        )
        await self._conn.commit()

    async def get_warming_account(self, account_id: int) -> Optional[WarmingAccount]:
        async with self._conn.execute(
            "SELECT * FROM warming_accounts WHERE id = ?", (account_id,)
        ) as cur:
            row = await cur.fetchone()
        return WarmingAccount(**dict(row)) if row else None

    async def get_user_warming_accounts(self, user_id: int) -> List[WarmingAccount]:
        async with self._conn.execute(
            "SELECT * FROM warming_accounts WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [WarmingAccount(**dict(r)) for r in rows]

    async def get_active_warming_accounts(self) -> List[WarmingAccount]:
        async with self._conn.execute(
            "SELECT * FROM warming_accounts WHERE status = 'active'"
        ) as cur:
            rows = await cur.fetchall()
        return [WarmingAccount(**dict(r)) for r in rows]

    async def count_active_warming_accounts(self, user_id: int = None) -> int:
        if user_id is not None:
            async with self._conn.execute(
                "SELECT COUNT(*) FROM warming_accounts WHERE status = 'active' AND user_id = ?",
                (user_id,),
            ) as cur:
                row = await cur.fetchone()
        else:
            async with self._conn.execute(
                "SELECT COUNT(*) FROM warming_accounts WHERE status = 'active'"
            ) as cur:
                row = await cur.fetchone()
        return row[0]

    async def update_warming_account_status(
        self, account_id: int, status: str, error_message: str = None
    ):
        await self._conn.execute(
            "UPDATE warming_accounts SET status = ?, error_message = ? WHERE id = ?",
            (status, error_message, account_id),
        )
        await self._conn.commit()

    async def update_warming_account_session(
        self, account_id: int, session_name: str, telegram_id: int = None
    ):
        await self._conn.execute(
            "UPDATE warming_accounts SET session_name = ?, telegram_id = ? WHERE id = ?",
            (session_name, telegram_id, account_id),
        )
        await self._conn.commit()

    async def update_warming_account_api(
        self, account_id: int, api_id: int, api_hash: str
    ):
        await self._conn.execute(
            "UPDATE warming_accounts SET api_id = ?, api_hash = ? WHERE id = ?",
            (api_id, api_hash, account_id),
        )
        await self._conn.commit()

    async def delete_warming_account(self, account_id: int):
        await self._conn.execute(
            "DELETE FROM warming_actions WHERE account_id = ?", (account_id,)
        )
        await self._conn.execute(
            "DELETE FROM warming_profiles WHERE account_id = ?", (account_id,)
        )
        await self._conn.execute(
            "DELETE FROM warming_accounts WHERE id = ?", (account_id,)
        )
        await self._conn.commit()

    async def get_all_warming_accounts(self) -> List[WarmingAccount]:
        async with self._conn.execute(
            "SELECT * FROM warming_accounts ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
        return [WarmingAccount(**dict(r)) for r in rows]

    # ─── Warming Profiles ─────────────────────────────────────────────────────

    async def get_warming_profile(self, account_id: int) -> Optional[WarmingProfile]:
        async with self._conn.execute(
            "SELECT * FROM warming_profiles WHERE account_id = ?", (account_id,)
        ) as cur:
            row = await cur.fetchone()
        return WarmingProfile(**dict(row)) if row else None

    _PROFILE_COLUMNS = frozenset({
        "account_age_days", "total_subscriptions", "daily_subscriptions",
        "dialog_count", "outgoing_messages", "online_time_minutes",
        "channel_joins", "trust_index", "warming_level",
        "last_reset_date", "last_action_at", "updated_at",
    })

    async def update_warming_profile(self, account_id: int, **kwargs):
        if not kwargs:
            return
        safe = {k: v for k, v in kwargs.items() if k in self._PROFILE_COLUMNS}
        if not safe:
            return
        safe["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in safe)
        values = list(safe.values()) + [account_id]
        await self._conn.execute(
            f"UPDATE warming_profiles SET {set_clause} WHERE account_id = ?", values
        )
        await self._conn.commit()

    async def increment_profile_stat(self, account_id: int, stat: str, amount: int = 1):
        if stat not in self._PROFILE_COLUMNS:
            logger.warning("increment_profile_stat: unknown column %r", stat)
            return
        await self._conn.execute(
            f"UPDATE warming_profiles SET {stat} = {stat} + ?, updated_at = CURRENT_TIMESTAMP WHERE account_id = ?",
            (amount, account_id),
        )
        await self._conn.commit()

    async def reset_daily_stats_if_needed(self, account_id: int):
        today = date.today().isoformat()
        async with self._conn.execute(
            "SELECT last_reset_date FROM warming_profiles WHERE account_id = ?",
            (account_id,),
        ) as cur:
            row = await cur.fetchone()

        if row and row[0] != today:
            await self._conn.execute(
                "UPDATE warming_profiles SET daily_subscriptions = 0, last_reset_date = ? WHERE account_id = ?",
                (today, account_id),
            )
            await self._conn.commit()

    # ─── Warming Actions ──────────────────────────────────────────────────────

    async def log_action(
        self,
        account_id: int,
        action_type: str,
        details: dict = None,
        status: str = "success",
    ):
        details_json = json.dumps(details, ensure_ascii=False) if details else None
        await self._conn.execute(
            "INSERT INTO warming_actions (account_id, action_type, details, status) VALUES (?, ?, ?, ?)",
            (account_id, action_type, details_json, status),
        )
        await self._conn.commit()

    async def get_account_actions(
        self, account_id: int, limit: int = 20, offset: int = 0
    ) -> List[WarmingAction]:
        async with self._conn.execute(
            "SELECT * FROM warming_actions WHERE account_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (account_id, limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [WarmingAction(**dict(r)) for r in rows]

    async def count_account_actions(self, account_id: int) -> int:
        async with self._conn.execute(
            "SELECT COUNT(*) FROM warming_actions WHERE account_id = ?", (account_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0]

    async def get_today_actions_count(self, account_id: int) -> int:
        today = date.today().isoformat()
        async with self._conn.execute(
            "SELECT COUNT(*) FROM warming_actions WHERE account_id = ? AND status = 'success' AND DATE(created_at) = ?",
            (account_id, today),
        ) as cur:
            row = await cur.fetchone()
        return row[0]

    # ─── Sponsors ─────────────────────────────────────────────────────────────

    async def add_sponsor_channel(
        self, source: str, channel_link: str, channel_title: str = None
    ) -> bool:
        try:
            await self._conn.execute(
                "INSERT OR IGNORE INTO sponsor_channels (source, channel_link, channel_title) VALUES (?, ?, ?)",
                (source, channel_link, channel_title),
            )
            await self._conn.commit()
            return True
        except Exception:
            return False

    async def get_sponsor_channels(
        self, source: str = None, limit: int = 20, offset: int = 0
    ) -> List[SponsorChannel]:
        if source:
            async with self._conn.execute(
                "SELECT * FROM sponsor_channels WHERE is_active = 1 AND source = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (source, limit, offset),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with self._conn.execute(
                "SELECT * FROM sponsor_channels WHERE is_active = 1 ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ) as cur:
                rows = await cur.fetchall()
        return [SponsorChannel(**dict(r)) for r in rows]

    async def count_sponsor_channels(self) -> int:
        async with self._conn.execute(
            "SELECT COUNT(*) FROM sponsor_channels WHERE is_active = 1"
        ) as cur:
            row = await cur.fetchone()
        return row[0]

    # ─── Settings ─────────────────────────────────────────────────────────────

    async def get_setting(self, key: str, default: str = None) -> Optional[str]:
        async with self._conn.execute(
            "SELECT value FROM bot_settings WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else default

    async def set_setting(self, key: str, value: str):
        await self._conn.execute(
            "INSERT OR REPLACE INTO bot_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, value),
        )
        await self._conn.commit()

    # ─── Stats ────────────────────────────────────────────────────────────────

    async def get_global_stats(self) -> dict:
        stats = {}
        async with self._conn.execute("SELECT COUNT(*) FROM users") as c:
            stats["total_users"] = (await c.fetchone())[0]
        async with self._conn.execute("SELECT COUNT(*) FROM warming_accounts") as c:
            stats["total_accounts"] = (await c.fetchone())[0]
        async with self._conn.execute(
            "SELECT COUNT(*) FROM warming_accounts WHERE status = 'active'"
        ) as c:
            stats["active_accounts"] = (await c.fetchone())[0]
        async with self._conn.execute("SELECT COUNT(*) FROM warming_actions") as c:
            stats["total_actions"] = (await c.fetchone())[0]
        async with self._conn.execute(
            "SELECT COUNT(*) FROM warming_actions WHERE strftime('%Y-%m-%d', created_at) = strftime('%Y-%m-%d', 'now')"
        ) as c:
            stats["today_actions"] = (await c.fetchone())[0]
        async with self._conn.execute(
            "SELECT COUNT(*) FROM warming_actions WHERE status = 'success'"
        ) as c:
            stats["successful_actions"] = (await c.fetchone())[0]
        return stats

    # ─── Mandatory channels ───────────────────────────────────────────────────

    async def add_mandatory_channel(self, channel_id: str, channel_title: str = None) -> bool:
        try:
            await self._conn.execute(
                "INSERT OR IGNORE INTO mandatory_channels (channel_id, channel_title) VALUES (?, ?)",
                (channel_id, channel_title),
            )
            await self._conn.commit()
            return True
        except Exception:
            return False

    async def remove_mandatory_channel(self, channel_id: str) -> bool:
        try:
            await self._conn.execute(
                "DELETE FROM mandatory_channels WHERE channel_id = ?", (channel_id,)
            )
            await self._conn.commit()
            return True
        except Exception:
            return False

    async def get_mandatory_channels(self) -> List[MandatoryChannel]:
        async with self._conn.execute(
            "SELECT * FROM mandatory_channels ORDER BY added_at ASC"
        ) as cur:
            rows = await cur.fetchall()
        return [MandatoryChannel(**dict(r)) for r in rows]
