"""BetWarrior (Kambi) prematch HTTP extractor.

BetWarrior runs the Kambi sportsbook. Its catalog (sport -> country -> league ->
events) and odds come from Kambi's public offering API over plain HTTP (no token).
That powers ``/track_league`` discovery.

Tracking forms accepted:
  - ``/track_league`` discovery (preferred): ``search_leagues`` -> listView.
  - ``betwarrior:group:<id>`` (Kambi group/league id).
  - a betwarrior URL carrying a numeric Kambi group id.

Odds (one call per league via betoffer/group): 1X2 + Asian handicap (📐) + goal line (📏).
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import urlparse

from core.extractor_base import Extractor, LeagueDiscoveryOption
from core.models import CompetitionExtraction, EventSnapshot, ProviderCapabilities
from extractors.betwarrior_http import discovery as discovery_module
from extractors.betwarrior_http.client import BetWarriorHttpClient
from extractors.betwarrior_http.parser import build_competition_extraction
from extractors.betwarrior_http.settings import BetWarriorHttpSettings, load_betwarrior_settings

_SUPPORTED_HOSTS = ("betwarrior.bet.ar", "betwarrior.com", "kambicdn.com")
_GROUP_SCHEME_RE = re.compile(r"^betwarrior:group:(\d+)$", re.IGNORECASE)
_GROUP_IN_URL_RE = re.compile(r"(?:group|filter)[/=](\d{6,})", re.IGNORECASE)


class BetWarriorHttpExtractor(Extractor):
    """HTTP extractor for BetWarrior (Kambi) prematch soccer leagues."""

    name = "betwarrior_http"
    display_name = "BetWarrior HTTP"
    supported_domains = _SUPPORTED_HOSTS
    supported_capabilities = ("ligas",)
    provider_capabilities = ProviderCapabilities(supports_http=True, supports_browserless=True)
    supports_league_discovery = True  # via the Kambi listView feed

    # The listView lists every prematch league; cache it briefly so a refresh sweep
    # / discovery search reuses one download.
    _LIST_VIEW_TTL_SECONDS = 90.0

    def __init__(self, *, settings: BetWarriorHttpSettings | None = None) -> None:
        self.settings = settings or load_betwarrior_settings()
        self._list_view_cache: dict[str, Any] | None = None
        self._list_view_cached_at = 0.0
        self._list_view_lock = asyncio.Lock()

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        normalized = (url or "").strip()
        if _GROUP_SCHEME_RE.match(normalized.lower()):
            return True
        host = urlparse(normalized.lower()).netloc
        return any(domain in host for domain in _SUPPORTED_HOSTS)

    async def extract_league(self, url: str) -> CompetitionExtraction:
        if not self.can_handle_url(url):
            raise ValueError(f"{self.name} cannot handle URL: {url}")
        group_id = _group_id_from_url(url)
        if group_id is None:
            raise ValueError(
                "Could not determine the BetWarrior league from the URL. Use "
                "'betwarrior:group:<id>'."
            )
        client = BetWarriorHttpClient(self.settings)
        group_payload = await client.fetch_group_bet_offers(group_id)
        return build_competition_extraction(
            group_id=group_id, group_payload=group_payload, source_url=url
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
        client = BetWarriorHttpClient(self.settings)
        list_view = await self._get_list_view(client)
        return discovery_module.build_league_options(
            list_view,
            platform=self.name,
            platform_display_name=self.display_name,
            country_name=country_name,
            query=query,
            limit=limit,
        )

    def build_competition_url(self, *, competition_external_id, source_url=None, metadata=None) -> str | None:
        del source_url, metadata
        return f"betwarrior:group:{competition_external_id}"

    async def _get_list_view(self, client: BetWarriorHttpClient) -> dict[str, Any]:
        """Return the listView feed from a short-lived in-process cache."""

        async with self._list_view_lock:
            now = time.monotonic()
            if self._list_view_cache is not None and (now - self._list_view_cached_at) < self._LIST_VIEW_TTL_SECONDS:
                return self._list_view_cache
            data = await client.fetch_list_view()
            if data.get("events"):
                self._list_view_cache = data
                self._list_view_cached_at = now
            return data


def _group_id_from_url(url: str) -> str | None:
    normalized = (url or "").strip()
    scheme_match = _GROUP_SCHEME_RE.match(normalized.lower())
    if scheme_match:
        return scheme_match.group(1)
    url_match = _GROUP_IN_URL_RE.search(normalized)
    return url_match.group(1) if url_match else None
