"""Betovo (Altenar) prematch HTTP extractor.

Betovo runs the Altenar sportsbook; its catalog (sports -> countries -> leagues ->
events, with Sportradar ids in ``extId``) comes from the Altenar frontend feed over
plain HTTP (no token). That powers ``/track_league`` discovery.

Tracking forms accepted:
  - ``/track_league`` discovery (preferred): ``search_leagues`` -> GetEvents.
  - ``betovo:champ:<id>`` (Altenar championship id).
  - a ``betovo`` URL carrying ``champids=<id>`` (or ``champId``).

Odds (per event, from GetEventDetails): 1X2 + Asian handicap (📐) + goal line (📏).
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from core.extractor_base import Extractor, LeagueDiscoveryOption
from core.models import CompetitionExtraction, EventSnapshot, LiveEventSnapshot, ProviderCapabilities
from extractors.betovo_http import discovery as discovery_module
from extractors.betovo_http.client import BetovoHttpClient
from extractors.betovo_http.parser import build_competition_extraction, live_events_from_livenow
from extractors.betovo_http.settings import BetovoHttpSettings, load_betovo_settings

_SUPPORTED_HOSTS = ("betovo848425.com", "betovo.com")
_CHAMP_SCHEME_RE = re.compile(r"^betovo:champ:(\d+)$", re.IGNORECASE)


class BetovoHttpExtractor(Extractor):
    """HTTP extractor for Betovo (Altenar) prematch soccer leagues."""

    name = "betovo_http"
    display_name = "Betovo"
    supported_domains = _SUPPORTED_HOSTS
    supported_capabilities = ("ligas",)
    provider_capabilities = ProviderCapabilities(supports_http=True, supports_browserless=True)
    supports_league_discovery = True  # via the Altenar GetEvents feed
    supports_live_detection = True  # via GetLivenow
    supports_prematch_listing = True  # via GetEvents (whole-sport day list)

    # The GetEvents feed lists every prematch league; cache it briefly so a refresh
    # sweep / discovery search reuses one download.
    _EVENTS_TTL_SECONDS = 90.0

    def __init__(self, *, settings: BetovoHttpSettings | None = None) -> None:
        self.settings = settings or load_betovo_settings()
        self._events_cache: dict[str, Any] | None = None
        self._events_cached_at = 0.0
        self._events_lock = asyncio.Lock()

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        normalized = (url or "").strip()
        if _CHAMP_SCHEME_RE.match(normalized.lower()):
            return True
        host = urlparse(normalized.lower()).netloc
        return any(domain in host for domain in _SUPPORTED_HOSTS)

    async def extract_league(self, url: str) -> CompetitionExtraction:
        if not self.can_handle_url(url):
            raise ValueError(f"{self.name} cannot handle URL: {url}")
        champ_id = _champ_id_from_url(url)
        if champ_id is None:
            raise ValueError(
                "Could not determine the Betovo league from the URL. Use "
                "'betovo:champ:<id>' or a betovo URL carrying 'champids=<id>'."
            )

        client = BetovoHttpClient(self.settings)
        events_payload = await client.fetch_events(champ_id=champ_id)
        events = [e for e in events_payload.get("events") or [] if str(e.get("champId")) == str(champ_id)]
        event_ids = [str(e.get("id")) for e in events if e.get("id") is not None]
        details_by_event = await client.fetch_many_event_details(event_ids)
        return build_competition_extraction(
            champ_id=champ_id,
            events_payload=events_payload,
            details_by_event=details_by_event,
            source_url=url,
        )

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError(f"{self.name} does not support direct match URLs yet.")

    async def list_live_events(self) -> list[LiveEventSnapshot]:
        client = BetovoHttpClient(self.settings)
        payload = await client.fetch_livenow()
        return live_events_from_livenow(payload)

    async def list_prematch_events(self) -> list[LiveEventSnapshot]:
        client = BetovoHttpClient(self.settings)
        payload = await client.fetch_events()  # whole-sport GetEvents (prematch)
        return live_events_from_livenow(payload)

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        client = BetovoHttpClient(self.settings)
        events_payload = await self._get_events(client)
        return discovery_module.build_league_options(
            events_payload,
            platform=self.name,
            platform_display_name=self.display_name,
            country_name=country_name,
            query=query,
            limit=limit,
        )

    def build_competition_url(self, *, competition_external_id, source_url=None, metadata=None) -> str | None:
        del source_url, metadata
        return f"betovo:champ:{competition_external_id}"

    async def _get_events(self, client: BetovoHttpClient) -> dict[str, Any]:
        """Return the full (no champ filter) GetEvents feed from a short-lived cache."""

        async with self._events_lock:
            now = time.monotonic()
            if self._events_cache is not None and (now - self._events_cached_at) < self._EVENTS_TTL_SECONDS:
                return self._events_cache
            data = await client.fetch_events()
            if data.get("events"):
                self._events_cache = data
                self._events_cached_at = now
            return data


def _champ_id_from_url(url: str) -> str | None:
    normalized = (url or "").strip()
    scheme_match = _CHAMP_SCHEME_RE.match(normalized.lower())
    if scheme_match:
        return scheme_match.group(1)
    query = parse_qs(urlparse(normalized).query)
    for key in ("champids", "champId", "championshipIds", "champ"):
        values = query.get(key) or query.get(key.lower())
        if values:
            candidate = str(values[0]).split(",")[0]
            if candidate.isdigit():
                return candidate
    return None
