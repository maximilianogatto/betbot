"""Generic repository facade over the current SQLite tracking storage.

The underlying SQLite schema is still implemented in `storage.bet365_tracking`
for backwards compatibility, but the rest of the application can now depend on
generic repository concepts such as competition, event, subscription, baseline,
and small change.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from storage import bet365_tracking as legacy


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


@dataclass(frozen=True)
class TrackedCompetition:
    """Represent one globally tracked competition."""

    id: int
    platform: str
    source_url: str
    competition_external_id: str
    competition_name: str
    needs_name_resolution: bool
    enabled: bool
    last_synced_at: str | None
    created_at: str
    updated_at: str

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

    tracked_competition_id: int
    external_event_id: str
    home: str
    away: str
    scheduled_label_date: str | None
    scheduled_label_time: str | None
    scheduled_at: str | None
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    alerted: bool
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


@dataclass(frozen=True)
class EventBaseline:
    """Represent one odds baseline for a chat and active event."""

    telegram_chat_id: int
    tracked_competition_id: int
    external_event_id: str
    baseline_home: float | None
    baseline_draw: float | None
    baseline_away: float | None
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
    tracked_competition_id: int
    external_event_id: str
    competition_name: str
    home: str
    away: str
    scheduled_label_date: str | None
    scheduled_label_time: str | None
    baseline_home: float | None
    baseline_draw: float | None
    baseline_away: float | None
    current_home: float | None
    current_draw: float | None
    current_away: float | None
    max_percent_change: float
    status: str
    created_at: str
    updated_at: str

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


class SqliteTrackingRepository:
    """Generic repository backed by the current SQLite implementation."""

    def create_pending_competition_request(
        self,
        chat_id: int,
        *,
        platform: str,
        source_url: str,
        competition_external_id: str,
        competition_name: str,
        requires_empty_confirmation: bool = False,
        needs_name_resolution: bool = False,
        payload: dict | None = None,
        expires_at: str | None = None,
    ) -> PendingCompetitionTrackRequest:
        pending = legacy.create_pending_track_request(
            chat_id,
            platform,
            source_url,
            extracted_metadata={
                "topic": competition_external_id,
                "league_name": competition_name,
                "url": source_url,
                "platform": platform,
                "payload": payload or {},
            },
            requires_empty_confirmation=requires_empty_confirmation,
            needs_name_resolution=needs_name_resolution,
            expires_at=expires_at,
        )
        return _map_pending_request(pending)

    def get_latest_pending_competition_request(
        self,
        chat_id: int,
    ) -> PendingCompetitionTrackRequest | None:
        pending = legacy.get_latest_pending_track_request(chat_id)
        return _map_pending_request(pending) if pending is not None else None

    def delete_pending_competition_request(self, chat_id: int) -> bool:
        return legacy.delete_pending_track_request(chat_id)

    def confirm_pending_competition_request(
        self,
        chat_id: int,
    ) -> ConfirmedCompetitionTrackRequest | None:
        confirmed = legacy.confirm_pending_track_request(chat_id)
        return _map_confirmed_track_request(confirmed) if confirmed is not None else None

    def list_tracked_competitions(self, chat_id: int) -> list[TrackedCompetitionSubscription]:
        return [_map_tracked_competition_subscription(item) for item in legacy.list_tracked_leagues(chat_id)]

    def list_globally_active_competitions(self) -> list[TrackedCompetition]:
        return [_map_tracked_competition(item) for item in legacy.list_globally_active_leagues()]

    def get_subscriptions_for_competition(
        self,
        tracked_competition_id: int,
        *,
        only_enabled: bool = True,
    ) -> list[CompetitionSubscription]:
        return [
            _map_subscription(item)
            for item in legacy.get_subscriptions_for_league(
                tracked_competition_id,
                only_enabled=only_enabled,
            )
        ]

    def get_tracked_competition(self, tracked_competition_id: int) -> TrackedCompetition | None:
        tracked = legacy.get_tracked_league(tracked_competition_id)
        return _map_tracked_competition(tracked) if tracked is not None else None

    def get_tracked_competition_subscription(
        self,
        chat_id: int,
        tracked_competition_id: int,
    ) -> TrackedCompetitionSubscription | None:
        tracked = legacy.get_tracked_league_subscription(chat_id, tracked_competition_id)
        return _map_tracked_competition_subscription(tracked) if tracked is not None else None

    def set_odds_notifications(
        self,
        chat_id: int,
        tracked_competition_id: int,
        enabled: bool,
    ) -> CompetitionSubscription:
        return _map_subscription(
            legacy.set_odds_notifications(chat_id, tracked_competition_id, enabled)
        )

    def set_change_percent_threshold(
        self,
        chat_id: int,
        tracked_competition_id: int,
        percent: float,
    ) -> CompetitionSubscription:
        return _map_subscription(
            legacy.set_change_percent_threshold(chat_id, tracked_competition_id, percent)
        )

    def initialize_event_baselines(
        self,
        chat_id: int,
        tracked_competition_id: int,
        events: Sequence[ActiveEventRecord],
    ) -> int:
        return legacy.initialize_match_baselines(
            chat_id,
            tracked_competition_id,
            [_to_legacy_active_event_record(event) for event in events],
        )

    def get_event_baseline(
        self,
        chat_id: int,
        tracked_competition_id: int,
        external_event_id: str,
    ) -> EventBaseline | None:
        baseline = legacy.get_match_baseline(chat_id, tracked_competition_id, external_event_id)
        return _map_event_baseline(baseline) if baseline is not None else None

    def upsert_event_baseline(
        self,
        chat_id: int,
        tracked_competition_id: int,
        external_event_id: str,
        *,
        baseline_home: float | None,
        baseline_draw: float | None,
        baseline_away: float | None,
    ) -> EventBaseline:
        baseline = legacy.upsert_match_baseline(
            chat_id,
            tracked_competition_id,
            external_event_id,
            baseline_home=baseline_home,
            baseline_draw=baseline_draw,
            baseline_away=baseline_away,
        )
        return _map_event_baseline(baseline)

    def upsert_small_change(
        self,
        chat_id: int,
        tracked_competition_id: int,
        external_event_id: str,
        *,
        home: str,
        away: str,
        scheduled_label_date: str | None,
        scheduled_label_time: str | None,
        baseline_home: float | None,
        baseline_draw: float | None,
        baseline_away: float | None,
        current_home: float | None,
        current_draw: float | None,
        current_away: float | None,
        max_percent_change: float,
        status: str = "pending",
    ) -> SmallChangeRecord:
        return _map_small_change_record(
            legacy.upsert_little_change(
                chat_id,
                tracked_competition_id,
                external_event_id,
                home=home,
                away=away,
                kickoff_label_date=scheduled_label_date,
                kickoff_label_time=scheduled_label_time,
                baseline_home=baseline_home,
                baseline_draw=baseline_draw,
                baseline_away=baseline_away,
                current_home=current_home,
                current_draw=current_draw,
                current_away=current_away,
                max_percent_change=max_percent_change,
                status=status,
            )
        )

    def list_pending_small_changes(self, chat_id: int) -> list[SmallChangeRecord]:
        return [_map_small_change_record(item) for item in legacy.list_pending_little_changes(chat_id)]

    def confirm_small_change(self, chat_id: int, small_change_id: int) -> SmallChangeRecord:
        return _map_small_change_record(legacy.confirm_little_change(chat_id, small_change_id))

    def confirm_all_small_changes(self, chat_id: int) -> list[SmallChangeRecord]:
        return [_map_small_change_record(item) for item in legacy.confirm_all_little_changes(chat_id)]

    def resolve_small_change_with_current_baseline(
        self,
        chat_id: int,
        tracked_competition_id: int,
        external_event_id: str,
    ) -> None:
        legacy.resolve_little_change_with_current_baseline(
            chat_id,
            tracked_competition_id,
            external_event_id,
        )

    def remove_tracked_competition_subscription(
        self,
        chat_id: int,
        tracked_competition_id: int,
    ) -> UntrackCompetitionResult:
        return _map_untrack_result(
            legacy.remove_tracked_league_subscription(chat_id, tracked_competition_id)
        )

    def update_tracked_competition(
        self,
        tracked_competition_id: int,
        *,
        source_url: str,
        competition_external_id: str,
        competition_name: str | None,
        needs_name_resolution: bool | None = None,
        last_synced_at: str | None = None,
        enabled: bool | None = None,
    ) -> TrackedCompetition:
        return _map_tracked_competition(
            legacy.update_tracked_league(
                tracked_competition_id,
                url=source_url,
                topic=competition_external_id,
                league_name=competition_name,
                needs_name_resolution=needs_name_resolution,
                last_scraped_at=last_synced_at,
                enabled=enabled,
            )
        )

    def upsert_active_events(
        self,
        tracked_competition_id: int,
        events: Sequence[ActiveEventUpsert],
    ) -> int:
        return legacy.upsert_active_matches(
            tracked_competition_id,
            [_to_legacy_active_event_upsert(event) for event in events],
        )

    def remove_missing_events(
        self,
        tracked_competition_id: int,
        current_event_ids: Iterable[str],
    ) -> int:
        return legacy.remove_missing_matches(tracked_competition_id, current_event_ids)

    def remove_past_events(
        self,
        tracked_competition_id: int,
        reference_time: str | None = None,
    ) -> int:
        return legacy.remove_past_matches(tracked_competition_id, reference_time)

    def get_active_events(
        self,
        tracked_competition_id: int,
        *,
        only_future: bool = True,
    ) -> list[ActiveEventRecord]:
        return [
            _map_active_event_record(item)
            for item in legacy.get_active_matches(
                tracked_competition_id,
                only_future=only_future,
            )
        ]

    def mark_events_alerted(
        self,
        tracked_competition_id: int,
        external_event_ids: Iterable[str],
    ) -> int:
        return legacy.mark_matches_alerted(tracked_competition_id, external_event_ids)

    def sanitize_tracking_state(self) -> None:
        legacy.sanitize_tracking_state()


def _map_pending_request(
    pending: legacy.PendingTrackRequest,
) -> PendingCompetitionTrackRequest:
    return PendingCompetitionTrackRequest(
        id=pending.id,
        telegram_chat_id=pending.telegram_chat_id,
        platform=pending.platform,
        source_url=pending.url,
        competition_external_id=pending.topic,
        competition_name=pending.league_name,
        requires_empty_confirmation=pending.requires_empty_confirmation,
        needs_name_resolution=pending.needs_name_resolution,
        payload_json=pending.payload_json,
        created_at=pending.created_at,
        expires_at=pending.expires_at,
    )


def _map_tracked_competition(
    tracked: legacy.TrackedLeague,
) -> TrackedCompetition:
    return TrackedCompetition(
        id=tracked.id,
        platform=tracked.platform,
        source_url=tracked.url,
        competition_external_id=tracked.topic,
        competition_name=tracked.league_name,
        needs_name_resolution=tracked.needs_name_resolution,
        enabled=tracked.enabled,
        last_synced_at=tracked.last_scraped_at,
        created_at=tracked.created_at,
        updated_at=tracked.updated_at,
    )


def _map_subscription(
    subscription: legacy.LeagueSubscription,
) -> CompetitionSubscription:
    return CompetitionSubscription(
        telegram_chat_id=subscription.telegram_chat_id,
        tracked_competition_id=subscription.tracked_league_id,
        notify_new_events=subscription.notify_new_matches,
        notify_odds_changes=subscription.notify_odds_changes,
        change_percent_threshold=subscription.change_percent_threshold,
        enabled=subscription.enabled,
        created_at=subscription.created_at,
        updated_at=subscription.updated_at,
    )


def _map_tracked_competition_subscription(
    tracked: legacy.TrackedLeagueSubscription,
) -> TrackedCompetitionSubscription:
    return TrackedCompetitionSubscription(
        tracked_competition=_map_tracked_competition(tracked.tracked_league),
        subscription=_map_subscription(tracked.subscription),
    )


def _map_confirmed_track_request(
    confirmed: legacy.ConfirmedTrackRequest,
) -> ConfirmedCompetitionTrackRequest:
    return ConfirmedCompetitionTrackRequest(
        pending_request=_map_pending_request(confirmed.pending_request),
        tracked_competition=_map_tracked_competition(confirmed.tracked_league),
        subscription=_map_subscription(confirmed.subscription),
    )


def _map_untrack_result(
    result: legacy.UntrackResult,
) -> UntrackCompetitionResult:
    return UntrackCompetitionResult(
        tracked_competition=_map_tracked_competition(result.tracked_league),
        removed_subscription=result.removed_subscription,
        competition_disabled=result.league_disabled,
        removed_active_events=result.removed_active_matches,
        remaining_enabled_subscriptions=result.remaining_enabled_subscriptions,
    )


def _map_active_event_record(
    record: legacy.ActiveMatchRecord,
) -> ActiveEventRecord:
    return ActiveEventRecord(
        tracked_competition_id=record.tracked_league_id,
        external_event_id=record.fixture_id,
        home=record.home,
        away=record.away,
        scheduled_label_date=record.kickoff_label_date,
        scheduled_label_time=record.kickoff_label_time,
        scheduled_at=record.kickoff_at,
        odds_home=record.odds_home,
        odds_draw=record.odds_draw,
        odds_away=record.odds_away,
        alerted=record.alerted,
        last_seen_at=record.last_seen_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_legacy_active_event_record(
    record: ActiveEventRecord,
) -> legacy.ActiveMatchRecord:
    return legacy.ActiveMatchRecord(
        tracked_league_id=record.tracked_competition_id,
        fixture_id=record.external_event_id,
        home=record.home,
        away=record.away,
        kickoff_label_date=record.scheduled_label_date,
        kickoff_label_time=record.scheduled_label_time,
        kickoff_at=record.scheduled_at,
        odds_home=record.odds_home,
        odds_draw=record.odds_draw,
        odds_away=record.odds_away,
        alerted=record.alerted,
        last_seen_at=record.last_seen_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_legacy_active_event_upsert(
    upsert: ActiveEventUpsert,
) -> legacy.ActiveMatchUpsert:
    return legacy.ActiveMatchUpsert(
        fixture_id=upsert.external_event_id,
        home=upsert.home,
        away=upsert.away,
        kickoff_label_date=upsert.scheduled_label_date,
        kickoff_label_time=upsert.scheduled_label_time,
        kickoff_at=upsert.scheduled_at,
        odds_home=upsert.odds_home,
        odds_draw=upsert.odds_draw,
        odds_away=upsert.odds_away,
    )


def _map_event_baseline(
    baseline: legacy.MatchBaseline,
) -> EventBaseline:
    return EventBaseline(
        telegram_chat_id=baseline.telegram_chat_id,
        tracked_competition_id=baseline.tracked_league_id,
        external_event_id=baseline.fixture_id,
        baseline_home=baseline.baseline_home,
        baseline_draw=baseline.baseline_draw,
        baseline_away=baseline.baseline_away,
        updated_at=baseline.updated_at,
    )


def _map_small_change_record(
    record: legacy.LittleChangeRecord,
) -> SmallChangeRecord:
    return SmallChangeRecord(
        id=record.id,
        telegram_chat_id=record.telegram_chat_id,
        tracked_competition_id=record.tracked_league_id,
        external_event_id=record.fixture_id,
        competition_name=record.league_name,
        home=record.home,
        away=record.away,
        scheduled_label_date=record.kickoff_label_date,
        scheduled_label_time=record.kickoff_label_time,
        baseline_home=record.baseline_home,
        baseline_draw=record.baseline_draw,
        baseline_away=record.baseline_away,
        current_home=record.current_home,
        current_draw=record.current_draw,
        current_away=record.current_away,
        max_percent_change=record.max_percent_change,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


tracking_repository = SqliteTrackingRepository()


__all__ = [
    "ActiveEventRecord",
    "ActiveEventUpsert",
    "CompetitionSubscription",
    "ConfirmedCompetitionTrackRequest",
    "EventBaseline",
    "PendingCompetitionTrackRequest",
    "SmallChangeRecord",
    "SqliteTrackingRepository",
    "TrackedCompetition",
    "TrackedCompetitionSubscription",
    "UntrackCompetitionResult",
    "tracking_repository",
]
