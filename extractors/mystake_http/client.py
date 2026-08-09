"""Async HTTP client for the Mystake prematch REST API.

Endpoints (host like ``https://analytics-sp.<x>.tech/api/prematch``):
  - ``getprematchtopgames/{region}`` -> featured games grouped by sport,
    each with its championship (``ch``) and region (``rg``).
  - ``getprematchgameall/{region}/{language}/?games=,<ids>`` -> game details
    (markets/odds) + team names.
  - ``https://wss-eu-uk1.ws-amazon.com/api/cache/get?key=live/headerformobile/<region>`` ->
    current live events, team/league maps and visible live odds.
  - ``https://wss-eu-uk1.ws-amazon.com/api/cache/get?key=live/games`` ->
    legacy base64-encoded live update/delete ids when Mystake exposes them.

Responses can be JSON strings containing either escaped JSON or base64
payloads. Cache payloads observed in production can also be gzip-compressed
after base64 decoding.
"""

from __future__ import annotations

import asyncio
import base64
import gzip
import json
import logging
from typing import Any

import httpx

from core.net import proxy_for_platform
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

    if not isinstance(payload, str):
        return payload
    try:
        return json.loads(payload)
    except (TypeError, ValueError):
        return payload


class MystakeHttpClient:
    """Defensive client for the Mystake prematch endpoints."""

    def __init__(self, settings: MystakeHttpSettings) -> None:
        if not settings.base_url:
            raise ValueError("MYSTAKE_API_BASE_URL host is not configured.")
        self.settings = settings
        self._http: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily build and reuse one keep-alive client (static headers)."""

        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=self.settings.timeout_seconds,
                headers=_HEADERS,
                proxy=proxy_for_platform("mystake_http"),
                limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
        self._http = None

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

    async def fetch_live_game_updates(self) -> dict[str, Any]:
        """Return the Mystake live update-id cache, or an empty dict when absent.

        In observations, ``live/games`` returns HTTP 204 when there are no live
        updates. When present, the body is a JSON string containing base64 JSON:
        ``{"UpdateList":[{"GameId": ...}], "DeleteList":[...]}``.
        """

        if not self.settings.cache_base_url:
            return {}
        data = await self._get_url(
            f"{self.settings.cache_base_url.rstrip('/')}/api/cache/get?key=live/games",
            allow_no_content=True,
        )
        if isinstance(data, dict):
            return data
        return {}

    async def fetch_live_header_mobile(self) -> dict[str, Any]:
        """Return the compact live snapshot used by Mystake's mobile header.

        This cache key is the stable live discovery source: it includes all
        visible live games, names maps, score/minute/red-card fields and a small
        set of highlighted odds. It returns HTTP 204 when the cache is absent.
        """

        if not self.settings.cache_base_url:
            return {}
        key = f"live/headerformobile/{self.settings.region}"
        data = await self._get_url(
            f"{self.settings.cache_base_url.rstrip('/')}/api/cache/get?key={key}",
            allow_no_content=True,
        )
        if isinstance(data, dict):
            return data
        return {}

    async def _get(self, path: str) -> Any:
        return await self._get_url(f"{self.settings.prematch_base}/{path}")

    async def _get_url(self, url: str, *, allow_no_content: bool = False) -> Any:
        last_error: Exception | None = None
        client = self._get_client()
        for attempt in range(self.settings.max_attempts):
            try:
                response = await client.get(url)
                if allow_no_content and response.status_code == 204:
                    return {}
                response.raise_for_status()
                return _decode_cache_payload(_decode(response.json()))
            except Exception as error:  # defensive polling
                last_error = error
                if attempt < self.settings.max_attempts - 1:
                    await asyncio.sleep(self.settings.retry_backoff_seconds)
        assert last_error is not None
        raise last_error


def _decode_cache_payload(payload: Any) -> Any:
    """Decode the optional base64/gzip JSON envelope used by cache/get endpoints."""

    if not isinstance(payload, str):
        return payload
    text = payload.strip()
    if not text:
        return payload
    try:
        raw = base64.b64decode(text + "=" * (-len(text) % 4))
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
        decoded = raw.decode("utf-8")
        return json.loads(decoded)
    except Exception:
        return payload
