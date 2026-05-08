"""Generic SQLite repository for platform/competition/event tracking.

This repository is the main persistence layer for the current bot. It stores:

- pending competition tracking requests per chat
- globally tracked competitions shared across chats
- per-chat subscriptions and thresholds
- global active events plus current odds
- per-chat baselines and small changes
- sent alerts to avoid duplicates

The schema is platform-agnostic so a future extractor can plug into the same
tables by providing `platform`, `competition_external_id`, and
`external_event_id`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
from typing import Any

from core.models import platform_display_name
from storage.mappers import (
    json_dumps as _json_dumps,
    row_to_active_event_record as _row_to_active_event_record,
    row_to_event_baseline as _row_to_event_baseline,
    row_to_pending_request as _row_to_pending_request,
    row_to_small_change_record as _row_to_small_change_record,
    row_to_subscription as _row_to_subscription,
    row_to_tracked_competition as _row_to_tracked_competition,
    row_to_tracked_competition_subscription as _row_to_tracked_competition_subscription,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_FILE_PATH = DATA_DIR / "tracking.sqlite3"
DEFAULT_CHANGE_THRESHOLD_PERCENT = 20.0
DEFAULT_NOTIFY_ODDS_CHANGES = True


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

    @property
    def platform_display_name(self) -> str:
        return platform_display_name(self.platform)


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
    baseline_markets_json: str | None # for others markets
    baseline_set_at: str
    updated_at: str

    @property
    def tracked_league_id(self) -> int:
        return self.tracked_competition_id

    @property
    def fixture_id(self) -> str:    #identifier for the event (depends on the platform)
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


class SqliteTrackingRepository:
    """Generic repository backed by a platform-neutral SQLite schema."""

    def __init__(
        self,
        *,
        default_change_threshold_percent: float = DEFAULT_CHANGE_THRESHOLD_PERCENT,
        default_notify_odds_changes: bool = DEFAULT_NOTIFY_ODDS_CHANGES,
    ) -> None:
        self.default_change_threshold_percent = float(default_change_threshold_percent)
        self.default_notify_odds_changes = bool(default_notify_odds_changes)

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
        payload: dict[str, Any] | None = None,
        expires_at: str | None = None,
    ) -> PendingCompetitionTrackRequest:
        """Store a new pending competition request for one Telegram chat."""

        normalized_platform = _normalize_platform(platform)
        normalized_url = _normalize_url(source_url)
        normalized_competition_id = competition_external_id.strip()
        normalized_name = competition_name.strip()

        if not normalized_competition_id:
            raise ValueError("competition_external_id must not be empty.")
        if _is_invalid_label(normalized_name):
            raise ValueError("competition_name must not be empty.")

        payload_json = _json_dumps(payload)
        created_at = _utc_now_iso()

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            connection.execute(     # delete old pending tracks
                """
                DELETE FROM pending_track_requests
                WHERE telegram_chat_id = ?
                """,
                (chat_id,),
            )
            cursor = connection.execute(    # create a new pending tracks
                """
                INSERT INTO pending_track_requests (
                    telegram_chat_id,
                    platform,
                    source_url,
                    competition_external_id,
                    competition_name,
                    requires_empty_confirmation,
                    needs_name_resolution,
                    payload_json,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    normalized_platform,
                    normalized_url,
                    normalized_competition_id,
                    normalized_name,
                    int(requires_empty_confirmation),
                    int(needs_name_resolution),
                    payload_json,
                    created_at,
                    _normalize_optional_text(expires_at),
                ),
            )
            row = connection.execute(
                """
                SELECT
                    id,
                    telegram_chat_id,
                    platform,
                    source_url,
                    competition_external_id,
                    competition_name,
                    requires_empty_confirmation,
                    needs_name_resolution,
                    payload_json,
                    created_at,
                    expires_at
                FROM pending_track_requests
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()

        if row is None:
            raise RuntimeError("Pending competition request was inserted but could not be reloaded.")

        return _row_to_pending_request(row)

    def get_latest_pending_competition_request(
        self,
        chat_id: int,
    ) -> PendingCompetitionTrackRequest | None:
        """Load the latest pending competition request for one Telegram chat."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            row = _fetch_pending_request_row(connection, chat_id)

        return _row_to_pending_request(row) if row is not None else None

    def delete_pending_competition_request(self, chat_id: int) -> bool:
        """Delete the latest pending competition request for one Telegram chat."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            cursor = connection.execute(
                """
                DELETE FROM pending_track_requests
                WHERE telegram_chat_id = ?
                """,
                (chat_id,),
            )

        return cursor.rowcount > 0

    def confirm_pending_competition_request(
        self,
        chat_id: int,
    ) -> ConfirmedCompetitionTrackRequest | None:
        """Confirm the latest pending request and create or reuse the subscription."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            pending_row = _fetch_pending_request_row(connection, chat_id)

            if pending_row is None:
                return None

            pending_request = _row_to_pending_request(pending_row)
            tracked_row = _fetch_tracked_competition_by_identity_row(
                connection,
                pending_request.platform,
                pending_request.competition_external_id,
            )
            now_iso = _utc_now_iso()
            subscription_created = False

            if tracked_row is None:
                cursor = connection.execute(
                    """
                    INSERT INTO tracked_competitions (
                        platform,
                        competition_external_id,
                        competition_name,
                        source_url,
                        metadata_json,
                        needs_name_resolution,
                        enabled,
                        last_refreshed_at,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1, NULL, ?, ?)
                    """,
                    (
                        pending_request.platform,
                        pending_request.competition_external_id,
                        pending_request.competition_name,
                        pending_request.source_url,
                        pending_request.payload_json,
                        int(pending_request.needs_name_resolution),
                        now_iso,
                        now_iso,
                    ),
                )
                tracked_competition_id = int(cursor.lastrowid)
            else:
                existing = _row_to_tracked_competition(tracked_row)
                resolved_name, resolved_needs_name_resolution = _resolve_competition_name(
                    existing.competition_name,
                    existing.needs_name_resolution,
                    pending_request.competition_name,
                    pending_request.needs_name_resolution,
                )
                tracked_competition_id = existing.id
                connection.execute(
                    """
                    UPDATE tracked_competitions
                    SET
                        source_url = ?,
                        competition_name = ?,
                        metadata_json = COALESCE(?, metadata_json),
                        needs_name_resolution = ?,
                        enabled = 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        pending_request.source_url,
                        resolved_name,
                        pending_request.payload_json,
                        int(resolved_needs_name_resolution),
                        now_iso,
                        tracked_competition_id,
                    ),
                )

            subscription_row = _fetch_subscription_row(connection, chat_id, tracked_competition_id)
            if subscription_row is None:
                subscription_created = True
                connection.execute(
                    """
                    INSERT INTO competition_subscriptions (
                        telegram_chat_id,
                        tracked_competition_id,
                        notify_new_events,
                        notify_odds_changes,
                        change_threshold_percent,
                        enabled,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, 1, ?, ?, 1, ?, ?)
                    """,
                    (
                        chat_id,
                        tracked_competition_id,
                        int(self.default_notify_odds_changes),
                        self.default_change_threshold_percent,
                        now_iso,
                        now_iso,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE competition_subscriptions
                    SET
                        enabled = 1,
                        updated_at = ?
                    WHERE telegram_chat_id = ? AND tracked_competition_id = ?
                    """,
                    (now_iso, chat_id, tracked_competition_id),
                )

            connection.execute(
                """
                DELETE FROM pending_track_requests
                WHERE id = ?
                """,
                (pending_request.id,),
            )

            tracked_row = _fetch_tracked_competition_row(connection, tracked_competition_id)
            subscription_row = _fetch_subscription_row(connection, chat_id, tracked_competition_id)

        if tracked_row is None or subscription_row is None:
            raise RuntimeError("Competition confirmation succeeded but the stored rows could not be reloaded.")

        return ConfirmedCompetitionTrackRequest(
            pending_request=pending_request,
            tracked_competition=_row_to_tracked_competition(tracked_row),
            subscription=_row_to_subscription(subscription_row),
            subscription_created=subscription_created,
        )

    def list_tracked_competitions(self, chat_id: int) -> list[TrackedCompetitionSubscription]:
        """List enabled tracked competitions for one Telegram chat."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            rows = connection.execute(
                """
                SELECT
                    tc.id AS tracked_competition_id,
                    tc.platform AS tracked_platform,
                    tc.source_url AS tracked_source_url,
                    tc.competition_external_id AS tracked_competition_external_id,
                    tc.competition_name AS tracked_competition_name,
                    tc.metadata_json AS tracked_metadata_json,
                    tc.needs_name_resolution AS tracked_needs_name_resolution,
                    tc.enabled AS tracked_enabled,
                    tc.last_refreshed_at AS tracked_last_refreshed_at,
                    tc.created_at AS tracked_created_at,
                    tc.updated_at AS tracked_updated_at,
                    cs.telegram_chat_id AS subscription_telegram_chat_id,
                    cs.tracked_competition_id AS subscription_tracked_competition_id,
                    cs.notify_new_events AS subscription_notify_new_events,
                    cs.notify_odds_changes AS subscription_notify_odds_changes,
                    cs.change_threshold_percent AS subscription_change_threshold_percent,
                    cs.enabled AS subscription_enabled,
                    cs.created_at AS subscription_created_at,
                    cs.updated_at AS subscription_updated_at
                FROM competition_subscriptions cs
                INNER JOIN tracked_competitions tc ON tc.id = cs.tracked_competition_id
                WHERE cs.telegram_chat_id = ?
                  AND cs.enabled = 1
                  AND tc.enabled = 1
                ORDER BY tc.platform, tc.competition_name, tc.id
                """,
                (chat_id,),
            ).fetchall()

        return [_row_to_tracked_competition_subscription(row) for row in rows]

    def list_globally_active_competitions(self) -> list[TrackedCompetition]:
        """List globally active competitions with at least one enabled subscription."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            rows = connection.execute(
                """
                SELECT
                    tc.id,
                    tc.platform,
                    tc.source_url,
                    tc.competition_external_id,
                    tc.competition_name,
                    tc.metadata_json,
                    tc.needs_name_resolution,
                    tc.enabled,
                    tc.last_refreshed_at,
                    tc.created_at,
                    tc.updated_at
                FROM tracked_competitions tc
                WHERE tc.enabled = 1
                  AND EXISTS (
                      SELECT 1
                      FROM competition_subscriptions cs
                      WHERE cs.tracked_competition_id = tc.id
                        AND cs.enabled = 1
                  )
                ORDER BY tc.platform, tc.competition_name, tc.id
                """
            ).fetchall()

        return [_row_to_tracked_competition(row) for row in rows]

    def get_subscriptions_for_competition(
        self,
        tracked_competition_id: int,
        *,
        only_enabled: bool = True,
    ) -> list[CompetitionSubscription]:
        """Return every chat subscription for one tracked competition."""

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            query = """
                SELECT
                    telegram_chat_id,
                    tracked_competition_id,
                    notify_new_events,
                    notify_odds_changes,
                    change_threshold_percent,
                    enabled,
                    created_at,
                    updated_at
                FROM competition_subscriptions
                WHERE tracked_competition_id = ?
            """
            params: list[int] = [tracked_competition_id]

            if only_enabled:
                query += " AND enabled = 1"

            query += " ORDER BY telegram_chat_id"
            rows = connection.execute(query, params).fetchall()

        return [_row_to_subscription(row) for row in rows]

    def get_tracked_competition(self, tracked_competition_id: int) -> TrackedCompetition | None:
        """Load one tracked competition by its local id."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            row = _fetch_tracked_competition_row(connection, tracked_competition_id)

        return _row_to_tracked_competition(row) if row is not None else None

    def get_tracked_competition_subscription(
        self,
        chat_id: int,
        tracked_competition_id: int,
    ) -> TrackedCompetitionSubscription | None:
        """Load one tracked competition subscription for one Telegram chat."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            row = _fetch_tracked_competition_subscription_row(
                connection,
                chat_id,
                tracked_competition_id,
            )

        return _row_to_tracked_competition_subscription(row) if row is not None else None

    def get_tracked_competition_subscription_by_identity(
        self,
        chat_id: int,
        *,
        platform: str,
        competition_external_id: str,
    ) -> TrackedCompetitionSubscription | None:
        """Load one enabled subscription by platform plus competition identity."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            row = _fetch_tracked_competition_subscription_by_identity_row(
                connection,
                chat_id,
                platform,
                competition_external_id,
            )

        return _row_to_tracked_competition_subscription(row) if row is not None else None

    def set_odds_notifications(
        self,
        chat_id: int,
        tracked_competition_id: int,
        enabled: bool,
    ) -> CompetitionSubscription:
        """Enable or disable odds notifications for one chat subscription."""

        now_iso = _utc_now_iso()

        with _connect() as connection:
            _ensure_subscription_exists(connection, chat_id, tracked_competition_id)
            _sanitize_tracking_state(connection)
            connection.execute(
                """
                UPDATE competition_subscriptions
                SET
                    notify_odds_changes = ?,
                    updated_at = ?
                WHERE telegram_chat_id = ? AND tracked_competition_id = ?
                """,
                (int(enabled), now_iso, chat_id, tracked_competition_id),
            )
            row = _fetch_subscription_row(connection, chat_id, tracked_competition_id)

        if row is None:
            raise RuntimeError("Subscription update succeeded but the row could not be reloaded.")

        return _row_to_subscription(row)

    def set_change_percent_threshold(
        self,
        chat_id: int,
        tracked_competition_id: int,
        percent: float,
    ) -> CompetitionSubscription:
        """Set the odds-alert threshold for one chat subscription."""

        if percent <= 0:
            raise ValueError("El porcentaje debe ser mayor a 0.")

        now_iso = _utc_now_iso()

        with _connect() as connection:
            _ensure_subscription_exists(connection, chat_id, tracked_competition_id)
            _sanitize_tracking_state(connection)
            connection.execute(
                """
                UPDATE competition_subscriptions
                SET
                    change_threshold_percent = ?,
                    updated_at = ?
                WHERE telegram_chat_id = ? AND tracked_competition_id = ?
                """,
                (float(percent), now_iso, chat_id, tracked_competition_id),
            )
            row = _fetch_subscription_row(connection, chat_id, tracked_competition_id)

        if row is None:
            raise RuntimeError("Threshold update succeeded but the row could not be reloaded.")

        return _row_to_subscription(row)

    def initialize_event_baselines(
        self,
        chat_id: int,
        tracked_competition_id: int,
        events: Sequence[ActiveEventRecord],
    ) -> int:
        """Create missing per-chat baselines for the provided active events."""

        now_iso = _utc_now_iso()
        payload = [
            (
                chat_id,
                event.id,
                _coerce_optional_float(event.odds_home),
                _coerce_optional_float(event.odds_draw),
                _coerce_optional_float(event.odds_away),
                event.markets_json,
                now_iso,
                now_iso,
            )
            for event in events
            if event.tracked_competition_id == tracked_competition_id
        ]

        if not payload:
            return 0

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            connection.executemany(
                """
                INSERT OR IGNORE INTO user_event_baselines (
                    chat_id,
                    active_event_id,
                    baseline_odds_home,
                    baseline_odds_draw,
                    baseline_odds_away,
                    baseline_markets_json,
                    baseline_set_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )

        return len(payload)

    def get_event_baseline(
        self,
        chat_id: int,
        tracked_competition_id: int,
        external_event_id: str,
    ) -> EventBaseline | None:
        """Load one per-chat baseline for one stored active event."""

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            row = connection.execute(
                """
                SELECT
                    ub.chat_id,
                    ub.active_event_id,
                    ae.tracked_competition_id,
                    ae.external_event_id,
                    ub.baseline_odds_home,
                    ub.baseline_odds_draw,
                    ub.baseline_odds_away,
                    ub.baseline_markets_json,
                    ub.baseline_set_at,
                    ub.updated_at
                FROM user_event_baselines ub
                INNER JOIN active_events ae ON ae.id = ub.active_event_id
                WHERE ub.chat_id = ?
                  AND ae.tracked_competition_id = ?
                  AND ae.external_event_id = ?
                """,
                (chat_id, tracked_competition_id, external_event_id.strip()),
            ).fetchone()

        return _row_to_event_baseline(row) if row is not None else None

    def upsert_event_baseline(
        self,
        chat_id: int,
        tracked_competition_id: int,
        external_event_id: str,
        *,
        baseline_home: float | None,
        baseline_draw: float | None,
        baseline_away: float | None,
        baseline_markets_json: str | None = None,
    ) -> EventBaseline:
        """Create or update the baseline for one chat and active event."""

        normalized_event_id = external_event_id.strip()
        if not normalized_event_id:
            raise ValueError("external_event_id must not be empty.")

        now_iso = _utc_now_iso()

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            event_row = _fetch_active_event_row(
                connection,
                tracked_competition_id,
                normalized_event_id,
            )

            if event_row is None:
                raise ValueError(
                    f"No active event found for tracked_competition_id={tracked_competition_id} "
                    f"and external_event_id={normalized_event_id}."
                )

            active_event_id = int(event_row["id"])
            connection.execute(
                """
                INSERT INTO user_event_baselines (
                    chat_id,
                    active_event_id,
                    baseline_odds_home,
                    baseline_odds_draw,
                    baseline_odds_away,
                    baseline_markets_json,
                    baseline_set_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, active_event_id) DO UPDATE SET
                    baseline_odds_home = excluded.baseline_odds_home,
                    baseline_odds_draw = excluded.baseline_odds_draw,
                    baseline_odds_away = excluded.baseline_odds_away,
                    baseline_markets_json = excluded.baseline_markets_json,
                    baseline_set_at = excluded.baseline_set_at,
                    updated_at = excluded.updated_at
                """,
                (
                    chat_id,
                    active_event_id,
                    _coerce_optional_float(baseline_home),
                    _coerce_optional_float(baseline_draw),
                    _coerce_optional_float(baseline_away),
                    _normalize_optional_text(baseline_markets_json),
                    now_iso,
                    now_iso,
                ),
            )
            row = connection.execute(
                """
                SELECT
                    ub.chat_id,
                    ub.active_event_id,
                    ae.tracked_competition_id,
                    ae.external_event_id,
                    ub.baseline_odds_home,
                    ub.baseline_odds_draw,
                    ub.baseline_odds_away,
                    ub.baseline_markets_json,
                    ub.baseline_set_at,
                    ub.updated_at
                FROM user_event_baselines ub
                INNER JOIN active_events ae ON ae.id = ub.active_event_id
                WHERE ub.chat_id = ? AND ub.active_event_id = ?
                """,
                (chat_id, active_event_id),
            ).fetchone()

        if row is None:
            raise RuntimeError("Baseline upsert succeeded but the row could not be reloaded.")

        return _row_to_event_baseline(row)

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
        """Create or update one per-chat small odds change record."""

        normalized_event_id = external_event_id.strip()
        normalized_status = status.strip().lower()

        if not normalized_event_id:
            raise ValueError("external_event_id must not be empty.")
        if not home.strip() or not away.strip():
            raise ValueError("home and away must not be empty.")
        if normalized_status not in {"pending", "confirmed", "ignored"}:
            raise ValueError("status must be pending, confirmed, or ignored.")

        now_iso = _utc_now_iso()

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            event_row = _fetch_active_event_row(
                connection,
                tracked_competition_id,
                normalized_event_id,
            )

            if event_row is None:
                raise ValueError(
                    f"No active event found for tracked_competition_id={tracked_competition_id} "
                    f"and external_event_id={normalized_event_id}."
                )

            competition_row = _fetch_tracked_competition_row(connection, tracked_competition_id)
            if competition_row is None:
                raise RuntimeError("Active event exists but its competition could not be loaded.")

            payload_json = _json_dumps(
                {
                    "competition_name": str(competition_row["competition_name"]),
                    "home": home.strip(),
                    "away": away.strip(),
                    "scheduled_label_date": _normalize_optional_text(scheduled_label_date),
                    "scheduled_label_time": _normalize_optional_text(scheduled_label_time),
                }
            )
            active_event_id = int(event_row["id"])
            confirmed_at = now_iso if normalized_status == "confirmed" else None
            dismissed_at = now_iso if normalized_status == "ignored" else None

            connection.execute(
                """
                INSERT INTO small_changes (
                    chat_id,
                    active_event_id,
                    previous_odds_home,
                    previous_odds_draw,
                    previous_odds_away,
                    current_odds_home,
                    current_odds_draw,
                    current_odds_away,
                    max_change_percent,
                    payload_json,
                    status,
                    created_at,
                    updated_at,
                    confirmed_at,
                    dismissed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, active_event_id) DO UPDATE SET
                    previous_odds_home = excluded.previous_odds_home,
                    previous_odds_draw = excluded.previous_odds_draw,
                    previous_odds_away = excluded.previous_odds_away,
                    current_odds_home = excluded.current_odds_home,
                    current_odds_draw = excluded.current_odds_draw,
                    current_odds_away = excluded.current_odds_away,
                    max_change_percent = excluded.max_change_percent,
                    payload_json = excluded.payload_json,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    confirmed_at = excluded.confirmed_at,
                    dismissed_at = excluded.dismissed_at
                """,
                (
                    chat_id,
                    active_event_id,
                    _coerce_optional_float(baseline_home),
                    _coerce_optional_float(baseline_draw),
                    _coerce_optional_float(baseline_away),
                    _coerce_optional_float(current_home),
                    _coerce_optional_float(current_draw),
                    _coerce_optional_float(current_away),
                    float(max_percent_change),
                    payload_json,
                    normalized_status,
                    now_iso,
                    now_iso,
                    confirmed_at,
                    dismissed_at,
                ),
            )
            row = _fetch_small_change_row_by_identity(connection, chat_id, active_event_id)

        if row is None:
            raise RuntimeError("Small change upsert succeeded but the row could not be reloaded.")

        return _row_to_small_change_record(row)

    def list_pending_small_changes(self, chat_id: int) -> list[SmallChangeRecord]:
        """List pending small changes for one Telegram chat."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            rows = connection.execute(
                """
                SELECT
                    sc.id,
                    sc.chat_id,
                    sc.active_event_id,
                    ae.tracked_competition_id,
                    ae.external_event_id,
                    tc.competition_name,
                    ae.home,
                    ae.away,
                    ae.scheduled_label_date,
                    ae.scheduled_label_time,
                    sc.previous_odds_home,
                    sc.previous_odds_draw,
                    sc.previous_odds_away,
                    sc.current_odds_home,
                    sc.current_odds_draw,
                    sc.current_odds_away,
                    sc.max_change_percent,
                    sc.payload_json,
                    sc.status,
                    sc.created_at,
                    sc.updated_at,
                    sc.confirmed_at,
                    sc.dismissed_at
                FROM small_changes sc
                INNER JOIN active_events ae ON ae.id = sc.active_event_id
                INNER JOIN tracked_competitions tc ON tc.id = ae.tracked_competition_id
                INNER JOIN competition_subscriptions cs
                    ON cs.tracked_competition_id = ae.tracked_competition_id
                   AND cs.telegram_chat_id = sc.chat_id
                WHERE sc.chat_id = ?
                  AND sc.status = 'pending'
                  AND cs.enabled = 1
                  AND tc.enabled = 1
                  AND ae.is_active = 1
                ORDER BY sc.updated_at DESC, tc.platform, tc.competition_name, ae.home, ae.away
                """,
                (chat_id,),
            ).fetchall()

        return [_row_to_small_change_record(row) for row in rows]

    def confirm_small_change(self, chat_id: int, small_change_id: int) -> SmallChangeRecord:
        """Confirm one pending small change and update the chat baseline."""

        now_iso = _utc_now_iso()

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            row = _fetch_small_change_row_by_id(connection, chat_id, small_change_id)

            if row is None:
                raise ValueError("No encontré ese little change para este chat.")

            record = _row_to_small_change_record(row)
            connection.execute(
                """
                INSERT INTO user_event_baselines (
                    chat_id,
                    active_event_id,
                    baseline_odds_home,
                    baseline_odds_draw,
                    baseline_odds_away,
                    baseline_markets_json,
                    baseline_set_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(chat_id, active_event_id) DO UPDATE SET
                    baseline_odds_home = excluded.baseline_odds_home,
                    baseline_odds_draw = excluded.baseline_odds_draw,
                    baseline_odds_away = excluded.baseline_odds_away,
                    baseline_markets_json = excluded.baseline_markets_json,
                    baseline_set_at = excluded.baseline_set_at,
                    updated_at = excluded.updated_at
                """,
                (
                    chat_id,
                    record.active_event_id,
                    _coerce_optional_float(record.current_home),
                    _coerce_optional_float(record.current_draw),
                    _coerce_optional_float(record.current_away),
                    now_iso,
                    now_iso,
                ),
            )
            connection.execute(
                """
                UPDATE small_changes
                SET
                    status = 'confirmed',
                    confirmed_at = ?,
                    dismissed_at = NULL,
                    updated_at = ?
                WHERE id = ? AND chat_id = ?
                """,
                (now_iso, now_iso, small_change_id, chat_id),
            )
            updated_row = _fetch_small_change_row_by_id(connection, chat_id, small_change_id)

        if updated_row is None:
            raise RuntimeError("Small change confirmation succeeded but the row could not be reloaded.")

        return _row_to_small_change_record(updated_row)

    def confirm_all_small_changes(self, chat_id: int) -> list[SmallChangeRecord]:
        """Confirm every pending small change for one Telegram chat."""

        pending_changes = self.list_pending_small_changes(chat_id)
        confirmed: list[SmallChangeRecord] = []

        for change in pending_changes:
            confirmed.append(self.confirm_small_change(chat_id, change.id))

        return confirmed

    def resolve_small_change_with_current_baseline(
        self,
        chat_id: int,
        tracked_competition_id: int,
        external_event_id: str,
    ) -> None:
        """Resolve a pending small change after an automatic baseline update."""

        normalized_event_id = external_event_id.strip()
        if not normalized_event_id:
            return

        now_iso = _utc_now_iso()

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            event_row = _fetch_active_event_row(
                connection,
                tracked_competition_id,
                normalized_event_id,
            )

            if event_row is None:
                return

            connection.execute(
                """
                UPDATE small_changes
                SET
                    status = 'confirmed',
                    confirmed_at = ?,
                    dismissed_at = NULL,
                    updated_at = ?
                WHERE chat_id = ?
                  AND active_event_id = ?
                  AND status = 'pending'
                """,
                (now_iso, now_iso, chat_id, int(event_row["id"])),
            )

    def remove_tracked_competition_subscription(
        self,
        chat_id: int,
        tracked_competition_id: int,
    ) -> UntrackCompetitionResult:
        """Remove one chat subscription and disable the competition if orphaned."""

        now_iso = _utc_now_iso()

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            tracked_row = _fetch_tracked_competition_row(connection, tracked_competition_id)

            if tracked_row is None:
                raise ValueError(f"No tracked competition found with id={tracked_competition_id}.")

            cursor = connection.execute(
                """
                DELETE FROM competition_subscriptions
                WHERE telegram_chat_id = ? AND tracked_competition_id = ?
                """,
                (chat_id, tracked_competition_id),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"No subscription found for chat_id={chat_id} and tracked_competition_id={tracked_competition_id}."
                )

            connection.execute(
                """
                DELETE FROM user_event_baselines
                WHERE chat_id = ?
                  AND active_event_id IN (
                      SELECT id
                      FROM active_events
                      WHERE tracked_competition_id = ?
                  )
                """,
                (chat_id, tracked_competition_id),
            )
            connection.execute(
                """
                DELETE FROM small_changes
                WHERE chat_id = ?
                  AND active_event_id IN (
                      SELECT id
                      FROM active_events
                      WHERE tracked_competition_id = ?
                  )
                """,
                (chat_id, tracked_competition_id),
            )
            connection.execute(
                """
                DELETE FROM sent_alerts
                WHERE chat_id = ?
                  AND active_event_id IN (
                      SELECT id
                      FROM active_events
                      WHERE tracked_competition_id = ?
                  )
                """,
                (chat_id, tracked_competition_id),
            )

            remaining_enabled_subscriptions = _count_enabled_subscriptions(
                connection,
                tracked_competition_id,
            )
            competition_disabled = False
            removed_active_events = 0

            if remaining_enabled_subscriptions == 0:
                competition_disabled = True
                connection.execute(
                    """
                    UPDATE tracked_competitions
                    SET
                        enabled = 0,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now_iso, tracked_competition_id),
                )
                obsolete_rows = connection.execute(
                    """
                    SELECT external_event_id
                    FROM active_events
                    WHERE tracked_competition_id = ?
                    ORDER BY external_event_id
                    """,
                    (tracked_competition_id,),
                ).fetchall()
                removed_active_events = connection.execute(
                    """
                    DELETE FROM active_events
                    WHERE tracked_competition_id = ?
                    """,
                    (tracked_competition_id,),
                ).rowcount
                for row in obsolete_rows:
                    logger.info("Deleted obsolete match: %s", str(row["external_event_id"]))

            tracked_row = _fetch_tracked_competition_row(connection, tracked_competition_id)

        if tracked_row is None:
            raise RuntimeError("Tracked competition could not be reloaded after untracking.")

        return UntrackCompetitionResult(
            tracked_competition=_row_to_tracked_competition(tracked_row),
            removed_subscription=True,
            competition_disabled=competition_disabled,
            removed_active_events=removed_active_events,
            remaining_enabled_subscriptions=remaining_enabled_subscriptions,
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
        """Update metadata for one tracked competition after a refresh."""

        normalized_url = _normalize_url(source_url)
        normalized_competition_id = competition_external_id.strip()
        now_iso = _utc_now_iso()

        if not normalized_competition_id:
            raise ValueError("competition_external_id must not be empty.")

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)

            existing_row = _fetch_tracked_competition_row(connection, tracked_competition_id)
            if existing_row is None:
                raise RuntimeError("Tracked competition update could not load the current row.")

            existing_competition = _row_to_tracked_competition(existing_row)
            resolved_name, resolved_needs_name_resolution = _resolve_competition_name(
                existing_competition.competition_name,
                existing_competition.needs_name_resolution,
                competition_name,
                needs_name_resolution,
            )

            if enabled is None:
                connection.execute(
                    """
                    UPDATE tracked_competitions
                    SET
                        source_url = ?,
                        competition_external_id = ?,
                        competition_name = ?,
                        needs_name_resolution = ?,
                        last_refreshed_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        normalized_url,
                        normalized_competition_id,
                        resolved_name,
                        int(resolved_needs_name_resolution),
                        _normalize_optional_text(last_synced_at),
                        now_iso,
                        tracked_competition_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE tracked_competitions
                    SET
                        source_url = ?,
                        competition_external_id = ?,
                        competition_name = ?,
                        needs_name_resolution = ?,
                        enabled = ?,
                        last_refreshed_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        normalized_url,
                        normalized_competition_id,
                        resolved_name,
                        int(resolved_needs_name_resolution),
                        int(enabled),
                        _normalize_optional_text(last_synced_at),
                        now_iso,
                        tracked_competition_id,
                    ),
                )

            row = _fetch_tracked_competition_row(connection, tracked_competition_id)

        if row is None:
            raise RuntimeError("Tracked competition update succeeded but the row could not be reloaded.")

        return _row_to_tracked_competition(row)

    def upsert_active_events(
        self,
        tracked_competition_id: int,
        events: Sequence[ActiveEventUpsert],
    ) -> int:
        """Insert or update the current active events for one competition."""

        if not events:
            return 0

        now_iso = _utc_now_iso()

        with _connect() as connection:
            competition_row = _fetch_tracked_competition_row(connection, tracked_competition_id)

            if competition_row is None:
                raise ValueError(f"No tracked competition found with id={tracked_competition_id}.")

            _sanitize_tracking_state(connection)
            competition = _row_to_tracked_competition(competition_row)
            payload: list[tuple[object, ...]] = []

            for event in events:
                external_event_id = event.external_event_id.strip()
                home = event.home.strip()
                away = event.away.strip()

                if not external_event_id or not home or not away:
                    raise ValueError(
                        "Each active event must include external_event_id, home, and away."
                    )

                markets_payload = event.markets_payload or _default_markets_payload(event)

                payload.append(
                    (
                        tracked_competition_id,
                        competition.platform,
                        competition.competition_external_id,
                        external_event_id,
                        home,
                        away,
                        _normalize_optional_text(event.scheduled_at),
                        _normalize_optional_text(event.scheduled_label_date),
                        _normalize_optional_text(event.scheduled_label_time),
                        _normalize_optional_text(event.event_url),
                        _coerce_optional_float(event.odds_home),
                        _coerce_optional_float(event.odds_draw),
                        _coerce_optional_float(event.odds_away),
                        _json_dumps(markets_payload),
                        _json_dumps(event.raw_payload),
                        now_iso,
                        now_iso,
                        now_iso,
                        now_iso,
                    )
                )

            connection.executemany(
                """
                INSERT INTO active_events (
                    tracked_competition_id,
                    platform,
                    competition_external_id,
                    external_event_id,
                    home,
                    away,
                    scheduled_at,
                    scheduled_label_date,
                    scheduled_label_time,
                    event_url,
                    odds_home,
                    odds_draw,
                    odds_away,
                    markets_json,
                    raw_payload_json,
                    first_seen_at,
                    last_seen_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(platform, external_event_id) DO UPDATE SET
                    tracked_competition_id = excluded.tracked_competition_id,
                    competition_external_id = excluded.competition_external_id,
                    home = excluded.home,
                    away = excluded.away,
                    scheduled_at = excluded.scheduled_at,
                    scheduled_label_date = excluded.scheduled_label_date,
                    scheduled_label_time = excluded.scheduled_label_time,
                    event_url = excluded.event_url,
                    odds_home = excluded.odds_home,
                    odds_draw = excluded.odds_draw,
                    odds_away = excluded.odds_away,
                    markets_json = excluded.markets_json,
                    raw_payload_json = excluded.raw_payload_json,
                    last_seen_at = excluded.last_seen_at,
                    is_active = 1,
                    updated_at = excluded.updated_at
                """,
                payload,
            )

        return len(payload)

    def remove_missing_events(
        self,
        tracked_competition_id: int,
        current_event_ids: Iterable[str],
    ) -> int:
        """Delete active events that no longer appear in the latest refresh."""

        normalized_event_ids = sorted(
            {
                external_event_id.strip()
                for external_event_id in current_event_ids
                if external_event_id and external_event_id.strip()
            }
        )

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            obsolete_rows = _fetch_obsolete_event_rows(
                connection,
                tracked_competition_id,
                normalized_event_ids,
            )

            if not obsolete_rows:
                return 0

            connection.executemany(
                """
                DELETE FROM active_events
                WHERE id = ?
                """,
                [(int(row["id"]),) for row in obsolete_rows],
            )

        for row in obsolete_rows:
            logger.info("Deleted obsolete match: %s", str(row["external_event_id"]))

        return len(obsolete_rows)

    def remove_past_events(
        self,
        tracked_competition_id: int,
        reference_time: str | None = None,
    ) -> int:
        """Delete active events that already started before the given reference time."""

        if reference_time is None:
            reference = datetime.now(timezone.utc)
        else:
            reference = _parse_utc_datetime(reference_time)
            if reference is None:
                reference = datetime.now(timezone.utc)

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            candidate_rows = connection.execute(
                """
                SELECT id, external_event_id, scheduled_at
                FROM active_events
                WHERE tracked_competition_id = ?
                  AND is_active = 1
                  AND scheduled_at IS NOT NULL
                ORDER BY scheduled_at
                """,
                (tracked_competition_id,),
            ).fetchall()

            obsolete_rows = [
                row
                for row in candidate_rows
                if _is_past_scheduled_at(row["scheduled_at"], reference)
            ]

            if not obsolete_rows:
                return 0

            connection.executemany(
                """
                DELETE FROM active_events
                WHERE id = ?
                """,
                [(int(row["id"]),) for row in obsolete_rows],
            )

        for row in obsolete_rows:
            logger.info("Deleted obsolete match: %s", str(row["external_event_id"]))

        return len(obsolete_rows)

    def get_active_events(
        self,
        tracked_competition_id: int,
        *,
        only_future: bool = True,
    ) -> list[ActiveEventRecord]:
        """Return the current active events for one tracked competition."""

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            rows = connection.execute(
                """
                SELECT
                    id,
                    tracked_competition_id,
                    platform,
                    competition_external_id,
                    external_event_id,
                    home,
                    away,
                    scheduled_label_date,
                    scheduled_label_time,
                    scheduled_at,
                    event_url,
                    odds_home,
                    odds_draw,
                    odds_away,
                    markets_json,
                    raw_payload_json,
                    reminder_sent_at,
                    is_active,
                    first_seen_at,
                    last_seen_at,
                    created_at,
                    updated_at
                FROM active_events
                WHERE tracked_competition_id = ?
                  AND is_active = 1
                ORDER BY scheduled_at IS NULL, scheduled_at, home, away, id
                """,
                (tracked_competition_id,),
            ).fetchall()

        records = [_row_to_active_event_record(row) for row in rows]

        if not only_future:
            return records

        now_utc = datetime.now(timezone.utc)
        return [
            record
            for record in records
            if _is_future_or_unscheduled(record.scheduled_at, now_utc)
        ]

    def has_sent_alert(
        self,
        chat_id: int,
        tracked_competition_id: int,
        external_event_id: str,
        alert_type: str,
    ) -> bool:
        """Return whether a specific alert type was already sent for this chat/event."""

        normalized_event_id = external_event_id.strip()
        normalized_alert_type = alert_type.strip().lower()

        if not normalized_event_id or not normalized_alert_type:
            return False

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            event_row = _fetch_active_event_row(
                connection,
                tracked_competition_id,
                normalized_event_id,
            )

            if event_row is None:
                return False

            row = connection.execute(
                """
                SELECT 1
                FROM sent_alerts
                WHERE chat_id = ? AND active_event_id = ? AND alert_type = ?
                LIMIT 1
                """,
                (chat_id, int(event_row["id"]), normalized_alert_type),
            ).fetchone()

        return row is not None

    def mark_sent_alert(
        self,
        chat_id: int,
        tracked_competition_id: int,
        external_event_id: str,
        alert_type: str,
    ) -> bool:
        """Persist that one alert type was sent for this chat/event."""

        normalized_event_id = external_event_id.strip()
        normalized_alert_type = alert_type.strip().lower()

        if not normalized_event_id or not normalized_alert_type:
            return False

        now_iso = _utc_now_iso()

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            event_row = _fetch_active_event_row(
                connection,
                tracked_competition_id,
                normalized_event_id,
            )

            if event_row is None:
                return False

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO sent_alerts (
                    chat_id,
                    active_event_id,
                    alert_type,
                    sent_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, int(event_row["id"]), normalized_alert_type, now_iso),
            )

        return cursor.rowcount > 0

    def mark_sent_alerts(
        self,
        chat_id: int,
        tracked_competition_id: int,
        external_event_ids: Iterable[str],
        alert_type: str,
    ) -> int:
        """Persist one alert type as sent for many events in one competition."""

        normalized_event_ids = sorted(
            {
                external_event_id.strip()
                for external_event_id in external_event_ids
                if external_event_id and external_event_id.strip()
            }
        )
        normalized_alert_type = alert_type.strip().lower()

        if not normalized_event_ids or not normalized_alert_type:
            return 0

        placeholders = ", ".join("?" for _ in normalized_event_ids)
        now_iso = _utc_now_iso()

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            event_rows = connection.execute(
                f"""
                SELECT id
                FROM active_events
                WHERE tracked_competition_id = ?
                  AND external_event_id IN ({placeholders})
                """,
                (tracked_competition_id, *normalized_event_ids),
            ).fetchall()

            if not event_rows:
                return 0

            cursor = connection.executemany(
                """
                INSERT OR IGNORE INTO sent_alerts (
                    chat_id,
                    active_event_id,
                    alert_type,
                    sent_at
                )
                VALUES (?, ?, ?, ?)
                """,
                [
                    (chat_id, int(row["id"]), normalized_alert_type, now_iso)
                    for row in event_rows
                ],
            )

        return cursor.rowcount

    def mark_events_alerted(
        self,
        tracked_competition_id: int,
        external_event_ids: Iterable[str],
    ) -> int:
        """Mark reminder alerts as sent for the provided active events."""

        normalized_event_ids = sorted(
            {
                external_event_id.strip()
                for external_event_id in external_event_ids
                if external_event_id and external_event_id.strip()
            }
        )

        if not normalized_event_ids:
            return 0

        now_iso = _utc_now_iso()
        placeholders = ", ".join("?" for _ in normalized_event_ids)

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            cursor = connection.execute(
                f"""
                UPDATE active_events
                SET
                    reminder_sent_at = ?,
                    updated_at = ?
                WHERE tracked_competition_id = ?
                  AND external_event_id IN ({placeholders})
                """,
                (now_iso, now_iso, tracked_competition_id, *normalized_event_ids),
            )

        return cursor.rowcount

    def sanitize_tracking_state(self) -> None:
        """Clean obviously invalid rows from the generic tracking storage."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)

# Connect to the database
def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    _initialize_schema(connection)
    return connection

# Inizializate database schema
def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS pending_track_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_chat_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            source_url TEXT NOT NULL,
            competition_external_id TEXT NOT NULL,
            competition_name TEXT NOT NULL,
            requires_empty_confirmation INTEGER NOT NULL DEFAULT 0,
            needs_name_resolution INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_track_requests_chat
        ON pending_track_requests(telegram_chat_id);

        CREATE TABLE IF NOT EXISTS tracked_competitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            competition_external_id TEXT NOT NULL,
            competition_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            metadata_json TEXT,
            needs_name_resolution INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_refreshed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(platform, competition_external_id)
        );

        CREATE TABLE IF NOT EXISTS competition_subscriptions (
            telegram_chat_id INTEGER NOT NULL,
            tracked_competition_id INTEGER NOT NULL,
            notify_new_events INTEGER NOT NULL DEFAULT 1,
            notify_odds_changes INTEGER NOT NULL DEFAULT 1,
            change_threshold_percent REAL NOT NULL DEFAULT 20.0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (telegram_chat_id, tracked_competition_id),
            FOREIGN KEY(tracked_competition_id) REFERENCES tracked_competitions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_competition_subscriptions_tracked_competition
        ON competition_subscriptions(tracked_competition_id);

        CREATE TABLE IF NOT EXISTS active_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracked_competition_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            competition_external_id TEXT NOT NULL,
            external_event_id TEXT NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            scheduled_at TEXT,
            scheduled_label_date TEXT,
            scheduled_label_time TEXT,
            event_url TEXT,
            odds_home REAL,
            odds_draw REAL,
            odds_away REAL,
            markets_json TEXT,
            raw_payload_json TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            reminder_sent_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(platform, external_event_id),
            FOREIGN KEY(tracked_competition_id) REFERENCES tracked_competitions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_active_events_tracked_competition
        ON active_events(tracked_competition_id, is_active, scheduled_at);

        CREATE TABLE IF NOT EXISTS user_event_baselines (
            chat_id INTEGER NOT NULL,
            active_event_id INTEGER NOT NULL,
            baseline_odds_home REAL,
            baseline_odds_draw REAL,
            baseline_odds_away REAL,
            baseline_markets_json TEXT,
            baseline_set_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, active_event_id),
            FOREIGN KEY(active_event_id) REFERENCES active_events(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS small_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            active_event_id INTEGER NOT NULL,
            previous_odds_home REAL,
            previous_odds_draw REAL,
            previous_odds_away REAL,
            current_odds_home REAL,
            current_odds_draw REAL,
            current_odds_away REAL,
            max_change_percent REAL NOT NULL,
            payload_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            confirmed_at TEXT,
            dismissed_at TEXT,
            UNIQUE(chat_id, active_event_id),
            FOREIGN KEY(active_event_id) REFERENCES active_events(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_small_changes_chat_status
        ON small_changes(chat_id, status, updated_at);

        CREATE TABLE IF NOT EXISTS sent_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            active_event_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            UNIQUE(chat_id, active_event_id, alert_type),
            FOREIGN KEY(active_event_id) REFERENCES active_events(id) ON DELETE CASCADE
        );
        """
    )


def _fetch_pending_request_row(
    connection: sqlite3.Connection,
    chat_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            id,
            telegram_chat_id,
            platform,
            source_url,
            competition_external_id,
            competition_name,
            requires_empty_confirmation,
            needs_name_resolution,
            payload_json,
            created_at,
            expires_at
        FROM pending_track_requests
        WHERE telegram_chat_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (chat_id,),
    ).fetchone()


def _fetch_tracked_competition_row(
    connection: sqlite3.Connection,
    tracked_competition_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            id,
            platform,
            source_url,
            competition_external_id,
            competition_name,
            metadata_json,
            needs_name_resolution,
            enabled,
            last_refreshed_at,
            created_at,
            updated_at
        FROM tracked_competitions
        WHERE id = ?
        """,
        (tracked_competition_id,),
    ).fetchone()


def _fetch_tracked_competition_by_identity_row(
    connection: sqlite3.Connection,
    platform: str,
    competition_external_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            id,
            platform,
            source_url,
            competition_external_id,
            competition_name,
            metadata_json,
            needs_name_resolution,
            enabled,
            last_refreshed_at,
            created_at,
            updated_at
        FROM tracked_competitions
        WHERE platform = ? AND competition_external_id = ?
        """,
        (_normalize_platform(platform), competition_external_id.strip()),
    ).fetchone()


def _fetch_subscription_row(
    connection: sqlite3.Connection,
    chat_id: int,
    tracked_competition_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            telegram_chat_id,
            tracked_competition_id,
            notify_new_events,
            notify_odds_changes,
            change_threshold_percent,
            enabled,
            created_at,
            updated_at
        FROM competition_subscriptions
        WHERE telegram_chat_id = ? AND tracked_competition_id = ?
        """,
        (chat_id, tracked_competition_id),
    ).fetchone()


def _fetch_tracked_competition_subscription_row(
    connection: sqlite3.Connection,
    chat_id: int,
    tracked_competition_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            tc.id AS tracked_competition_id,
            tc.platform AS tracked_platform,
            tc.source_url AS tracked_source_url,
            tc.competition_external_id AS tracked_competition_external_id,
            tc.competition_name AS tracked_competition_name,
            tc.metadata_json AS tracked_metadata_json,
            tc.needs_name_resolution AS tracked_needs_name_resolution,
            tc.enabled AS tracked_enabled,
            tc.last_refreshed_at AS tracked_last_refreshed_at,
            tc.created_at AS tracked_created_at,
            tc.updated_at AS tracked_updated_at,
            cs.telegram_chat_id AS subscription_telegram_chat_id,
            cs.tracked_competition_id AS subscription_tracked_competition_id,
            cs.notify_new_events AS subscription_notify_new_events,
            cs.notify_odds_changes AS subscription_notify_odds_changes,
            cs.change_threshold_percent AS subscription_change_threshold_percent,
            cs.enabled AS subscription_enabled,
            cs.created_at AS subscription_created_at,
            cs.updated_at AS subscription_updated_at
        FROM competition_subscriptions cs
        INNER JOIN tracked_competitions tc ON tc.id = cs.tracked_competition_id
        WHERE cs.telegram_chat_id = ? AND cs.tracked_competition_id = ?
        LIMIT 1
        """,
        (chat_id, tracked_competition_id),
    ).fetchone()


def _fetch_tracked_competition_subscription_by_identity_row(
    connection: sqlite3.Connection,
    chat_id: int,
    platform: str,
    competition_external_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            tc.id AS tracked_competition_id,
            tc.platform AS tracked_platform,
            tc.source_url AS tracked_source_url,
            tc.competition_external_id AS tracked_competition_external_id,
            tc.competition_name AS tracked_competition_name,
            tc.metadata_json AS tracked_metadata_json,
            tc.needs_name_resolution AS tracked_needs_name_resolution,
            tc.enabled AS tracked_enabled,
            tc.last_refreshed_at AS tracked_last_refreshed_at,
            tc.created_at AS tracked_created_at,
            tc.updated_at AS tracked_updated_at,
            cs.telegram_chat_id AS subscription_telegram_chat_id,
            cs.tracked_competition_id AS subscription_tracked_competition_id,
            cs.notify_new_events AS subscription_notify_new_events,
            cs.notify_odds_changes AS subscription_notify_odds_changes,
            cs.change_threshold_percent AS subscription_change_threshold_percent,
            cs.enabled AS subscription_enabled,
            cs.created_at AS subscription_created_at,
            cs.updated_at AS subscription_updated_at
        FROM competition_subscriptions cs
        INNER JOIN tracked_competitions tc ON tc.id = cs.tracked_competition_id
        WHERE cs.telegram_chat_id = ?
          AND tc.platform = ?
          AND tc.competition_external_id = ?
          AND cs.enabled = 1
          AND tc.enabled = 1
        LIMIT 1
        """,
        (chat_id, _normalize_platform(platform), competition_external_id.strip()),
    ).fetchone()


def _fetch_active_event_row(
    connection: sqlite3.Connection,
    tracked_competition_id: int,
    external_event_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            id,
            tracked_competition_id,
            platform,
            competition_external_id,
            external_event_id,
            home,
            away,
            scheduled_label_date,
            scheduled_label_time,
            scheduled_at,
            event_url,
            odds_home,
            odds_draw,
            odds_away,
            markets_json,
            raw_payload_json,
            reminder_sent_at,
            is_active,
            first_seen_at,
            last_seen_at,
            created_at,
            updated_at
        FROM active_events
        WHERE tracked_competition_id = ?
          AND external_event_id = ?
          AND is_active = 1
        LIMIT 1
        """,
        (tracked_competition_id, external_event_id.strip()),
    ).fetchone()


def _fetch_small_change_row_by_id(
    connection: sqlite3.Connection,
    chat_id: int,
    small_change_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            sc.id,
            sc.chat_id,
            sc.active_event_id,
            ae.tracked_competition_id,
            ae.external_event_id,
            tc.competition_name,
            ae.home,
            ae.away,
            ae.scheduled_label_date,
            ae.scheduled_label_time,
            sc.previous_odds_home,
            sc.previous_odds_draw,
            sc.previous_odds_away,
            sc.current_odds_home,
            sc.current_odds_draw,
            sc.current_odds_away,
            sc.max_change_percent,
            sc.payload_json,
            sc.status,
            sc.created_at,
            sc.updated_at,
            sc.confirmed_at,
            sc.dismissed_at
        FROM small_changes sc
        INNER JOIN active_events ae ON ae.id = sc.active_event_id
        INNER JOIN tracked_competitions tc ON tc.id = ae.tracked_competition_id
        WHERE sc.id = ? AND sc.chat_id = ?
        LIMIT 1
        """,
        (small_change_id, chat_id),
    ).fetchone()


def _fetch_small_change_row_by_identity(
    connection: sqlite3.Connection,
    chat_id: int,
    active_event_id: int,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            sc.id,
            sc.chat_id,
            sc.active_event_id,
            ae.tracked_competition_id,
            ae.external_event_id,
            tc.competition_name,
            ae.home,
            ae.away,
            ae.scheduled_label_date,
            ae.scheduled_label_time,
            sc.previous_odds_home,
            sc.previous_odds_draw,
            sc.previous_odds_away,
            sc.current_odds_home,
            sc.current_odds_draw,
            sc.current_odds_away,
            sc.max_change_percent,
            sc.payload_json,
            sc.status,
            sc.created_at,
            sc.updated_at,
            sc.confirmed_at,
            sc.dismissed_at
        FROM small_changes sc
        INNER JOIN active_events ae ON ae.id = sc.active_event_id
        INNER JOIN tracked_competitions tc ON tc.id = ae.tracked_competition_id
        WHERE sc.chat_id = ? AND sc.active_event_id = ?
        LIMIT 1
        """,
        (chat_id, active_event_id),
    ).fetchone()


def _fetch_obsolete_event_rows(
    connection: sqlite3.Connection,
    tracked_competition_id: int,
    current_event_ids: Sequence[str],
) -> list[sqlite3.Row]:
    if not current_event_ids:
        return connection.execute(
            """
            SELECT id, external_event_id
            FROM active_events
            WHERE tracked_competition_id = ? AND is_active = 1
            ORDER BY external_event_id
            """,
            (tracked_competition_id,),
        ).fetchall()

    placeholders = ", ".join("?" for _ in current_event_ids)
    return connection.execute(
        f"""
        SELECT id, external_event_id
        FROM active_events
        WHERE tracked_competition_id = ?
          AND is_active = 1
          AND external_event_id NOT IN ({placeholders})
        ORDER BY external_event_id
        """,
        (tracked_competition_id, *current_event_ids),
    ).fetchall()


def _ensure_tracked_competition_exists(
    connection: sqlite3.Connection,
    tracked_competition_id: int,
) -> None:
    row = _fetch_tracked_competition_row(connection, tracked_competition_id)
    if row is None:
        raise ValueError(f"No tracked competition found with id={tracked_competition_id}.")


def _ensure_subscription_exists(
    connection: sqlite3.Connection,
    chat_id: int,
    tracked_competition_id: int,
) -> None:
    _ensure_tracked_competition_exists(connection, tracked_competition_id)
    if _fetch_subscription_row(connection, chat_id, tracked_competition_id) is None:
        raise ValueError(
            f"No subscription found for chat_id={chat_id} and tracked_competition_id={tracked_competition_id}."
        )


def _count_enabled_subscriptions(
    connection: sqlite3.Connection,
    tracked_competition_id: int,
) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*) AS subscription_count
        FROM competition_subscriptions
        WHERE tracked_competition_id = ? AND enabled = 1
        """,
        (tracked_competition_id,),
    ).fetchone()
    return int(row["subscription_count"]) if row is not None else 0


def _sanitize_tracking_state(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        DELETE FROM pending_track_requests
        WHERE TRIM(COALESCE(platform, '')) = ''
           OR TRIM(COALESCE(source_url, '')) = ''
           OR TRIM(COALESCE(competition_external_id, '')) = ''
           OR TRIM(COALESCE(competition_name, '')) = ''
           OR LOWER(TRIM(COALESCE(competition_name, ''))) = 'none'
        """
    )
    connection.execute(
        """
        DELETE FROM tracked_competitions
        WHERE TRIM(COALESCE(platform, '')) = ''
           OR TRIM(COALESCE(source_url, '')) = ''
           OR TRIM(COALESCE(competition_external_id, '')) = ''
           OR TRIM(COALESCE(competition_name, '')) = ''
           OR LOWER(TRIM(COALESCE(competition_name, ''))) = 'none'
        """
    )
    connection.execute(
        """
        DELETE FROM active_events
        WHERE tracked_competition_id IN (
            SELECT id
            FROM tracked_competitions
            WHERE enabled = 0
        )
        """
    )


def _resolve_competition_name(
    existing_name: str,
    existing_needs_name_resolution: bool,
    new_name: str | None,
    new_needs_name_resolution: bool | None,
) -> tuple[str, bool]:
    normalized_new_name = (new_name or "").strip()
    incoming_is_provisional = bool(new_needs_name_resolution)

    if not _is_invalid_label(normalized_new_name):
        if incoming_is_provisional and not existing_needs_name_resolution:
            return existing_name, False

        return normalized_new_name, incoming_is_provisional

    logger.info(
        "Preserving existing competition_name because extractor returned an empty name."
    )
    return existing_name, existing_needs_name_resolution


def _is_invalid_label(value: str | None) -> bool:
    normalized = (value or "").strip()
    return not normalized or normalized.lower() == "none"


def _normalize_platform(platform: str) -> str:
    normalized = platform.strip().lower()
    if not normalized:
        raise ValueError("platform must not be empty.")
    return normalized


def _normalize_url(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        raise ValueError("source_url must not be empty.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _coerce_optional_float(value: float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _default_markets_payload(event: ActiveEventUpsert) -> dict[str, Any] | None:
    if (
        event.odds_home is None
        and event.odds_draw is None
        and event.odds_away is None
    ):
        return None

    return {
        "1x2": {
            "home": event.odds_home,
            "draw": event.odds_draw,
            "away": event.odds_away,
        }
    }


def _parse_utc_datetime(raw_value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _is_past_scheduled_at(raw_value: str | None, reference: datetime) -> bool:
    if raw_value is None:
        return False

    parsed = _parse_utc_datetime(str(raw_value))
    if parsed is None:
        return False

    return parsed < reference


def _is_future_or_unscheduled(raw_value: str | None, reference: datetime) -> bool:
    if raw_value is None:
        return True

    parsed = _parse_utc_datetime(raw_value)
    if parsed is None:
        return True

    return parsed >= reference


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


tracking_repository = SqliteTrackingRepository()


__all__ = [
    "ActiveEventRecord",
    "ActiveEventUpsert",
    "CompetitionSubscription",
    "ConfirmedCompetitionTrackRequest",
    "DB_FILE_PATH",
    "EventBaseline",
    "PendingCompetitionTrackRequest",
    "SmallChangeRecord",
    "SqliteTrackingRepository",
    "TrackedCompetition",
    "TrackedCompetitionSubscription",
    "UntrackCompetitionResult",
    "tracking_repository",
]
