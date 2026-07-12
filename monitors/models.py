"""Internal models for tracking refreshes, diffs, and command responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models import ActiveEventRecord, EventBaseline, TrackedCompetition


@dataclass(frozen=True)
class CommandResult:
    """Represent a simple bot-facing command response."""

    ok: bool
    message: str


@dataclass(frozen=True)
class OddsChange:
    """Represent one odds change detected for a fixture."""

    before: ActiveEventRecord
    after: ActiveEventRecord


@dataclass(frozen=True)
class MarketChangeDetail:
    """Represent one concrete odds change inside a normalized market payload."""

    market_type: str
    market_name: str
    selection: str
    line: str | None
    before: float
    after: float
    percent_change: float


@dataclass(frozen=True)
class SubscriptionOddsAlert:
    """Represent one odds alert decision for a specific chat baseline."""

    match: ActiveEventRecord
    baseline: EventBaseline
    max_percent_change: float
    change_details: tuple[MarketChangeDetail, ...]
    changed_market_types: tuple[str, ...]
    confirmed_baseline_markets_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class CompetitionRefreshResult:
    """Summarize the result of refreshing one tracked competition."""

    tracked_league: TrackedCompetition
    active_matches: list[ActiveEventRecord]
    new_matches: list[ActiveEventRecord]
    odds_changes: list[OddsChange]
    reminder_matches: list[ActiveEventRecord]
    removed_missing_count: int
    removed_past_count: int
    degraded: bool = False
    degraded_reason: str | None = None


@dataclass(frozen=True)
class UnavailableCompetitionRefresh:
    """Summarize one refresh attempt that could not produce a usable snapshot."""

    tracked_league: TrackedCompetition
    reason: str


@dataclass(frozen=True)
class RefreshSummary:
    """Summarize a refresh pass over one or more tracked competitions."""

    tracks_requested: int
    tracks_refreshed: int
    active_matches: int
    new_events: int
    odds_changes: int
    failed_leagues: list[str]
    degraded_leagues: list[str]
    league_results: list[CompetitionRefreshResult]
    unavailable_competitions: list[UnavailableCompetitionRefresh]
    elapsed_seconds: float = 0.0


__all__ = [
    "CommandResult",
    "CompetitionRefreshResult",
    "MarketChangeDetail",
    "OddsChange",
    "RefreshSummary",
    "SubscriptionOddsAlert",
    "UnavailableCompetitionRefresh",
]
