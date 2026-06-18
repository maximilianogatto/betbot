"""Solcasino prematch HTTP extractor (Betby/sptpub snapshot feed).

A league is a Betby ``tournament`` id. The full directory (every sport, country
and league with names) comes from the merged prematch snapshot, served over
plain HTTP with no token — that powers ``/track_league`` discovery.

Tracking forms accepted:
  - ``/track_league`` discovery (preferred): ``search_leagues`` -> snapshot.
  - ``solcasino:tournament:<id>`` -> one league from the snapshot.
  - a ``solcasino.io`` URL whose ``bt-path`` ends in ``-<tournament_id>``.

Odds come from the broad snapshot: 1X2 + totals (rendered as 📏 GL). Asian
handicap is not exposed by Betby over plain HTTP, so it is omitted.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from core.extractor_base import Extractor, LeagueDiscoveryOption
from core.models import CompetitionExtraction, EventSnapshot, LiveEventSnapshot, ProviderCapabilities
from extractors.solcasino_http import discovery as discovery_module
from extractors.solcasino_http.client import SolcasinoHttpClient
from extractors.solcasino_http.parser import (
    build_competition_extraction,
    live_events_from_snapshot,
    prematch_events_from_snapshot,
)
from extractors.solcasino_http.settings import SolcasinoHttpSettings, load_solcasino_settings

_SUPPORTED_HOSTS = ("solcasino.io", "sptpub.com")
_TOURNAMENT_SCHEME_RE = re.compile(r"^solcasino:tournament:(\d{6,})$", re.IGNORECASE)
_PATH_TOURNAMENT_RE = re.compile(r"-(\d{12,})/?$")


class SolcasinoHttpExtractor(Extractor):
    """HTTP extractor for Solcasino (Betby) prematch soccer leagues."""

    name = "solcasino_http"
    display_name = "Solcasino"
    supported_domains = _SUPPORTED_HOSTS
    supported_capabilities = ("ligas",)
    provider_capabilities = ProviderCapabilities(supports_http=True, supports_browserless=True)
    supports_league_discovery = True  # via the merged Betby snapshot
    supports_live_detection = True  # via the Betby live feed
    supports_prematch_listing = True  # via the merged Betby prematch snapshot

    # The snapshot (~hundreds of KB across a few chunks) lists every league; cache
    # it briefly so a refresh sweep / discovery search reuses one download.
    _SNAPSHOT_TTL_SECONDS = 120.0

    def __init__(self, *, settings: SolcasinoHttpSettings | None = None) -> None:
        self.settings = settings or load_solcasino_settings()
        self._snapshot_cache: dict[str, Any] | None = None
        self._snapshot_cached_at = 0.0
        self._snapshot_lock = asyncio.Lock()

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        normalized = (url or "").strip()
        if _TOURNAMENT_SCHEME_RE.match(normalized.lower()):
            return True
        host = urlparse(normalized.lower()).netloc
        return any(domain in host for domain in _SUPPORTED_HOSTS)

    async def extract_league(self, url: str) -> CompetitionExtraction:
        if not self.can_handle_url(url):
            raise ValueError(f"{self.name} cannot handle URL: {url}")
        tournament_id = _tournament_id_from_url(url)
        if tournament_id is None:
            raise ValueError(
                "Could not determine the Solcasino league from the URL. Use "
                "'solcasino:tournament:<id>' or a solcasino.io URL whose bt-path "
                "ends in '-<tournament_id>'."
            )
        client = SolcasinoHttpClient(self.settings)
        snapshot = await self._get_snapshot(client)
        return build_competition_extraction(
            tournament_id=tournament_id, snapshot=snapshot, source_url=url
        )

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError(f"{self.name} does not support direct match URLs yet.")

    async def list_live_events(self) -> list[LiveEventSnapshot]:
        client = SolcasinoHttpClient(self.settings)
        snapshot = await client.fetch_snapshot(feed="live")
        return live_events_from_snapshot(snapshot, sport_id=self.settings.sport_id)

    async def list_prematch_events(self) -> list[LiveEventSnapshot]:
        client = SolcasinoHttpClient(self.settings)
        snapshot = await self._get_snapshot(client)  # cached prematch snapshot
        return prematch_events_from_snapshot(snapshot, sport_id=self.settings.sport_id)

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        client = SolcasinoHttpClient(self.settings)
        snapshot = await self._get_snapshot(client)
        return discovery_module.build_league_options(
            snapshot,
            platform=self.name,
            platform_display_name=self.display_name,
            sport_id=self.settings.sport_id,
            country_name=country_name,
            query=query,
            limit=limit,
        )

    def build_competition_url(self, *, competition_external_id, source_url=None, metadata=None) -> str | None:
        del source_url, metadata
        return f"solcasino:tournament:{competition_external_id}"

    async def _get_snapshot(self, client: SolcasinoHttpClient) -> dict[str, Any]:
        """Return the merged snapshot from a short-lived in-process cache."""

        async with self._snapshot_lock:
            now = time.monotonic()
            if (
                self._snapshot_cache is not None
                and (now - self._snapshot_cached_at) < self._SNAPSHOT_TTL_SECONDS
            ):
                return self._snapshot_cache
            snapshot = await client.fetch_snapshot()
            if snapshot.get("events"):
                self._snapshot_cache = snapshot
                self._snapshot_cached_at = now
            return snapshot


def _tournament_id_from_url(url: str) -> str | None:
    normalized = (url or "").strip()
    scheme_match = _TOURNAMENT_SCHEME_RE.match(normalized.lower())
    if scheme_match:
        return scheme_match.group(1)

    parsed = urlparse(normalized)
    bt_path = parse_qs(parsed.query).get("bt-path", [""])[0]
    decoded = unquote(bt_path or parsed.path or "")
    match = _PATH_TOURNAMENT_RE.search(decoded)
    return match.group(1) if match else None
