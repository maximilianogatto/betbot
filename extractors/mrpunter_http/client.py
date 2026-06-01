"""Async HTTP client for the MrPunter (FSB) sportsbook API.

Auth: the ``/es/spbk/`` HTML embeds two anonymous JWTs (authorization + session);
we scrape them with plain HTTP (no browser) and send them — plus ``time-area`` —
on every ``/api/eventlist`` call. Tokens are cached briefly and re-bootstrapped
on expiry / 403.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from typing import Any

import httpx

from extractors.mrpunter_http.settings import MrPunterHttpSettings

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}")


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception:
        return {}


def extract_tokens_from_html(html: str) -> tuple[str, str] | None:
    """Return (authorization, session) JWTs embedded in the spbk HTML, or None."""

    jwts = _JWT_RE.findall(html or "")
    auth = next((t for t in jwts if "customerType" in _decode_jwt_payload(t)), None)
    session = next((t for t in jwts if "expiredDate" in _decode_jwt_payload(t)), None)
    if auth and session:
        return auth, session
    return None


class MrPunterHttpClient:
    """Defensive async client for the FSB eventlist endpoints."""

    def __init__(self, settings: MrPunterHttpSettings) -> None:
        if not settings.api_host:
            raise ValueError("MrPunter api_host is not configured.")
        self.settings = settings
        self._tokens: tuple[str, str] | None = None
        self._tokens_at = 0.0
        self._token_lock = asyncio.Lock()

    async def _ensure_tokens(self, *, force: bool = False) -> tuple[str, str]:
        async with self._token_lock:
            now = time.monotonic()
            if (
                not force
                and self._tokens is not None
                and (now - self._tokens_at) < self.settings.token_ttl_seconds
            ):
                return self._tokens
            headers = {"accept": "text/html,*/*", "user-agent": _UA, "accept-language": "es-AR,es;q=0.9"}
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, follow_redirects=True) as client:
                response = await client.get(self.settings.spbk_url, headers=headers)
                response.raise_for_status()
                tokens = extract_tokens_from_html(response.text)
            if tokens is None:
                raise RuntimeError("Could not bootstrap MrPunter tokens from the spbk HTML.")
            self._tokens, self._tokens_at = tokens, now
            return tokens

    def _api_headers(self, tokens: tuple[str, str]) -> dict[str, str]:
        auth, session = tokens
        return {
            "accept": "application/json",
            "authorization": auth,
            "session": session,
            "time-area": "01",
            "accept-language": "es-AR",
            "user-agent": _UA,
            "origin": self.settings.site_origin,
            "referer": f"https://{self.settings.api_host}/{self.settings.language_path}/spbk/",
        }

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.settings.max_attempts):
            try:
                tokens = await self._ensure_tokens(force=attempt > 0)
                response = await client.get(
                    f"{self.settings.api_base}/{path}", headers=self._api_headers(tokens)
                )
                if response.status_code == 403:  # token likely expired -> re-bootstrap next attempt
                    raise httpx.HTTPStatusError("403 token expected", request=response.request, response=response)
                response.raise_for_status()
                return response.json()
            except Exception as error:  # defensive polling
                last_error = error
                if attempt < self.settings.max_attempts - 1:
                    await asyncio.sleep(self.settings.retry_backoff_seconds)
        assert last_error is not None
        raise last_error

    async def fetch_navigation(self) -> list[dict[str, Any]]:
        """Return the sports -> countries -> leagues navigation tree."""

        path = f"navigation/v2/sports?regionCode={self.settings.region_code}"
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, follow_redirects=True) as client:
            data = await self._get(client, path)
        return data.get("data") if isinstance(data, dict) else []

    async def fetch_league_odds(self, master_league_id: str, *, is_live: bool = False) -> list[list[Any]]:
        """Return events (positional arrays) + markets for one league."""

        path = (
            f"leagues/v2/{master_league_id}/gameOdds"
            f"?marketTypeIds={self.settings.market_type_ids}&IsLive={'true' if is_live else 'false'}"
        )
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, follow_redirects=True) as client:
            data = await self._get(client, path)
        events = data.get("data") if isinstance(data, dict) else None
        return events if isinstance(events, list) else []

    async def fetch_live_initial(self) -> dict[str, Any]:
        """Return the live feed: per-sport counts + in-play events for the sport."""

        path = (
            f"events/v2/live/initial?regionCode={self.settings.region_code}"
            f"&sportId={self.settings.sport_id}"
        )
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, follow_redirects=True) as client:
            data = await self._get(client, path)
        return data if isinstance(data, dict) else {}

    async def fetch_many_league_odds(
        self, master_league_ids: list[str], *, is_live: bool = False
    ) -> dict[str, list[list[Any]]]:
        """Fetch several leagues' odds with bounded concurrency."""

        semaphore = asyncio.Semaphore(self.settings.league_fetch_concurrency)
        results: dict[str, list[list[Any]]] = {}

        async def worker(mid: str) -> None:
            async with semaphore:
                try:
                    results[mid] = await self.fetch_league_odds(mid, is_live=is_live)
                except Exception:
                    logger.exception("MrPunter league odds fetch failed master_league_id=%s", mid)
                    results[mid] = []

        await asyncio.gather(*(worker(mid) for mid in master_league_ids))
        return results
