import asyncio
import logging
import random
from datetime import datetime
from typing import TYPE_CHECKING, Dict

from telethon.errors import (
    AuthKeyUnregisteredError,
    PhoneNumberBannedError,
    UserDeactivatedError,
)

from config import config
from database.db import Database
from services.piarflow import PiarFlowClient
from userbot.manager import UserbotManager

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)


def calculate_trust_index(profile) -> float:
    """Calculate account trust index (0–100) from warmup profile stats."""
    score = 0.0
    score += min(profile.account_age_days * 1.0, 25)
    score += min(profile.total_subscriptions * 2.0, 20)
    score += min(profile.dialog_count * 2.0, 20)
    score += min(profile.outgoing_messages * 0.5, 15)
    score += min(profile.online_time_minutes / 60.0, 10)
    score += min(profile.channel_joins * 1.0, 10)
    return round(min(score, 100.0), 1)


def get_warming_level(trust_index: float) -> int:
    if trust_index <= 20:
        return 1
    if trust_index <= 40:
        return 2
    if trust_index <= 60:
        return 3
    if trust_index <= 80:
        return 4
    return 5


def make_progress_bar(value: float, maximum: float = 100, width: int = 10) -> str:
    filled = int(round(value / maximum * width))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {value:.1f}%"


class WarmupService:
    """Core account-warming service using the service-layer pattern."""

    def __init__(
        self,
        db: Database,
        userbot: UserbotManager,
        piarflow: PiarFlowClient,
        bot: "Bot" = None,
    ):
        self.db = db
        self.userbot = userbot
        self.piarflow = piarflow
        self.bot = bot
        self._tasks: Dict[int, asyncio.Task] = {}

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self):
        """Reconnect and resume active accounts after bot restart."""
        for account in await self.db.get_active_warming_accounts():
            if account.session_name and account.api_id and account.api_hash:
                ok = await self.userbot.connect_account(
                    account.id, account.session_name, account.api_id, account.api_hash
                )
                if ok:
                    self._spawn_task(account.id)
                else:
                    await self.db.update_warming_account_status(
                        account.id, "error", "Session reconnect failed"
                    )

    async def stop(self):
        """Cancel all running tasks and disconnect clients."""
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        await self.userbot.disconnect_all()

    # ─── Public API ───────────────────────────────────────────────────────────

    async def start_warming(self, account_id: int) -> bool:
        """Activate warming for an account. Returns False if per-user limit reached."""
        account = await self.db.get_warming_account(account_id)
        if not account:
            return False

        active = await self.db.count_active_warming_accounts(user_id=account.user_id)
        if active >= config.MAX_WARMING_ACCOUNTS:
            return False

        if not self.userbot.is_connected(account_id):
            if account.session_name and account.api_id and account.api_hash:
                ok = await self.userbot.connect_account(
                    account_id, account.session_name, account.api_id, account.api_hash
                )
                if not ok:
                    return False

        await self.db.update_warming_account_status(account_id, "active")
        self._spawn_task(account_id)
        return True

    async def stop_warming(self, account_id: int):
        task = self._tasks.pop(account_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.db.update_warming_account_status(account_id, "paused")

    def get_active_count(self) -> int:
        return len(self._tasks)

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _spawn_task(self, account_id: int):
        if account_id in self._tasks:
            return
        task = asyncio.create_task(
            self._warming_loop(account_id), name=f"warmup_{account_id}"
        )
        task.add_done_callback(lambda t: self._on_done(account_id, t))
        self._tasks[account_id] = task

    def _on_done(self, account_id: int, task: asyncio.Task):
        self._tasks.pop(account_id, None)
        if not task.cancelled() and task.exception():
            logger.error("Warming task %s raised: %s", account_id, task.exception())

    async def _notify(self, account_id: int, text: str):
        """Send message to the account's owner via bot."""
        if not self.bot:
            return
        try:
            account = await self.db.get_warming_account(account_id)
            if not account:
                return
            user = await self.db.get_user_by_id(account.user_id)
            if user:
                await self.bot.send_message(user.telegram_id, text, parse_mode="HTML")
        except Exception as exc:
            logger.warning("Failed to notify user for account %s: %s", account_id, exc)

    async def _warming_loop(self, account_id: int):
        logger.info("Warming loop started for account %s", account_id)
        while True:
            try:
                account = await self.db.get_warming_account(account_id)
                if not account or account.status != "active":
                    break

                await self.db.reset_daily_stats_if_needed(account_id)

                profile = await self.db.get_warming_profile(account_id)
                if not profile:
                    break

                lvl_cfg = config.WARMING_LEVELS.get(
                    profile.warming_level, config.WARMING_LEVELS[1]
                )
                today_count = await self.db.get_today_actions_count(account_id)

                if today_count >= lvl_cfg["daily_actions"]:
                    logger.info(
                        "Account %s hit daily limit (%s/%s). Sleeping 1h.",
                        account_id, today_count, lvl_cfg["daily_actions"],
                    )
                    await asyncio.sleep(3600)
                    continue

                await self._perform_action(account_id, account, profile)

                delay = random.uniform(
                    lvl_cfg["action_delay_min"], lvl_cfg["action_delay_max"]
                )
                logger.info("Account %s: next action in %.0fs", account_id, delay)
                await asyncio.sleep(delay)

            except asyncio.CancelledError:
                break
            except (UserDeactivatedError, PhoneNumberBannedError, AuthKeyUnregisteredError) as exc:
                logger.error("Account %s banned/deactivated: %s", account_id, exc)
                await self.db.update_warming_account_status(account_id, "banned", str(exc))
                await self.db.log_action(account_id, "account_banned", {"error": str(exc)}, "failed")
                account = await self.db.get_warming_account(account_id)
                phone = account.phone if account else f"#{account_id}"
                await self._notify(
                    account_id,
                    f'<tg-emoji emoji-id="5870657884844462243">❌</tg-emoji> '
                    f'<b>Аккаунт {phone} заблокирован!</b>\n\n'
                    f'Telegram заблокировал аккаунт во время прогрева.\n'
                    f'Прогрев остановлен.'
                )
                break
            except Exception as exc:
                logger.error("Warming loop error account %s: %s", account_id, exc)
                await asyncio.sleep(60)

        logger.info("Warming loop ended for account %s", account_id)

    async def _perform_action(self, account_id: int, account, profile):
        action = random.choices(
            ["join_channel", "read_messages", "online_status", "simulate_online"],
            weights=[0.50, 0.25, 0.15, 0.10],
        )[0]

        if action == "join_channel":
            await self._act_join_channel(account_id, account, profile)
        elif action == "read_messages":
            await self._act_read_messages(account_id)
        elif action == "online_status":
            await self._act_online_status(account_id)
        elif action == "simulate_online":
            await self._act_simulate_online(account_id)

        await self._recalculate_trust(account_id)

    async def _act_join_channel(self, account_id: int, account, profile):
        # Берём каналы только из БД (добавляются администратором или накапливаются органически)
        sponsors = await self.db.get_sponsor_channels(limit=50)
        if not sponsors:
            logger.info("No channels in DB for account %s — skipping join", account_id)
            return

        channel_link = random.choice(sponsors).channel_link
        success = await self.userbot.join_channel(account_id, channel_link)
        status = "success" if success else "failed"
        await self.db.log_action(
            account_id, "join_channel",
            {"channel": channel_link},
            status,
        )

        if success:
            await self.db.increment_profile_stat(account_id, "total_subscriptions")
            await self.db.increment_profile_stat(account_id, "daily_subscriptions")
            await self.db.increment_profile_stat(account_id, "channel_joins")

    async def _act_read_messages(self, account_id: int):
        sponsors = await self.db.get_sponsor_channels(limit=10)
        if not sponsors:
            return
        channel = random.choice(sponsors)
        success = await self.userbot.read_channel_messages(account_id, channel.channel_link)
        await self.db.log_action(
            account_id,
            "read_messages",
            {"channel": channel.channel_link},
            "success" if success else "failed",
        )

    async def _act_online_status(self, account_id: int):
        ok = await self.userbot.update_online_status(account_id, online=True)
        await asyncio.sleep(random.uniform(30, 120))
        await self.userbot.update_online_status(account_id, online=False)
        await self.db.log_action(
            account_id, "online_status", {}, "success" if ok else "failed"
        )
        if ok:
            await self.db.increment_profile_stat(account_id, "online_time_minutes", 2)

    async def _act_simulate_online(self, account_id: int):
        minutes = random.randint(2, 8)
        actual = await self.userbot.simulate_online_session(account_id, minutes)
        await self.db.log_action(
            account_id, "simulate_online", {"minutes": actual}, "success"
        )
        if actual > 0:
            await self.db.increment_profile_stat(
                account_id, "online_time_minutes", actual
            )

    async def _recalculate_trust(self, account_id: int):
        profile = await self.db.get_warming_profile(account_id)
        if not profile:
            return
        old_level = profile.warming_level
        trust = calculate_trust_index(profile)
        level = get_warming_level(trust)
        await self.db.update_warming_profile(
            account_id,
            trust_index=trust,
            warming_level=level,
            last_action_at=datetime.now().isoformat(),
        )

        if level <= old_level:
            return

        account = await self.db.get_warming_account(account_id)
        phone = account.phone if account else f"#{account_id}"
        bar = make_progress_bar(trust)

        level_names = {
            1: "🌱 Новый",
            2: "Базовый",
            3: "Средний",
            4: "Высокий",
            5: "⭐ Прогрет",
        }

        if level == 5:
            await self._notify(
                account_id,
                f'<tg-emoji emoji-id="6041731551845159060">🎉</tg-emoji> '
                f'<b>Аккаунт {phone} полностью прогрет!</b>\n\n'
                f'{bar}\n\n'
                f'Уровень доверия достиг максимума — аккаунт готов к работе.\n'
                f'Прогрев продолжается для поддержания активности.'
            )
        else:
            cfg = config.WARMING_LEVELS.get(level, {})
            await self._notify(
                account_id,
                f'<tg-emoji emoji-id="5870930636742595124">📊</tg-emoji> '
                f'<b>Аккаунт {phone} — новый уровень!</b>\n\n'
                f'Уровень {old_level} → <b>{level}</b> ({level_names.get(level, "")})\n'
                f'{bar}\n\n'
                f'Теперь: {cfg.get("daily_actions", "?")} действий/день'
            )
