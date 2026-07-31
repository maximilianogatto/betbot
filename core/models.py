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
import json


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO format."""

    return datetime.now(timezone.utc).isoformat()


def platform_display_name(platform_key: str) -> str:
    """Return a friendly display name for one platform key."""

    normalized_key = platform_key.strip().lower()

    if not normalized_key:
        return "Desconocida"

    # Drop the internal "_http" transport suffix; users don't care how the bot
    # fetches data ("bz_http" -> "Bz", not "Bz Http").
    if normalized_key.endswith("_http"):
        normalized_key = normalized_key[: -len("_http")]

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




def _loads_json_object(raw_value: Any) -> dict[str, Any]:
    normalized = (str(raw_value).strip() if raw_value is not None else "")
    if not normalized:
        return {}
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


@dataclass(frozen=True)
class LiveWatchEntry:
    """One fixture the user wants to be alerted about when it goes live."""

    id: int
    chat_id: int
    home: str
    away: str
    league_hint: str | None
    note: str | None
    status: str  # 'watching' | 'fired'
    matched_platform: str | None
    matched_event_id: str | None
    matched_minute: str | None
    created_at: str
    fired_at: str | None
    kickoff_at: str | None = None
    prematch_seen_at: str | None = None
    prematch_platform: str | None = None
    fired_platforms: str | None = None
    prematch_fired_platforms: str | None = None
    countdown_fired_at: str | None = None
    chat_local_id: int | None = None
    live_state_json: str | None = None
    status_flags: int = 1
    fired_odds_mask: int = 0
    fired_stats_mask: int = 0

    @property
    def fired_platforms_list(self) -> list[str]:
        if not self.fired_platforms:
            return []
        return [p.strip() for p in self.fired_platforms.split(",") if p.strip()]

    @property
    def prematch_fired_platforms_list(self) -> list[str]:
        if not self.prematch_fired_platforms:
            return []
        return [p.strip() for p in self.prematch_fired_platforms.split(",") if p.strip()]

    @property
    def live_state(self) -> dict[str, Any]:
        """Return last observed live state keyed by platform."""
        return _loads_json_object(self.live_state_json)


@dataclass(frozen=True)
class LiveWatchSettings:
    """Per-chat switches for high-frequency live-watch alerts."""

    chat_id: int
    alert_goals: bool = True
    alert_red_cards: bool = True
    alert_yellow_cards: bool = False


@dataclass(frozen=True)
class PendingCompetitionTrackRequest:
    """Represent one unresolved track request for a Telegram chat."""

    id: int
    telegram_chat_id: int
    platform: str
    source_url: str
    competition_external_id: str
    competition_name: str
    requires_empty_confirmation: bool
    needs_name_resolution: bool
    payload_json: str | None
    created_at: str
    expires_at: str | None

    @property
    def url(self) -> str:
        return self.source_url

    @property
    def topic(self) -> str:
        return self.competition_external_id

    @property
    def league_name(self) -> str:
        return self.competition_name

    @property
    def platform_display_name(self) -> str:
        return platform_display_name(self.platform)


@dataclass(frozen=True)
class TrackedCompetition:
    """Represent one globally tracked competition."""

    id: int
    platform: str
    source_url: str
    competition_external_id: str
    competition_name: str
    metadata_json: str | None
    needs_name_resolution: bool
    enabled: bool
    last_synced_at: str | None
    consecutive_unavailable_refreshes: int
    last_unavailable_refresh_at: str | None
    last_unavailable_reason: str | None
    last_unavailable_notification_at: str | None
    created_at: str
    updated_at: str
    unified_competition_id: int | None = None

    @property
    def url(self) -> str:
        return self.source_url

    @property
    def topic(self) -> str:
        return self.competition_external_id

    @property
    def league_name(self) -> str:
        return self.competition_name

    @property
    def last_scraped_at(self) -> str | None:
        return self.last_synced_at

    @property
    def platform_display_name(self) -> str:
        return platform_display_name(self.platform)

    @property
    def tracked_competition(self) -> TrackedCompetition:
        return self

    @property
    def tracked_league(self) -> TrackedCompetition:
        return self

    @property
    def subscription(self) -> CompetitionSubscription:
        return CompetitionSubscription(
            telegram_chat_id=0,
            tracked_competition_id=self.id,
            notify_new_events=True,
            notify_odds_changes=True,
            change_percent_threshold=20.0,
            enabled=True,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @property
    def subscription_created(self) -> bool:
        return True


@dataclass(frozen=True)
class CompetitionSubscription:
    """Represent one chat subscription to a tracked competition."""

    telegram_chat_id: int
    tracked_competition_id: int
    notify_new_events: bool
    notify_odds_changes: bool
    change_percent_threshold: float
    enabled: bool
    created_at: str
    updated_at: str

    @property
    def tracked_league_id(self) -> int:
        return self.tracked_competition_id

    @property
    def notify_new_matches(self) -> bool:
        return self.notify_new_events


@dataclass(frozen=True)
class TrackedCompetitionSubscription:
    """Combine tracked competition metadata with chat-specific flags."""

    tracked_competition: TrackedCompetition
    subscription: CompetitionSubscription

    @property
    def tracked_league(self) -> TrackedCompetition:
        return self.tracked_competition


@dataclass(frozen=True)
class ConfirmedCompetitionTrackRequest:
    """Describe the result of confirming a pending track request."""

    pending_request: PendingCompetitionTrackRequest
    tracked_competition: TrackedCompetition
    subscription: CompetitionSubscription
    subscription_created: bool

    @property
    def tracked_league(self) -> TrackedCompetition:
        return self.tracked_competition


@dataclass(frozen=True)
class UntrackCompetitionResult:
    """Describe what happened after unsubscribing from a competition."""

    tracked_competition: TrackedCompetition
    removed_subscription: bool
    competition_disabled: bool
    removed_active_events: int
    remaining_enabled_subscriptions: int

    @property
    def tracked_league(self) -> TrackedCompetition:
        return self.tracked_competition

    @property
    def league_disabled(self) -> bool:
        return self.competition_disabled

    @property
    def removed_active_matches(self) -> int:
        return self.removed_active_events


@dataclass(frozen=True)
class ActiveEventUpsert:
    """Represent one active event before it is persisted."""

    external_event_id: str
    home: str
    away: str
    scheduled_label_date: str | None
    scheduled_label_time: str | None
    scheduled_at: str | None
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    event_url: str | None = None
    markets_payload: dict[str, Any] | None = None
    raw_payload: dict[str, Any] | None = None

    @property
    def fixture_id(self) -> str:
        return self.external_event_id

    @property
    def kickoff_label_date(self) -> str | None:
        return self.scheduled_label_date

    @property
    def kickoff_label_time(self) -> str | None:
        return self.scheduled_label_time

    @property
    def kickoff_at(self) -> str | None:
        return self.scheduled_at


@dataclass(frozen=True)
class ActiveEventRecord:
    """Represent one currently stored active event row."""

    id: int
    tracked_competition_id: int
    platform: str
    competition_external_id: str
    external_event_id: str
    home: str
    away: str
    scheduled_label_date: str | None
    scheduled_label_time: str | None
    scheduled_at: str | None
    event_url: str | None
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    markets_json: str | None
    raw_payload_json: str | None
    alerted: bool
    is_active: bool
    first_seen_at: str
    last_seen_at: str
    created_at: str
    updated_at: str

    @property
    def tracked_league_id(self) -> int:
        return self.tracked_competition_id

    @property
    def fixture_id(self) -> str:
        return self.external_event_id

    @property
    def kickoff_label_date(self) -> str | None:
        return self.scheduled_label_date

    @property
    def kickoff_label_time(self) -> str | None:
        return self.scheduled_label_time

    @property
    def kickoff_at(self) -> str | None:
        return self.scheduled_at

    @property
    def stats_url(self) -> str | None:
        normalized_payload = (self.raw_payload_json or "").strip()
        if not normalized_payload:
            return None
        try:
            payload = json.loads(normalized_payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        stats_url = payload.get("stats_url")
        return stats_url.strip() if isinstance(stats_url, str) and stats_url.strip() else None

    @property
    def missing_seen_count(self) -> int:
        normalized_payload = (self.raw_payload_json or "").strip()
        if not normalized_payload:
            return 0
        try:
            payload = json.loads(normalized_payload)
        except json.JSONDecodeError:
            return 0
        if not isinstance(payload, dict):
            return 0
        raw_value = payload.get("missing_seen_count")
        if isinstance(raw_value, int):
            return max(0, raw_value)
        if isinstance(raw_value, str) and raw_value.isdigit():
            return int(raw_value)
        return 0

    @property
    def is_missing(self) -> bool:
        return self.missing_seen_count > 0


@dataclass(frozen=True)
class StatsLeagueLink:
    """Link one tracked odds competition to one stats provider league."""

    id: int
    tracked_competition_id: int
    stats_provider: str
    stats_league_id: str
    stats_league_name: str
    stats_country_name: str | None
    confidence: float
    payload_json: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StatsLeagueSubscription:
    """Track one provider-native stats league independently from sportsbook odds."""

    telegram_chat_id: int
    stats_provider: str
    stats_league_id: str
    stats_league_name: str
    stats_country_name: str | None
    source_url: str | None
    payload_json: str | None
    enabled: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class StatsMatchLinkRecord:
    """Cache one resolved odds event -> stats provider match identity."""

    id: int
    active_event_id: int
    stats_provider: str
    stats_match_id: str
    stats_url: str | None
    confidence: float
    method: str
    payload_json: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class EventBaseline:
    """Represent one odds baseline for a chat and active event."""

    telegram_chat_id: int
    active_event_id: int
    tracked_competition_id: int
    external_event_id: str
    baseline_home: float | None
    baseline_draw: float | None
    baseline_away: float | None
    baseline_markets_json: str | None
    baseline_set_at: str
    updated_at: str

    @property
    def tracked_league_id(self) -> int:
        return self.tracked_competition_id

    @property
    def fixture_id(self) -> str:
        return self.external_event_id


@dataclass(frozen=True)
class SmallChangeRecord:
    """Represent one pending or processed small odds change."""

    id: int
    telegram_chat_id: int
    active_event_id: int
    tracked_competition_id: int
    external_event_id: str
    competition_name: str
    home: str
    away: str
    scheduled_label_date: str | None
    scheduled_label_time: str | None
    scheduled_at: str | None
    baseline_home: float | None
    baseline_draw: float | None
    baseline_away: float | None
    current_home: float | None
    current_draw: float | None
    current_away: float | None
    max_percent_change: float
    payload_json: str | None
    status: str
    created_at: str
    updated_at: str
    confirmed_at: str | None
    dismissed_at: str | None

    @property
    def tracked_league_id(self) -> int:
        return self.tracked_competition_id

    @property
    def fixture_id(self) -> str:
        return self.external_event_id

    @property
    def league_name(self) -> str:
        return self.competition_name

    @property
    def kickoff_label_date(self) -> str | None:
        return self.scheduled_label_date

    @property
    def kickoff_label_time(self) -> str | None:
        return self.scheduled_label_time


@dataclass(frozen=True)
class LeagueDiscoveryOption:
    """Represent one platform-native league that can be tracked without pasting a URL."""

    platform: str
    platform_display_name: str
    country_id: str | None
    country_name: str
    league_id: str
    league_name: str
    source_url: str
    games_count: int | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class MatchResult:
    """Cómo terminó un partido, con los indicadores que explican el resultado.

    Es el registro histórico sobre el que después se corren análisis: por eso se
    guarda el payload crudo del provider además de las columnas normalizadas
    (normalizar entre 6 providers es la parte difícil, y el crudo evita perder
    datos que hoy no sabemos que vamos a querer).

    `status` distingue FINISHED de SUSPENDED/POSTPONED a propósito: un partido
    suspendido guardado como 0-0 envenena cualquier análisis posterior.
    """

    # Identidad
    home: str
    away: str
    status: str  # FINISHED | SUSPENDED | POSTPONED | UNKNOWN
    source: str  # live_watch | manual | tracking
    recorded_at: str
    id: int | None = None
    platform: str | None = None
    external_event_id: str | None = None
    unified_competition_id: int | None = None
    competition_name: str | None = None
    country_name: str | None = None
    kickoff_at: str | None = None
    actual_start_at: str | None = None

    # Nivel 1: sin esto no se puede evaluar nada
    final_home_score: int | None = None
    final_away_score: int | None = None
    ht_home_score: int | None = None
    ht_away_score: int | None = None

    # Nivel 2: los que explican el resultado
    xg_home: float | None = None
    xg_away: float | None = None
    shots_on_target_home: int | None = None
    shots_on_target_away: int | None = None
    red_cards_home: int | None = None
    red_cards_away: int | None = None
    goal_minutes_json: str | None = None      # [{"minute": 23, "team": "home"}, ...]
    red_card_minutes_json: str | None = None

    # Trazabilidad
    stats_provider: str | None = None
    stats_match_id: str | None = None
    raw_payload_json: str | None = None       # crudo del provider (nivel 3 vive acá)
    updated_at: str | None = None

    @property
    def is_settled(self) -> bool:
        """True sólo si el partido terminó y tiene marcador utilizable."""

        return (
            self.status == "FINISHED"
            and self.final_home_score is not None
            and self.final_away_score is not None
        )


@dataclass(frozen=True)
class LiveWatchHit:
    """Una entrada vigilada que acaba de coincidir con un evento.

    Vive en core (y no en services/live_watch.py, donde nació) porque
    `MatchLiveEvent` lo transporta: el core no puede importar desde services.
    """

    entry: LiveWatchEntry
    event: LiveEventSnapshot | None = None
    score: float = 0.0
    phase: str = "live"  # "live" | "pre" | "countdown" | "goal" | "red_card" | "yellow_card"
    custom_message: str | None = None


__all__ = [
    "CompetitionExtraction",
    "CompetitionKey",
    "LiveWatchHit",
    "MatchResult",
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
    "LiveWatchEntry",
    "LiveWatchSettings",
    "PendingCompetitionTrackRequest",
    "TrackedCompetition",
    "CompetitionSubscription",
    "TrackedCompetitionSubscription",
    "ConfirmedCompetitionTrackRequest",
    "UntrackCompetitionResult",
    "ActiveEventUpsert",
    "ActiveEventRecord",
    "StatsLeagueLink",
    "StatsLeagueSubscription",
    "StatsMatchLinkRecord",
    "EventBaseline",
    "SmallChangeRecord",
    "LeagueDiscoveryOption",
]
