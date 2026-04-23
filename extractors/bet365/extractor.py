"""Bet365 extractor adapter that implements the common extractor interface."""

from __future__ import annotations

from core.extractor_base import Extractor
from core.models import CompetitionExtraction, CompetitionKey, EventKey, EventSnapshot, Odds1X2, utc_now_iso
from services.bet365_extractor import (
    Bet365BrowserExtractor,
    Bet365ExtractorSettings,
    Bet365LeagueExtraction,
    Bet365Match,
    validate_bet365_league_url,
)


class Bet365Extractor(Extractor):
    """Wrap the current Bet365 scraper behind the generic extractor interface."""

    name = "bet365"

    def __init__(
        self,
        *,
        settings: Bet365ExtractorSettings | None = None,
        browser_extractor: Bet365BrowserExtractor | None = None,
    ) -> None:
        self._browser_extractor = browser_extractor or Bet365BrowserExtractor(settings)

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

        extraction = await self._browser_extractor.extract_league(url)
        return _to_competition_extraction(extraction)

    async def extract_match(self, url: str) -> EventSnapshot:
        """Match-level extraction is reserved for a future refactor."""

        raise NotImplementedError("Bet365 match extraction is not implemented yet.")

    async def start(self) -> None:
        """Start the persistent browser used by the current Bet365 scraper."""

        await self._browser_extractor.start()

    async def stop(self) -> None:
        """Stop the persistent browser used by the current Bet365 scraper."""

        await self._browser_extractor.stop()


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
            source_url=extraction.url,
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


def _to_event_snapshot(
    match: Bet365Match,
    *,
    platform: str,
    competition_external_id: str,
    competition_name: str,
    source_url: str,
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
        source_url=source_url,
        odds_1x2=Odds1X2(
            home=match.odds_home,
            draw=match.odds_draw,
            away=match.odds_away,
        ),
        extracted_at=extracted_at,
        metadata={
            "platform": platform,
            "competition_name": competition_name,
        },
        raw_payload=match.raw,
    )
