"""Row and payload adapters used by the generic tracking repository."""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from storage.tracking_repository import (
        ActiveEventRecord,
        CompetitionSubscription,
        EventBaseline,
        PendingCompetitionTrackRequest,
        SmallChangeRecord,
        TrackedCompetition,
        TrackedCompetitionSubscription,
    )


def row_to_pending_request(row: sqlite3.Row) -> "PendingCompetitionTrackRequest":
    from storage.tracking_repository import PendingCompetitionTrackRequest

    return PendingCompetitionTrackRequest(
        id=int(row["id"]),
        telegram_chat_id=int(row["telegram_chat_id"]),
        platform=str(row["platform"]),
        source_url=str(row["source_url"]),
        competition_external_id=str(row["competition_external_id"]),
        competition_name=str(row["competition_name"]),
        requires_empty_confirmation=bool(row["requires_empty_confirmation"]),
        needs_name_resolution=bool(row["needs_name_resolution"]),
        payload_json=row_optional_text(row, "payload_json"),
        created_at=str(row["created_at"]),
        expires_at=row_optional_text(row, "expires_at"),
    )


def row_to_tracked_competition(row: sqlite3.Row) -> "TrackedCompetition":
    from storage.tracking_repository import TrackedCompetition

    return TrackedCompetition(
        id=int(row["id"]),
        platform=str(row["platform"]),
        source_url=str(row["source_url"]),
        competition_external_id=str(row["competition_external_id"]),
        competition_name=str(row["competition_name"]),
        metadata_json=row_optional_text(row, "metadata_json"),
        needs_name_resolution=bool(row["needs_name_resolution"]),
        enabled=bool(row["enabled"]),
        last_synced_at=row_optional_text(row, "last_refreshed_at"),
        consecutive_unavailable_refreshes=int(row["consecutive_unavailable_refreshes"]),
        last_unavailable_refresh_at=row_optional_text(row, "last_unavailable_refresh_at"),
        last_unavailable_reason=row_optional_text(row, "last_unavailable_reason"),
        last_unavailable_notification_at=row_optional_text(row, "last_unavailable_notification_at"),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def row_to_subscription(row: sqlite3.Row) -> "CompetitionSubscription":
    from storage.tracking_repository import CompetitionSubscription

    return CompetitionSubscription(
        telegram_chat_id=int(row["telegram_chat_id"]),
        tracked_competition_id=int(row["tracked_competition_id"]),
        notify_new_events=bool(row["notify_new_events"]),
        notify_odds_changes=bool(row["notify_odds_changes"]),
        change_percent_threshold=float(row["change_threshold_percent"]),
        enabled=bool(row["enabled"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def row_to_tracked_competition_subscription(
    row: sqlite3.Row,
) -> "TrackedCompetitionSubscription":
    from storage.tracking_repository import TrackedCompetitionSubscription

    from storage.tracking_repository import CompetitionSubscription, TrackedCompetition

    tracked_competition = TrackedCompetition(
        id=int(row["tracked_competition_id"]),
        platform=str(row["tracked_platform"]),
        source_url=str(row["tracked_source_url"]),
        competition_external_id=str(row["tracked_competition_external_id"]),
        competition_name=str(row["tracked_competition_name"]),
        metadata_json=row_optional_text(row, "tracked_metadata_json"),
        needs_name_resolution=bool(row["tracked_needs_name_resolution"]),
        enabled=bool(row["tracked_enabled"]),
        last_synced_at=row_optional_text(row, "tracked_last_refreshed_at"),
        consecutive_unavailable_refreshes=int(row["tracked_consecutive_unavailable_refreshes"]),
        last_unavailable_refresh_at=row_optional_text(row, "tracked_last_unavailable_refresh_at"),
        last_unavailable_reason=row_optional_text(row, "tracked_last_unavailable_reason"),
        last_unavailable_notification_at=row_optional_text(row, "tracked_last_unavailable_notification_at"),
        created_at=str(row["tracked_created_at"]),
        updated_at=str(row["tracked_updated_at"]),
    )
    subscription = CompetitionSubscription(
        telegram_chat_id=int(row["subscription_telegram_chat_id"]),
        tracked_competition_id=int(row["subscription_tracked_competition_id"]),
        notify_new_events=bool(row["subscription_notify_new_events"]),
        notify_odds_changes=bool(row["subscription_notify_odds_changes"]),
        change_percent_threshold=float(row["subscription_change_threshold_percent"]),
        enabled=bool(row["subscription_enabled"]),
        created_at=str(row["subscription_created_at"]),
        updated_at=str(row["subscription_updated_at"]),
    )
    return TrackedCompetitionSubscription(
        tracked_competition=tracked_competition,
        subscription=subscription,
    )


def row_to_active_event_record(row: sqlite3.Row) -> "ActiveEventRecord":
    from storage.tracking_repository import ActiveEventRecord

    return ActiveEventRecord(
        id=int(row["id"]),
        tracked_competition_id=int(row["tracked_competition_id"]),
        platform=str(row["platform"]),
        competition_external_id=str(row["competition_external_id"]),
        external_event_id=str(row["external_event_id"]),
        home=str(row["home"]),
        away=str(row["away"]),
        scheduled_label_date=row_optional_text(row, "scheduled_label_date"),
        scheduled_label_time=row_optional_text(row, "scheduled_label_time"),
        scheduled_at=row_optional_text(row, "scheduled_at"),
        event_url=row_optional_text(row, "event_url"),
        odds_home=row_optional_float(row, "odds_home"),
        odds_draw=row_optional_float(row, "odds_draw"),
        odds_away=row_optional_float(row, "odds_away"),
        markets_json=row_optional_text(row, "markets_json"),
        raw_payload_json=row_optional_text(row, "raw_payload_json"),
        alerted=row_optional_text(row, "reminder_sent_at") is not None,
        is_active=bool(row["is_active"]),
        first_seen_at=str(row["first_seen_at"]),
        last_seen_at=str(row["last_seen_at"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def row_to_event_baseline(row: sqlite3.Row) -> "EventBaseline":
    from storage.tracking_repository import EventBaseline

    return EventBaseline(
        telegram_chat_id=int(row["chat_id"]),
        active_event_id=int(row["active_event_id"]),
        tracked_competition_id=int(row["tracked_competition_id"]),
        external_event_id=str(row["external_event_id"]),
        baseline_home=row_optional_float(row, "baseline_odds_home"),
        baseline_draw=row_optional_float(row, "baseline_odds_draw"),
        baseline_away=row_optional_float(row, "baseline_odds_away"),
        baseline_markets_json=row_optional_text(row, "baseline_markets_json"),
        baseline_set_at=str(row["baseline_set_at"]),
        updated_at=str(row["updated_at"]),
    )


def row_to_small_change_record(row: sqlite3.Row) -> "SmallChangeRecord":
    from storage.tracking_repository import SmallChangeRecord

    return SmallChangeRecord(
        id=int(row["id"]),
        telegram_chat_id=int(row["chat_id"]),
        active_event_id=int(row["active_event_id"]),
        tracked_competition_id=int(row["tracked_competition_id"]),
        external_event_id=str(row["external_event_id"]),
        competition_name=str(row["competition_name"]),
        home=str(row["home"]),
        away=str(row["away"]),
        scheduled_label_date=row_optional_text(row, "scheduled_label_date"),
        scheduled_label_time=row_optional_text(row, "scheduled_label_time"),
        baseline_home=row_optional_float(row, "previous_odds_home"),
        baseline_draw=row_optional_float(row, "previous_odds_draw"),
        baseline_away=row_optional_float(row, "previous_odds_away"),
        current_home=row_optional_float(row, "current_odds_home"),
        current_draw=row_optional_float(row, "current_odds_draw"),
        current_away=row_optional_float(row, "current_odds_away"),
        max_percent_change=float(row["max_change_percent"]),
        payload_json=row_optional_text(row, "payload_json"),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        confirmed_at=row_optional_text(row, "confirmed_at"),
        dismissed_at=row_optional_text(row, "dismissed_at"),
    )


def row_optional_text(row: sqlite3.Row, key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    return str(value)


def row_optional_float(row: sqlite3.Row, key: str) -> float | None:
    value = row[key]
    if value is None:
        return None
    return float(value)


def json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


__all__ = [
    "json_dumps",
    "row_optional_float",
    "row_optional_text",
    "row_to_active_event_record",
    "row_to_event_baseline",
    "row_to_pending_request",
    "row_to_small_change_record",
    "row_to_subscription",
    "row_to_tracked_competition",
    "row_to_tracked_competition_subscription",
]
