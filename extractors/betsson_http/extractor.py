"""Betsson (OBG) prematch + live HTTP extractor.

Betsson Argentina (cba.betsson.bet.ar) runs the OBG / Betsson Group sportsbook.
Its catalogue (sport -> region -> competition -> events) and odds come from a
public JSON API over plain HTTP, gated only by static brand headers (see
``settings.py``). That powers ``/track_league`` discovery and live detection.

Tracking forms accepted:
  - ``/track_league`` discovery (preferred): ``search_leagues`` -> categories tree.
  - ``betsson:competition:<id>`` (OBG competition id).
  - a betsson.bet.ar URL carrying ``/apuestas-deportivas/<slug>`` (resolved to a
    competition id via the tree's ``indexBySlug``).

Odds (one events-table call per competition): 1X2 + European handicap (📐) +
total goals (📏) + BTTS. Prematch listing comes from the categories tree (one
cached call), and live detection from events-table ``eventPhase=Live``.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import urlparse, unquote

from core.extractor_base import Extractor, LeagueDiscoveryOption
from core.models import CompetitionExtraction, EventSnapshot, LiveEventSnapshot, ProviderCapabilities
from extractors.betsson_http import discovery as discovery_module
from extractors.betsson_http.client import BetssonHttpClient
from extractors.betsson_http.parser import (
    build_competition_extraction,
    live_events_from_table,
    prematch_events_from_tree,
)
from extractors.betsson_http.settings import BetssonHttpSettings, load_betsson_settings

_SUPPORTED_HOSTS = ("betsson.bet.ar",)
_COMPETITION_SCHEME_RE = re.compile(r"^betsson:competition:([0-9]+)$", re.IGNORECASE)
_SLUG_PATH_RE = re.compile(r"/apuestas-deportivas/(?P<slug>[a-z0-9\-/]+)", re.IGNORECASE)


class BetssonHttpExtractor(Extractor):
    """HTTP extractor for Betsson (OBG) prematch + live soccer leagues."""

    name = "betsson_http"
    display_name = "Betsson"
    supported_domains = _SUPPORTED_HOSTS
    supported_capabilities = ("ligas", "eventos 1X2", "handicap", "totales")
    provider_capabilities = ProviderCapabilities(supports_http=True, supports_browserless=True)
    supports_league_discovery = True  # via the OBG categories tree (full league catalog)
    supports_live_detection = True  # via events-table eventPhase=Live
    supports_prematch_listing = True  # from the categories tree (one cached call)

    _TREE_TTL_SECONDS = 90.0

    def __init__(self, *, settings: BetssonHttpSettings | None = None) -> None:
        self.settings = settings or load_betsson_settings()
        self._tree_cache: dict[str, Any] | None = None
        self._tree_cached_at = 0.0
        self._tree_lock = asyncio.Lock()

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        normalized = (url or "").strip()
        if _COMPETITION_SCHEME_RE.match(normalized.lower()):
            return True
        host = urlparse(normalized.lower()).netloc
        return any(domain in host for domain in _SUPPORTED_HOSTS)

    async def extract_league(self, url: str) -> CompetitionExtraction:
        if not self.can_handle_url(url):
            raise ValueError(f"{self.name} cannot handle URL: {url}")
        client = BetssonHttpClient(self.settings)
        competition_id = await self._competition_id_from_url(url, client)
        if competition_id is None:
            raise ValueError(
                "Could not determine the Betsson competition from the URL. Use "
                "'betsson:competition:<id>'."
            )
        table = await client.fetch_competition_events(competition_id)
        return build_competition_extraction(
            competition_id=competition_id, table_payload=table, source_url=url
        )

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError(f"{self.name} does not support direct match URLs yet.")

    async def list_live_events(self) -> list[LiveEventSnapshot]:
        client = BetssonHttpClient(self.settings)
        payload = await client.fetch_live_events()
        return live_events_from_table(payload)

    async def list_prematch_events(self) -> list[LiveEventSnapshot]:
        client = BetssonHttpClient(self.settings)
        tree = await self._get_tree(client)
        return prematch_events_from_tree(tree, category_id=self.settings.category_id)

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        client = BetssonHttpClient(self.settings)
        tree = await self._get_tree(client)
        return discovery_module.build_league_options_from_tree(
            tree,
            platform=self.name,
            platform_display_name=self.display_name,
            category_id=self.settings.category_id,
            country_name=country_name,
            query=query,
            limit=limit,
        )

    def build_competition_url(self, *, competition_external_id, source_url=None, metadata=None) -> str | None:
        del source_url, metadata
        return f"betsson:competition:{competition_external_id}"

    async def _competition_id_from_url(self, url: str, client: BetssonHttpClient) -> str | None:
        normalized = (url or "").strip()
        scheme_match = _COMPETITION_SCHEME_RE.match(normalized.lower())
        if scheme_match:
            return scheme_match.group(1)
        slug_match = _SLUG_PATH_RE.search(unquote(normalized))
        if slug_match:
            slug = slug_match.group("slug").strip("/").lower()
            tree = await self._get_tree(client)
            return discovery_module.resolve_competition_id_from_slug(tree, slug)
        return None

    async def _get_tree(self, client: BetssonHttpClient) -> dict[str, Any]:
        """Return the categories tree from a short-lived in-process cache."""

        async with self._tree_lock:
            now = time.monotonic()
            if self._tree_cache is not None and (now - self._tree_cached_at) < self._TREE_TTL_SECONDS:
                return self._tree_cache
            data = await client.fetch_categories_tree()
            if (((data or {}).get("data") or {}).get("items")):
                self._tree_cache = data
                self._tree_cached_at = now
            return data
