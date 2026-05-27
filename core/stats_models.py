"""Domain models for external match statistics providers.

Stats providers are intentionally separate from sportsbook odds extractors:

- odds extractors discover betting fixtures and prices;
- stats providers resolve those fixtures to richer match context;
- the tracking layer can link both through explicit league/match mappings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StatsProviderCapabilities:
    """Machine-readable capabilities exposed by a stats provider."""

    supports_league_discovery: bool = False
    supports_fixture_discovery: bool = False
    supports_live: bool = False
    supports_h2h: bool = False
    supports_lineups: bool = False
    supports_injuries: bool = False
    supports_odds: bool = False
    requires_browser_bootstrap: bool = False


@dataclass(frozen=True)
class StatsProviderDescriptor:
    """Describe one stats provider exposed to Telegram flows."""

    key: str
    display_name: str
    capabilities: StatsProviderCapabilities = field(default_factory=StatsProviderCapabilities)
    implemented: bool = True


@dataclass(frozen=True)
class StatsLeagueOption:
    """One provider-native league/tournament that can be linked to a tracked league."""

    provider: str
    provider_display_name: str
    country_name: str | None
    league_id: str
    league_name: str
    season_id: str | None = None
    source_url: str | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class StatsFixture:
    """One fixture from a stats provider league."""

    provider: str
    league_id: str
    match_id: str
    home: str
    away: str
    scheduled_at: str | None
    status: str | None = None
    stats_url: str | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class MatchIdentityCandidate:
    """Odds-event identity used to resolve a provider stats match."""

    home: str
    away: str
    scheduled_at: str | None
    league_name: str | None = None
    stats_url: str | None = None
    platform: str | None = None
    external_event_id: str | None = None


@dataclass(frozen=True)
class StatsMatchLink:
    """Persistable link between one odds event and one stats provider match."""

    provider: str
    stats_match_id: str
    stats_url: str | None
    confidence: float
    method: str
    home_similarity: float | None = None
    away_similarity: float | None = None
    kickoff_delta_minutes: float | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class MatchStatsReport:
    """Compact report returned by a stats provider for Telegram rendering."""

    provider: str
    match_id: str
    title: str
    markdown: str
    data: dict[str, Any]
    generated_at: str


__all__ = [
    "MatchIdentityCandidate",
    "MatchStatsReport",
    "StatsFixture",
    "StatsLeagueOption",
    "StatsMatchLink",
    "StatsProviderCapabilities",
    "StatsProviderDescriptor",
]
