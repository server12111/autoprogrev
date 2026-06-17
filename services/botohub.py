import logging
from typing import Optional

import aiohttp

from config import config

logger = logging.getLogger(__name__)

BASE_URL = "https://views.botohub.me"


class BotohubClient:
    """BotoHub Views API client.

    Auth: Authorization: <api_token>  (no Bearer prefix)
    Endpoint: POST /ad/SendPost

    SendPostResult codes:
      1 — success
      2 — invalid token
      3 — user blocked bot
      4 — rate limit
      7 — ad impression limit reached
      8 — no ads available
      9 — bot disabled
    """

    def __init__(self, token: str = None):
        self.token = token or config.BOTOHUB_TOKEN
        self._session: Optional[aiohttp.ClientSession] = None

    def _headers(self) -> dict:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def send_ad(self, chat_id: int, hi: bool = False) -> int:
        """Send ad to user. Returns SendPostResult code.

        hi=True  — use after /start for new/returning users (once per 24h)
        hi=False — regular ad show triggered by user action
        """
        if not self.token:
            return 0
        try:
            session = await self._get_session()
            async with session.post(
                f"{BASE_URL}/ad/SendPost",
                json={"SendToChatId": chat_id, "hi": hi},
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    code = data.get("SendPostResult", 0)
                    _codes = {
                        1: "success", 2: "invalid token", 3: "user blocked bot",
                        4: "rate limit", 7: "impression limit", 8: "no ads", 9: "bot disabled",
                        11: "unknown/queued",
                    }
                    logger.info("BotoHub: chat=%s hi=%s → code=%s (%s)", chat_id, hi, code, _codes.get(code, "?"))
                    return code
                logger.error("BotoHub HTTP %s for chat %s", resp.status, chat_id)
                return 0
        except Exception as exc:
            logger.warning("BotoHub send_ad failed for %s: %s", chat_id, exc)
            return 0
