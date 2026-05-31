"""Async HTTP client for the BetWarrior (Kambi) offering API.

Endpoints (host eu-offering-api.kambicdn.com; all plain HTTP, no token):
  - ``GET /listView/<sport>.json`` -> prematch events with their ``path``
    (sport -> country -> league); used for league discovery.
  - ``GET /betoffer/group/<groupId>.json`` -> every event + all bet offers for one
    league (group) in a single call.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from extractors.betwarrior_http.settings import BetWarriorHttpSettings

logger = logging.getLogger(__name__)


class BetWarriorHttpClient:
    """Defensive async client for the Kambi offering endpoints."""

    def __init__(self, settings: BetWarriorHttpSettings) -> None:
        if not settings.api_host or not settings.offering:
            raise ValueError("BetWarrior api_host/offering are not configured.")
        self.settings = settings

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "origin": self.settings.site_origin,
            "referer": f"{self.settings.site_origin}/",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        }

    async def fetch_list_view(self) -> dict[str, Any]:
        """Return the prematch listView for the configured sport (events + paths)."""

        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, headers=self._headers) as client:
            data = await self._get(client, f"listView/{self.settings.sport_term}.json", self.settings.common_params)
        return data if isinstance(data, dict) else {}

    async def fetch_group_bet_offers(self, group_id: str | int) -> dict[str, Any]:
        """Return every event + bet offer for one league (group) in one call."""

        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, headers=self._headers) as client:
            data = await self._get(client, f"betoffer/group/{group_id}.json", self.settings.common_params)
        return data if isinstance(data, dict) else {}

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict[str, str]) -> Any:
        url = f"{self.settings.api_base}/{path}"
        last_error: Exception | None = None
        for attempt in range(self.settings.max_attempts):
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
            except Exception as error:  # defensive polling
                last_error = error
                if attempt < self.settings.max_attempts - 1:
                    await asyncio.sleep(self.settings.retry_backoff_seconds)
        assert last_error is not None
        raise last_error
