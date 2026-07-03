from __future__ import annotations

from typing import Protocol
from core.models import StatsLeagueLink, StatsMatchLinkRecord

class StatsLinksPort(Protocol):
    """Port defining links between odds competitions/events and stats providers."""

    def list_stats_league_links(
        self,
        tracked_competition_id: int,
    ) -> list[StatsLeagueLink]:
        """List all stats provider link mappings for a tracked competition."""
        ...

    def upsert_stats_league_link(
        self,
        tracked_competition_id: int,
        stats_provider: str,
        stats_league_id: str,
        stats_league_name: str,
        stats_country_name: str | None = None,
        confidence: float = 1.0,
        payload_json: str | None = None,
    ) -> None:
        """Create or update a mapping between a tracked competition and a stats provider league."""
        ...

    def get_stats_match_link(
        self,
        active_event_id: int,
        stats_provider: str | None = None,
    ) -> StatsMatchLinkRecord | None:
        """Retrieve a cached stats provider match mapping link for an event."""
        ...

    def upsert_stats_match_link(
        self,
        active_event_id: int,
        stats_provider: str,
        stats_match_id: str,
        stats_url: str | None = None,
        confidence: float = 1.0,
        method: str = "manual",
        payload_json: str | None = None,
    ) -> None:
        """Store or update a cached match link mapping to a stats provider."""
        ...
