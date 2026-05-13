"""Bet365 extractor adapter that implements the common extractor interface."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from core.extractor_base import CompetitionUnavailableError
from core.extractor_base import Extractor
from core.models import CompetitionExtraction, CompetitionKey, EventKey, EventSnapshot, Odds1X2, utc_now_iso
from extractors.bet365.client import (
    Bet365BrowserExtractor,
    Bet365ExtractorSettings,
    Bet365LeagueExtraction,
    Bet365Match,
    validate_bet365_league_url,
)
from extractors.bet365.playwright_asian import (
    Bet365AsianLeagueExtraction,
    Bet365AsianMatch,
    Bet365PlaywrightAsianClient,
)

logger = logging.getLogger(__name__)


class Bet365Extractor(Extractor):
    """Wrap the current Bet365 scraper behind the generic extractor interface."""

    name = "bet365"
    display_name = "Bet365"
    supported_domains = ("bet365.bet.ar", "bet365.es", "bet365.com")
    supported_capabilities = ("ligas", "eventos 1X2", "asian handicap", "goal line")

    def __init__(
        self,
        *,
        settings: Bet365ExtractorSettings | None = None,
        playwright_asian_client: Bet365PlaywrightAsianClient | None = None,
        browser_extractor: Bet365BrowserExtractor | None = None,
    ) -> None:
        self._settings = settings or Bet365ExtractorSettings()
        self._playwright_asian_client = playwright_asian_client or Bet365PlaywrightAsianClient(
            self._settings
        )
        self._fallback_browser_extractor = browser_extractor

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        """Return whether the given URL belongs to Bet365."""

        try:
            validate_bet365_league_url(url)
        except ValueError:
            return False

        return True

    async def extract_league(self, url: str) -> CompetitionExtraction:
        """Extract one Bet365 league and adapt it to the generic domain model."""

        try:
            extraction = await self._playwright_asian_client.extract_league_with_asian_lines(url)
        except CompetitionUnavailableError as error:
            logger.warning(
                "Bet365 Playwright response-capture extractor could not refresh url=%s: %s. Falling back to legacy extractor.",
                url,
                error,
            )
            fallback_extraction = await self._get_fallback_browser_extractor().extract_league(url)
            return _to_competition_extraction(fallback_extraction)
        except Exception as error:
            logger.warning(
                "Bet365 Playwright response-capture extractor failed for url=%s: %s. Falling back to legacy extractor.",
                url,
                error,
            )
            fallback_extraction = await self._get_fallback_browser_extractor().extract_league(url)
            return _to_competition_extraction(fallback_extraction)

        return _to_competition_extraction_from_asian(extraction)

    async def extract_match(self, url: str) -> EventSnapshot:
        """Match-level extraction is reserved for a future refactor."""

        raise NotImplementedError("Bet365 match extraction is not implemented yet.")

    async def start(self) -> None:
        """Start the persistent browser used by the current Bet365 scraper."""

        await self._playwright_asian_client.start()

    async def stop(self) -> None:
        """Stop the persistent browser used by the current Bet365 scraper."""

        await self._playwright_asian_client.stop()

        if self._fallback_browser_extractor is not None:
            await self._fallback_browser_extractor.stop()

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
        """Return a direct Bet365 event URL when it can be derived safely."""

        del competition_external_id, competition_metadata, event_metadata

        normalized_source_url = (source_url or "").strip()
        normalized_event_id = external_event_id.strip()

        direct_url = _build_bet365_event_url(normalized_source_url, normalized_event_id)
        if direct_url:
            return direct_url

        normalized_event_url = (event_url or "").strip()
        return normalized_event_url or None

    def _get_fallback_browser_extractor(self) -> Bet365BrowserExtractor:
        if self._fallback_browser_extractor is None:
            self._fallback_browser_extractor = Bet365BrowserExtractor(self._settings)
        return self._fallback_browser_extractor


def _to_competition_extraction(extraction: Bet365LeagueExtraction) -> CompetitionExtraction:
    """Adapt the current Bet365 payload to the generic competition model."""

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

    metadata = {
        "bet365_league_id": extraction.league_id,
    }

    return CompetitionExtraction(
        competition=competition_key,
        competition_name=extraction.league_name,
        source_url=extraction.url,
        events=events,
        is_empty=extraction.is_empty,
        is_provisional_name=extraction.is_provisional_name,
        extracted_at=extracted_at,
        metadata=metadata,
        raw_payload=extraction.payload,
    )


def _to_competition_extraction_from_asian(
    extraction: Bet365AsianLeagueExtraction,
) -> CompetitionExtraction:
    """Adapt the Playwright response-capture Bet365 payload to the generic model."""

    competition_key = CompetitionKey(
        platform=extraction.platform,
        competition_external_id=extraction.topic,
    )
    extracted_at = utc_now_iso()
    events = [
        _to_event_snapshot_from_asian(
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
    match: Bet365Match,
    *,
    platform: str,
    competition_external_id: str,
    competition_name: str,
    competition_url: str,
    extracted_at: str,
) -> EventSnapshot:
    """Adapt one normalized Bet365 match to the generic event snapshot model."""

    return EventSnapshot(
        key=EventKey(
            platform=platform,
            competition_external_id=competition_external_id,
            external_event_id=match.fixture_id,
        ),
        competition_name=competition_name,
        home=match.home,
        away=match.away,
        scheduled_label_date=match.kickoff_label_date,
        scheduled_label_time=match.kickoff_label_time,
        scheduled_at=match.kickoff_at,
        source_url=_build_bet365_event_url(competition_url, match.fixture_id),
        odds_1x2=Odds1X2(
            home=match.odds_home,
            draw=match.odds_draw,
            away=match.odds_away,
        ),
        extracted_at=extracted_at,
        markets_payload=None,
        metadata={
            "platform": platform,
            "competition_name": competition_name,
        },
        raw_payload=match.raw,
    )


def _to_event_snapshot_from_asian(
    match: Bet365AsianMatch,
    *,
    platform: str,
    competition_external_id: str,
    competition_name: str,
    competition_url: str,
    extracted_at: str,
) -> EventSnapshot:
    """Adapt one Playwright-captured Bet365 match to the generic event snapshot model."""

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
    """Build a direct Bet365 event URL from one competition URL and fixture id."""

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
