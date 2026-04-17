"""Unified SQLite persistence for the Bet365 tracking workflow.

This module is the single source of truth for the simplified Bet365 bot.
It keeps two concepts clearly separated:

1. chat subscriptions:
   which Telegram chats track which leagues and with what notification flags
2. global league state:
   the current scraped fixtures and odds for each tracked league

That separation avoids duplicating scraped data when multiple chats follow
the same league.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_FILE_PATH = DATA_DIR / "bet365_tracking.sqlite3"


@dataclass(frozen=True)
class PendingTrackRequest:
    """Represent one unresolved `/track_url` request for a Telegram chat."""

    id: int
    telegram_chat_id: int
    platform: str
    url: str
    topic: str
    league_name: str
    requires_empty_confirmation: bool
    needs_name_resolution: bool
    payload_json: str | None
    created_at: str
    expires_at: str | None


@dataclass(frozen=True)
class TrackedLeague:
    """Represent one globally tracked Bet365 league."""

    id: int
    platform: str
    url: str
    topic: str
    league_name: str
    needs_name_resolution: bool
    enabled: bool
    last_scraped_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class LeagueSubscription:
    """Represent one chat subscription to a tracked Bet365 league."""

    telegram_chat_id: int
    tracked_league_id: int
    notify_new_matches: bool
    notify_odds_changes: bool
    change_percent_threshold: float
    enabled: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TrackedLeagueSubscription:
    """Combine tracked league metadata with chat-specific subscription flags."""

    tracked_league: TrackedLeague
    subscription: LeagueSubscription


@dataclass(frozen=True)
class ConfirmedTrackRequest:
    """Describe the result of confirming a pending Bet365 track request."""

    pending_request: PendingTrackRequest
    tracked_league: TrackedLeague
    subscription: LeagueSubscription


@dataclass(frozen=True)
class UntrackResult:
    """Describe what happened after a chat unsubscribed from a league."""

    tracked_league: TrackedLeague
    removed_subscription: bool
    league_disabled: bool
    removed_active_matches: int
    remaining_enabled_subscriptions: int


@dataclass(frozen=True)
class ActiveMatchUpsert:
    """Represent one active Bet365 match before it is persisted."""

    fixture_id: str
    home: str
    away: str
    kickoff_label_date: str | None
    kickoff_label_time: str | None
    kickoff_at: str | None
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None


@dataclass(frozen=True)
class ActiveMatchRecord:
    """Represent one currently stored Bet365 match row."""

    tracked_league_id: int
    fixture_id: str
    home: str
    away: str
    kickoff_label_date: str | None
    kickoff_label_time: str | None
    kickoff_at: str | None
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    alerted: bool
    last_seen_at: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MatchBaseline:
    """Represent one odds baseline for a chat and fixture."""

    telegram_chat_id: int
    tracked_league_id: int
    fixture_id: str
    baseline_home: float | None
    baseline_draw: float | None
    baseline_away: float | None
    updated_at: str


@dataclass(frozen=True)
class LittleChangeRecord:
    """Represent one pending or processed small odds change for a chat."""

    id: int
    telegram_chat_id: int
    tracked_league_id: int
    fixture_id: str
    league_name: str
    home: str
    away: str
    kickoff_label_date: str | None
    kickoff_label_time: str | None
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


def create_pending_track_request(
    chat_id: int,
    platform: str,
    url: str,
    extracted_metadata: dict[str, Any],
    *,
    requires_empty_confirmation: bool = False,
    needs_name_resolution: bool = False,
    expires_at: str | None = None,
) -> PendingTrackRequest:
    """Store a new pending Bet365 track request for one Telegram chat."""

    normalized_platform = _normalize_platform(platform)
    normalized_url = _normalize_url(url)
    topic = str(extracted_metadata.get("topic", "")).strip()
    league_name = str(extracted_metadata.get("league_name", "")).strip()

    if not topic:
        raise ValueError("Extracted metadata must include a non-empty topic.")

    if _is_invalid_label(league_name):
        raise ValueError("Extracted metadata must include a non-empty league_name.")

    payload_json = json.dumps(extracted_metadata, ensure_ascii=False, sort_keys=True)
    created_at = _utc_now_iso()

    with _connect() as connection:
        connection.execute(
            """
            DELETE FROM pending_track_requests
            WHERE telegram_chat_id = ?
            """,
            (chat_id,),
        )
        cursor = connection.execute(
            """
            INSERT INTO pending_track_requests (
                telegram_chat_id,
                platform,
                url,
                topic,
                league_name,
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
                topic,
                league_name,
                int(requires_empty_confirmation),
                int(needs_name_resolution),
                payload_json,
                created_at,
                expires_at,
            ),
        )
        pending_request_id = int(cursor.lastrowid)

    return PendingTrackRequest(
        id=pending_request_id,
        telegram_chat_id=chat_id,
        platform=normalized_platform,
        url=normalized_url,
        topic=topic,
        league_name=league_name,
        requires_empty_confirmation=requires_empty_confirmation,
        needs_name_resolution=needs_name_resolution,
        payload_json=payload_json,
        created_at=created_at,
        expires_at=expires_at,
    )


def get_latest_pending_track_request(chat_id: int) -> PendingTrackRequest | None:
    """Load the latest pending Bet365 track request for one Telegram chat."""

    now_iso = _utc_now_iso()

    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                telegram_chat_id,
                platform,
                url,
                topic,
                league_name,
                requires_empty_confirmation,
                needs_name_resolution,
                payload_json,
                created_at,
                expires_at
            FROM pending_track_requests
            WHERE telegram_chat_id = ?
              AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (chat_id, now_iso),
        ).fetchone()

    if row is None:
        return None

    return _row_to_pending_track_request(row)


def delete_pending_track_request(chat_id: int) -> bool:
    """Delete any pending track request for one Telegram chat."""

    with _connect() as connection:
        cursor = connection.execute(
            """
            DELETE FROM pending_track_requests
            WHERE telegram_chat_id = ?
            """,
            (chat_id,),
        )

    return cursor.rowcount > 0


def confirm_pending_track_request(chat_id: int) -> ConfirmedTrackRequest | None:
    """Confirm the latest pending Bet365 request and activate tracking."""

    pending_request = get_latest_pending_track_request(chat_id)

    if pending_request is None:
        return None

    now_iso = _utc_now_iso()

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO tracked_leagues (
                platform,
                url,
                topic,
                league_name,
                needs_name_resolution,
                enabled,
                last_scraped_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform, topic) DO UPDATE SET
                url = excluded.url,
                league_name = CASE
                    WHEN excluded.needs_name_resolution = 1
                     AND tracked_leagues.needs_name_resolution = 0
                    THEN tracked_leagues.league_name
                    ELSE excluded.league_name
                END,
                needs_name_resolution = CASE
                    WHEN excluded.needs_name_resolution = 1
                     AND tracked_leagues.needs_name_resolution = 0
                    THEN tracked_leagues.needs_name_resolution
                    ELSE excluded.needs_name_resolution
                END,
                enabled = 1,
                updated_at = excluded.updated_at
            """,
            (
                pending_request.platform,
                pending_request.url,
                pending_request.topic,
                pending_request.league_name,
                int(pending_request.needs_name_resolution),
                1,
                None,
                now_iso,
                now_iso,
            ),
        )

        tracked_league_row = connection.execute(
            """
            SELECT
                id,
                platform,
                url,
                topic,
                league_name,
                needs_name_resolution,
                enabled,
                last_scraped_at,
                created_at,
                updated_at
            FROM tracked_leagues
            WHERE platform = ? AND topic = ?
            """,
            (pending_request.platform, pending_request.topic),
        ).fetchone()

        if tracked_league_row is None:
            raise RuntimeError("Tracked league upsert succeeded but the row could not be reloaded.")

        tracked_league = _row_to_tracked_league(tracked_league_row)

        connection.execute(
            """
            INSERT INTO tracked_league_subscriptions (
                telegram_chat_id,
                tracked_league_id,
                notify_new_matches,
                notify_odds_changes,
                change_percent_threshold,
                enabled,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_chat_id, tracked_league_id) DO UPDATE SET
                notify_new_matches = excluded.notify_new_matches,
                notify_odds_changes = excluded.notify_odds_changes,
                change_percent_threshold = COALESCE(
                    tracked_league_subscriptions.change_percent_threshold,
                    excluded.change_percent_threshold
                ),
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                tracked_league.id,
                1,
                0,
                20.0,
                1,
                now_iso,
                now_iso,
            ),
        )

        subscription_row = connection.execute(
            """
            SELECT
                telegram_chat_id,
                tracked_league_id,
                notify_new_matches,
                notify_odds_changes,
                change_percent_threshold,
                enabled,
                created_at,
                updated_at
            FROM tracked_league_subscriptions
            WHERE telegram_chat_id = ? AND tracked_league_id = ?
            """,
            (chat_id, tracked_league.id),
        ).fetchone()

        connection.execute(
            """
            DELETE FROM pending_track_requests
            WHERE telegram_chat_id = ?
            """,
            (chat_id,),
        )

    if subscription_row is None:
        raise RuntimeError("Subscription upsert succeeded but the row could not be reloaded.")

    return ConfirmedTrackRequest(
        pending_request=pending_request,
        tracked_league=tracked_league,
        subscription=_row_to_subscription(subscription_row),
    )


def list_tracked_leagues(chat_id: int) -> list[TrackedLeagueSubscription]:
    """List confirmed tracked Bet365 leagues for one Telegram chat."""

    with _connect() as connection:
        _sanitize_tracking_state(connection)
        rows = connection.execute(
            """
            SELECT
                tl.id AS tracked_league_id,
                tl.platform AS tracked_league_platform,
                tl.url AS tracked_league_url,
                tl.topic AS tracked_league_topic,
                tl.league_name AS tracked_league_name,
                tl.needs_name_resolution AS tracked_league_needs_name_resolution,
                tl.enabled AS tracked_league_enabled,
                tl.last_scraped_at AS tracked_league_last_scraped_at,
                tl.created_at AS tracked_league_created_at,
                tl.updated_at AS tracked_league_updated_at,
                tls.telegram_chat_id AS subscription_chat_id,
                tls.tracked_league_id AS subscription_tracked_league_id,
                tls.notify_new_matches AS subscription_notify_new_matches,
                tls.notify_odds_changes AS subscription_notify_odds_changes,
                tls.change_percent_threshold AS subscription_change_percent_threshold,
                tls.enabled AS subscription_enabled,
                tls.created_at AS subscription_created_at,
                tls.updated_at AS subscription_updated_at
            FROM tracked_leagues tl
            INNER JOIN tracked_league_subscriptions tls
                ON tls.tracked_league_id = tl.id
            WHERE tls.telegram_chat_id = ?
              AND tls.enabled = 1
              AND tl.enabled = 1
              AND tl.league_name IS NOT NULL
              AND TRIM(tl.league_name) != ''
              AND LOWER(TRIM(tl.league_name)) != 'none'
              AND tl.topic IS NOT NULL
              AND TRIM(tl.topic) != ''
            ORDER BY tl.league_name, tl.id
            """,
            (chat_id,),
        ).fetchall()

    return [_row_to_tracked_league_subscription(row) for row in rows]


def list_globally_active_leagues() -> list[TrackedLeague]:
    """List leagues that are enabled and still have at least one subscriber."""

    with _connect() as connection:
        _sanitize_tracking_state(connection)
        rows = connection.execute(
            """
            SELECT
                tl.id,
                tl.platform,
                tl.url,
                tl.topic,
                tl.league_name,
                tl.needs_name_resolution,
                tl.enabled,
                tl.last_scraped_at,
                tl.created_at,
                tl.updated_at
            FROM tracked_leagues tl
            WHERE tl.enabled = 1
              AND tl.league_name IS NOT NULL
              AND TRIM(tl.league_name) != ''
              AND LOWER(TRIM(tl.league_name)) != 'none'
              AND tl.topic IS NOT NULL
              AND TRIM(tl.topic) != ''
              AND EXISTS (
                SELECT 1
                FROM tracked_league_subscriptions tls
                WHERE tls.tracked_league_id = tl.id
                  AND tls.enabled = 1
              )
            ORDER BY tl.platform, tl.league_name, tl.id
            """
        ).fetchall()

    return [_row_to_tracked_league(row) for row in rows]


def get_subscriptions_for_league(
    tracked_league_id: int,
    *,
    only_enabled: bool = True,
) -> list[LeagueSubscription]:
    """Load all subscriptions for one tracked league."""

    query = """
        SELECT
            telegram_chat_id,
            tracked_league_id,
            notify_new_matches,
            notify_odds_changes,
            change_percent_threshold,
            enabled,
            created_at,
            updated_at
        FROM tracked_league_subscriptions
        WHERE tracked_league_id = ?
    """
    params: tuple[object, ...] = (tracked_league_id,)

    if only_enabled:
        query += " AND enabled = 1"

    query += " ORDER BY telegram_chat_id"

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        rows = connection.execute(query, params).fetchall()

    return [_row_to_subscription(row) for row in rows]


def get_tracked_league(tracked_league_id: int) -> TrackedLeague | None:
    """Load one globally tracked league by identifier."""

    with _connect() as connection:
        _sanitize_tracking_state(connection)
        row = connection.execute(
            """
            SELECT
                id,
                platform,
                url,
                topic,
                league_name,
                needs_name_resolution,
                enabled,
                last_scraped_at,
                created_at,
                updated_at
            FROM tracked_leagues
            WHERE id = ?
              AND league_name IS NOT NULL
              AND TRIM(league_name) != ''
              AND LOWER(TRIM(league_name)) != 'none'
              AND topic IS NOT NULL
              AND TRIM(topic) != ''
            """,
            (tracked_league_id,),
        ).fetchone()

    if row is None:
        return None

    return _row_to_tracked_league(row)


def get_tracked_league_subscription(
    chat_id: int,
    tracked_league_id: int,
) -> TrackedLeagueSubscription | None:
    """Load one tracked league plus subscription for a specific chat."""

    with _connect() as connection:
        _sanitize_tracking_state(connection)
        row = connection.execute(
            """
            SELECT
                tl.id AS tracked_league_id,
                tl.platform AS tracked_league_platform,
                tl.url AS tracked_league_url,
                tl.topic AS tracked_league_topic,
                tl.league_name AS tracked_league_name,
                tl.needs_name_resolution AS tracked_league_needs_name_resolution,
                tl.enabled AS tracked_league_enabled,
                tl.last_scraped_at AS tracked_league_last_scraped_at,
                tl.created_at AS tracked_league_created_at,
                tl.updated_at AS tracked_league_updated_at,
                tls.telegram_chat_id AS subscription_chat_id,
                tls.tracked_league_id AS subscription_tracked_league_id,
                tls.notify_new_matches AS subscription_notify_new_matches,
                tls.notify_odds_changes AS subscription_notify_odds_changes,
                tls.change_percent_threshold AS subscription_change_percent_threshold,
                tls.enabled AS subscription_enabled,
                tls.created_at AS subscription_created_at,
                tls.updated_at AS subscription_updated_at
            FROM tracked_leagues tl
            INNER JOIN tracked_league_subscriptions tls
                ON tls.tracked_league_id = tl.id
            WHERE tls.telegram_chat_id = ? AND tls.tracked_league_id = ?
              AND tls.enabled = 1
              AND tl.enabled = 1
              AND tl.league_name IS NOT NULL
              AND TRIM(tl.league_name) != ''
              AND LOWER(TRIM(tl.league_name)) != 'none'
              AND tl.topic IS NOT NULL
              AND TRIM(tl.topic) != ''
            """,
            (chat_id, tracked_league_id),
        ).fetchone()

    if row is None:
        return None

    return _row_to_tracked_league_subscription(row)


def set_odds_notifications(
    chat_id: int,
    tracked_league_id: int,
    enabled: bool,
) -> LeagueSubscription:
    """Enable or disable odds-change notifications for one subscription."""

    now_iso = _utc_now_iso()

    with _connect() as connection:
        _sanitize_tracking_state(connection)
        cursor = connection.execute(
            """
            UPDATE tracked_league_subscriptions
            SET
                notify_odds_changes = ?,
                updated_at = ?
            WHERE telegram_chat_id = ? AND tracked_league_id = ?
              AND enabled = 1
            """,
            (int(enabled), now_iso, chat_id, tracked_league_id),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"No subscription found for chat_id={chat_id} and tracked_league_id={tracked_league_id}."
            )

        row = connection.execute(
            """
            SELECT
                telegram_chat_id,
                tracked_league_id,
                notify_new_matches,
                notify_odds_changes,
                change_percent_threshold,
                enabled,
                created_at,
                updated_at
            FROM tracked_league_subscriptions
            WHERE telegram_chat_id = ? AND tracked_league_id = ?
            """,
            (chat_id, tracked_league_id),
        ).fetchone()

    if row is None:
        raise RuntimeError("Subscription update succeeded but the row could not be reloaded.")

    return _row_to_subscription(row)


def set_change_percent_threshold(
    chat_id: int,
    tracked_league_id: int,
    percent: float,
) -> LeagueSubscription:
    """Update the alert sensitivity threshold for one subscription."""

    normalized_percent = float(percent)
    if normalized_percent <= 0:
        raise ValueError("El porcentaje mínimo de cambio debe ser mayor a 0.")

    now_iso = _utc_now_iso()

    with _connect() as connection:
        _sanitize_tracking_state(connection)
        cursor = connection.execute(
            """
            UPDATE tracked_league_subscriptions
            SET
                change_percent_threshold = ?,
                updated_at = ?
            WHERE telegram_chat_id = ? AND tracked_league_id = ?
              AND enabled = 1
            """,
            (normalized_percent, now_iso, chat_id, tracked_league_id),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"No subscription found for chat_id={chat_id} and tracked_league_id={tracked_league_id}."
            )

        row = connection.execute(
            """
            SELECT
                telegram_chat_id,
                tracked_league_id,
                notify_new_matches,
                notify_odds_changes,
                change_percent_threshold,
                enabled,
                created_at,
                updated_at
            FROM tracked_league_subscriptions
            WHERE telegram_chat_id = ? AND tracked_league_id = ?
            """,
            (chat_id, tracked_league_id),
        ).fetchone()

    if row is None:
        raise RuntimeError("Threshold update succeeded but the row could not be reloaded.")

    return _row_to_subscription(row)


def initialize_match_baselines(
    chat_id: int,
    tracked_league_id: int,
    matches: Sequence[ActiveMatchRecord],
) -> int:
    """Insert missing per-chat baselines for the provided matches."""

    payload = [
        (
            chat_id,
            tracked_league_id,
            match.fixture_id,
            _coerce_optional_float(match.odds_home),
            _coerce_optional_float(match.odds_draw),
            _coerce_optional_float(match.odds_away),
            _utc_now_iso(),
        )
        for match in matches
        if match.fixture_id.strip()
    ]

    if not payload:
        return 0

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        connection.executemany(
            """
            INSERT OR IGNORE INTO subscription_match_baselines (
                telegram_chat_id,
                tracked_league_id,
                fixture_id,
                baseline_home,
                baseline_draw,
                baseline_away,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )

    return len(payload)


def get_match_baseline(
    chat_id: int,
    tracked_league_id: int,
    fixture_id: str,
) -> MatchBaseline | None:
    """Load one per-chat baseline for a tracked fixture."""

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        row = connection.execute(
            """
            SELECT
                telegram_chat_id,
                tracked_league_id,
                fixture_id,
                baseline_home,
                baseline_draw,
                baseline_away,
                updated_at
            FROM subscription_match_baselines
            WHERE telegram_chat_id = ?
              AND tracked_league_id = ?
              AND fixture_id = ?
            """,
            (chat_id, tracked_league_id, fixture_id.strip()),
        ).fetchone()

    if row is None:
        return None

    return _row_to_match_baseline(row)


def upsert_match_baseline(
    chat_id: int,
    tracked_league_id: int,
    fixture_id: str,
    *,
    baseline_home: float | None,
    baseline_draw: float | None,
    baseline_away: float | None,
) -> MatchBaseline:
    """Create or replace one per-chat baseline row."""

    normalized_fixture_id = fixture_id.strip()
    if not normalized_fixture_id:
        raise ValueError("fixture_id must not be empty.")

    now_iso = _utc_now_iso()

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        connection.execute(
            """
            INSERT INTO subscription_match_baselines (
                telegram_chat_id,
                tracked_league_id,
                fixture_id,
                baseline_home,
                baseline_draw,
                baseline_away,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_chat_id, tracked_league_id, fixture_id) DO UPDATE SET
                baseline_home = excluded.baseline_home,
                baseline_draw = excluded.baseline_draw,
                baseline_away = excluded.baseline_away,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                tracked_league_id,
                normalized_fixture_id,
                _coerce_optional_float(baseline_home),
                _coerce_optional_float(baseline_draw),
                _coerce_optional_float(baseline_away),
                now_iso,
            ),
        )
        row = connection.execute(
            """
            SELECT
                telegram_chat_id,
                tracked_league_id,
                fixture_id,
                baseline_home,
                baseline_draw,
                baseline_away,
                updated_at
            FROM subscription_match_baselines
            WHERE telegram_chat_id = ?
              AND tracked_league_id = ?
              AND fixture_id = ?
            """,
            (chat_id, tracked_league_id, normalized_fixture_id),
        ).fetchone()

    if row is None:
        raise RuntimeError("Baseline upsert succeeded but the row could not be reloaded.")

    return _row_to_match_baseline(row)


def upsert_little_change(
    chat_id: int,
    tracked_league_id: int,
    fixture_id: str,
    *,
    home: str,
    away: str,
    kickoff_label_date: str | None,
    kickoff_label_time: str | None,
    baseline_home: float | None,
    baseline_draw: float | None,
    baseline_away: float | None,
    current_home: float | None,
    current_draw: float | None,
    current_away: float | None,
    max_percent_change: float,
    status: str = "pending",
) -> LittleChangeRecord:
    """Create or update one per-chat little-change record."""

    normalized_fixture_id = fixture_id.strip()
    normalized_home = home.strip()
    normalized_away = away.strip()
    normalized_status = status.strip().lower()

    if not normalized_fixture_id:
        raise ValueError("fixture_id must not be empty.")
    if not normalized_home or not normalized_away:
        raise ValueError("home and away must not be empty.")
    if normalized_status not in {"pending", "confirmed", "ignored"}:
        raise ValueError("status must be pending, confirmed, or ignored.")

    now_iso = _utc_now_iso()

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        connection.execute(
            """
            INSERT INTO little_changes (
                telegram_chat_id,
                tracked_league_id,
                fixture_id,
                home,
                away,
                kickoff_label_date,
                kickoff_label_time,
                baseline_home,
                baseline_draw,
                baseline_away,
                current_home,
                current_draw,
                current_away,
                max_percent_change,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_chat_id, tracked_league_id, fixture_id) DO UPDATE SET
                home = excluded.home,
                away = excluded.away,
                kickoff_label_date = excluded.kickoff_label_date,
                kickoff_label_time = excluded.kickoff_label_time,
                baseline_home = excluded.baseline_home,
                baseline_draw = excluded.baseline_draw,
                baseline_away = excluded.baseline_away,
                current_home = excluded.current_home,
                current_draw = excluded.current_draw,
                current_away = excluded.current_away,
                max_percent_change = excluded.max_percent_change,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                tracked_league_id,
                normalized_fixture_id,
                normalized_home,
                normalized_away,
                _normalize_optional_text(kickoff_label_date),
                _normalize_optional_text(kickoff_label_time),
                _coerce_optional_float(baseline_home),
                _coerce_optional_float(baseline_draw),
                _coerce_optional_float(baseline_away),
                _coerce_optional_float(current_home),
                _coerce_optional_float(current_draw),
                _coerce_optional_float(current_away),
                float(max_percent_change),
                normalized_status,
                now_iso,
                now_iso,
            ),
        )
        row = connection.execute(
            """
            SELECT
                lc.id,
                lc.telegram_chat_id,
                lc.tracked_league_id,
                lc.fixture_id,
                tl.league_name,
                lc.home,
                lc.away,
                lc.kickoff_label_date,
                lc.kickoff_label_time,
                lc.baseline_home,
                lc.baseline_draw,
                lc.baseline_away,
                lc.current_home,
                lc.current_draw,
                lc.current_away,
                lc.max_percent_change,
                lc.status,
                lc.created_at,
                lc.updated_at
            FROM little_changes lc
            INNER JOIN tracked_leagues tl ON tl.id = lc.tracked_league_id
            WHERE lc.telegram_chat_id = ?
              AND lc.tracked_league_id = ?
              AND lc.fixture_id = ?
            """,
            (chat_id, tracked_league_id, normalized_fixture_id),
        ).fetchone()

    if row is None:
        raise RuntimeError("Little change upsert succeeded but the row could not be reloaded.")

    return _row_to_little_change_record(row)


def list_pending_little_changes(chat_id: int) -> list[LittleChangeRecord]:
    """List pending little changes for one Telegram chat."""

    with _connect() as connection:
        _sanitize_tracking_state(connection)
        rows = connection.execute(
            """
            SELECT
                lc.id,
                lc.telegram_chat_id,
                lc.tracked_league_id,
                lc.fixture_id,
                tl.league_name,
                lc.home,
                lc.away,
                lc.kickoff_label_date,
                lc.kickoff_label_time,
                lc.baseline_home,
                lc.baseline_draw,
                lc.baseline_away,
                lc.current_home,
                lc.current_draw,
                lc.current_away,
                lc.max_percent_change,
                lc.status,
                lc.created_at,
                lc.updated_at
            FROM little_changes lc
            INNER JOIN tracked_leagues tl ON tl.id = lc.tracked_league_id
            INNER JOIN tracked_league_subscriptions tls
                ON tls.tracked_league_id = lc.tracked_league_id
               AND tls.telegram_chat_id = lc.telegram_chat_id
            WHERE lc.telegram_chat_id = ?
              AND lc.status = 'pending'
              AND tls.enabled = 1
              AND tl.enabled = 1
            ORDER BY lc.updated_at DESC, tl.league_name, lc.home, lc.away
            """,
            (chat_id,),
        ).fetchall()

    return [_row_to_little_change_record(row) for row in rows]


def confirm_little_change(chat_id: int, little_change_id: int) -> LittleChangeRecord:
    """Confirm one pending little change and move its baseline to current values."""

    with _connect() as connection:
        _sanitize_tracking_state(connection)
        row = connection.execute(
            """
            SELECT
                lc.id,
                lc.telegram_chat_id,
                lc.tracked_league_id,
                lc.fixture_id,
                tl.league_name,
                lc.home,
                lc.away,
                lc.kickoff_label_date,
                lc.kickoff_label_time,
                lc.baseline_home,
                lc.baseline_draw,
                lc.baseline_away,
                lc.current_home,
                lc.current_draw,
                lc.current_away,
                lc.max_percent_change,
                lc.status,
                lc.created_at,
                lc.updated_at
            FROM little_changes lc
            INNER JOIN tracked_leagues tl ON tl.id = lc.tracked_league_id
            WHERE lc.id = ?
              AND lc.telegram_chat_id = ?
            """,
            (little_change_id, chat_id),
        ).fetchone()

        if row is None:
            raise ValueError("No encontré ese little change para este chat.")

        record = _row_to_little_change_record(row)

        connection.execute(
            """
            INSERT INTO subscription_match_baselines (
                telegram_chat_id,
                tracked_league_id,
                fixture_id,
                baseline_home,
                baseline_draw,
                baseline_away,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_chat_id, tracked_league_id, fixture_id) DO UPDATE SET
                baseline_home = excluded.baseline_home,
                baseline_draw = excluded.baseline_draw,
                baseline_away = excluded.baseline_away,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                record.tracked_league_id,
                record.fixture_id,
                _coerce_optional_float(record.current_home),
                _coerce_optional_float(record.current_draw),
                _coerce_optional_float(record.current_away),
                _utc_now_iso(),
            ),
        )

        connection.execute(
            """
            UPDATE little_changes
            SET
                status = 'confirmed',
                updated_at = ?
            WHERE id = ?
            """,
            (_utc_now_iso(), little_change_id),
        )

        updated_row = connection.execute(
            """
            SELECT
                lc.id,
                lc.telegram_chat_id,
                lc.tracked_league_id,
                lc.fixture_id,
                tl.league_name,
                lc.home,
                lc.away,
                lc.kickoff_label_date,
                lc.kickoff_label_time,
                lc.baseline_home,
                lc.baseline_draw,
                lc.baseline_away,
                lc.current_home,
                lc.current_draw,
                lc.current_away,
                lc.max_percent_change,
                lc.status,
                lc.created_at,
                lc.updated_at
            FROM little_changes lc
            INNER JOIN tracked_leagues tl ON tl.id = lc.tracked_league_id
            WHERE lc.id = ?
            """,
            (little_change_id,),
        ).fetchone()

    if updated_row is None:
        raise RuntimeError("Little change confirmation succeeded but the row could not be reloaded.")

    return _row_to_little_change_record(updated_row)


def confirm_all_little_changes(chat_id: int) -> list[LittleChangeRecord]:
    """Confirm every pending little change for one chat."""

    pending_changes = list_pending_little_changes(chat_id)
    confirmed: list[LittleChangeRecord] = []

    for change in pending_changes:
        confirmed.append(confirm_little_change(chat_id, change.id))

    return confirmed


def resolve_little_change_with_current_baseline(
    chat_id: int,
    tracked_league_id: int,
    fixture_id: str,
) -> None:
    """Mark an existing little change as confirmed after an automatic baseline update."""

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        connection.execute(
            """
            UPDATE little_changes
            SET
                status = 'confirmed',
                updated_at = ?
            WHERE telegram_chat_id = ?
              AND tracked_league_id = ?
              AND fixture_id = ?
              AND status = 'pending'
            """,
            (_utc_now_iso(), chat_id, tracked_league_id, fixture_id.strip()),
        )


def remove_tracked_league_subscription(chat_id: int, tracked_league_id: int) -> UntrackResult:
    """Remove one chat subscription and disable the league if it becomes orphaned."""

    now_iso = _utc_now_iso()

    with _connect() as connection:
        _sanitize_tracking_state(connection)
        tracked_league_row = connection.execute(
            """
            SELECT
                id,
                platform,
                url,
                topic,
                league_name,
                needs_name_resolution,
                enabled,
                last_scraped_at,
                created_at,
                updated_at
            FROM tracked_leagues
            WHERE id = ?
            """,
            (tracked_league_id,),
        ).fetchone()

        if tracked_league_row is None:
            raise ValueError(f"No tracked league found with id={tracked_league_id}.")

        tracked_league = _row_to_tracked_league(tracked_league_row)

        cursor = connection.execute(
            """
            DELETE FROM tracked_league_subscriptions
            WHERE telegram_chat_id = ? AND tracked_league_id = ?
            """,
            (chat_id, tracked_league_id),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"No subscription found for chat_id={chat_id} and tracked_league_id={tracked_league_id}."
            )

        connection.execute(
            """
            DELETE FROM subscription_match_baselines
            WHERE telegram_chat_id = ? AND tracked_league_id = ?
            """,
            (chat_id, tracked_league_id),
        )
        connection.execute(
            """
            DELETE FROM little_changes
            WHERE telegram_chat_id = ? AND tracked_league_id = ?
            """,
            (chat_id, tracked_league_id),
        )

        remaining_enabled_subscriptions = _count_enabled_subscriptions(connection, tracked_league_id)
        league_disabled = False
        removed_active_matches = 0

        if remaining_enabled_subscriptions == 0:
            league_disabled = True

            connection.execute(
                """
                UPDATE tracked_leagues
                SET
                    enabled = 0,
                    updated_at = ?
                WHERE id = ?
                """,
                (now_iso, tracked_league_id),
            )

            removed_active_matches = connection.execute(
                """
                DELETE FROM active_matches
                WHERE tracked_league_id = ?
                """,
                (tracked_league_id,),
            ).rowcount

            tracked_league = TrackedLeague(
                id=tracked_league.id,
                platform=tracked_league.platform,
                url=tracked_league.url,
                topic=tracked_league.topic,
                league_name=tracked_league.league_name,
                needs_name_resolution=tracked_league.needs_name_resolution,
                enabled=False,
                last_scraped_at=tracked_league.last_scraped_at,
                created_at=tracked_league.created_at,
                updated_at=now_iso,
            )

    return UntrackResult(
        tracked_league=tracked_league,
        removed_subscription=True,
        league_disabled=league_disabled,
        removed_active_matches=removed_active_matches,
        remaining_enabled_subscriptions=remaining_enabled_subscriptions,
    )


def update_tracked_league(
    tracked_league_id: int,
    *,
    url: str,
    topic: str,
    league_name: str | None,
    needs_name_resolution: bool | None = None,
    last_scraped_at: str | None = None,
    enabled: bool | None = None,
) -> TrackedLeague:
    """Refresh metadata for one tracked league after a new scrape."""

    normalized_url = _normalize_url(url)
    normalized_topic = topic.strip()
    normalized_league_name = (league_name or "").strip()
    now_iso = _utc_now_iso()

    if not normalized_topic:
        raise ValueError("topic must not be empty.")

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)

        existing_row = connection.execute(
            """
            SELECT
                id,
                platform,
                url,
                topic,
                league_name,
                needs_name_resolution,
                enabled,
                last_scraped_at,
                created_at,
                updated_at
            FROM tracked_leagues
            WHERE id = ?
            """,
            (tracked_league_id,),
        ).fetchone()

        if existing_row is None:
            raise RuntimeError("Tracked league update could not load the current row.")

        existing_tracked_league = _row_to_tracked_league(existing_row)
        if _is_invalid_label(normalized_league_name):
            logger.info(
                "Preserving existing league_name for tracked_league_id=%s because extractor returned empty name.",
                tracked_league_id,
            )
            resolved_league_name = existing_tracked_league.league_name
            resolved_needs_name_resolution = existing_tracked_league.needs_name_resolution
        else:
            resolved_league_name = normalized_league_name
            resolved_needs_name_resolution = (
                existing_tracked_league.needs_name_resolution
                if needs_name_resolution is None
                else needs_name_resolution
            )

        if resolved_needs_name_resolution and not existing_tracked_league.needs_name_resolution:
            resolved_needs_name_resolution = False
            resolved_league_name = existing_tracked_league.league_name

        if _is_invalid_label(resolved_league_name):
            raise ValueError("league_name must not be empty.")

        if enabled is None:
            connection.execute(
                """
                UPDATE tracked_leagues
                SET
                    url = ?,
                    topic = ?,
                    league_name = ?,
                    needs_name_resolution = ?,
                    last_scraped_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    normalized_url,
                    normalized_topic,
                    resolved_league_name,
                    int(resolved_needs_name_resolution),
                    _normalize_optional_text(last_scraped_at),
                    now_iso,
                    tracked_league_id,
                ),
            )
        else:
            connection.execute(
                """
                UPDATE tracked_leagues
                SET
                    url = ?,
                    topic = ?,
                    league_name = ?,
                    needs_name_resolution = ?,
                    enabled = ?,
                    last_scraped_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    normalized_url,
                    normalized_topic,
                    resolved_league_name,
                    int(resolved_needs_name_resolution),
                    int(enabled),
                    _normalize_optional_text(last_scraped_at),
                    now_iso,
                    tracked_league_id,
                ),
            )

        row = connection.execute(
            """
            SELECT
                id,
                platform,
                url,
                topic,
                league_name,
                needs_name_resolution,
                enabled,
                last_scraped_at,
                created_at,
                updated_at
            FROM tracked_leagues
            WHERE id = ?
            """,
            (tracked_league_id,),
        ).fetchone()

    if row is None:
        raise RuntimeError("Tracked league update succeeded but the row could not be reloaded.")

    return _row_to_tracked_league(row)


def upsert_active_matches(
    tracked_league_id: int,
    matches: Sequence[ActiveMatchUpsert],
) -> int:
    """Insert or update the current active matches for one tracked league."""

    now_iso = _utc_now_iso()
    payload = []

    for match in matches:
        fixture_id = match.fixture_id.strip()
        home = match.home.strip()
        away = match.away.strip()

        if not fixture_id or not home or not away:
            raise ValueError("Each active Bet365 match must include fixture_id, home, and away.")

        payload.append(
            (
                tracked_league_id,
                fixture_id,
                home,
                away,
                _normalize_optional_text(match.kickoff_label_date),
                _normalize_optional_text(match.kickoff_label_time),
                _normalize_optional_text(match.kickoff_at),
                _coerce_optional_float(match.odds_home),
                _coerce_optional_float(match.odds_draw),
                _coerce_optional_float(match.odds_away),
                now_iso,
                now_iso,
                now_iso,
            )
        )

    if not payload:
        return 0

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        connection.executemany(
            """
            INSERT INTO active_matches (
                tracked_league_id,
                fixture_id,
                home,
                away,
                kickoff_label_date,
                kickoff_label_time,
                kickoff_at,
                odds_home,
                odds_draw,
                odds_away,
                alerted,
                last_seen_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            ON CONFLICT(tracked_league_id, fixture_id) DO UPDATE SET
                home = excluded.home,
                away = excluded.away,
                kickoff_label_date = excluded.kickoff_label_date,
                kickoff_label_time = excluded.kickoff_label_time,
                kickoff_at = excluded.kickoff_at,
                odds_home = excluded.odds_home,
                odds_draw = excluded.odds_draw,
                odds_away = excluded.odds_away,
                last_seen_at = excluded.last_seen_at,
                updated_at = excluded.updated_at
            """,
            payload,
        )

    return len(payload)


def remove_missing_matches(
    tracked_league_id: int,
    current_fixture_ids: Iterable[str],
) -> int:
    """Delete active matches that no longer appear in the latest scrape."""

    normalized_fixture_ids = sorted(
        {fixture_id.strip() for fixture_id in current_fixture_ids if fixture_id and fixture_id.strip()}
    )

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        if not normalized_fixture_ids:
            obsolete_fixture_ids = [
                str(row["fixture_id"])
                for row in connection.execute(
                    """
                    SELECT fixture_id
                    FROM active_matches
                    WHERE tracked_league_id = ?
                    ORDER BY fixture_id
                    """,
                    (tracked_league_id,),
                ).fetchall()
            ]
        else:
            placeholders = ", ".join("?" for _ in normalized_fixture_ids)
            obsolete_fixture_ids = [
                str(row["fixture_id"])
                for row in connection.execute(
                    f"""
                    SELECT fixture_id
                    FROM active_matches
                    WHERE tracked_league_id = ?
                      AND fixture_id NOT IN ({placeholders})
                    ORDER BY fixture_id
                    """,
                    (tracked_league_id, *normalized_fixture_ids),
                ).fetchall()
            ]

        deleted_rows = _delete_active_matches_by_fixture_ids(
            connection,
            tracked_league_id=tracked_league_id,
            fixture_ids=obsolete_fixture_ids,
        )

    return deleted_rows


def remove_past_matches(tracked_league_id: int, reference_time: str | None = None) -> int:
    """Delete matches whose kickoff is already in the past."""

    cutoff = _parse_iso_datetime(reference_time) if reference_time else datetime.now(timezone.utc)

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        rows = connection.execute(
            """
            SELECT fixture_id, kickoff_at
            FROM active_matches
            WHERE tracked_league_id = ?
            """,
            (tracked_league_id,),
        ).fetchall()

        obsolete_fixture_ids = []
        for row in rows:
            kickoff = _parse_iso_datetime(row["kickoff_at"])
            if kickoff is None:
                continue

            if kickoff < cutoff:
                obsolete_fixture_ids.append(str(row["fixture_id"]))

        deleted_rows = _delete_active_matches_by_fixture_ids(
            connection,
            tracked_league_id=tracked_league_id,
            fixture_ids=obsolete_fixture_ids,
        )

    return deleted_rows


def delete_active_matches(tracked_league_id: int) -> int:
    """Delete every stored active match for one tracked league."""

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        cursor = connection.execute(
            """
            DELETE FROM active_matches
            WHERE tracked_league_id = ?
            """,
            (tracked_league_id,),
        )

    return cursor.rowcount


def get_active_matches(
    tracked_league_id: int,
    *,
    only_future: bool = True,
) -> list[ActiveMatchRecord]:
    """Load currently stored active matches for one tracked league."""

    query = """
        SELECT
            tracked_league_id,
            fixture_id,
            home,
            away,
            kickoff_label_date,
            kickoff_label_time,
            kickoff_at,
            odds_home,
            odds_draw,
            odds_away,
            alerted,
            last_seen_at,
            created_at,
            updated_at
        FROM active_matches
        WHERE tracked_league_id = ?
    """

    query += " ORDER BY kickoff_at IS NULL, kickoff_at, home, away, fixture_id"

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        rows = connection.execute(query, (tracked_league_id,)).fetchall()

    matches = [_row_to_active_match_record(row) for row in rows]

    if not only_future:
        return matches

    return [match for match in matches if not _is_past_active_match(match)]


def mark_matches_alerted(
    tracked_league_id: int,
    fixture_ids: Iterable[str],
) -> int:
    """Mark one or more active matches as already reminder-alerted."""

    normalized_fixture_ids = sorted(
        {fixture_id.strip() for fixture_id in fixture_ids if fixture_id and fixture_id.strip()}
    )

    if not normalized_fixture_ids:
        return 0

    placeholders = ", ".join("?" for _ in normalized_fixture_ids)

    with _connect() as connection:
        _ensure_tracked_league_exists(connection, tracked_league_id)
        _sanitize_tracking_state(connection)
        cursor = connection.execute(
            f"""
            UPDATE active_matches
            SET
                alerted = 1,
                updated_at = ?
            WHERE tracked_league_id = ?
              AND fixture_id IN ({placeholders})
            """,
            (_utc_now_iso(), tracked_league_id, *normalized_fixture_ids),
        )

    return cursor.rowcount


def _connect() -> sqlite3.Connection:
    """Open a SQLite connection and lazily create the Bet365 schema."""

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_FILE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    _ensure_schema(connection)
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    """Create the minimal SQLite schema for Bet365 tracking if needed."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS pending_track_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_chat_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            url TEXT NOT NULL,
            topic TEXT NOT NULL,
            league_name TEXT NOT NULL,
            requires_empty_confirmation INTEGER NOT NULL DEFAULT 0,
            needs_name_resolution INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT,
            created_at TEXT NOT NULL,
            expires_at TEXT
        );

        CREATE TABLE IF NOT EXISTS tracked_leagues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            url TEXT NOT NULL,
            topic TEXT NOT NULL,
            league_name TEXT NOT NULL,
            needs_name_resolution INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (platform, topic),
            UNIQUE (platform, url)
        );

        CREATE TABLE IF NOT EXISTS tracked_league_subscriptions (
            telegram_chat_id INTEGER NOT NULL,
            tracked_league_id INTEGER NOT NULL,
            notify_new_matches INTEGER NOT NULL CHECK (notify_new_matches IN (0, 1)),
            notify_odds_changes INTEGER NOT NULL CHECK (notify_odds_changes IN (0, 1)),
            change_percent_threshold REAL NOT NULL DEFAULT 20.0,
            enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (telegram_chat_id, tracked_league_id),
            FOREIGN KEY (tracked_league_id) REFERENCES tracked_leagues(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS active_matches (
            tracked_league_id INTEGER NOT NULL,
            fixture_id TEXT NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            kickoff_label_date TEXT,
            kickoff_label_time TEXT,
            kickoff_at TEXT,
            odds_home REAL,
            odds_draw REAL,
            odds_away REAL,
            alerted INTEGER NOT NULL DEFAULT 0,
            last_seen_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (tracked_league_id, fixture_id),
            FOREIGN KEY (tracked_league_id) REFERENCES tracked_leagues(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS subscription_match_baselines (
            telegram_chat_id INTEGER NOT NULL,
            tracked_league_id INTEGER NOT NULL,
            fixture_id TEXT NOT NULL,
            baseline_home REAL,
            baseline_draw REAL,
            baseline_away REAL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (telegram_chat_id, tracked_league_id, fixture_id),
            FOREIGN KEY (tracked_league_id) REFERENCES tracked_leagues(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS little_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_chat_id INTEGER NOT NULL,
            tracked_league_id INTEGER NOT NULL,
            fixture_id TEXT NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            kickoff_label_date TEXT,
            kickoff_label_time TEXT,
            baseline_home REAL,
            baseline_draw REAL,
            baseline_away REAL,
            current_home REAL,
            current_draw REAL,
            current_away REAL,
            max_percent_change REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (telegram_chat_id, tracked_league_id, fixture_id),
            FOREIGN KEY (tracked_league_id) REFERENCES tracked_leagues(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_pending_track_requests_chat
            ON pending_track_requests (telegram_chat_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_tracked_league_subscriptions_chat
            ON tracked_league_subscriptions (telegram_chat_id, enabled);

        CREATE INDEX IF NOT EXISTS idx_active_matches_league
            ON active_matches (tracked_league_id, kickoff_at, last_seen_at);

        CREATE INDEX IF NOT EXISTS idx_match_baselines_chat
            ON subscription_match_baselines (telegram_chat_id, tracked_league_id);

        CREATE INDEX IF NOT EXISTS idx_little_changes_chat_status
            ON little_changes (telegram_chat_id, status, updated_at);
        """
    )

    _ensure_column(
        connection,
        table_name="tracked_leagues",
        column_name="last_scraped_at",
        definition="last_scraped_at TEXT",
    )
    _ensure_column(
        connection,
        table_name="tracked_leagues",
        column_name="needs_name_resolution",
        definition="needs_name_resolution INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(
        connection,
        table_name="pending_track_requests",
        column_name="requires_empty_confirmation",
        definition="requires_empty_confirmation INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(
        connection,
        table_name="pending_track_requests",
        column_name="needs_name_resolution",
        definition="needs_name_resolution INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(
        connection,
        table_name="active_matches",
        column_name="kickoff_label_date",
        definition="kickoff_label_date TEXT",
    )
    _ensure_column(
        connection,
        table_name="active_matches",
        column_name="kickoff_label_time",
        definition="kickoff_label_time TEXT",
    )
    _ensure_column(
        connection,
        table_name="active_matches",
        column_name="alerted",
        definition="alerted INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(
        connection,
        table_name="tracked_league_subscriptions",
        column_name="change_percent_threshold",
        definition="change_percent_threshold REAL NOT NULL DEFAULT 20.0",
    )
    _sanitize_tracking_state(connection)


def sanitize_tracking_state() -> None:
    """Clean inconsistent Bet365 rows already stored in SQLite."""

    with _connect() as connection:
        _sanitize_tracking_state(connection)


def _sanitize_tracking_state(connection: sqlite3.Connection) -> None:
    """Remove orphaned or invalid rows from the Bet365 tracking database."""

    connection.execute(
        """
        DELETE FROM pending_track_requests
        WHERE platform IS NULL
           OR TRIM(platform) = ''
           OR url IS NULL
           OR TRIM(url) = ''
           OR topic IS NULL
           OR TRIM(topic) = ''
           OR league_name IS NULL
           OR TRIM(league_name) = ''
           OR LOWER(TRIM(league_name)) = 'none'
        """
    )

    connection.execute(
        """
        DELETE FROM tracked_league_subscriptions
        WHERE tracked_league_id NOT IN (
            SELECT id FROM tracked_leagues
        )
        """
    )

    connection.execute(
        """
        DELETE FROM active_matches
        WHERE tracked_league_id NOT IN (
            SELECT id FROM tracked_leagues
        )
           OR fixture_id IS NULL
           OR TRIM(fixture_id) = ''
           OR home IS NULL
           OR TRIM(home) = ''
           OR away IS NULL
           OR TRIM(away) = ''
        """
    )

    connection.execute(
        """
        DELETE FROM subscription_match_baselines
        WHERE tracked_league_id NOT IN (
            SELECT id FROM tracked_leagues
        )
           OR fixture_id IS NULL
           OR TRIM(fixture_id) = ''
           OR NOT EXISTS (
               SELECT 1
               FROM tracked_league_subscriptions tls
               WHERE tls.telegram_chat_id = subscription_match_baselines.telegram_chat_id
                 AND tls.tracked_league_id = subscription_match_baselines.tracked_league_id
                 AND tls.enabled = 1
           )
        """
    )

    connection.execute(
        """
        DELETE FROM little_changes
        WHERE tracked_league_id NOT IN (
            SELECT id FROM tracked_leagues
        )
           OR fixture_id IS NULL
           OR TRIM(fixture_id) = ''
           OR home IS NULL
           OR TRIM(home) = ''
           OR away IS NULL
           OR TRIM(away) = ''
           OR status NOT IN ('pending', 'confirmed', 'ignored')
           OR NOT EXISTS (
               SELECT 1
               FROM tracked_league_subscriptions tls
               WHERE tls.telegram_chat_id = little_changes.telegram_chat_id
                 AND tls.tracked_league_id = little_changes.tracked_league_id
                 AND tls.enabled = 1
           )
        """
    )

    invalid_league_ids = [
        int(row["id"])
        for row in connection.execute(
            """
            SELECT id
            FROM tracked_leagues
            WHERE platform IS NULL
               OR TRIM(platform) = ''
               OR url IS NULL
               OR TRIM(url) = ''
               OR topic IS NULL
               OR TRIM(topic) = ''
               OR league_name IS NULL
               OR TRIM(league_name) = ''
               OR LOWER(TRIM(league_name)) = 'none'
            """
        ).fetchall()
    ]

    if invalid_league_ids:
        placeholders = ", ".join("?" for _ in invalid_league_ids)
        connection.execute(
            f"DELETE FROM tracked_league_subscriptions WHERE tracked_league_id IN ({placeholders})",
            tuple(invalid_league_ids),
        )
        connection.execute(
            f"DELETE FROM active_matches WHERE tracked_league_id IN ({placeholders})",
            tuple(invalid_league_ids),
        )
        connection.execute(
            f"DELETE FROM tracked_leagues WHERE id IN ({placeholders})",
            tuple(invalid_league_ids),
        )

    orphaned_league_ids = [
        int(row["id"])
        for row in connection.execute(
            """
            SELECT tl.id
            FROM tracked_leagues tl
            LEFT JOIN tracked_league_subscriptions tls
                ON tls.tracked_league_id = tl.id AND tls.enabled = 1
            GROUP BY tl.id
            HAVING COUNT(tls.telegram_chat_id) = 0
            """
        ).fetchall()
    ]

    if orphaned_league_ids:
        placeholders = ", ".join("?" for _ in orphaned_league_ids)
        connection.execute(
            f"DELETE FROM active_matches WHERE tracked_league_id IN ({placeholders})",
            tuple(orphaned_league_ids),
        )
        connection.execute(
            f"DELETE FROM tracked_leagues WHERE id IN ({placeholders})",
            tuple(orphaned_league_ids),
        )


def _ensure_column(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    """Add a missing column to an existing SQLite table when needed."""

    columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }

    if column_name in columns:
        return

    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {definition}")


def _ensure_tracked_league_exists(connection: sqlite3.Connection, tracked_league_id: int) -> None:
    """Validate that a tracked league exists before touching related rows."""

    row = connection.execute(
        "SELECT 1 FROM tracked_leagues WHERE id = ?",
        (tracked_league_id,),
    ).fetchone()

    if row is None:
        raise ValueError(f"No tracked league found with id={tracked_league_id}.")


def _delete_active_matches_by_fixture_ids(
    connection: sqlite3.Connection,
    *,
    tracked_league_id: int,
    fixture_ids: Sequence[str],
) -> int:
    """Delete specific active fixtures and log each deleted identifier."""

    normalized_fixture_ids = [fixture_id for fixture_id in fixture_ids if fixture_id]

    if not normalized_fixture_ids:
        return 0

    for fixture_id in normalized_fixture_ids:
        logger.info("Deleted obsolete match: %s", fixture_id)

    placeholders = ", ".join("?" for _ in normalized_fixture_ids)
    connection.execute(
        f"""
        DELETE FROM subscription_match_baselines
        WHERE tracked_league_id = ?
          AND fixture_id IN ({placeholders})
        """,
        (tracked_league_id, *normalized_fixture_ids),
    )
    connection.execute(
        f"""
        DELETE FROM little_changes
        WHERE tracked_league_id = ?
          AND fixture_id IN ({placeholders})
        """,
        (tracked_league_id, *normalized_fixture_ids),
    )
    cursor = connection.execute(
        f"""
        DELETE FROM active_matches
        WHERE tracked_league_id = ?
          AND fixture_id IN ({placeholders})
        """,
        (tracked_league_id, *normalized_fixture_ids),
    )
    return cursor.rowcount


def _count_enabled_subscriptions(connection: sqlite3.Connection, tracked_league_id: int) -> int:
    """Count active subscriptions for one tracked league."""

    row = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM tracked_league_subscriptions
        WHERE tracked_league_id = ? AND enabled = 1
        """,
        (tracked_league_id,),
    ).fetchone()

    if row is None:
        return 0

    return int(row["total"])


def _normalize_platform(platform: str) -> str:
    """Normalize the platform identifier before persistence."""

    normalized_platform = platform.strip().lower()

    if not normalized_platform:
        raise ValueError("platform must not be empty.")

    return normalized_platform


def _normalize_url(url: str) -> str:
    """Normalize a URL string before storing it in SQLite."""

    normalized_url = url.strip()

    if not normalized_url:
        raise ValueError("url must not be empty.")

    return normalized_url


def _normalize_optional_text(value: str | None) -> str | None:
    """Normalize optional text values before storing them."""

    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


def _is_invalid_label(value: str | None) -> bool:
    """Return whether a label is missing or effectively unusable."""

    if value is None:
        return True

    normalized_value = value.strip()
    return not normalized_value or normalized_value.lower() == "none"


def _coerce_optional_float(value: float | None) -> float | None:
    """Normalize optional odds values before persistence."""

    if value is None:
        return None

    return float(value)


def _row_to_pending_track_request(row: sqlite3.Row) -> PendingTrackRequest:
    """Convert one SQLite row into a `PendingTrackRequest`."""

    return PendingTrackRequest(
        id=int(row["id"]),
        telegram_chat_id=int(row["telegram_chat_id"]),
        platform=str(row["platform"]),
        url=str(row["url"]),
        topic=str(row["topic"]),
        league_name=str(row["league_name"]),
        requires_empty_confirmation=bool(row["requires_empty_confirmation"]),
        needs_name_resolution=bool(row["needs_name_resolution"]),
        payload_json=str(row["payload_json"]) if row["payload_json"] is not None else None,
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]) if row["expires_at"] is not None else None,
    )


def _row_to_tracked_league(row: sqlite3.Row) -> TrackedLeague:
    """Convert one SQLite row into a `TrackedLeague`."""

    return TrackedLeague(
        id=int(row["id"]),
        platform=str(row["platform"]),
        url=str(row["url"]),
        topic=str(row["topic"]),
        league_name=str(row["league_name"]),
        needs_name_resolution=bool(row["needs_name_resolution"]),
        enabled=bool(row["enabled"]),
        last_scraped_at=str(row["last_scraped_at"]) if row["last_scraped_at"] is not None else None,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_subscription(row: sqlite3.Row) -> LeagueSubscription:
    """Convert one SQLite row into a `LeagueSubscription`."""

    return LeagueSubscription(
        telegram_chat_id=int(row["telegram_chat_id"]),
        tracked_league_id=int(row["tracked_league_id"]),
        notify_new_matches=bool(row["notify_new_matches"]),
        notify_odds_changes=bool(row["notify_odds_changes"]),
        change_percent_threshold=float(row["change_percent_threshold"]),
        enabled=bool(row["enabled"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_tracked_league_subscription(row: sqlite3.Row) -> TrackedLeagueSubscription:
    """Convert a joined SQLite row into `TrackedLeagueSubscription`."""

    tracked_league = TrackedLeague(
        id=int(row["tracked_league_id"]),
        platform=str(row["tracked_league_platform"]),
        url=str(row["tracked_league_url"]),
        topic=str(row["tracked_league_topic"]),
        league_name=str(row["tracked_league_name"]),
        needs_name_resolution=bool(row["tracked_league_needs_name_resolution"]),
        enabled=bool(row["tracked_league_enabled"]),
        last_scraped_at=(
            str(row["tracked_league_last_scraped_at"])
            if row["tracked_league_last_scraped_at"] is not None
            else None
        ),
        created_at=str(row["tracked_league_created_at"]),
        updated_at=str(row["tracked_league_updated_at"]),
    )
    subscription = LeagueSubscription(
        telegram_chat_id=int(row["subscription_chat_id"]),
        tracked_league_id=int(row["subscription_tracked_league_id"]),
        notify_new_matches=bool(row["subscription_notify_new_matches"]),
        notify_odds_changes=bool(row["subscription_notify_odds_changes"]),
        change_percent_threshold=float(row["subscription_change_percent_threshold"]),
        enabled=bool(row["subscription_enabled"]),
        created_at=str(row["subscription_created_at"]),
        updated_at=str(row["subscription_updated_at"]),
    )

    return TrackedLeagueSubscription(
        tracked_league=tracked_league,
        subscription=subscription,
    )


def _row_to_active_match_record(row: sqlite3.Row) -> ActiveMatchRecord:
    """Convert one SQLite row into an `ActiveMatchRecord`."""

    return ActiveMatchRecord(
        tracked_league_id=int(row["tracked_league_id"]),
        fixture_id=str(row["fixture_id"]),
        home=str(row["home"]),
        away=str(row["away"]),
        kickoff_label_date=(
            str(row["kickoff_label_date"]) if row["kickoff_label_date"] is not None else None
        ),
        kickoff_label_time=(
            str(row["kickoff_label_time"]) if row["kickoff_label_time"] is not None else None
        ),
        kickoff_at=str(row["kickoff_at"]) if row["kickoff_at"] is not None else None,
        odds_home=_coerce_optional_float(row["odds_home"]),
        odds_draw=_coerce_optional_float(row["odds_draw"]),
        odds_away=_coerce_optional_float(row["odds_away"]),
        alerted=bool(row["alerted"]),
        last_seen_at=str(row["last_seen_at"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_match_baseline(row: sqlite3.Row) -> MatchBaseline:
    """Convert one SQLite row into a `MatchBaseline`."""

    return MatchBaseline(
        telegram_chat_id=int(row["telegram_chat_id"]),
        tracked_league_id=int(row["tracked_league_id"]),
        fixture_id=str(row["fixture_id"]),
        baseline_home=_coerce_optional_float(row["baseline_home"]),
        baseline_draw=_coerce_optional_float(row["baseline_draw"]),
        baseline_away=_coerce_optional_float(row["baseline_away"]),
        updated_at=str(row["updated_at"]),
    )


def _row_to_little_change_record(row: sqlite3.Row) -> LittleChangeRecord:
    """Convert one SQLite row into a `LittleChangeRecord`."""

    return LittleChangeRecord(
        id=int(row["id"]),
        telegram_chat_id=int(row["telegram_chat_id"]),
        tracked_league_id=int(row["tracked_league_id"]),
        fixture_id=str(row["fixture_id"]),
        league_name=str(row["league_name"]),
        home=str(row["home"]),
        away=str(row["away"]),
        kickoff_label_date=(
            str(row["kickoff_label_date"]) if row["kickoff_label_date"] is not None else None
        ),
        kickoff_label_time=(
            str(row["kickoff_label_time"]) if row["kickoff_label_time"] is not None else None
        ),
        baseline_home=_coerce_optional_float(row["baseline_home"]),
        baseline_draw=_coerce_optional_float(row["baseline_draw"]),
        baseline_away=_coerce_optional_float(row["baseline_away"]),
        current_home=_coerce_optional_float(row["current_home"]),
        current_draw=_coerce_optional_float(row["current_draw"]),
        current_away=_coerce_optional_float(row["current_away"]),
        max_percent_change=float(row["max_percent_change"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _parse_iso_datetime(value: object) -> datetime | None:
    """Parse one stored ISO timestamp into an aware UTC datetime."""

    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _is_past_active_match(match: ActiveMatchRecord) -> bool:
    """Return whether one stored active match already kicked off."""

    kickoff = _parse_iso_datetime(match.kickoff_at)

    if kickoff is None:
        return False

    return kickoff < datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""

    return datetime.now(timezone.utc).isoformat()
