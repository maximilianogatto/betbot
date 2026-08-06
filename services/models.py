"""Internal models for tracking refreshes, diffs, and command responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Re-exportados: nacieron acá y medio repo los importa de este nombre, pero
# ahora viven en core para que los eventos de dominio puedan transportarlos.
from core.models import (  # noqa: F401
    ActiveEventRecord,
    EventBaseline,
    MarketChangeDetail,
    SubscriptionOddsAlert,
    TrackedCompetition,
)


@dataclass(frozen=True)
class CommandResult:
    """Represent a simple bot-facing command response."""

    ok: bool
    message: str
    data: Any = None


@dataclass(frozen=True)
class OddsChange:
    """Represent one odds change detected for a fixture."""

    before: ActiveEventRecord
    after: ActiveEventRecord


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
