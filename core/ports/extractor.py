from __future__ import annotations

from typing import Protocol, Any
from core.models import (
    CompetitionExtraction,
    EventSnapshot,
    LiveEventSnapshot,
    LeagueDiscoveryOption,
    PlatformDescriptor,
)

class ExtractorPort(Protocol):
    """Port defining the interface for concrete sportsbook extractors."""

    name: str

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        """Return True if this extractor can scrape the provided competition/match URL."""
        ...

    async def extract_league(self, url: str) -> CompetitionExtraction:
        """Scrape league page and return all parsed prematch fixture data."""
        ...

    async def extract_match(self, url: str) -> EventSnapshot:
        """Scrape a specific match detail page and return detailed odds/metadata."""
        ...

    async def list_live_events(self) -> list[LiveEventSnapshot]:
        """Fetch ongoing in-play events from the platform's live scoreboard feed."""
        ...

    async def list_prematch_events(self) -> list[LiveEventSnapshot]:
        """Fetch all upcoming prematch events from the platform's prematch scoreboard."""
        ...

    async def search_leagues(
        self,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        """Search platform catalog for leagues belonging to a specific country."""
        ...

    def describe_platform(self) -> PlatformDescriptor:
        """Return descriptors and static capabilities for this platform."""
        ...

    async def start(self) -> None:
        """Start background scraper resources (e.g. launch Chromium or browser contexts)."""
        ...

    async def stop(self) -> None:
        """Stop background scraper resources and free memory cleanly."""
        ...
