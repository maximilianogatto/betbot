"""Rainbet prematch HTTP extractor (Betby/sptpub snapshot feed).

A league is a Betby ``tournament`` id. The full directory (every sport, country
and league with names) comes from the merged prematch snapshot, served over
plain HTTP with no token — that powers ``/track_league`` discovery.

Tracking forms accepted:
  - ``/track_league`` discovery (preferred): ``search_leagues`` -> snapshot.
  - ``rainbet:tournament:<id>`` -> one league from the snapshot.
  - a ``rainbet.com`` URL whose ``bt-path`` ends in ``-<tournament_id>``.

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
from core.models import CompetitionExtraction, EventSnapshot, ProviderCapabilities
from extractors.rainbet_http import discovery as discovery_module
from extractors.rainbet_http.client import RainbetHttpClient
from extractors.rainbet_http.parser import build_competition_extraction
from extractors.rainbet_http.settings import RainbetHttpSettings, load_rainbet_settings

_SUPPORTED_HOSTS = ("rainbet.com", "sptpub.com")
_TOURNAMENT_SCHEME_RE = re.compile(r"^rainbet:tournament:(\d{6,})$", re.IGNORECASE)
_PATH_TOURNAMENT_RE = re.compile(r"-(\d{12,})/?$")


class RainbetHttpExtractor(Extractor):
    """HTTP extractor for Rainbet (Betby) prematch soccer leagues."""

    name = "rainbet_http"
    display_name = "Rainbet HTTP"
    supported_domains = _SUPPORTED_HOSTS
    supported_capabilities = ("ligas",)
    provider_capabilities = ProviderCapabilities(supports_http=True, supports_browserless=True)
    supports_league_discovery = True  # via the merged Betby snapshot

    # The snapshot (~hundreds of KB across a few chunks) lists every league; cache
    # it briefly so a refresh sweep / discovery search reuses one download.
    _SNAPSHOT_TTL_SECONDS = 120.0

    def __init__(self, *, settings: RainbetHttpSettings | None = None) -> None:
        self.settings = settings or load_rainbet_settings()
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
                "Could not determine the Rainbet league from the URL. Use "
                "'rainbet:tournament:<id>' or a rainbet.com URL whose bt-path "
                "ends in '-<tournament_id>'."
            )
        client = RainbetHttpClient(self.settings)
        snapshot = await self._get_snapshot(client)
        return build_competition_extraction(
            tournament_id=tournament_id, snapshot=snapshot, source_url=url
        )

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError(f"{self.name} does not support direct match URLs yet.")

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        client = RainbetHttpClient(self.settings)
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
        return f"rainbet:tournament:{competition_external_id}"

    async def _get_snapshot(self, client: RainbetHttpClient) -> dict[str, Any]:
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
