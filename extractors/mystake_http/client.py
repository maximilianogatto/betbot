"""Async HTTP client for the Mystake prematch REST API."""

from __future__ import annotations

import asyncio
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


class MystakeHttpClient:
    """Defensive client for ``/prematch/getprematch``."""

    def __init__(self, settings: MystakeHttpSettings) -> None:
        if not settings.base_url:
            raise ValueError(
                "MYSTAKE_API_BASE_URL is not configured. Capture the real "
                "getprematch host from mystake.bet and set it before use."
            )
        self.settings = settings

    async def fetch_prematch(self, *, game_ids: list[int] | None = None) -> dict[str, Any]:
        """Fetch the prematch feed for the configured region/sport/language."""

        params: dict[str, Any] = {
            "region": self.settings.region,
            "sport": self.settings.sport_id,
            "language": self.settings.language,
        }
        if game_ids:
            params["games"] = "," + ",".join(str(game_id) for game_id in game_ids)

        url = f"{self.settings.base_url}/prematch/getprematch"
        last_error: Exception | None = None
        for attempt in range(self.settings.max_attempts):
            try:
                async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, headers=_HEADERS) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    payload = response.json()
                if isinstance(payload, dict):
                    return payload
                raise ValueError("Mystake getprematch did not return a JSON object.")
            except Exception as error:  # defensive polling
                last_error = error
                if attempt < self.settings.max_attempts - 1:
                    await asyncio.sleep(self.settings.retry_backoff_seconds)
        assert last_error is not None
        raise last_error
