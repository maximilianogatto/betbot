from __future__ import annotations

from typing import Protocol
from core.stats_models import (
    StatsLeagueOption,
    StatsFixture,
    StatsMatchLink,
    MatchStatsReport,
    StatsProviderDescriptor,
    MatchIdentityCandidate,
)

class StatsProviderPort(Protocol):
    """Port defining the interface for external match statistics providers."""

    async def search_leagues(
        self,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[StatsLeagueOption]:
        """Search stats provider for leagues/tournaments matching a country or name query."""
        ...

    async def list_fixtures(
        self,
        league_id: str,
        limit: int | None = None,
    ) -> list[StatsFixture]:
        """List fixtures for a stats provider league."""
        ...

    async def resolve_match(
        self,
        candidate: MatchIdentityCandidate,
        options: list[StatsFixture],
    ) -> StatsMatchLink | None:
        """Heuristically resolve a sportsbook event to a provider match candidate."""
        ...

    async def build_match_report(
        self,
        stats_match_id: str,
    ) -> MatchStatsReport:
        """Generate a rendered statistics report for in-play/prematch match analytics."""
        ...

    def build_match_url(
        self,
        stats_match_id: str,
    ) -> str | None:
        """Return the public web URL for a stats provider match page."""
        ...

    def describe_provider(self) -> StatsProviderDescriptor:
        """Return capabilities and descriptions for this stats provider."""
        ...

    async def start(self) -> None:
        """Initialize stats provider background resources."""
        ...

    async def stop(self) -> None:
        """Release stats provider resources cleanly."""
        ...
