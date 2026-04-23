"""Abstract extractor interface for sportsbook-specific scrapers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.models import CompetitionExtraction, EventSnapshot


class Extractor(ABC):
    """Common interface implemented by each sportsbook extractor.

    A future platform should only need to:

    1. decide whether it can handle a URL
    2. return a `CompetitionExtraction` for competition URLs
    3. optionally return an `EventSnapshot` for direct event URLs

    The rest of the tracking stack can then operate on the generic models
    without knowing platform-specific parsing details.
    """

    name: str

    @classmethod
    @abstractmethod
    def can_handle_url(cls, url: str) -> bool:
        """Return whether this extractor can handle the given URL."""

    @abstractmethod
    async def extract_league(self, url: str) -> CompetitionExtraction:
        """Extract one competition payload from a sportsbook URL.

        The returned `CompetitionExtraction` must include a stable
        `platform + competition_external_id` identity plus normalized event
        snapshots for any currently visible events.
        """

    @abstractmethod
    async def extract_match(self, url: str) -> EventSnapshot:
        """Extract one event payload from a sportsbook URL."""

    async def start(self) -> None:
        """Start any optional shared runtime resources for the extractor."""

    async def stop(self) -> None:
        """Stop any optional shared runtime resources for the extractor."""
