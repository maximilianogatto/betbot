"""Async HTTP client for the BZ (m.bz.com) sportsbook API.

Endpoints (all plain HTTP; require ``x-client-type`` + ``x-channel-type``):
  - ``GET /api/sports/match/search?statusList=0&sportId=<sr:sport:N>&pageSize=&marketMode=0``
    -> tournaments grouped with their matches (prematch when statusList=0).
  - ``GET /api/odds/v2/bz/all?sportId=<sr:sport:N>&matchId=<sr:match:N>``
    -> full market list for one match (1X2 / Handicap / Total / ...).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from core.net import proxy_for_platform

from extractors.bz_http.settings import BzHttpSettings

logger = logging.getLogger(__name__)


class BzHttpClient:
    """Defensive async client for the BZ sportsbook endpoints."""

    def __init__(self, settings: BzHttpSettings) -> None:
        if not settings.base_url:
            raise ValueError("BZ_API_BASE_URL is not configured.")
        self.settings = settings
        self._http: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily build and reuse one keep-alive client (avoids a TLS handshake
        per request across polling cycles). Headers are static for BZ."""

        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=self.settings.timeout_seconds,
                headers=self._headers,
                proxy=proxy_for_platform("bz_http"),
                limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
        self._http = None

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "content-type": "application/json",
            "origin": self.settings.base_url,
            "referer": f"{self.settings.base_url}/",
            "user-agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Chrome/124"
            ),
            "x-client-type": self.settings.client_type,
            "x-channel-type": self.settings.channel_type,
            "x-browser-language": self.settings.language,
        }

    async def fetch_match_search(self) -> list[dict[str, Any]]:
        """Return prematch tournaments (grouped, with matches) for the configured sport."""

        path = (
            f"sports/match/search?statusList={self.settings.status_list}"
            f"&sportId={self.settings.sport_id}&pageSize={self.settings.page_size}&marketMode=0"
        )
        data = await self._get(self._get_client(), path)
        return data if isinstance(data, list) else []

    async def fetch_live_search(self) -> list[dict[str, Any]]:
        """Return tournaments grouped with their LIVE matches (statusList=1)."""

        path = (
            f"sports/match/search?statusList=1"
            f"&sportId={self.settings.sport_id}&pageSize={self.settings.page_size}&marketMode=0"
        )
        data = await self._get(self._get_client(), path)
        return data if isinstance(data, list) else []

    async def fetch_match_odds(self, match_id: str) -> list[dict[str, Any]]:
        """Return the full market tabs for one match id."""

        path = f"odds/v2/bz/all?sportId={self.settings.sport_id}&matchId={match_id}"
        data = await self._get(self._get_client(), path)
        return data if isinstance(data, list) else []

    async def fetch_many_match_odds(self, match_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Fetch odds for several matches with bounded concurrency."""

        semaphore = asyncio.Semaphore(self.settings.odds_fetch_concurrency)
        results: dict[str, list[dict[str, Any]]] = {}

        client = self._get_client()

        async def worker(match_id: str) -> None:
            async with semaphore:
                path = f"odds/v2/bz/all?sportId={self.settings.sport_id}&matchId={match_id}"
                try:
                    data = await self._get(client, path)
                    results[match_id] = data if isinstance(data, list) else []
                except Exception:  # one failed match must not abort the league
                    logger.exception("BZ odds fetch failed match_id=%s", match_id)
                    results[match_id] = []

        await asyncio.gather(*(worker(match_id) for match_id in match_ids))
        return results

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        url = f"{self.settings.api_base}/{path}"
        last_error: Exception | None = None
        for attempt in range(self.settings.max_attempts):
            try:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and payload.get("success") is False:
                    raise ValueError(f"BZ API error {payload.get('errCode')}: {payload.get('errMessage')}")
                return payload.get("data") if isinstance(payload, dict) else payload
            except Exception as error:  # defensive polling
                last_error = error
                if attempt < self.settings.max_attempts - 1:
                    await asyncio.sleep(self.settings.retry_backoff_seconds)
        assert last_error is not None
        raise last_error
