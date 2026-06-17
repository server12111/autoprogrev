import logging
from typing import Any, Dict, List, Optional

import aiohttp

from config import config

logger = logging.getLogger(__name__)

BASE_URL = "https://piarflow.com/v1"


class PiarFlowClient:
    """PiarFlow API client.

    Auth: Authorization: Bearer <api_key>
    Base URL: https://piarflow.com/v1

    Key endpoints:
      POST /traffic_bot/add        — register/update bot
      POST /traffic_bot/api_key    — get API key for registered bot
      GET  /traffic_bot            — bot data & stats
      GET  /traffic_bot/stats      — daily metrics (?date=YYYY-MM-DD)
      POST /users/check            — validate user / detect flagged accounts
      POST /sponsors               — get task list for user
      POST /sponsors/check         — verify task completion
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.PIARFLOW_API_KEY
        self._session: Optional[aiohttp.ClientSession] = None

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self._headers())
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _configured(self) -> bool:
        if not self.api_key:
            logger.warning("PiarFlow: API key not configured")
            return False
        return True

    async def _post(self, path: str, payload: dict, ok_statuses=(200, 409)) -> Optional[dict]:
        if not self._configured():
            return None
        try:
            session = await self._get_session()
            async with session.post(
                f"{BASE_URL}{path}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in ok_statuses:
                    try:
                        return await resp.json()
                    except Exception:
                        return {"status": resp.status}
                logger.error("PiarFlow POST %s → HTTP %s", path, resp.status)
                return None
        except Exception as exc:
            logger.error("PiarFlow POST %s failed: %s", path, exc)
            return None

    async def _get(self, path: str, params: dict = None) -> Optional[dict]:
        if not self._configured():
            return None
        try:
            session = await self._get_session()
            async with session.get(
                f"{BASE_URL}{path}",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.error("PiarFlow GET %s → HTTP %s", path, resp.status)
                return None
        except Exception as exc:
            logger.error("PiarFlow GET %s failed: %s", path, exc)
            return None

    # ─── Bot management ───────────────────────────────────────────────────────

    async def register_bot(self, bot_token: str, owner_chat_id: int) -> Optional[dict]:
        """Register or update the traffic bot in PiarFlow."""
        return await self._post(
            "/traffic_bot/add",
            {"bot_token": bot_token, "chat_id": owner_chat_id},
        )

    async def get_bot_info(self) -> Optional[dict]:
        """Get bot data and current statistics."""
        return await self._get("/traffic_bot")

    async def get_bot_stats(self, date: str = None) -> Optional[dict]:
        """Get daily performance metrics. date format: YYYY-MM-DD."""
        params = {"date": date} if date else None
        return await self._get("/traffic_bot/stats", params=params)

    # ─── User operations ─────────────────────────────────────────────────────

    async def check_user(self, user_id: int, chat_id: int) -> Optional[dict]:
        """Validate user and detect flagged/banned accounts."""
        return await self._post("/users/check", {"user_id": user_id, "chat_id": chat_id})

    # ─── Sponsor tasks ────────────────────────────────────────────────────────

    async def get_sponsors(self, user_id: int, chat_id: int, max_sponsors: int = 5) -> List[Dict[str, Any]]:
        """Get sponsor task list for a user (channels to subscribe to).

        Returns list of sponsor objects with channel links.
        """
        data = await self._post(
            "/sponsors",
            {"user_id": user_id, "chat_id": chat_id, "max_sponsors": max_sponsors},
        )
        if not data:
            return []
        # Response may be a list directly or {"sponsors": [...]}
        if isinstance(data, list):
            return data
        return data.get("sponsors", data.get("tasks", []))

    async def check_completion(self, user_id: int, links: List[str]) -> Dict[str, str]:
        """Verify task completion for given channel links.

        Returns dict: {link: status} where status is one of:
          'subscribed', 'unsubscribed', 'not_counted'
        """
        data = await self._post(
            "/sponsors/check",
            {"user_id": user_id, "links": links},
        )
        if not data:
            return {}
        # Normalize to {link: status}
        if isinstance(data, dict):
            return data.get("result", data)
        return {}

    async def get_next_task_link(self, user_id: int, chat_id: int) -> Optional[str]:
        """Return the first unsubscribed sponsor channel link, or None."""
        sponsors = await self.get_sponsors(user_id, chat_id, max_sponsors=3)
        for sponsor in sponsors:
            link = (
                sponsor.get("link")
                or sponsor.get("channel_link")
                or sponsor.get("url")
                or sponsor.get("channel")
            )
            if link:
                return link
        return None
