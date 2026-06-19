"""MrPunter (FSB) prematch + live HTTP extractor.

MrPunter runs the FSB sportsbook. Its catalog + odds come from the FSB eventlist
API; auth is two anonymous JWTs scraped from the /es/spbk/ HTML (plain HTTP, no
browser). That powers /track_league discovery and live detection.

Tracking forms accepted:
  - /track_league discovery (preferred): search_leagues -> navigation tree.
  - mrpunter:league:<MasterLeagueId>.
  - an mrpunter/fssb URL carrying a MasterLeagueId.

Odds (gameOdds per league): 1X2 + goal line (📏); Asian handicap (📐) when offered.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import urlparse

from core.extractor_base import Extractor, LeagueDiscoveryOption
from core.models import CompetitionExtraction, EventSnapshot, LiveEventSnapshot, ProviderCapabilities
from extractors.mrpunter_http import discovery as discovery_module
from extractors.mrpunter_http.client import MrPunterHttpClient
from extractors.mrpunter_http.parser import build_competition_extraction, live_events_from_league_odds
from extractors.mrpunter_http.settings import MrPunterHttpSettings, load_mrpunter_settings

_SUPPORTED_HOSTS = ("mrpunter.com", "fssb.io")
_LEAGUE_SCHEME_RE = re.compile(r"^mrpunter:league:(\d+)$", re.IGNORECASE)
_LEAGUE_IN_URL_RE = re.compile(r"(?:league|liga)[/=](\d{2,})", re.IGNORECASE)


class MrPunterHttpExtractor(Extractor):
    """HTTP extractor for MrPunter (FSB) prematch + live soccer leagues."""

    name = "mrpunter_http"
    display_name = "MrPunter"
    supported_domains = _SUPPORTED_HOSTS
    supported_capabilities = ("ligas",)
    provider_capabilities = ProviderCapabilities(supports_http=True, supports_live=True, supports_browserless=True)
    supports_league_discovery = True
    supports_live_detection = True  # via events/v2/live/initial

    _NAV_TTL_SECONDS = 90.0

    def __init__(self, *, settings: MrPunterHttpSettings | None = None) -> None:
        self.settings = settings or load_mrpunter_settings()
        self._client = MrPunterHttpClient(self.settings)
        self._nav_cache: list[dict[str, Any]] | None = None
        self._nav_cached_at = 0.0
        self._nav_lock = asyncio.Lock()

    async def stop(self) -> None:
        await self._client.aclose()

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        normalized = (url or "").strip()
        if _LEAGUE_SCHEME_RE.match(normalized.lower()):
            return True
        host = urlparse(normalized.lower()).netloc
        return any(domain in host for domain in _SUPPORTED_HOSTS)

    async def extract_league(self, url: str) -> CompetitionExtraction:
        if not self.can_handle_url(url):
            raise ValueError(f"{self.name} cannot handle URL: {url}")
        master_id = _league_id_from_url(url)
        if master_id is None:
            raise ValueError(
                "Could not determine the MrPunter league from the URL. Use "
                "'mrpunter:league:<MasterLeagueId>'."
            )
        events = await self._client.fetch_league_odds(master_id, is_live=False)
        country, league_name = await self._resolve_league_meta(master_id)
        return build_competition_extraction(
            master_league_id=master_id,
            events=events,
            source_url=url,
            competition_name=league_name,
            country_name=country,
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
        navigation = await self._get_navigation()
        return discovery_module.build_league_options(
            navigation,
            platform=self.name,
            platform_display_name=self.display_name,
            sport_id=self.settings.sport_id,
            country_name=country_name,
            query=query,
            limit=limit,
        )

    async def list_live_events(self) -> list[LiveEventSnapshot]:
        # The events/v2/live/initial feed returns an empty data array even when
        # live football exists (navigation's liveEventsQuantity proves it), so we
        # gather live events per league: navigation -> live football leagues ->
        # their gameOdds with IsLive=true (same positional array shape).
        navigation = await self._get_navigation()
        sport_id = str(self.settings.sport_id)
        sport = next((s for s in navigation or [] if str(s.get("_id")) == sport_id), None)
        if sport is None:
            return []
        master_ids: list[str] = []
        for country in sport.get("countries", []) or []:
            for league in country.get("Leagues", []) or []:
                if (league.get("liveEventsQuantity") or 0) > 0 and league.get("MasterLeagueId") is not None:
                    master_ids.append(str(league["MasterLeagueId"]))
        if not master_ids:
            return []
        events_by_league = await self._client.fetch_many_league_odds(master_ids, is_live=True)
        return live_events_from_league_odds(events_by_league, sport_id=sport_id)

    def build_competition_url(self, *, competition_external_id, source_url=None, metadata=None) -> str | None:
        del source_url, metadata
        return f"mrpunter:league:{competition_external_id}"

    async def _get_navigation(self) -> list[dict[str, Any]]:
        async with self._nav_lock:
            now = time.monotonic()
            if self._nav_cache is not None and (now - self._nav_cached_at) < self._NAV_TTL_SECONDS:
                return self._nav_cache
            data = await self._client.fetch_navigation()
            if data:
                self._nav_cache = data
                self._nav_cached_at = now
            return data

    async def _resolve_league_meta(self, master_id: str) -> tuple[str | None, str | None]:
        """Best-effort country + league name for a MasterLeagueId from navigation."""

        try:
            navigation = await self._get_navigation()
        except Exception:
            return None, None
        for sport in navigation or []:
            if str(sport.get("_id")) != str(self.settings.sport_id):
                continue
            for country in sport.get("countries") or []:
                for league in country.get("Leagues") or []:
                    if str(league.get("MasterLeagueId")) == str(master_id):
                        return country.get("RegionName"), league.get("LeagueName")
        return None, None


def _league_id_from_url(url: str) -> str | None:
    normalized = (url or "").strip()
    scheme = _LEAGUE_SCHEME_RE.match(normalized.lower())
    if scheme:
        return scheme.group(1)
    match = _LEAGUE_IN_URL_RE.search(normalized)
    return match.group(1) if match else None
