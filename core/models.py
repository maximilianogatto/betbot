"""Generic domain models shared across sportsbook extractors.

These models represent the contract exposed by concrete extractors to the rest
of the application. The tracking stack and the SQLite repository now consume
platform-agnostic terms such as competition, event, and odds snapshot.

Identity rules expected by the tracking stack:
- competition: `platform + competition_external_id`
- event: `platform + competition_external_id + external_event_id`

That is the minimum contract a future platform implementation should satisfy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class PlatformDescriptor:
    """Describe one supported betting platform exposed by the extractor layer."""

    key: str
    display_name: str
    domains: tuple[str, ...] = ()
    supports: tuple[str, ...] = ()
    implemented: bool = True


@dataclass(frozen=True)
class Odds1X2:
    """Represent one normalized 1/X/2 odds set."""

    home: float | None
    draw: float | None
    away: float | None


@dataclass(frozen=True)
class CompetitionKey:
    """Identify one competition inside a given betting platform."""

    platform: str
    competition_external_id: str


@dataclass(frozen=True)
class EventKey:
    """Identify one event inside a given competition and platform."""

    platform: str
    competition_external_id: str
    external_event_id: str


@dataclass(frozen=True)
class EventSnapshot:
    """Represent one extracted event plus its current odds snapshot."""

    key: EventKey
    competition_name: str
    home: str
    away: str
    scheduled_label_date: str | None
    scheduled_label_time: str | None
    scheduled_at: str | None
    source_url: str | None
    odds_1x2: Odds1X2
    extracted_at: str
    stats_url: str | None = None
    markets_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def platform(self) -> str:
        """Compatibility accessor for the event platform."""

        return self.key.platform

    @property
    def competition_external_id(self) -> str:
        """Return the normalized external competition identifier."""

        return self.key.competition_external_id

    @property
    def external_event_id(self) -> str:
        """Return the normalized external event identifier."""

        return self.key.external_event_id


@dataclass(frozen=True)
class CompetitionExtraction:
    """Represent the extracted state of one competition page."""

    competition: CompetitionKey
    competition_name: str
    source_url: str
    events: list[EventSnapshot]
    is_empty: bool
    is_provisional_name: bool
    extracted_at: str
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def platform(self) -> str:
        """Return the extractor platform name."""

        return self.competition.platform

    @property
    def competition_external_id(self) -> str:
        """Return the normalized external competition identifier."""

        return self.competition.competition_external_id


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO format."""

    return datetime.now(timezone.utc).isoformat()


def platform_display_name(platform_key: str) -> str:
    """Return a friendly display name for one platform key."""

    normalized_key = platform_key.strip().lower()

    if not normalized_key:
        return "Desconocida"

    return normalized_key.replace("_", " ").replace("-", " ").title()


__all__ = [
    "CompetitionExtraction",
    "CompetitionKey",
    "EventKey",
    "EventSnapshot",
    "Odds1X2",
    "PlatformDescriptor",
    "platform_display_name",
    "utc_now_iso",
]
