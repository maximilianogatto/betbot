"""Async HTTP client for the Mystake prematch REST API.

Endpoints (host like ``https://analytics-sp.<x>.tech/api/prematch``):
  - ``getprematchtopgames/{region}`` -> featured games grouped by sport,
    each with its championship (``ch``) and region (``rg``).
  - ``getprematchgameall/{region}/{language}/?games=,<ids>`` -> game details
    (markets/odds) + team names.

Both responses are JSON strings that contain escaped JSON (double-encoded).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from extractors.mystake_http.settings import MystakeHttpSettings

logger = logging.getLogger(__name__)

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://mystake.bet",
    "Referer": "https://mystake.bet/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _decode(payload: Any) -> Any:
    """Decode a (possibly) double-encoded JSON string response."""

    return json.loads(payload) if isinstance(payload, str) else payload


class MystakeHttpClient:
    """Defensive client for the Mystake prematch endpoints."""

    def __init__(self, settings: MystakeHttpSettings) -> None:
        if not settings.base_url:
            raise ValueError("MYSTAKE_API_BASE_URL host is not configured.")
        self.settings = settings

    async def fetch_topgames(self) -> list[dict[str, Any]]:
        """Return featured games grouped by sport for the configured region."""

        data = await self._get(f"getprematchtopgames/{self.settings.region}")
        return data if isinstance(data, list) else []

    async def fetch_header(self) -> dict[str, Any]:
        """Return the full navigation tree (sports -> regions -> champs -> games).

        This is the complete prematch directory with translated league names; it
        powers league discovery without pasting a URL. Served from the ``sport``
        API path (not ``prematch``).
        """

        url = f"{self.settings.sport_base}/getheader/{self.settings.region}"
        data = await self._get_url(url)
        return data if isinstance(data, dict) else {}

    async def fetch_games(self, game_ids: list[int]) -> dict[str, Any]:
        """Return raw game details (with markets + teams) for the given ids."""

        if not game_ids:
            return {"game": "[]", "teams": "[]"}
        ids = ",".join(str(game_id) for game_id in game_ids)
        path = f"getprematchgameall/{self.settings.region}/{self.settings.language}/?games=,{ids}"
        data = await self._get(path)
        return data if isinstance(data, dict) else {}

    async def _get(self, path: str) -> Any:
        return await self._get_url(f"{self.settings.prematch_base}/{path}")

    async def _get_url(self, url: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.settings.max_attempts):
            try:
                async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, headers=_HEADERS) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    return _decode(response.json())
            except Exception as error:  # defensive polling
                last_error = error
                if attempt < self.settings.max_attempts - 1:
                    await asyncio.sleep(self.settings.retry_backoff_seconds)
        assert last_error is not None
        raise last_error
