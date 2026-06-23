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


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO format."""

    return datetime.now(timezone.utc).isoformat()


def platform_display_name(platform_key: str) -> str:
    """Return a friendly display name for one platform key."""

    normalized_key = platform_key.strip().lower()

    if not normalized_key:
        return "Desconocida"

    return normalized_key.replace("_", " ").replace("-", " ").title()


@dataclass(frozen=True)
class ProviderCapabilities:
    """Machine-readable capabilities exposed by a provider adapter."""

    supports_http: bool = False
    supports_live: bool = False
    supports_deep_markets: bool = False
    supports_browserless: bool = False


@dataclass(frozen=True)
class PlatformDescriptor:
    """Describe one supported betting platform exposed by the extractor layer."""

    key: str
    display_name: str
    domains: tuple[str, ...] = ()
    supports: tuple[str, ...] = ()
    implemented: bool = True
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)


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

    def to_match_snapshot(self) -> MatchSnapshot:
        """Convert this EventSnapshot to a unified MatchSnapshot."""
        from datetime import datetime, timezone
        scheduled_dt = datetime.now(timezone.utc)
        if self.scheduled_at:
            try:
                # Handle trailing Z or timezone offsets
                iso_str = self.scheduled_at
                if iso_str.endswith("Z"):
                    iso_str = iso_str[:-1] + "+00:00"
                scheduled_dt = datetime.fromisoformat(iso_str)
            except Exception:
                pass
        btts_odds = None
        if self.markets_payload and "btts" in self.markets_payload:
            btts = self.markets_payload["btts"] or {}
            btts_odds = (btts.get("yes"), btts.get("no"))
        return MatchSnapshot(
            platform=self.platform,
            external_event_id=self.external_event_id,
            home=self.home,
            away=self.away,
            scheduled_at=scheduled_dt,
            odds_1x2=self.odds_1x2,
            odds_btts=btts_odds,
            event_url=self.source_url,
            live_state=None,
            markets=self.markets_payload,
            raw_payload=self.raw_payload,
            extracted_at=self.extracted_at,
        )


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


@dataclass(frozen=True)
class LiveEventSnapshot:
    """One currently in-play event, as reported by a platform's live feed.

    Used by the live-watch poller to detect when a watched fixture goes live.
    """

    platform: str
    external_event_id: str
    home: str
    away: str
    competition_name: str | None = None
    country_name: str | None = None
    minute: str | None = None  # human label, e.g. "12'", "HT", "2ª parte"
    home_score: int | None = None
    away_score: int | None = None
    home_red_cards: int | None = None
    away_red_cards: int | None = None
    home_yellow_cards: int | None = None
    away_yellow_cards: int | None = None
    scheduled_at: str | None = None
    odds_1x2: Odds1X2 | None = None
    # Optional extra markets (same shape as a parsed ActiveEventRecord.markets_json):
    # {"asian_handicap": {...}, "goal_line": {...}, ...}. Populated by the live
    # parsers when the in-play feed exposes them, for richer live alerts.
    markets_payload: dict[str, Any] | None = None
    source_url: str | None = None
    is_soccer: bool = True  # False for eSports football and similar virtual feeds
    extracted_at: str = ""
    live_stats: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_match_snapshot(self) -> MatchSnapshot:
        """Convert this LiveEventSnapshot to a unified MatchSnapshot."""
        from datetime import datetime, timezone
        scheduled_dt = datetime.now(timezone.utc)
        if self.scheduled_at:
            try:
                iso_str = self.scheduled_at
                if iso_str.endswith("Z"):
                    iso_str = iso_str[:-1] + "+00:00"
                scheduled_dt = datetime.fromisoformat(iso_str)
            except Exception:
                pass
        live_state = None
        if self.minute is not None or self.home_score is not None:
            live_state = LiveState(
                minute=self.minute or "0'",
                home_score=self.home_score if self.home_score is not None else 0,
                away_score=self.away_score if self.away_score is not None else 0,
                home_red_cards=self.home_red_cards if self.home_red_cards is not None else 0,
                away_red_cards=self.away_red_cards if self.away_red_cards is not None else 0,
                yellow_cards={
                    "home": self.home_yellow_cards or 0,
                    "away": self.away_yellow_cards or 0,
                } if (self.home_yellow_cards or self.away_yellow_cards) else None,
            )
        return MatchSnapshot(
            platform=self.platform,
            external_event_id=self.external_event_id,
            home=self.home,
            away=self.away,
            scheduled_at=scheduled_dt,
            odds_1x2=self.odds_1x2 or Odds1X2(None, None, None),
            odds_btts=None,
            event_url=self.source_url,
            live_state=live_state,
            markets=self.markets_payload,
            raw_payload=self.raw_payload,
            extracted_at=self.extracted_at or utc_now_iso(),
        )


@dataclass(frozen=True)
class LiveState:
    """Represent the real-time state of an ongoing (in-play) match."""

    minute: str
    home_score: int
    away_score: int
    home_red_cards: int
    away_red_cards: int
    yellow_cards: dict[str, int] | None = None
    goal_scorers: list[str] | None = None  # List of player names who scored

@dataclass(frozen=True)
class MatchSnapshot:
    """The unified canonical model representing a football match snapshot."""

    platform: str
    external_event_id: str
    home: str
    away: str
    scheduled_at: datetime
    odds_1x2: Odds1X2
    odds_btts: tuple[float | None, float | None] | None = None  # (btts_yes, btts_no)
    event_url: str | None = None
    live_state: LiveState | None = None
    markets: dict[str, Any] | None = None  # AH, O/U and other secondary markets
    raw_payload: dict[str, Any] | None = None
    extracted_at: str = field(default_factory=utc_now_iso)



__all__ = [
    "CompetitionExtraction",
    "CompetitionKey",
    "EventKey",
    "EventSnapshot",
    "LiveEventSnapshot",
    "Odds1X2",
    "PlatformDescriptor",
    "ProviderCapabilities",
    "LiveState",
    "MatchSnapshot",
    "platform_display_name",
    "utc_now_iso",
]
