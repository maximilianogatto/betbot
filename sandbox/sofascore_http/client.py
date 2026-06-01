"""HTTP-only SofaScore research client backed by curl_cffi.

SofaScore returns `403 Forbidden` to the repository's normal `httpx` client from
the current network, even when browser headers and cookies are replayed. The
same public API URLs return JSON through curl_cffi/libcurl without Playwright.

This module is research-only. It deliberately keeps a small wrapper surface so
it can later become a production `StatsProvider` without copying endpoint logic
into Telegram handlers.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time
from typing import Any, Callable

from curl_cffi import requests


logger = logging.getLogger(__name__)


class SofaScoreHTTPError(RuntimeError):
    """Raised when SofaScore returns an unusable HTTP response."""


@dataclass(frozen=True)
class SofaScoreHTTPSettings:
    """Configure the lightweight SofaScore research client."""

    base_url: str = "https://www.sofascore.com/api/v1"
    timeout_seconds: float = 15.0
    retries: int = 2
    retry_delay_seconds: float = 0.35
    min_request_interval_seconds: float = 0.15
    cache_ttl_seconds: float = 30.0
    impersonate: str | None = None


class SofaScoreHTTPClient:
    """Fetch public SofaScore JSON endpoints without a browser session.

    The session is deliberately serialized through a small lock. This keeps the
    libcurl session reuse predictable and enforces a conservative request rate
    when multiple async provider calls delegate work to background threads.
    """

    def __init__(
        self,
        settings: SofaScoreHTTPSettings | None = None,
        *,
        session: Any | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or SofaScoreHTTPSettings()
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._monotonic = monotonic
        self._sleep = sleep
        self._request_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._last_request_started_at: float | None = None
        self.request_count = 0
        self.cache_hit_count = 0

    def close(self) -> None:
        """Close the owned libcurl session."""

        if self._owns_session:
            self._session.close()

    def __enter__(self) -> SofaScoreHTTPClient:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def get_json(self, path: str, *, cache_ttl_seconds: float | None = None) -> dict[str, Any]:
        """GET one SofaScore API path and validate its JSON object payload."""

        url = f"{self.settings.base_url.rstrip('/')}/{path.lstrip('/')}"
        ttl = self.settings.cache_ttl_seconds if cache_ttl_seconds is None else max(0.0, cache_ttl_seconds)
        cached = self._cached_payload(url, ttl=ttl)
        if cached is not None:
            return cached
        last_error: Exception | None = None
        for attempt in range(1, self.settings.retries + 1):
            try:
                with self._request_lock:
                    self._wait_for_rate_limit()
                    started_at = self._monotonic()
                    self._last_request_started_at = started_at
                    response = self._session.get(
                        url,
                        timeout=self.settings.timeout_seconds,
                        impersonate=self.settings.impersonate,
                    )
                    self.request_count += 1
                elapsed_seconds = self._monotonic() - started_at
                logger.debug(
                    "SofaScore HTTP GET path=%s status=%s duration_seconds=%.3f attempt=%s/%s",
                    path,
                    response.status_code,
                    elapsed_seconds,
                    attempt,
                    self.settings.retries,
                )
                if response.status_code == 404:
                    return {}
                if response.status_code != 200:
                    raise SofaScoreHTTPError(
                        f"SofaScore GET {path} returned HTTP {response.status_code}: {response.text[:200]}"
                    )
                payload = response.json()
                if not isinstance(payload, dict):
                    raise SofaScoreHTTPError(f"SofaScore GET {path} returned non-object JSON.")
                self._store_cached_payload(url, payload, ttl=ttl)
                return payload
            except (requests.RequestsError, ValueError, SofaScoreHTTPError) as exc:
                last_error = exc
                if attempt < self.settings.retries:
                    self._sleep(self.settings.retry_delay_seconds)
        raise SofaScoreHTTPError(f"SofaScore GET {path} failed after retries: {last_error}") from last_error

    def _cached_payload(self, url: str, *, ttl: float) -> dict[str, Any] | None:
        if ttl <= 0:
            return None
        with self._cache_lock:
            cached = self._cache.get(url)
            if cached is None:
                return None
            expires_at, payload = cached
            if expires_at <= self._monotonic():
                self._cache.pop(url, None)
                return None
            self.cache_hit_count += 1
            return payload

    def _store_cached_payload(self, url: str, payload: dict[str, Any], *, ttl: float) -> None:
        if ttl <= 0:
            return
        with self._cache_lock:
            self._cache[url] = (self._monotonic() + ttl, payload)

    def _wait_for_rate_limit(self) -> None:
        previous = self._last_request_started_at
        if previous is None:
            return
        remaining = self.settings.min_request_interval_seconds - (self._monotonic() - previous)
        if remaining > 0:
            self._sleep(remaining)

    def get_categories(self, *, sport_slug: str = "football") -> list[dict[str, Any]]:
        """Return available country/category nodes for one sport."""

        return _dict_items(self.get_json(f"sport/{sport_slug}/categories/all"), "categories")

    def get_category_tournaments(self, category_id: int) -> list[dict[str, Any]]:
        """Return unique tournaments grouped under one country/category."""

        payload = self.get_json(f"category/{category_id}/unique-tournaments")
        tournaments: list[dict[str, Any]] = []
        for group in _dict_items(payload, "groups"):
            tournaments.extend(_dict_items(group, "uniqueTournaments"))
        return tournaments

    def get_live_events(self, *, sport_slug: str = "football") -> list[dict[str, Any]]:
        """Return current live events for one sport."""

        return _dict_items(self.get_json(f"sport/{sport_slug}/events/live"), "events")

    def get_scheduled_events(self, date: str, *, sport_slug: str = "football") -> list[dict[str, Any]]:
        """Return events scheduled on one ISO date."""

        return _dict_items(self.get_json(f"sport/{sport_slug}/scheduled-events/{date}"), "events")

    def get_unique_tournament_seasons(self, unique_tournament_id: int) -> list[dict[str, Any]]:
        """Return known seasons for one unique tournament."""

        return _dict_items(self.get_json(f"unique-tournament/{unique_tournament_id}/seasons"), "seasons")

    def get_tournament_scheduled_events(self, unique_tournament_id: int, date: str) -> list[dict[str, Any]]:
        """Return tournament fixtures scheduled on one ISO date."""

        return _dict_items(
            self.get_json(f"unique-tournament/{unique_tournament_id}/scheduled-events/{date}"),
            "events",
        )

    def get_season_events(
        self,
        unique_tournament_id: int,
        season_id: int,
        *,
        direction: str = "last",
        page: int = 0,
    ) -> list[dict[str, Any]]:
        """Return one season event page.

        SofaScore exposes historical pages under `last`. Future pages under
        `next` may return 404 when a season has no remaining scheduled matches.
        """

        if direction not in {"last", "next"}:
            raise ValueError("direction must be 'last' or 'next'.")
        payload = self.get_json(
            f"unique-tournament/{unique_tournament_id}/season/{season_id}/events/{direction}/{page}"
        )
        return _dict_items(payload, "events")

    def get_season_standings(self, unique_tournament_id: int, season_id: int) -> list[dict[str, Any]]:
        """Return standings tables for one season when available."""

        return _dict_items(
            self.get_json(f"unique-tournament/{unique_tournament_id}/season/{season_id}/standings/total"),
            "standings",
        )

    def get_event(self, event_id: int) -> dict[str, Any]:
        """Return one event metadata document."""

        return _dict_value(self.get_json(f"event/{event_id}"), "event")

    def get_event_statistics(self, event_id: int) -> list[dict[str, Any]]:
        """Return live/final grouped match statistics when covered."""

        return _dict_items(self.get_json(f"event/{event_id}/statistics"), "statistics")

    def get_event_incidents(self, event_id: int) -> list[dict[str, Any]]:
        """Return timeline incidents such as goals, cards and period markers."""

        return _dict_items(self.get_json(f"event/{event_id}/incidents"), "incidents")

    def get_event_lineups(self, event_id: int) -> dict[str, Any]:
        """Return lineups when available."""

        return self.get_json(f"event/{event_id}/lineups")

    def get_event_h2h(self, event_id: int) -> dict[str, Any]:
        """Return compact head-to-head counters when available."""

        return self.get_json(f"event/{event_id}/h2h")

    def get_event_win_probability(self, event_id: int) -> dict[str, Any]:
        """Return SofaScore's win-probability document when available."""

        return self.get_json(f"event/{event_id}/win-probability")

    def get_event_odds(self, event_id: int, *, provider_id: int = 1) -> dict[str, Any]:
        """Return provider-specific event odds, including 1X2 when exposed."""

        return self.get_json(f"event/{event_id}/odds/{provider_id}/all")


def _dict_items(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Return only dictionary items under `key` from one defensive payload."""

    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict_value(payload: dict[str, Any], key: str) -> dict[str, Any]:
    """Return one nested object or an empty object."""

    value = payload.get(key)
    return value if isinstance(value, dict) else {}


__all__ = [
    "SofaScoreHTTPClient",
    "SofaScoreHTTPError",
    "SofaScoreHTTPSettings",
]
