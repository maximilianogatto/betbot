"""BZ (m.bz.com) prematch HTTP extractor.

m.bz.com is a Sportradar-id sportsbook: tournaments, matches and competitors all
carry ``sr:...`` ids, so tracked events line up directly with the Sportradar
stats provider. The full directory (tournaments by country, with names) comes
from ``match/search`` over plain HTTP — that powers ``/track_league`` discovery.

Tracking forms accepted:
  - ``/track_league`` discovery (preferred): ``search_leagues`` -> match/search.
  - ``bz:tournament:<id>`` (numeric or ``sr:tournament:<id>``).
  - an ``m.bz.com`` URL carrying a ``sr:tournament:<id>`` (or ``tournamentId``).

Odds (per match, from ``odds/v2/bz/all``): 1X2 + Asian handicap (📐) + total (📏).
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from core.extractor_base import Extractor, LeagueDiscoveryOption
from core.models import CompetitionExtraction, EventSnapshot, LiveEventSnapshot, ProviderCapabilities
from extractors.bz_http import discovery as discovery_module
from extractors.bz_http.client import BzHttpClient
from extractors.bz_http.parser import build_competition_extraction, find_tournament, live_events_from_search
from extractors.bz_http.settings import BzHttpSettings, load_bz_settings

_SUPPORTED_HOSTS = ("bz.com",)
_TOURNAMENT_SCHEME_RE = re.compile(r"^bz:tournament:(?:sr:tournament:)?(\d+)$", re.IGNORECASE)
_SR_TOURNAMENT_RE = re.compile(r"sr:tournament:(\d+)", re.IGNORECASE)
_SR_CATEGORY_RE = re.compile(r"sr:category:(\d+)", re.IGNORECASE)


def _category_external_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text.split(":")[-1] if text.startswith("sr:category:") else text



class BzHttpExtractor(Extractor):
    """HTTP extractor for BZ (m.bz.com) prematch soccer leagues."""

    name = "bz_http"
    display_name = "BZ"
    supported_domains = _SUPPORTED_HOSTS
    supported_capabilities = ("ligas",)
    provider_capabilities = ProviderCapabilities(supports_http=True, supports_browserless=True)
    supports_league_discovery = True  # via the match/search feed
    supports_live_detection = True  # via statusList=1 search
    supports_prematch_listing = True  # via statusList=0 search

    # The match/search feed lists every prematch tournament; cache it briefly so a
    # refresh sweep / discovery search reuses one download.
    _SEARCH_TTL_SECONDS = 90.0

    def __init__(self, *, settings: BzHttpSettings | None = None) -> None:
        self.settings = settings or load_bz_settings()
        self._search_cache: list[dict[str, Any]] | None = None
        self._search_cached_at = 0.0
        self._search_lock = asyncio.Lock()

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
                "Could not determine the BZ league from the URL. Use "
                "'bz:tournament:<id>' or an m.bz.com URL carrying 'sr:tournament:<id>'."
            )

        client = BzHttpClient(self.settings)
        search_data = await self._get_search(client)

        if tournament_id.startswith("category:"):
            cat_num = tournament_id.split(":")[-1]
            tournaments = [
                t for t in search_data
                if isinstance(t, dict) and _category_external_id(t.get("categoryId")) == cat_num
            ]
            if not tournaments:
                return build_competition_extraction(
                    tournament_id=tournament_id,
                    tournament={"name": "Unknown Category", "matches": []},
                    odds_by_match={},
                    source_url=url,
                )
            all_matches = []
            country_name = "Category"
            for t in tournaments:
                if t.get("categoryName"):
                    country_name = t["categoryName"]
                for m in t.get("matches") or []:
                    if isinstance(m, dict):
                        all_matches.append(m)
            match_ids = [str(m.get("id")) for m in all_matches if m.get("id")]
            odds_by_match = await client.fetch_many_match_odds(match_ids)
            merged_tournament = {
                "id": tournament_id,
                "name": country_name,
                "categoryName": country_name,
                "matches": all_matches
            }
            return build_competition_extraction(
                tournament_id=tournament_id,
                tournament=merged_tournament,
                odds_by_match=odds_by_match,
                source_url=url,
            )

        tournament = find_tournament(search_data, tournament_id)
        if tournament is None:
            return build_competition_extraction(
                tournament_id=tournament_id,
                tournament={"name": None, "matches": []},
                odds_by_match={},
                source_url=url,
            )

        match_ids = [str(m.get("id")) for m in tournament.get("matches") or [] if isinstance(m, dict) and m.get("id")]
        odds_by_match = await client.fetch_many_match_odds(match_ids)
        return build_competition_extraction(
            tournament_id=tournament_id,
            tournament=tournament,
            odds_by_match=odds_by_match,
            source_url=url,
        )

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError(f"{self.name} does not support direct match URLs yet.")

    async def list_live_events(self) -> list[LiveEventSnapshot]:
        client = BzHttpClient(self.settings)
        search_data = await client.fetch_live_search()
        return live_events_from_search(search_data)

    async def list_prematch_events(self) -> list[LiveEventSnapshot]:
        client = BzHttpClient(self.settings)
        search_data = await client.fetch_match_search()  # statusList=0 (not started)
        return live_events_from_search(search_data)

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        client = BzHttpClient(self.settings)
        search_data = await self._get_search(client)
        return discovery_module.build_league_options(
            search_data,
            platform=self.name,
            platform_display_name=self.display_name,
            country_name=country_name,
            query=query,
            limit=limit,
        )

    def build_competition_url(self, *, competition_external_id, source_url=None, metadata=None) -> str | None:
        del source_url, metadata
        external = str(competition_external_id).split(":")[-1]
        return f"bz:tournament:{external}"

    async def _get_search(self, client: BzHttpClient) -> list[dict[str, Any]]:
        """Return the match/search feed from a short-lived in-process cache."""

        async with self._search_lock:
            now = time.monotonic()
            if self._search_cache is not None and (now - self._search_cached_at) < self._SEARCH_TTL_SECONDS:
                return self._search_cache
            data = await client.fetch_match_search()
            if data:
                self._search_cache = data
                self._search_cached_at = now
            return data


def _tournament_id_from_url(url: str) -> str | None:
    normalized = (url or "").strip()
    scheme_match = _TOURNAMENT_SCHEME_RE.match(normalized.lower())
    if scheme_match:
        return scheme_match.group(1)

    decoded = unquote(normalized)
    cat_match = _SR_CATEGORY_RE.search(decoded)
    if cat_match:
        return f"category:{cat_match.group(1)}"

    sr_match = _SR_TOURNAMENT_RE.search(decoded)
    if sr_match:
        return sr_match.group(1)

    query = parse_qs(urlparse(normalized).query)
    for key in ("tournamentId", "tournament", "tid"):
        values = query.get(key)
        if values:
            candidate = str(values[0]).split(":")[-1]
            if candidate.isdigit():
                return candidate
    return None
