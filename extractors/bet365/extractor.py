"""Bet365 HTTP-first extractor adapter implementing the common interface."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from core.extractor_base import Extractor, CompetitionUnavailableError, LeagueDiscoveryOption
from core.models import (
    CompetitionExtraction,
    CompetitionKey,
    EventKey,
    EventSnapshot,
    Odds1X2,
    ProviderCapabilities,
    utc_now_iso,
)
from extractors.bet365.client import (
    Bet365HttpClient,
    Bet365ExtractorSettings,
    Bet365AsianLeagueExtraction,
    Bet365AsianMatch,
    validate_bet365_league_url,
)

logger = logging.getLogger(__name__)


class Bet365Extractor(Extractor):
    """Clean HTTP extractor adapter for Bet365 soccer leagues."""

    name = "bet365"
    display_name = "Bet365"
    supported_domains = ("bet365.bet.ar", "bet365.es", "bet365.com")
    supported_capabilities = ("ligas", "eventos 1X2", "asian handicap", "goal line")
    provider_capabilities = ProviderCapabilities(
        supports_http=True,
        supports_live=False,
        supports_deep_markets=True,
        supports_browserless=True,
    )
    supports_league_discovery = True

    def __init__(self, *, settings: Bet365ExtractorSettings | None = None) -> None:
        self._settings = settings or Bet365ExtractorSettings()
        self._client = Bet365HttpClient(self._settings)

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        """Return whether the given URL belongs to Bet365."""
        try:
            validate_bet365_league_url(url)
            return True
        except ValueError:
            return False

    async def extract_league(self, url: str) -> CompetitionExtraction:
        """Extract one Bet365 league dynamically."""
        extraction = await self._client.fetch_league(url)
        return _to_competition_extraction(extraction)

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError("Bet365 direct match extraction is not supported.")

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        """Discover trackable leagues over plain HTTP from allsportsmenu."""
        
        # We search first on bet.ar for Argentina region, fallback to bet365.es
        host = "www.bet365.bet.ar"
        try:
            menu_data = await self._client.fetch_allsportsmenu(host, pd="#AL#R^1#")
        except Exception as error:
            logger.warning("Failed to fetch menu from Argentina host, trying Spain host: %s", error)
            host = "www.bet365.es"
            try:
                menu_data = await self._client.fetch_allsportsmenu(host, pd="#AL#R^1#")
            except Exception as final_error:
                logger.error("Failed to fetch menu from both hosts: %s", final_error)
                return []
                
        # Parse tournaments from the flat menu layout
        records = menu_data.replace("\x08", "").strip().split("|")
        options = []
        
        for record in records:
            parts = record.split(";")
            if not parts[0] or parts[0] not in ("EV", "CL"):
                continue
            fields = {}
            for p in parts[1:]:
                if "=" in p:
                    k, v = p.split("=", 1)
                    fields[k] = v
                    
            name = fields.get("NA") or fields.get("EX") or fields.get("IT") or ""
            pd = fields.get("PD")
            
            # Filter for soccer categories carrying a specific tournament ID
            if pd and "#B1#" in pd and "#E" in pd:
                league_match = re.search(r"#E([^#]+)#", pd)
                if not league_match:
                    continue
                league_id = league_match.group(1)
                
                # Construct visual URL
                clean_path = pd.strip("#").replace("#", "/")
                source_url = f"https://{host}/#/{clean_path}/"
                
                options.append(
                    LeagueDiscoveryOption(
                        platform=self.name,
                        platform_display_name=self.display_name,
                        country_id=None,
                        country_name="International",
                        league_id=league_id,
                        league_name=name,
                        source_url=source_url,
                        raw_payload={"pd": pd},
                    )
                )
                
        # Filter matching country_name or query
        query_norm = (query or "").strip().lower()
        country_norm = country_name.strip().lower()
        
        filtered = []
        for opt in options:
            match_name = opt.league_name.lower()
            if query_norm and query_norm not in match_name:
                continue
            if country_norm and country_norm != "international" and country_norm not in match_name:
                # Best-effort matching country in league name
                continue
            filtered.append(opt)
            if len(filtered) >= limit:
                break
                
        return filtered

    def build_competition_url(
        self,
        *,
        competition_external_id: str,
        source_url: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> str | None:
        return source_url

    def build_event_url(
        self,
        *,
        competition_external_id: str,
        external_event_id: str,
        source_url: str | None = None,
        event_url: str | None = None,
        competition_metadata: dict[str, object] | None = None,
        event_metadata: dict[str, object] | None = None,
    ) -> str | None:
        del competition_external_id, competition_metadata, event_metadata
        normalized_source_url = (source_url or "").strip()
        normalized_event_id = external_event_id.strip()

        direct_url = _build_bet365_event_url(normalized_source_url, normalized_event_id)
        if direct_url:
            return direct_url

        normalized_event_url = (event_url or "").strip()
        return normalized_event_url or None


def _to_competition_extraction(extraction: Bet365AsianLeagueExtraction) -> CompetitionExtraction:
    competition_key = CompetitionKey(
        platform=extraction.platform,
        competition_external_id=extraction.topic,
    )
    extracted_at = utc_now_iso()
    events = [
        _to_event_snapshot(
            match,
            platform=extraction.platform,
            competition_external_id=extraction.topic,
            competition_name=extraction.league_name,
            competition_url=extraction.url,
            extracted_at=extracted_at,
        )
        for match in extraction.matches
    ]

    return CompetitionExtraction(
        competition=competition_key,
        competition_name=extraction.league_name,
        source_url=extraction.url,
        events=events,
        is_empty=not events,
        is_provisional_name=False,
        extracted_at=extracted_at,
        metadata={},
        raw_payload=extraction.payload,
    )


def _to_event_snapshot(
    match: Bet365AsianMatch,
    *,
    platform: str,
    competition_external_id: str,
    competition_name: str,
    competition_url: str,
    extracted_at: str,
) -> EventSnapshot:
    return EventSnapshot(
        key=EventKey(
            platform=platform,
            competition_external_id=competition_external_id,
            external_event_id=match.fixture_id,
        ),
        competition_name=competition_name,
        home=match.home,
        away=match.away,
        scheduled_label_date=match.scheduled_label_date,
        scheduled_label_time=match.scheduled_label_time,
        scheduled_at=match.scheduled_at,
        source_url=match.event_url or _build_bet365_event_url(competition_url, match.fixture_id),
        odds_1x2=Odds1X2(
            home=match.odds_home,
            draw=match.odds_draw,
            away=match.odds_away,
        ),
        extracted_at=extracted_at,
        stats_url=match.stats_url,
        markets_payload=match.markets_payload,
        metadata={
            "platform": platform,
            "competition_name": competition_name,
        },
        raw_payload=match.raw,
    )


def _build_bet365_event_url(competition_url: str, fixture_id: str) -> str | None:
    normalized_fixture_id = fixture_id.strip()
    normalized_competition_url = competition_url.strip()

    if not normalized_fixture_id or not normalized_competition_url:
        return None

    parsed_url = urlparse(normalized_competition_url)
    if "bet365" not in parsed_url.netloc.lower():
        return None

    return (
        f"{parsed_url.scheme}://{parsed_url.netloc}"
        f"/#/AC/B1/C1/D8/E{normalized_fixture_id}/F3/I1/"
    )
