import asyncio
import logging
import os
import random
from typing import Dict, Optional

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    ChannelPrivateError,
    FloodWaitError,
    PhoneNumberBannedError,
    SessionPasswordNeededError,
    UserAlreadyParticipantError,
    UserDeactivatedError,
)
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import GetHistoryRequest, ReadHistoryRequest

from config import config

logger = logging.getLogger(__name__)

_TELETHON_TIMEOUT = 30   # seconds for any single Telethon call
_FLOOD_WAIT_CAP  = 300   # max seconds to wait on FloodWait (5 min)


async def _with_timeout(coro, timeout: int = _TELETHON_TIMEOUT):
    """Run a coroutine with a hard timeout; return None on TimeoutError."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("Telethon operation timed out after %ss", timeout)
        return None


class UserbotManager:
    """Manages Telethon client connections for account warming."""

    def __init__(self, sessions_path: str = None):
        self.sessions_path = sessions_path or config.SESSIONS_PATH
        os.makedirs(self.sessions_path, exist_ok=True)
        self._clients: Dict[int, TelegramClient] = {}
        self._login_clients: Dict[str, TelegramClient] = {}

    def _session_path(self, name: str) -> str:
        return os.path.join(self.sessions_path, name)

    # ─── Login flow ───────────────────────────────────────────────────────────

    async def start_login(self, phone: str, api_id: int, api_hash: str) -> None:
        session_path = self._session_path(f"tmp_{phone.replace('+', '')}")
        client = TelegramClient(session_path, api_id, api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                await client.send_code_request(phone)
            self._login_clients[phone] = client
        except Exception:
            try:
                await client.disconnect()
            except Exception:
                pass
            raise

    async def complete_login(self, phone: str, code: str) -> None:
        client = self._login_clients.get(phone)
        if not client:
            raise ValueError(f"No pending login for {phone}")
        await client.sign_in(phone, code)

    async def complete_2fa(self, phone: str, password: str) -> None:
        client = self._login_clients.get(phone)
        if not client:
            raise ValueError(f"No pending login for {phone}")
        await client.sign_in(password=password)

    async def finalize_login(
        self, phone: str, account_id: int, session_name: str, api_id: int, api_hash: str
    ) -> Optional[int]:
        client = self._login_clients.pop(phone, None)
        if not client:
            return None
        try:
            if not await client.is_user_authorized():
                return None
            me = await client.get_me()
            if not me:
                return None
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

        tmp_file = self._session_path(f"tmp_{phone.replace('+', '')}.session")
        perm_file = self._session_path(f"{session_name}.session")
        if os.path.exists(tmp_file):
            os.rename(tmp_file, perm_file)

        perm_client = TelegramClient(self._session_path(session_name), api_id, api_hash)
        try:
            await perm_client.connect()
            self._clients[account_id] = perm_client
        except Exception as exc:
            logger.error("Failed to connect permanent session for account %s: %s", account_id, exc)
            try:
                await perm_client.disconnect()
            except Exception:
                pass
            return None

        return me.id

    async def cancel_login(self, phone: str):
        client = self._login_clients.pop(phone, None)
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
        tmp = self._session_path(f"tmp_{phone.replace('+', '')}.session")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

    # ─── Client lifecycle ─────────────────────────────────────────────────────

    async def connect_account(
        self, account_id: int, session_name: str, api_id: int, api_hash: str
    ) -> bool:
        if account_id in self._clients:
            return True
        session_file = self._session_path(f"{session_name}.session")
        if not os.path.exists(session_file):
            logger.warning("Session file not found: %s", session_file)
            return False
        client = TelegramClient(self._session_path(session_name), api_id, api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return False
            self._clients[account_id] = client
            return True
        except Exception as exc:
            logger.error("Failed to connect account %s: %s", account_id, exc)
            try:
                await client.disconnect()
            except Exception:
                pass
            return False

    async def disconnect_account(self, account_id: int):
        client = self._clients.pop(account_id, None)
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def disconnect_all(self):
        for account_id in list(self._clients.keys()):
            await self.disconnect_account(account_id)

    def is_connected(self, account_id: int) -> bool:
        return account_id in self._clients

    async def get_me(self, account_id: int):
        client = self._clients.get(account_id)
        if not client:
            return None
        return await _with_timeout(client.get_me())

    # ─── Warming actions ──────────────────────────────────────────────────────

    async def join_channel(self, account_id: int, channel_link: str) -> bool:
        client = self._clients.get(account_id)
        if not client:
            return False
        try:
            await _with_timeout(client(JoinChannelRequest(channel_link)))
            logger.info("Account %s joined %s", account_id, channel_link)
            return True
        except UserAlreadyParticipantError:
            return True
        except FloodWaitError as exc:
            wait = min(exc.seconds, _FLOOD_WAIT_CAP)
            logger.warning("FloodWait %ss (capped %ss) for account %s", exc.seconds, wait, account_id)
            await asyncio.sleep(wait)
            return False
        except ChannelPrivateError:
            logger.warning("Channel %s is private/invalid", channel_link)
            return False
        except (UserDeactivatedError, PhoneNumberBannedError, AuthKeyUnregisteredError):
            raise
        except Exception as exc:
            logger.error("join_channel error for account %s: %s", account_id, exc)
            return False

    async def read_channel_messages(
        self, account_id: int, channel_link: str, count: int = 5
    ) -> bool:
        client = self._clients.get(account_id)
        if not client:
            return False
        try:
            entity = await _with_timeout(client.get_entity(channel_link))
            if entity is None:
                return False
            history = await _with_timeout(client(
                GetHistoryRequest(
                    peer=entity, limit=count, offset_date=None,
                    offset_id=0, max_id=0, min_id=0, add_offset=0, hash=0,
                )
            ))
            if history and history.messages:
                await _with_timeout(
                    client(ReadHistoryRequest(peer=entity, max_id=history.messages[0].id))
                )
            return True
        except FloodWaitError as exc:
            wait = min(exc.seconds, _FLOOD_WAIT_CAP)
            await asyncio.sleep(wait)
            return False
        except (UserDeactivatedError, PhoneNumberBannedError, AuthKeyUnregisteredError):
            raise
        except Exception as exc:
            logger.error("read_channel_messages error for account %s: %s", account_id, exc)
            return False

    async def update_online_status(self, account_id: int, online: bool = True) -> bool:
        client = self._clients.get(account_id)
        if not client:
            return False
        try:
            await _with_timeout(client(UpdateStatusRequest(offline=not online)))
            return True
        except FloodWaitError as exc:
            wait = min(exc.seconds, _FLOOD_WAIT_CAP)
            await asyncio.sleep(wait)
            return False
        except (UserDeactivatedError, PhoneNumberBannedError, AuthKeyUnregisteredError):
            raise
        except Exception as exc:
            logger.error("update_online_status error for account %s: %s", account_id, exc)
            return False

    async def simulate_online_session(
        self, account_id: int, duration_minutes: int = 5
    ) -> int:
        elapsed = 0
        try:
            await self.update_online_status(account_id, online=True)
            while elapsed < duration_minutes:
                try:
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    raise
                elapsed += 1
                await self.update_online_status(account_id, online=True)
        except asyncio.CancelledError:
            raise
        except (UserDeactivatedError, PhoneNumberBannedError, AuthKeyUnregisteredError):
            raise
        except Exception as exc:
            logger.error("simulate_online error for account %s: %s", account_id, exc)
        finally:
            try:
                await self.update_online_status(account_id, online=False)
            except Exception:
                pass
        return elapsed

    async def get_dialog_count(self, account_id: int) -> int:
        client = self._clients.get(account_id)
        if not client:
            return 0
        try:
            dialogs = await _with_timeout(client.get_dialogs(limit=500), timeout=60)
            return len(dialogs) if dialogs else 0
        except Exception as exc:
            logger.error("get_dialog_count error for account %s: %s", account_id, exc)
            return 0

    async def send_to_saved_messages(self, account_id: int, text: str) -> bool:
        client = self._clients.get(account_id)
        if not client:
            return False
        try:
            await _with_timeout(client.send_message("me", text))
            return True
        except Exception as exc:
            logger.error("send_to_saved_messages error for account %s: %s", account_id, exc)
            return False
