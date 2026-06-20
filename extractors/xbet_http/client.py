"""Small async HTTP client for 1xBet-compatible LineFeed endpoints."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# pyrefly: ignore [missing-import]
import httpx

from core.net import proxy_for_platform

from extractors.xbet_http.settings import XBetHttpSettings

logger = logging.getLogger(__name__)


class XBetHttpClientError(RuntimeError):
    """Raised when LineFeed polling cannot return a trusted JSON payload."""


def normalize_linefeed_base_url(raw_base_url: str) -> str:
    raw = str(raw_base_url).strip().rstrip("/")
    if not raw:
        raw = XBetHttpSettings().base_url
    if "://" not in raw:
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    path = parsed.path.rstrip("/")
    if not path or path == "/":
        path = "/service-api/LineFeed"
    elif not path.endswith("/LineFeed"):
        path = f"{path}/LineFeed" if "service-api" in path else f"{path}/service-api/LineFeed"

    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")


def extract_champ_id(url: str) -> str | None:
    values = parse_qs(urlparse(url).query).get("champ")
    if not values:
        return None
    champ_id = str(values[0]).strip()
    return champ_id or None


def build_champ_url(*, base_url: str, champ_id: str, language: str) -> str:
    query = urlencode({"champ": champ_id, "lng": language})
    return f"{normalize_linefeed_base_url(base_url)}/GetChampZip?{query}"


def build_game_url(*, base_url: str, event_id: str, language: str) -> str:
    query = urlencode({"id": event_id, "lng": language})
    return f"{normalize_linefeed_base_url(base_url)}/GetGameZip?{query}"


def build_sports_short_url(
    *,
    base_url: str,
    sport_id: str,
    language: str,
    country_group: str,
) -> str:
    query = urlencode(
        {
            "sports": sport_id,
            "lng": language,
            "withCountries": "true",
            "country": country_group,
            "virtualSports": "true",
            "gr": "2025",
            "groupChamps": "true",
        }
    )
    return f"{normalize_linefeed_base_url(base_url)}/GetSportsShortZip?{query}"


def build_live_1x2_url(
    *,
    base_url: str,
    sport_id: str,
    language: str,
    gr: str,
    country: str,
    mode: str,
    cfview: str,
    count: int,
) -> str:
    """Build the LiveFeed Get1x2_VZip URL (currently in-play events for a sport)."""

    live_base = normalize_linefeed_base_url(base_url).replace("/LineFeed", "/LiveFeed")
    query = urlencode(
        {
            "sports": sport_id,
            "count": str(count),
            "lng": language,
            "gr": gr,
            "cfview": cfview,
            "mode": mode,
            "country": country,
            "virtualSports": "true",
            "noFilterBlockEvent": "true",
        }
    )
    return f"{live_base}/Get1x2_VZip?{query}"


def base_url_from_linefeed_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    marker = "/GetChampZip"
    if marker in path:
        path = path.split(marker, 1)[0]
    return normalize_linefeed_base_url(urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")))


class XBetHttpClient:
    """Fetch LineFeed JSON with tiny retries and per-client rate limiting."""

    def __init__(self, settings: XBetHttpSettings | None = None) -> None:
        self.settings = settings or XBetHttpSettings()
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0
        self._http: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazily build and reuse one keep-alive client (headers vary per URL, so
        they're passed per request rather than baked into the client)."""

        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.timeout_seconds),
                follow_redirects=True,
                proxy=proxy_for_platform("1xbet_http"),
                limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()
        self._http = None

    async def fetch_champ_zip(self, url: str) -> dict[str, Any]:
        return await self._fetch_json(url)

    async def fetch_game_zip(self, url: str) -> dict[str, Any]:
        return await self._fetch_json(url)

    async def fetch_sports_short_zip(self, url: str) -> dict[str, Any]:
        return await self._fetch_json(url)

    async def fetch_live_1x2_zip(self, url: str) -> dict[str, Any]:
        return await self._fetch_json(url)

    async def _fetch_json(self, url: str) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(1, self.settings.max_attempts + 1):
            try:
                await self._respect_rate_limit()
                return await self._request_json(url)
            except (httpx.TimeoutException, httpx.TransportError, XBetHttpClientError) as error:
                last_error = error
                if attempt >= self.settings.max_attempts:
                    break
                logger.warning(
                    "1xBet HTTP request failed; retrying url=%s attempt=%s/%s error=%s",
                    url,
                    attempt,
                    self.settings.max_attempts,
                    error,
                )
                await asyncio.sleep(self.settings.retry_backoff_seconds * attempt)

        raise XBetHttpClientError(f"1xBet HTTP request failed for {url}: {last_error}") from last_error

    async def _respect_rate_limit(self) -> None:
        async with self._request_lock:
            elapsed = time.monotonic() - self._last_request_at
            wait_seconds = self.settings.min_request_interval_seconds - elapsed
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            self._last_request_at = time.monotonic()

    async def _request_json(self, url: str) -> dict[str, Any]:
        headers = _headers_for_url(url)
        response = await self._get_client().get(url, headers=headers)

        if response.status_code >= 500:
            raise XBetHttpClientError(f"LineFeed server returned {response.status_code}")
        if response.status_code >= 400:
            raise XBetHttpClientError(f"LineFeed request returned {response.status_code}")

        try:
            payload = response.json()
        except ValueError as error:
            raise XBetHttpClientError("LineFeed response was not valid JSON.") from error

        if not isinstance(payload, dict):
            raise XBetHttpClientError("LineFeed response JSON was not an object.")

        return payload


def _headers_for_url(url: str) -> dict[str, str]:
    origin = origin_from_url(url)
    return {
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        "Origin": origin,
        "Referer": f"{origin}/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        ),
    }
