"""Async HTTP client for the Betsson (OBG) sportsbook JSON API.

Endpoints (host cba.betsson.bet.ar; plain HTTP, static brand headers only):
  - ``GET /api/sb/v1/widgets/categories/v2`` -> full sport -> region -> competition
    tree (with each competition's events). Source for league discovery.
  - ``GET /api/sb/v1/widgets/events-table/v2`` -> every event of a competition (or
    every live event of a sport) plus its main markets/selections in one call.
    Paginated (``pageNumber`` / ``totalPages``); we walk all pages.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from extractors.betsson_http.settings import BetssonHttpSettings

logger = logging.getLogger(__name__)

# How many markets per event the events-table should return. The main coupon
# markets we parse (1X2, totals, BTTS) sit near the top of the popularity sort,
# so a small cap keeps payloads light while still covering them.
_MAX_MARKET_COUNT = 12
_MAX_PAGES = 12  # safety bound on pagination loops


class BetssonHttpClient:
    """Defensive async client for the Betsson/OBG widget endpoints."""

    def __init__(self, settings: BetssonHttpSettings) -> None:
        if not settings.brand_id or not settings.market_code:
            raise ValueError("Betsson brand_id/market_code are not configured.")
        self.settings = settings

    async def fetch_categories_tree(self) -> dict[str, Any]:
        """Return the full categories tree (sport -> region -> competition)."""

        async with self._open() as client:
            data = await self._get(client, "/widgets/categories/v2", None)
        return data if isinstance(data, dict) else {}

    async def fetch_competition_events(self, competition_id: str | int) -> dict[str, Any]:
        """Return every event + main markets for one competition (all pages merged)."""

        params = {
            "categoryIds": self.settings.category_id,
            "competitionIds": str(competition_id),
            "eventSortBy": "StartDate",
            "includeSkeleton": "true",
            "maxMarketCount": str(_MAX_MARKET_COUNT),
            "priceFormats": "1",
        }
        return await self._fetch_events_table(params)

    async def fetch_live_events(self) -> dict[str, Any]:
        """Return every in-play event of the configured sport (all pages merged)."""

        params = {
            "categoryIds": self.settings.category_id,
            "eventPhase": "Live",
            "eventSortBy": "StartDate",
            "includeSkeleton": "true",
            "maxMarketCount": "1",
            "priceFormats": "1",
        }
        return await self._fetch_events_table(params)

    async def _fetch_events_table(self, base_params: dict[str, str]) -> dict[str, Any]:
        """Walk the paginated events-table and merge events/markets/selections."""

        merged: dict[str, Any] = {
            "events": [],
            "markets": [],
            "selections": [],
            "scoreboards": [],
        }
        async with self._open() as client:
            page = 1
            while page <= _MAX_PAGES:
                params = dict(base_params, pageNumber=str(page))
                payload = await self._get(client, "/widgets/events-table/v2", params)
                data = (payload or {}).get("data") if isinstance(payload, dict) else None
                if not isinstance(data, dict):
                    break
                for key in ("events", "markets", "selections", "scoreboards"):
                    chunk = data.get(key)
                    if isinstance(chunk, list):
                        merged[key].extend(chunk)
                total_pages = data.get("totalPages")
                has_more = data.get("hasMoreEvents")
                if has_more is False or (isinstance(total_pages, int) and page >= total_pages):
                    break
                if not data.get("events"):
                    break
                page += 1
        return merged

    def _open(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.settings.timeout_seconds,
            headers=self.settings.headers,
            http2=True,
        )

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict[str, str] | None) -> Any:
        url = f"{self.settings.api_base}{path}"
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
