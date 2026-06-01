"""Async HTTP client for the Betovo (Altenar) sportsbook API.

Endpoints (host sb2frontend-altenar2.biahosted.com/api; all plain HTTP, no token;
every call carries the shared params incl. ``integration=betovo``):
  - ``GET /widget/GetEvents?sportId=<n>[&champIds=<id>]`` -> normalized prematch
    feed: events + champs (leagues) + categories (countries) + headline odds.
  - ``GET /widget/GetEventDetails?eventId=<id>`` -> full market list for one event
    (1x2 / Asian handicap / goal line / ...).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from extractors.betovo_http.settings import BetovoHttpSettings

logger = logging.getLogger(__name__)


class BetovoHttpClient:
    """Defensive async client for the Betovo/Altenar endpoints."""

    def __init__(self, settings: BetovoHttpSettings) -> None:
        if not settings.frontend_host or not settings.integration:
            raise ValueError("Betovo frontend_host/integration are not configured.")
        self.settings = settings

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "origin": self.settings.site_origin,
            "referer": f"{self.settings.site_origin}/",
            "user-agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Chrome/124"
            ),
        }

    async def fetch_events(self, *, champ_id: str | int | None = None) -> dict[str, Any]:
        """Return the normalized GetEvents feed (optionally one league via champIds)."""

        params = {**self.settings.common_params, "sportId": str(self.settings.sport_id)}
        if champ_id is not None:
            params["champIds"] = str(champ_id)
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, headers=self._headers) as client:
            data = await self._get(client, "widget/GetEvents", params)
        return data if isinstance(data, dict) else {}

    async def fetch_livenow(self) -> dict[str, Any]:
        """Return all currently in-play events for the configured sport."""

        params = {**self.settings.common_params, "sportId": str(self.settings.sport_id), "eventCount": "0"}
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, headers=self._headers) as client:
            data = await self._get(client, "widget/GetLivenow", params)
        return data if isinstance(data, dict) else {}

    async def fetch_event_details(self, event_id: str | int) -> dict[str, Any]:
        """Return the full market list for one event id."""

        params = {**self.settings.common_params, "eventId": str(event_id), "showNonBoosts": "false"}
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, headers=self._headers) as client:
            data = await self._get(client, "widget/GetEventDetails", params)
        return data if isinstance(data, dict) else {}

    async def fetch_many_event_details(self, event_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch full details for several events with bounded concurrency."""

        semaphore = asyncio.Semaphore(self.settings.detail_fetch_concurrency)
        results: dict[str, dict[str, Any]] = {}

        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, headers=self._headers) as client:
            async def worker(event_id: str) -> None:
                async with semaphore:
                    params = {
                        **self.settings.common_params,
                        "eventId": str(event_id),
                        "showNonBoosts": "false",
                    }
                    try:
                        data = await self._get(client, "widget/GetEventDetails", params)
                        results[event_id] = data if isinstance(data, dict) else {}
                    except Exception:  # one failed event must not abort the league
                        logger.exception("Betovo event detail fetch failed event_id=%s", event_id)
                        results[event_id] = {}

            await asyncio.gather(*(worker(event_id) for event_id in event_ids))
        return results

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
