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
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
import os
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
    row_to_stats_league_link as _row_to_stats_league_link,
    row_to_stats_league_subscription as _row_to_stats_league_subscription,
    row_to_stats_match_link as _row_to_stats_match_link,
    row_to_subscription as _row_to_subscription,
    row_to_tracked_competition as _row_to_tracked_competition,
    row_to_tracked_competition_subscription as _row_to_tracked_competition_subscription,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
# Ruta de la DB configurable por entorno (BETBOT_DB_PATH). Útil para smoke tests
# sin tocar la DB real: ej. BETBOT_DB_PATH=data/tracking.smoke.sqlite3
# Acepta ruta absoluta o relativa al root del proyecto. Sin la var, usa el default.
_db_path_env = os.environ.get("BETBOT_DB_PATH", "").strip()
if _db_path_env:
    _db_path = Path(_db_path_env)
    DB_FILE_PATH = _db_path if _db_path.is_absolute() else (PROJECT_ROOT / _db_path)
else:
    DB_FILE_PATH = DATA_DIR / "tracking.sqlite3"
DEFAULT_CHANGE_THRESHOLD_PERCENT = 20.0
DEFAULT_NOTIFY_ODDS_CHANGES = True
STATS_PAYLOAD_CACHE_MAX_ROWS = 200


# --- Tipos de dominio ---
# Definiciones UNIFICADAS en core/models.py (única fuente de verdad). Este módulo
# las RE-EXPORTA por compatibilidad con los consumidores legacy hasta que S9a/b/c
# los migren a importar de core.models directo. Antes estaban duplicadas acá.
from core.models import (
    ActiveEventRecord,
    ActiveEventUpsert,
    CompetitionSubscription,
    ConfirmedCompetitionTrackRequest,
    EventBaseline,
    LiveWatchEntry,
    LiveWatchSettings,
    PendingCompetitionTrackRequest,
    SmallChangeRecord,
    StatsLeagueLink,
    StatsLeagueSubscription,
    StatsMatchLinkRecord,
    TrackedCompetition,
    TrackedCompetitionSubscription,
    UntrackCompetitionResult,
)


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
                uc_id = _find_or_create_unified_competition_id(connection, pending_request.competition_name)
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
                        consecutive_unavailable_refreshes,
                        last_unavailable_refresh_at,
                        last_unavailable_reason,
                        last_unavailable_notification_at,
                        last_refreshed_at,
                        unified_competition_id,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1, 0, NULL, NULL, NULL, NULL, ?, ?, ?)
                    """,
                    (
                        pending_request.platform,
                        pending_request.competition_external_id,
                        pending_request.competition_name,
                        pending_request.source_url,
                        pending_request.payload_json,
                        int(pending_request.needs_name_resolution),
                        uc_id,
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
                uc_id = existing.unified_competition_id
                if uc_id is None:
                    uc_id = _find_or_create_unified_competition_id(connection, resolved_name)
                connection.execute(
                    """
                    UPDATE tracked_competitions
                    SET
                        source_url = ?,
                        competition_name = ?,
                        metadata_json = COALESCE(?, metadata_json),
                        needs_name_resolution = ?,
                        enabled = 1,
                        consecutive_unavailable_refreshes = 0,
                        last_unavailable_refresh_at = NULL,
                        last_unavailable_reason = NULL,
                        last_unavailable_notification_at = NULL,
                        unified_competition_id = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        pending_request.source_url,
                        resolved_name,
                        pending_request.payload_json,
                        int(resolved_needs_name_resolution),
                        uc_id,
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

            # League-level subscription: the chat inherits every other platform of
            # this league, and the league's subscribers inherit this platform.
            _propagate_unified_subscriptions(connection, uc_id)

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

    def auto_track_live_detected_league(
        self,
        chat_id: int,
        platform: str,
        competition_external_id: str,
        competition_name: str,
        source_url: str,
    ) -> int:
        """Automatically expand tracked_competitions and subscribe the chat to this league."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            
            tracked_row = _fetch_tracked_competition_by_identity_row(
                connection,
                platform,
                competition_external_id,
            )
            now_iso = _utc_now_iso()
            
            if tracked_row is None:
                uc_id = _find_or_create_unified_competition_id(connection, competition_name)
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
                        consecutive_unavailable_refreshes,
                        last_unavailable_refresh_at,
                        last_unavailable_reason,
                        last_unavailable_notification_at,
                        last_refreshed_at,
                        unified_competition_id,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, NULL, 0, 1, 0, NULL, NULL, NULL, NULL, ?, ?, ?)
                    """,
                    (
                        _normalize_platform(platform),
                        competition_external_id.strip(),
                        competition_name.strip(),
                        source_url.strip(),
                        uc_id,
                        now_iso,
                        now_iso,
                    ),
                )
                tracked_competition_id = int(cursor.lastrowid)
            else:
                existing = _row_to_tracked_competition(tracked_row)
                tracked_competition_id = existing.id
                uc_id = existing.unified_competition_id
                if uc_id is None:
                    uc_id = _find_or_create_unified_competition_id(connection, existing.competition_name)
                
                connection.execute(
                    """
                    UPDATE tracked_competitions
                    SET
                        enabled = 1,
                        unified_competition_id = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        uc_id,
                        now_iso,
                        tracked_competition_id,
                    ),
                )

            subscription_row = _fetch_subscription_row(connection, chat_id, tracked_competition_id)
            if subscription_row is None:
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
                    (
                        now_iso,
                        chat_id,
                        tracked_competition_id,
                    ),
                )

            _propagate_unified_subscriptions(connection, uc_id)

            return tracked_competition_id

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
                    tc.consecutive_unavailable_refreshes AS tracked_consecutive_unavailable_refreshes,
                    tc.last_unavailable_refresh_at AS tracked_last_unavailable_refresh_at,
                    tc.last_unavailable_reason AS tracked_last_unavailable_reason,
                    tc.last_unavailable_notification_at AS tracked_last_unavailable_notification_at,
                    tc.created_at AS tracked_created_at,
                    tc.updated_at AS tracked_updated_at,
                    tc.unified_competition_id AS tracked_unified_competition_id,
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
                LEFT JOIN unified_competitions uc ON uc.id = tc.unified_competition_id
                WHERE cs.telegram_chat_id = ?
                  AND cs.enabled = 1
                  AND tc.enabled = 1
                ORDER BY COALESCE(uc.name, tc.competition_name), tc.platform, tc.id
                """,
                (chat_id,),
            ).fetchall()

        return [_row_to_tracked_competition_subscription(row) for row in rows]

    def get_or_create_unified_competition(self, name: str) -> int:
        """Find or create a unified competition by name, returning its ID."""
        with _connect() as connection:
            _sanitize_tracking_state(connection)
            return _find_or_create_unified_competition_id(connection, name)

    def list_subscribed_unified_competitions(self, chat_id: int) -> list[dict[str, Any]]:
        """List distinct unified competitions with active subscriptions for a chat."""
        with _connect() as connection:
            _sanitize_tracking_state(connection)
            rows = connection.execute(
                """
                SELECT DISTINCT uc.id, uc.name
                FROM unified_competitions uc
                INNER JOIN tracked_competitions tc ON tc.unified_competition_id = uc.id
                INNER JOIN competition_subscriptions cs ON cs.tracked_competition_id = tc.id
                WHERE cs.telegram_chat_id = ?
                  AND cs.enabled = 1
                  AND tc.enabled = 1
                ORDER BY uc.name
                """,
                (chat_id,),
            ).fetchall()
        return [{"id": r["id"], "name": r["name"]} for r in rows]

    def list_tracked_competitions_for_unified(self, unified_competition_id: int) -> list[TrackedCompetition]:
        """List all tracked competitions linked to a unified competition."""
        with _connect() as connection:
            _sanitize_tracking_state(connection)
            rows = connection.execute(
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
                    consecutive_unavailable_refreshes,
                    last_unavailable_refresh_at,
                    last_unavailable_reason,
                    last_unavailable_notification_at,
                    created_at,
                    updated_at,
                    unified_competition_id
                FROM tracked_competitions
                WHERE unified_competition_id = ?
                  AND enabled = 1
                """,
                (unified_competition_id,),
            ).fetchall()
        return [_row_to_tracked_competition(row) for row in rows]

    def link_tracked_competition_to_unified(self, tracked_competition_id: int, unified_competition_id: int) -> None:
        """Link a tracked competition to a unified competition."""
        now_iso = _utc_now_iso()
        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            # Ensure unified competition exists
            row = connection.execute(
                "SELECT id FROM unified_competitions WHERE id = ?",
                (unified_competition_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unified competition ID {unified_competition_id} does not exist.")
            connection.execute(
                """
                UPDATE tracked_competitions
                SET unified_competition_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (unified_competition_id, now_iso, tracked_competition_id),
            )
            # Subscribers of the league inherit the newly linked platform (and
            # subscribers of the moved competition inherit the league's platforms).
            _propagate_unified_subscriptions(connection, unified_competition_id)

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
                    tc.consecutive_unavailable_refreshes,
                    tc.last_unavailable_refresh_at,
                    tc.last_unavailable_reason,
                    tc.last_unavailable_notification_at,
                    tc.created_at,
                    tc.updated_at,
                    tc.unified_competition_id
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

    def get_earliest_kickoffs(
        self, competition_ids: Sequence[int]
    ) -> dict[int, str | None]:
        """Map each competition id to its earliest active-event kickoff (UTC ISO).

        Used to schedule refreshes by proximity to kickoff. Events that already
        finished (older than IN_PLAY_GRACE) are excluded so they don't pin a
        league to the fast tier; ``None`` means no upcoming/in-play event.
        """

        ids = [int(cid) for cid in dict.fromkeys(competition_ids)]
        result: dict[int, str | None] = {cid: None for cid in ids}
        if not ids:
            return result

        floor_iso = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        placeholders = ",".join("?" for _ in ids)
        with _connect() as connection:
            rows = connection.execute(
                f"""
                SELECT tracked_competition_id AS cid, MIN(scheduled_at) AS earliest
                FROM active_events
                WHERE is_active = 1
                  AND scheduled_at IS NOT NULL
                  AND scheduled_at >= ?
                  AND tracked_competition_id IN ({placeholders})
                GROUP BY tracked_competition_id
                """,
                (floor_iso, *ids),
            ).fetchall()
        for row in rows:
            result[int(row["cid"])] = row["earliest"]
        return result

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

    def get_tracked_competition_by_identity(
        self,
        *,
        platform: str,
        competition_external_id: str,
    ) -> TrackedCompetition | None:
        """Load one tracked competition by platform plus external identity."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            row = _fetch_tracked_competition_by_identity_row(
                connection,
                platform,
                competition_external_id,
            )

        return _row_to_tracked_competition(row) if row is not None else None

    def get_enabled_subscription_count(self, tracked_competition_id: int) -> int:
        """Return how many enabled chat subscriptions share one competition."""

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            return _count_enabled_subscriptions(connection, tracked_competition_id)

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

            status_flags = 16
            if normalized_status == "confirmed":
                status_flags = 32
            elif normalized_status == "ignored":
                status_flags = 64

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
                    status_flags,
                    created_at,
                    updated_at,
                    confirmed_at,
                    dismissed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    status_flags = excluded.status_flags,
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
                    status_flags,
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
                    ae.scheduled_at,
                    sc.previous_odds_home,
                    sc.previous_odds_draw,
                    sc.previous_odds_away,
                    sc.current_odds_home,
                    sc.current_odds_draw,
                    sc.current_odds_away,
                    sc.max_change_percent,
                    sc.payload_json,
                    sc.status,
                    sc.status_flags,
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
                  AND sc.status_flags = 16
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
            active_event_row = connection.execute(
                """
                SELECT markets_json
                FROM active_events
                WHERE id = ?
                """,
                (record.active_event_id,),
            ).fetchone()
            baseline_markets_json = None
            if active_event_row is not None:
                baseline_markets_json = _normalize_optional_text(active_event_row["markets_json"])
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
                    record.active_event_id,
                    _coerce_optional_float(record.current_home),
                    _coerce_optional_float(record.current_draw),
                    _coerce_optional_float(record.current_away),
                    baseline_markets_json,
                    now_iso,
                    now_iso,
                ),
            )
            connection.execute(
                """
                UPDATE small_changes
                SET
                    status = 'confirmed',
                    status_flags = 32,
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
                    status_flags = 32,
                    confirmed_at = ?,
                    dismissed_at = NULL,
                    updated_at = ?
                WHERE chat_id = ?
                  AND active_event_id = ?
                  AND status_flags = 16
                """,
                (now_iso, now_iso, chat_id, int(event_row["id"])),
            )

    def remove_tracked_competition_subscription(
        self,
        chat_id: int,
        tracked_competition_id: int,
    ) -> UntrackCompetitionResult:
        """Remove one chat subscription and disable the competition if orphaned."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            return _remove_chat_subscription(connection, chat_id, tracked_competition_id)

    def remove_unified_subscription(
        self,
        chat_id: int,
        unified_competition_id: int,
    ) -> list[UntrackCompetitionResult]:
        """Untrack a whole unified league for one chat (all its platforms)."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            rows = connection.execute(
                """
                SELECT cs.tracked_competition_id
                FROM competition_subscriptions cs
                INNER JOIN tracked_competitions tc ON tc.id = cs.tracked_competition_id
                WHERE cs.telegram_chat_id = ? AND tc.unified_competition_id = ?
                ORDER BY cs.tracked_competition_id
                """,
                (chat_id, unified_competition_id),
            ).fetchall()
            if not rows:
                raise ValueError(
                    f"No subscriptions found for chat_id={chat_id} in unified league {unified_competition_id}."
                )
            return [
                _remove_chat_subscription(connection, chat_id, int(row["tracked_competition_id"]))
                for row in rows
            ]

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
                        consecutive_unavailable_refreshes = 0,
                        last_unavailable_refresh_at = NULL,
                        last_unavailable_reason = NULL,
                        last_unavailable_notification_at = NULL,
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
                        consecutive_unavailable_refreshes = 0,
                        last_unavailable_refresh_at = NULL,
                        last_unavailable_reason = NULL,
                        last_unavailable_notification_at = NULL,
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

    def update_tracked_competition_source(
        self,
        tracked_competition_id: int,
        *,
        source_url: str,
        competition_external_id: str,
        competition_name: str | None,
        needs_name_resolution: bool | None = None,
        payload: dict[str, Any] | None = None,
    ) -> TrackedCompetition:
        """Manually update the source URL and identity for one tracked competition."""

        normalized_url = _normalize_url(source_url)
        normalized_competition_id = competition_external_id.strip()
        payload_json = _json_dumps(payload)
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
            conflicting_row = _fetch_tracked_competition_by_identity_row(
                connection,
                existing_competition.platform,
                normalized_competition_id,
            )
            if conflicting_row is not None and int(conflicting_row["id"]) != tracked_competition_id:
                raise ValueError(
                    "La nueva URL apunta a una competencia que ya existe en el tracking."
                )

            resolved_name, resolved_needs_name_resolution = _resolve_competition_name(
                existing_competition.competition_name,
                existing_competition.needs_name_resolution,
                competition_name,
                needs_name_resolution,
            )

            connection.execute(
                """
                UPDATE tracked_competitions
                SET
                    source_url = ?,
                    competition_external_id = ?,
                    competition_name = ?,
                    metadata_json = COALESCE(?, metadata_json),
                    needs_name_resolution = ?,
                    consecutive_unavailable_refreshes = 0,
                    last_unavailable_refresh_at = NULL,
                    last_unavailable_reason = NULL,
                    last_unavailable_notification_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    normalized_url,
                    normalized_competition_id,
                    resolved_name,
                    payload_json,
                    int(resolved_needs_name_resolution),
                    now_iso,
                    tracked_competition_id,
                ),
            )
            connection.execute(
                """
                UPDATE active_events
                SET
                    competition_external_id = ?,
                    updated_at = ?
                WHERE tracked_competition_id = ?
                """,
                (
                    normalized_competition_id,
                    now_iso,
                    tracked_competition_id,
                ),
            )
            row = _fetch_tracked_competition_row(connection, tracked_competition_id)

        if row is None:
            raise RuntimeError("Tracked competition source update succeeded but the row could not be reloaded.")

        return _row_to_tracked_competition(row)

    def record_unavailable_refresh(
        self,
        tracked_competition_id: int,
        *,
        reason: str,
    ) -> TrackedCompetition:
        """Increment the unavailable-refresh state for one tracked competition."""

        normalized_reason = _normalize_optional_text(reason)
        now_iso = _utc_now_iso()

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            connection.execute(
                """
                UPDATE tracked_competitions
                SET
                    consecutive_unavailable_refreshes = consecutive_unavailable_refreshes + 1,
                    last_unavailable_refresh_at = ?,
                    last_unavailable_reason = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    now_iso,
                    normalized_reason,
                    now_iso,
                    tracked_competition_id,
                ),
            )
            row = _fetch_tracked_competition_row(connection, tracked_competition_id)

        if row is None:
            raise RuntimeError("Unavailable refresh state update succeeded but the row could not be reloaded.")

        return _row_to_tracked_competition(row)

    def should_send_unavailable_refresh_warning(
        self,
        tracked_competition_id: int,
        *,
        minimum_failures: int,
        cooldown_seconds: int,
    ) -> bool:
        """Return whether an unavailable-refresh warning should be sent now."""

        tracked_competition = self.get_tracked_competition(tracked_competition_id)
        if tracked_competition is None:
            return False

        if tracked_competition.consecutive_unavailable_refreshes < minimum_failures:
            return False

        last_notified_at = tracked_competition.last_unavailable_notification_at
        if last_notified_at is None:
            return True

        try:
            notified_at = datetime.fromisoformat(last_notified_at)
        except ValueError:
            return True

        if notified_at.tzinfo is None:
            notified_at = notified_at.replace(tzinfo=timezone.utc)

        elapsed_seconds = (datetime.now(timezone.utc) - notified_at.astimezone(timezone.utc)).total_seconds()
        return elapsed_seconds >= cooldown_seconds

    def mark_unavailable_refresh_warning_sent(self, tracked_competition_id: int) -> None:
        """Persist that an unavailable-refresh warning was sent recently."""

        now_iso = _utc_now_iso()

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            _sanitize_tracking_state(connection)
            connection.execute(
                """
                UPDATE tracked_competitions
                SET
                    last_unavailable_notification_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now_iso, now_iso, tracked_competition_id),
            )

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
        *,
        remove_after_cycles: int = 1,
    ) -> int:
        """Soft-remove active events that no longer appear in the latest refresh."""

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

            now_iso = _utc_now_iso()
            rows_to_delete: list[tuple[int]] = []

            for row in obsolete_rows:
                raw_payload = _loads_json_object(row["raw_payload_json"])
                next_missing_count = int(raw_payload.get("missing_seen_count", 0)) + 1

                if next_missing_count >= max(1, remove_after_cycles):
                    rows_to_delete.append((int(row["id"]),))
                    continue

                raw_payload["missing_seen_count"] = next_missing_count
                raw_payload["missing_updated_at"] = now_iso
                raw_payload["status"] = "missing"

                connection.execute(
                    """
                    UPDATE active_events
                    SET
                        raw_payload_json = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (_json_dumps(raw_payload), now_iso, int(row["id"])),
                )

            if rows_to_delete:
                connection.executemany(
                    """
                    DELETE FROM active_events
                    WHERE id = ?
                    """,
                    rows_to_delete,
                )

        deleted_event_ids = {
            int(row_id)
            for (row_id,) in rows_to_delete
        }
        for row in obsolete_rows:
            if int(row["id"]) in deleted_event_ids:
                logger.info("Deleted obsolete match: %s", str(row["external_event_id"]))
            else:
                logger.info(
                    "Keeping temporarily missing match: %s missing_seen_count=%s",
                    str(row["external_event_id"]),
                    int(_loads_json_object(row["raw_payload_json"]).get("missing_seen_count", 0)) + 1,
                )

        return len(rows_to_delete)

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
            if _is_future_or_unscheduled(record.scheduled_at, now_utc) and not record.is_missing
        ]

    def get_active_events_for_unified_competition(
        self,
        unified_competition_id: int,
        *,
        only_future: bool = True,
    ) -> list[ActiveEventRecord]:
        """Return the current active events for all tracked competitions linked to this unified competition."""

        with _connect() as connection:
            _sanitize_tracking_state(connection)
            rows = connection.execute(
                """
                SELECT
                    ae.id,
                    ae.tracked_competition_id,
                    ae.platform,
                    ae.competition_external_id,
                    ae.external_event_id,
                    ae.home,
                    ae.away,
                    ae.scheduled_label_date,
                    ae.scheduled_label_time,
                    ae.scheduled_at,
                    ae.event_url,
                    ae.odds_home,
                    ae.odds_draw,
                    ae.odds_away,
                    ae.markets_json,
                    ae.raw_payload_json,
                    ae.reminder_sent_at,
                    ae.is_active,
                    ae.first_seen_at,
                    ae.last_seen_at,
                    ae.created_at,
                    ae.updated_at
                FROM active_events ae
                INNER JOIN tracked_competitions tc ON tc.id = ae.tracked_competition_id
                WHERE tc.unified_competition_id = ?
                  AND ae.is_active = 1
                ORDER BY ae.scheduled_at IS NULL, ae.scheduled_at, ae.home, ae.away, ae.id
                """,
                (unified_competition_id,),
            ).fetchall()

        records = [_row_to_active_event_record(row) for row in rows]

        if not only_future:
            return records

        now_utc = datetime.now(timezone.utc)
        return [
            record
            for record in records
            if _is_future_or_unscheduled(record.scheduled_at, now_utc) and not record.is_missing
        ]

    def upsert_stats_league_link(
        self,
        tracked_competition_id: int,
        *,
        stats_provider: str,
        stats_league_id: str,
        stats_league_name: str,
        stats_country_name: str | None = None,
        confidence: float = 1.0,
        payload: dict[str, Any] | None = None,
    ) -> StatsLeagueLink:
        """Create or update the stats-provider league linked to a tracked competition."""

        normalized_provider = _normalize_platform(stats_provider)
        normalized_league_id = stats_league_id.strip()
        normalized_league_name = stats_league_name.strip()
        if not normalized_league_id:
            raise ValueError("stats_league_id must not be empty.")
        if _is_invalid_label(normalized_league_name):
            raise ValueError("stats_league_name must not be empty.")

        now_iso = _utc_now_iso()
        payload_json = _json_dumps(payload)

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            uc_row = connection.execute(
                "SELECT unified_competition_id FROM tracked_competitions WHERE id = ?",
                (tracked_competition_id,),
            ).fetchone()
            uc_id = uc_row["unified_competition_id"] if uc_row else None

            # The link belongs to the unified league: updating it from any platform
            # updates the single shared row (inheritance across platforms).
            existing = None
            if uc_id is not None:
                existing = connection.execute(
                    "SELECT id FROM stats_league_links WHERE unified_competition_id = ? AND stats_provider = ?",
                    (uc_id, normalized_provider),
                ).fetchone()
            if existing is None:
                existing = connection.execute(
                    "SELECT id FROM stats_league_links WHERE tracked_competition_id = ? AND stats_provider = ?",
                    (tracked_competition_id, normalized_provider),
                ).fetchone()

            if existing is not None:
                connection.execute(
                    """
                    UPDATE stats_league_links
                    SET tracked_competition_id = ?, unified_competition_id = ?,
                        stats_league_id = ?, stats_league_name = ?, stats_country_name = ?,
                        confidence = ?, payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        tracked_competition_id,
                        uc_id,
                        normalized_league_id,
                        normalized_league_name,
                        _normalize_optional_text(stats_country_name),
                        float(confidence),
                        payload_json,
                        now_iso,
                        existing["id"],
                    ),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO stats_league_links (
                        tracked_competition_id,
                        unified_competition_id,
                        stats_provider,
                        stats_league_id,
                        stats_league_name,
                        stats_country_name,
                        confidence,
                        payload_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tracked_competition_id,
                        uc_id,
                        normalized_provider,
                        normalized_league_id,
                        normalized_league_name,
                        _normalize_optional_text(stats_country_name),
                        float(confidence),
                        payload_json,
                        now_iso,
                        now_iso,
                    ),
                )
            row = _fetch_stats_league_link_row(connection, tracked_competition_id, stats_provider=normalized_provider)

        if row is None:
            raise RuntimeError("Stats league link was upserted but could not be reloaded.")
        return _row_to_stats_league_link(row)

    def get_stats_league_link(self, tracked_competition_id: int, stats_provider: str | None = None) -> StatsLeagueLink | None:
        """Return a specific stats-provider league link or the first one linked (supporting unified leagues)."""
        links = self.list_stats_league_links(tracked_competition_id)
        if not links:
            return None
        if stats_provider:
            normalized = _normalize_platform(stats_provider)
            for link in links:
                if link.stats_provider == normalized:
                    return link
        return links[0]

    def list_stats_league_links(self, tracked_competition_id: int) -> list[StatsLeagueLink]:
        """Return all stats-provider league links associated with a tracked competition (and implicitly its unified league)."""

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            uc_row = connection.execute(
                "SELECT unified_competition_id FROM tracked_competitions WHERE id = ?",
                (tracked_competition_id,),
            ).fetchone()
            
            uc_id = uc_row["unified_competition_id"] if uc_row else None
            
            if uc_id is not None:
                # Direct unified-level read: links belong to the league, so every
                # platform of the league sees them (also covers legacy rows whose
                # unified column was backfilled from their tracked competition).
                rows = connection.execute(
                    """
                    SELECT
                        id,
                        tracked_competition_id,
                        stats_provider,
                        stats_league_id,
                        stats_league_name,
                        stats_country_name,
                        confidence,
                        payload_json,
                        created_at,
                        updated_at
                    FROM stats_league_links
                    WHERE unified_competition_id = ?
                    """,
                    (uc_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT
                        id,
                        tracked_competition_id,
                        stats_provider,
                        stats_league_id,
                        stats_league_name,
                        stats_country_name,
                        confidence,
                        payload_json,
                        created_at,
                        updated_at
                    FROM stats_league_links
                    WHERE tracked_competition_id = ?
                    """,
                    (tracked_competition_id,),
                ).fetchall()

        seen = set()
        links = []
        for row in rows:
            link = _row_to_stats_league_link(row)
            key = (link.stats_provider, link.stats_league_id)
            if key not in seen:
                seen.add(key)
                links.append(link)
        return links

    def upsert_stats_league_subscription(
        self,
        chat_id: int,
        *,
        stats_provider: str,
        stats_league_id: str,
        stats_league_name: str,
        stats_country_name: str | None = None,
        source_url: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> StatsLeagueSubscription:
        """Follow one stats league without requiring a sportsbook competition."""

        normalized_provider = _normalize_platform(stats_provider)
        normalized_league_id = stats_league_id.strip()
        normalized_league_name = stats_league_name.strip()
        if not normalized_league_id:
            raise ValueError("stats_league_id must not be empty.")
        if _is_invalid_label(normalized_league_name):
            raise ValueError("stats_league_name must not be empty.")

        now_iso = _utc_now_iso()
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO stats_league_subscriptions (
                    telegram_chat_id,
                    stats_provider,
                    stats_league_id,
                    stats_league_name,
                    stats_country_name,
                    source_url,
                    payload_json,
                    enabled,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(telegram_chat_id, stats_provider, stats_league_id) DO UPDATE SET
                    stats_league_name = excluded.stats_league_name,
                    stats_country_name = excluded.stats_country_name,
                    source_url = excluded.source_url,
                    payload_json = excluded.payload_json,
                    enabled = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    int(chat_id),
                    normalized_provider,
                    normalized_league_id,
                    normalized_league_name,
                    _normalize_optional_text(stats_country_name),
                    _normalize_optional_text(source_url),
                    _json_dumps(payload),
                    now_iso,
                    now_iso,
                ),
            )
            row = _fetch_stats_league_subscription_row(
                connection,
                int(chat_id),
                normalized_provider,
                normalized_league_id,
            )
        if row is None:
            raise RuntimeError("Stats league subscription was upserted but could not be reloaded.")
        return _row_to_stats_league_subscription(row)

    def list_stats_league_subscriptions(
        self,
        chat_id: int,
        *,
        only_enabled: bool = True,
    ) -> list[StatsLeagueSubscription]:
        """Return provider-native stats leagues followed by one chat."""

        query = """
            SELECT
                telegram_chat_id,
                stats_provider,
                stats_league_id,
                stats_league_name,
                stats_country_name,
                source_url,
                payload_json,
                enabled,
                created_at,
                updated_at
            FROM stats_league_subscriptions
            WHERE telegram_chat_id = ?
        """
        parameters: list[Any] = [int(chat_id)]
        if only_enabled:
            query += " AND enabled = 1"
        query += " ORDER BY stats_country_name, stats_league_name, stats_provider"
        with _connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_row_to_stats_league_subscription(row) for row in rows]

    def list_globally_active_stats_leagues(self) -> list[StatsLeagueSubscription]:
        """Return enabled standalone stats subscriptions across all chats."""

        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    telegram_chat_id,
                    stats_provider,
                    stats_league_id,
                    stats_league_name,
                    stats_country_name,
                    source_url,
                    payload_json,
                    enabled,
                    created_at,
                    updated_at
                FROM stats_league_subscriptions
                WHERE enabled = 1
                ORDER BY stats_provider, stats_league_id, telegram_chat_id
                """
            ).fetchall()
        return [_row_to_stats_league_subscription(row) for row in rows]

    def delete_stats_league_subscription(
        self,
        chat_id: int,
        *,
        stats_provider: str,
        stats_league_id: str,
    ) -> bool:
        """Stop following one standalone stats league for one chat."""

        with _connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM stats_league_subscriptions
                WHERE telegram_chat_id = ?
                  AND stats_provider = ?
                  AND stats_league_id = ?
                """,
                (int(chat_id), _normalize_platform(stats_provider), stats_league_id.strip()),
            )
        return cursor.rowcount > 0

    def get_cached_stats_payload(self, cache_key: str) -> dict[str, Any] | None:
        """Return a cached stats payload if present and not expired, else None.

        Backs the anti-ban / latency cache: expensive provider payloads are stored
        so repeated reads of a tracked league's stats do not hit Sportradar again.
        """

        now_iso = _utc_now_iso()
        with _connect() as connection:
            row = connection.execute(
                "SELECT payload_json, expires_at FROM stats_payload_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None or str(row["expires_at"]) <= now_iso:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None

    def set_cached_stats_payload(self, cache_key: str, payload: dict[str, Any], *, ttl_seconds: float) -> None:
        """Persist a stats payload under cache_key with a TTL (seconds)."""

        fetched = datetime.now(timezone.utc)
        expires = fetched + timedelta(seconds=max(1.0, float(ttl_seconds)))
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO stats_payload_cache (cache_key, payload_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    fetched_at = excluded.fetched_at,
                    expires_at = excluded.expires_at
                """,
                (cache_key, _json_dumps(payload), fetched.isoformat(), expires.isoformat()),
            )
            _enforce_stats_payload_cache_limit(connection)

    def purge_expired_stats_payloads(self) -> int:
        """Delete cached stats payloads past their TTL. Returns rows removed.

        Expired rows are only skipped on read (get_cached_stats_payload), never
        deleted, so without this they linger. Run periodically (daily job).
        """

        now_iso = datetime.now(timezone.utc).isoformat()
        with _connect() as connection:
            cursor = connection.execute(
                "DELETE FROM stats_payload_cache WHERE expires_at < ?",
                (now_iso,),
            )
            return cursor.rowcount

    # ----- live watch -----

    def add_live_watch(
        self,
        chat_id: int,
        *,
        home: str,
        away: str,
        league_hint: str | None = None,
        note: str | None = None,
        kickoff_at: str | None = None,
    ) -> LiveWatchEntry:
        """Add a fixture to a chat's live-watch list (status 'watching')."""

        now_iso = _utc_now_iso()
        with _connect() as connection:
            row_max = connection.execute(
                "SELECT COALESCE(MAX(chat_local_id), 0) as max_id FROM live_watch_entries WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            next_local_id = (row_max["max_id"] or 0) + 1

            cursor = connection.execute(
                """
                INSERT INTO live_watch_entries
                    (chat_id, chat_local_id, home, away, league_hint, note, status, created_at, kickoff_at, status_flags)
                VALUES (?, ?, ?, ?, ?, ?, 'watching', ?, ?, 1)
                """,
                (
                    chat_id,
                    next_local_id,
                    home.strip(),
                    away.strip(),
                    (league_hint or None),
                    (note or None),
                    now_iso,
                    kickoff_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM live_watch_entries WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return _row_to_live_watch(row)

    def list_live_watches(self, chat_id: int, *, status: str | None = None) -> list[LiveWatchEntry]:
        """Return a chat's live-watch entries, optionally filtered by status."""

        with _connect() as connection:
            if status == "watching":
                rows = connection.execute(
                    "SELECT * FROM live_watch_entries WHERE chat_id = ? AND status = 'watching' ORDER BY id",
                    (chat_id,),
                ).fetchall()
            elif status == "fired":
                rows = connection.execute(
                    "SELECT * FROM live_watch_entries WHERE chat_id = ? AND fired_platforms IS NOT NULL AND fired_platforms != '' ORDER BY id",
                    (chat_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM live_watch_entries WHERE chat_id = ? ORDER BY id", (chat_id,)
                ).fetchall()
        return [_row_to_live_watch(row) for row in rows]

    def get_live_watch(self, chat_id: int, watch_id: int) -> LiveWatchEntry | None:
        """Get one live-watch entry by its database ID for a chat."""

        with _connect() as connection:
            row = connection.execute(
                "SELECT * FROM live_watch_entries WHERE id = ? AND chat_id = ?",
                (watch_id, chat_id),
            ).fetchone()
        return _row_to_live_watch(row) if row else None

    def get_live_watch_by_local_id(self, chat_id: int, local_id: int) -> LiveWatchEntry | None:
        """Get one live-watch entry by chat_local_id for a chat."""

        with _connect() as connection:
            row = connection.execute(
                "SELECT * FROM live_watch_entries WHERE chat_local_id = ? AND chat_id = ?",
                (local_id, chat_id),
            ).fetchone()
        return _row_to_live_watch(row) if row else None

    def list_all_active_live_watches(self) -> list[LiveWatchEntry]:
        """Return every still-watching entry across all chats (for the poller)."""

        with _connect() as connection:
            rows = connection.execute(
                "SELECT * FROM live_watch_entries WHERE status = 'watching' ORDER BY chat_id, id"
            ).fetchall()
        return [_row_to_live_watch(row) for row in rows]

    def mark_live_watch_fired(
        self,
        watch_id: int,
        *,
        platform: str,
        event_id: str,
        minute: str | None,
    ) -> None:
        """Mark a platform as fired for this watch entry."""

        with _connect() as connection:
            row = connection.execute(
                "SELECT fired_platforms, fired_odds_mask FROM live_watch_entries WHERE id = ?", (watch_id,)
            ).fetchone()
            current = row["fired_platforms"] if row else None
            current_mask = row["fired_odds_mask"] if row and row["fired_odds_mask"] is not None else 0

            flag = _platform_to_odds_flag(platform)
            new_mask = current_mask | flag

            if current:
                platforms_list = [p.strip() for p in current.split(",") if p.strip()]
                if platform not in platforms_list:
                    platforms_list.append(platform)
                new_val = ",".join(platforms_list)
            else:
                new_val = platform

            connection.execute(
                """
                UPDATE live_watch_entries
                SET fired_platforms = ?, fired_odds_mask = ?, matched_platform = ?, matched_event_id = ?,
                    matched_minute = ?, fired_at = ?
                WHERE id = ?
                """,
                (new_val, new_mask, platform, event_id, minute, _utc_now_iso(), watch_id),
            )

    def mark_live_watch_prematch_seen(self, watch_id: int, *, platform: str, event_id: str) -> None:
        """Record that a watched fixture was listed in prematch (one-shot, stays watching)."""

        with _connect() as connection:
            connection.execute(
                """
                UPDATE live_watch_entries
                SET prematch_seen_at = ?, prematch_platform = ?, matched_event_id = COALESCE(matched_event_id, ?)
                WHERE id = ?
                """,
                (_utc_now_iso(), platform, event_id, watch_id),
            )

    def mark_live_watch_prematch_fired(
        self,
        watch_id: int,
        *,
        platform: str,
        event_id: str,
    ) -> None:
        """Mark a platform as fired in prematch for this watch entry."""

        with _connect() as connection:
            row = connection.execute(
                "SELECT prematch_fired_platforms, fired_odds_mask FROM live_watch_entries WHERE id = ?", (watch_id,)
            ).fetchone()
            current = row["prematch_fired_platforms"] if row else None
            current_mask = row["fired_odds_mask"] if row and row["fired_odds_mask"] is not None else 0

            flag = _platform_to_odds_flag(platform)
            new_mask = current_mask | flag

            if current:
                platforms_list = [p.strip() for p in current.split(",") if p.strip()]
                if platform not in platforms_list:
                    platforms_list.append(platform)
                new_val = ",".join(platforms_list)
            else:
                new_val = platform

            connection.execute(
                """
                UPDATE live_watch_entries
                SET prematch_fired_platforms = ?, fired_odds_mask = ?,
                    prematch_seen_at = ?,
                    prematch_platform = ?,
                    matched_event_id = COALESCE(matched_event_id, ?)
                WHERE id = ?
                """,
                (new_val, new_mask, _utc_now_iso(), platform, event_id, watch_id),
            )

    def mark_live_watch_countdown_fired(self, watch_id: int) -> None:
        """Mark kickoff countdown as fired for this watch entry."""
        with _connect() as connection:
            connection.execute(
                """
                UPDATE live_watch_entries
                SET countdown_fired_at = ?
                WHERE id = ?
                """,
                (_utc_now_iso(), watch_id),
            )

    def update_live_watch_platform_state(
        self,
        watch_id: int,
        *,
        platform: str,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist the last observed live state for one platform.

        Returns the full platform->state mapping after the update.
        """

        with _connect() as connection:
            row = connection.execute(
                "SELECT live_state_json FROM live_watch_entries WHERE id = ?", (watch_id,)
            ).fetchone()
            current = _loads_json_object(row["live_state_json"] if row else None)
            current[str(platform)] = dict(state)
            connection.execute(
                """
                UPDATE live_watch_entries
                SET live_state_json = ?
                WHERE id = ?
                """,
                (json.dumps(current, ensure_ascii=False, sort_keys=True), watch_id),
            )
        return current

    def get_live_watch_settings(self, chat_id: int) -> LiveWatchSettings:
        """Return per-chat live alert settings, with defaults if unset."""

        with _connect() as connection:
            row = connection.execute(
                "SELECT * FROM live_watch_settings WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        if row is None:
            return LiveWatchSettings(chat_id=chat_id)
        return LiveWatchSettings(
            chat_id=int(row["chat_id"]),
            alert_goals=bool(row["alert_goals"]),
            alert_red_cards=bool(row["alert_red_cards"]),
            alert_yellow_cards=bool(row["alert_yellow_cards"]),
        )

    def set_live_watch_settings(
        self,
        chat_id: int,
        *,
        alert_goals: bool | None = None,
        alert_red_cards: bool | None = None,
        alert_yellow_cards: bool | None = None,
    ) -> LiveWatchSettings:
        """Upsert per-chat live alert settings and return the saved settings."""

        current = self.get_live_watch_settings(chat_id)
        new_goals = current.alert_goals if alert_goals is None else bool(alert_goals)
        new_reds = current.alert_red_cards if alert_red_cards is None else bool(alert_red_cards)
        new_yellows = current.alert_yellow_cards if alert_yellow_cards is None else bool(alert_yellow_cards)
        now_iso = _utc_now_iso()
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO live_watch_settings (
                    chat_id, alert_goals, alert_red_cards, alert_yellow_cards, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    alert_goals = excluded.alert_goals,
                    alert_red_cards = excluded.alert_red_cards,
                    alert_yellow_cards = excluded.alert_yellow_cards,
                    updated_at = excluded.updated_at
                """,
                (chat_id, int(new_goals), int(new_reds), int(new_yellows), now_iso),
            )
        return LiveWatchSettings(
            chat_id=chat_id,
            alert_goals=new_goals,
            alert_red_cards=new_reds,
            alert_yellow_cards=new_yellows,
        )

    def set_peak_digest_subscription(self, chat_id: int, enabled: bool) -> bool:
        """Enable/disable the daily special-league peak digest for a chat."""

        now_iso = _utc_now_iso()
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO peak_digest_subscriptions (chat_id, enabled, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (chat_id, int(bool(enabled)), now_iso),
            )
        return bool(enabled)

    def is_peak_digest_enabled(self, chat_id: int) -> bool:
        """Return whether a chat is subscribed to the daily peak digest."""

        with _connect() as connection:
            row = connection.execute(
                "SELECT enabled FROM peak_digest_subscriptions WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        return bool(row["enabled"]) if row is not None else False

    def list_peak_digest_chats(self) -> list[int]:
        """Return chat_ids subscribed to the daily peak digest."""

        with _connect() as connection:
            rows = connection.execute(
                "SELECT chat_id FROM peak_digest_subscriptions WHERE enabled = 1"
            ).fetchall()
        return [int(row["chat_id"]) for row in rows]

    # ---- Per-chat settings (display timezone, ...) ----

    def get_chat_timezone(self, chat_id: int) -> str | None:
        """Return the IANA timezone name saved for a chat, or None if unset."""

        with _connect() as connection:
            row = connection.execute(
                "SELECT timezone FROM chat_settings WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
        if row is None:
            return None
        value = row["timezone"]
        return value.strip() if isinstance(value, str) and value.strip() else None

    def set_chat_timezone(self, chat_id: int, timezone_name: str) -> None:
        """Persist the display timezone (IANA name) for a chat."""

        now_iso = _utc_now_iso()
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_settings (chat_id, timezone, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    timezone = excluded.timezone,
                    updated_at = excluded.updated_at
                """,
                (chat_id, timezone_name.strip(), now_iso),
            )

    def clear_chat_timezone(self, chat_id: int) -> None:
        """Drop a chat's timezone override (falls back to the default)."""

        now_iso = _utc_now_iso()
        with _connect() as connection:
            connection.execute(
                """
                INSERT INTO chat_settings (chat_id, timezone, updated_at)
                VALUES (?, NULL, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    timezone = NULL,
                    updated_at = excluded.updated_at
                """,
                (chat_id, now_iso),
            )

    # ---- Unified competition helpers (cross-platform league grouping) ----
    def get_unified_competition(self, unified_competition_id: int) -> dict | None:
        with _connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, public_id, display_name, country, gender, age_group
                FROM unified_competitions WHERE id = ?
                """,
                (unified_competition_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def create_unified_competition(self, name: str) -> int:
        """Create a NEW unified competition (no fuzzy merge) and return its id."""

        with _connect() as connection:
            return _insert_unified_competition(connection, name)

    def suggest_similar_unified(
        self,
        name: str,
        *,
        exclude_unified_id: int | None = None,
        min_score: float = 0.8,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Loosely-similar unified leagues, to *suggest* (not auto-merge).

        Guarded by the discriminators so it never proposes leagues that differ in
        gender or age (e.g. Women vs U20) or in an explicit country. Returns
        ``[{id, name, public_id, score}]`` sorted by descending score.
        """

        from core.league_naming import extract_league_traits, normalize_league_name, league_name_similarity

        name_clean = name.strip()
        target_norm = normalize_league_name(name_clean)
        if len(target_norm.split()) < 2:
            return []  # too generic to suggest anything meaningful
        target = extract_league_traits(name_clean)

        suggestions: list[dict[str, Any]] = []
        with _connect() as connection:
            rows = connection.execute(
                "SELECT id, name, public_id FROM unified_competitions"
            ).fetchall()
        for r in rows:
            if exclude_unified_id is not None and r["id"] == exclude_unified_id:
                continue
            cand = extract_league_traits(r["name"])
            if target["gender"] != cand["gender"] or target["age_group"] != cand["age_group"]:
                continue
            if target["country"] and cand["country"] and target["country"] != cand["country"]:
                continue
            if normalize_league_name(r["name"]) == target_norm:
                continue  # identical canonical -> would have auto-merged already
            score = league_name_similarity(name_clean, r["name"])
            if score >= min_score:
                suggestions.append(
                    {"id": r["id"], "name": r["name"], "public_id": r["public_id"], "score": score}
                )
        suggestions.sort(key=lambda s: s["score"], reverse=True)
        return suggestions[:limit]

    def delete_unified_competition(self, unified_competition_id: int) -> None:
        """Delete a unified competition (its competitions should be reassigned first)."""

        with _connect() as connection:
            connection.execute(
                "DELETE FROM unified_competitions WHERE id = ?",
                (unified_competition_id,),
            )

    def merge_unified_competitions(self, from_id: int, into_id: int) -> dict:
        """Merge league ``from_id`` into ``into_id`` atomically.

        Moves tracked competitions and stats links (on provider conflict the
        target's link wins), propagates subscriptions to the merged platform set,
        and deletes the source league. This is THE merge primitive — deleting the
        source unified directly would cascade-delete its stats links.
        """

        if from_id == into_id:
            raise ValueError("Cannot merge a unified competition into itself.")
        now_iso = _utc_now_iso()
        with _connect() as connection:
            for uid in (from_id, into_id):
                if connection.execute(
                    "SELECT 1 FROM unified_competitions WHERE id = ?", (uid,)
                ).fetchone() is None:
                    raise ValueError(f"Unified competition ID {uid} does not exist.")

            moved_links = connection.execute(
                """
                UPDATE stats_league_links
                SET unified_competition_id = ?, updated_at = ?
                WHERE unified_competition_id = ?
                  AND stats_provider NOT IN (
                      SELECT stats_provider FROM stats_league_links
                      WHERE unified_competition_id = ?
                  )
                """,
                (into_id, now_iso, from_id, into_id),
            ).rowcount
            connection.execute(
                "DELETE FROM stats_league_links WHERE unified_competition_id = ?",
                (from_id,),
            )
            moved_comps = connection.execute(
                """
                UPDATE tracked_competitions
                SET unified_competition_id = ?, updated_at = ?
                WHERE unified_competition_id = ?
                """,
                (into_id, now_iso, from_id),
            ).rowcount
            new_subscriptions = _propagate_unified_subscriptions(connection, into_id)
            connection.execute(
                "DELETE FROM unified_competitions WHERE id = ?",
                (from_id,),
            )
        return {
            "moved_competitions": moved_comps,
            "moved_stats_links": moved_links,
            "new_subscriptions": new_subscriptions,
        }

    # ------------------------------------------------------------------
    # Do-not-auto-merge exceptions (keyed by platform + external_id pairs)
    # ------------------------------------------------------------------
    @staticmethod
    def _canonical_merge_pair(
        platform_a: str,
        external_id_a: str,
        platform_b: str,
        external_id_b: str,
    ) -> tuple[str, str, str, str]:
        """Return the pair in canonical (a <= b) order so it is order-independent."""

        a = (str(platform_a), str(external_id_a))
        b = (str(platform_b), str(external_id_b))
        if a <= b:
            return (a[0], a[1], b[0], b[1])
        return (b[0], b[1], a[0], a[1])

    def get_merge_exceptions(self) -> set[tuple[str, str, str, str]]:
        """Return all blocked competition pairs as canonical 4-tuples (fast in-memory check)."""

        with _connect() as connection:
            rows = connection.execute(
                "SELECT platform_a, external_id_a, platform_b, external_id_b "
                "FROM unified_merge_exceptions"
            ).fetchall()
        return {
            (r["platform_a"], r["external_id_a"], r["platform_b"], r["external_id_b"])
            for r in rows
        }

    def block_unlinked_competition(
        self, tracked_competition_id: int, unified_competition_id: int
    ) -> int:
        """Record do-not-auto-merge exceptions when a competition is split off a league.

        Stores ONE row per *other* member competition still in the unified league,
        so the learner can never re-merge the separated competition with ANY of the
        platforms it was just detached from (while it stays free to merge with
        unrelated leagues). Returns how many exception rows were inserted.
        """

        with _connect() as connection:
            target = connection.execute(
                "SELECT platform, competition_external_id FROM tracked_competitions WHERE id = ?",
                (tracked_competition_id,),
            ).fetchone()
            if target is None:
                return 0
            members = connection.execute(
                "SELECT platform, competition_external_id FROM tracked_competitions "
                "WHERE unified_competition_id = ? AND id != ?",
                (unified_competition_id, tracked_competition_id),
            ).fetchall()
            now_iso = _utc_now_iso()
            inserted = 0
            for member in members:
                pa, xa, pb, xb = self._canonical_merge_pair(
                    target["platform"],
                    target["competition_external_id"],
                    member["platform"],
                    member["competition_external_id"],
                )
                if (pa, xa) == (pb, xb):
                    continue
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO unified_merge_exceptions "
                    "(platform_a, external_id_a, platform_b, external_id_b, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (pa, xa, pb, xb, now_iso),
                )
                inserted += cursor.rowcount
        return inserted

    def clear_merge_exceptions_between(
        self, unified_a_id: int, unified_b_id: int
    ) -> int:
        """Delete any do-not-merge exceptions between two unified leagues' members.

        Used by a manual /link_league override: the user asserts the leagues ARE the
        same, so the blocklist that would forbid the merge is removed. Returns how
        many exception rows were deleted (to warn the user an override happened).
        """

        with _connect() as connection:
            comps_a = connection.execute(
                "SELECT platform, competition_external_id FROM tracked_competitions "
                "WHERE unified_competition_id = ?",
                (unified_a_id,),
            ).fetchall()
            comps_b = connection.execute(
                "SELECT platform, competition_external_id FROM tracked_competitions "
                "WHERE unified_competition_id = ?",
                (unified_b_id,),
            ).fetchall()
            deleted = 0
            for ca in comps_a:
                for cb in comps_b:
                    pa, xa, pb, xb = self._canonical_merge_pair(
                        ca["platform"],
                        ca["competition_external_id"],
                        cb["platform"],
                        cb["competition_external_id"],
                    )
                    cursor = connection.execute(
                        "DELETE FROM unified_merge_exceptions "
                        "WHERE platform_a = ? AND external_id_a = ? "
                        "AND platform_b = ? AND external_id_b = ?",
                        (pa, xa, pb, xb),
                    )
                    deleted += cursor.rowcount
        return deleted

    def relink_unified_by_normalized_name(self) -> dict:
        """Re-unify tracked competitions whose names share the same canonical form.

        Fixes leagues that were split across unified competitions because their
        per-platform names differed ("USL League 2" vs "League Two", "Estados
        Unidos" vs "USA"). Conservative: only merges EXACT canonical matches.
        """

        from core.league_naming import normalize_league_name

        merged_groups = 0
        moved = 0
        now_iso = _utc_now_iso()
        with _connect() as connection:
            rows = connection.execute(
                "SELECT id, competition_name, unified_competition_id FROM tracked_competitions WHERE enabled = 1"
            ).fetchall()
            groups: dict[str, list[tuple]] = {}
            for r in rows:
                norm = normalize_league_name(r["competition_name"])
                if not norm:
                    continue
                groups.setdefault(norm, []).append(
                    (r["id"], r["unified_competition_id"], r["competition_name"])
                )

            for _norm, members in groups.items():
                if len(members) <= 1:
                    continue
                unified_ids = {u for _, u, _ in members if u is not None}
                if unified_ids:
                    target = min(unified_ids)
                else:
                    target = _insert_unified_competition(connection, members[0][2])
                changed = False
                for comp_id, current, _name in members:
                    if current != target:
                        connection.execute(
                            "UPDATE tracked_competitions SET unified_competition_id = ?, updated_at = ? WHERE id = ?",
                            (target, now_iso, comp_id),
                        )
                        moved += 1
                        changed = True
                if changed:
                    merged_groups += 1
                    _propagate_unified_subscriptions(connection, target)
                # delete unified competitions left empty by the merge
                for uid in unified_ids:
                    if uid == target:
                        continue
                    remaining = connection.execute(
                        "SELECT 1 FROM tracked_competitions WHERE unified_competition_id = ? LIMIT 1",
                        (uid,),
                    ).fetchone()
                    if remaining is None:
                        connection.execute("DELETE FROM unified_competitions WHERE id = ?", (uid,))

        return {"groups_merged": merged_groups, "competitions_moved": moved}

    # ---- Pre-kickoff reminders opt-in (default OFF): per league + per match ----
    def set_competition_reminders(self, tracked_competition_id: int, enabled: bool) -> None:
        with _connect() as connection:
            connection.execute(
                "UPDATE tracked_competitions SET reminders_enabled = ?, updated_at = ? WHERE id = ?",
                (1 if enabled else 0, _utc_now_iso(), tracked_competition_id),
            )

    def competition_reminders_enabled(self, tracked_competition_id: int) -> bool:
        with _connect() as connection:
            row = connection.execute(
                "SELECT reminders_enabled FROM tracked_competitions WHERE id = ?",
                (tracked_competition_id,),
            ).fetchone()
        return bool(row["reminders_enabled"]) if row is not None else False

    def set_event_reminder(self, tracked_competition_id: int, external_event_id: str, enabled: bool) -> None:
        with _connect() as connection:
            connection.execute(
                "UPDATE active_events SET reminder_enabled = ?, updated_at = ? "
                "WHERE tracked_competition_id = ? AND external_event_id = ?",
                (1 if enabled else 0, _utc_now_iso(), tracked_competition_id, str(external_event_id)),
            )

    def event_reminder_enabled_ids(self, tracked_competition_id: int) -> set[str]:
        with _connect() as connection:
            rows = connection.execute(
                "SELECT external_event_id FROM active_events "
                "WHERE tracked_competition_id = ? AND reminder_enabled = 1",
                (tracked_competition_id,),
            ).fetchall()
        return {str(r["external_event_id"]) for r in rows}

    def get_all_active_events_with_league(self) -> list[Any]:
        """Return all active events as SimpleNamespace objects with their tracked league name."""
        from types import SimpleNamespace
        with _connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    ae.id,
                    ae.tracked_competition_id,
                    ae.platform,
                    ae.competition_external_id,
                    ae.external_event_id,
                    ae.home,
                    ae.away,
                    ae.scheduled_label_date,
                    ae.scheduled_label_time,
                    ae.scheduled_at,
                    ae.event_url,
                    ae.odds_home,
                    ae.odds_draw,
                    ae.odds_away,
                    ae.markets_json,
                    ae.raw_payload_json,
                    ae.reminder_sent_at,
                    ae.is_active,
                    ae.first_seen_at,
                    ae.last_seen_at,
                    ae.created_at,
                    ae.updated_at,
                    tc.competition_name as league_name
                FROM active_events ae
                JOIN tracked_competitions tc ON ae.tracked_competition_id = tc.id
                WHERE ae.is_active = 1
                """
            ).fetchall()
        return [SimpleNamespace(**dict(row)) for row in rows]

    def purge_expired_live_watches(
        self,
        *,
        kickoff_grace_hours: float = 2.0,
        stale_hours: float = 16.0,
        fired_retain_hours: float = 3.0,
    ) -> int:
        """Delete watch entries whose time has passed. Returns the count removed.

        - watching with a known kickoff: removed once now > kickoff + grace.
        - watching without a kickoff: removed once older than ``stale_hours``.
        - fired: removed ``fired_retain_hours`` after firing to keep the list tidy.
        """

        now = datetime.now(timezone.utc)
        kickoff_cutoff = (now - timedelta(hours=kickoff_grace_hours)).isoformat()
        stale_cutoff = (now - timedelta(hours=stale_hours)).isoformat()
        fired_cutoff = (now - timedelta(hours=fired_retain_hours)).isoformat()
        with _connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM live_watch_entries
                WHERE (status = 'watching' AND kickoff_at IS NOT NULL AND kickoff_at < ?)
                   OR (status = 'watching' AND kickoff_at IS NULL AND created_at < ?)
                   OR (status = 'fired' AND fired_at IS NOT NULL AND fired_at < ?)
                """,
                (kickoff_cutoff, stale_cutoff, fired_cutoff),
            )
        return cursor.rowcount

    def remove_live_watch(self, chat_id: int, watch_id: int) -> bool:
        """Delete one live-watch entry for a chat. Returns True if removed."""

        with _connect() as connection:
            cursor = connection.execute(
                "DELETE FROM live_watch_entries WHERE id = ? AND chat_id = ?", (watch_id, chat_id)
            )
        return cursor.rowcount > 0

    def remove_live_watch_by_local_id(self, chat_id: int, local_id: int) -> bool:
        """Delete one live-watch entry by chat_local_id for a chat. Returns True if removed."""

        with _connect() as connection:
            cursor = connection.execute(
                "DELETE FROM live_watch_entries WHERE chat_local_id = ? AND chat_id = ?",
                (local_id, chat_id),
            )
        return cursor.rowcount > 0

    def clear_live_watches(self, chat_id: int, *, status: str | None = None) -> int:
        """Delete a chat's live-watch entries (optionally by status). Returns count."""

        with _connect() as connection:
            if status:
                cursor = connection.execute(
                    "DELETE FROM live_watch_entries WHERE chat_id = ? AND status = ?", (chat_id, status)
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM live_watch_entries WHERE chat_id = ?", (chat_id,)
                )
        return cursor.rowcount

    def delete_stats_league_link(self, tracked_competition_id: int, stats_provider: str | None = None) -> bool:
        """Delete the stats-provider league link for one tracked competition."""

        with _connect() as connection:
            _ensure_tracked_competition_exists(connection, tracked_competition_id)
            if stats_provider:
                normalized_provider = _normalize_platform(stats_provider)
                cursor = connection.execute(
                    """
                    DELETE FROM stats_league_links
                    WHERE tracked_competition_id = ? AND stats_provider = ?
                    """,
                    (tracked_competition_id, normalized_provider),
                )
            else:
                cursor = connection.execute(
                    """
                    DELETE FROM stats_league_links
                    WHERE tracked_competition_id = ?
                    """,
                    (tracked_competition_id,),
                )

        return cursor.rowcount > 0

    def upsert_stats_match_link(
        self,
        active_event_id: int,
        *,
        stats_provider: str,
        stats_match_id: str,
        stats_url: str | None,
        confidence: float,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> StatsMatchLinkRecord:
        """Create or update the resolved stats-provider match for one active event."""

        normalized_provider = _normalize_platform(stats_provider)
        normalized_match_id = stats_match_id.strip()
        normalized_method = method.strip()
        if not normalized_match_id:
            raise ValueError("stats_match_id must not be empty.")
        if not normalized_method:
            raise ValueError("method must not be empty.")

        now_iso = _utc_now_iso()
        payload_json = _json_dumps(payload)

        with _connect() as connection:
            _ensure_active_event_exists(connection, active_event_id)
            connection.execute(
                """
                INSERT INTO stats_match_links (
                    active_event_id,
                    stats_provider,
                    stats_match_id,
                    stats_url,
                    confidence,
                    method,
                    payload_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(active_event_id, stats_provider) DO UPDATE SET
                    stats_match_id = excluded.stats_match_id,
                    stats_url = excluded.stats_url,
                    confidence = excluded.confidence,
                    method = excluded.method,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    active_event_id,
                    normalized_provider,
                    normalized_match_id,
                    _normalize_optional_text(stats_url),
                    float(confidence),
                    normalized_method,
                    payload_json,
                    now_iso,
                    now_iso,
                ),
            )
            row = _fetch_stats_match_link_row(connection, active_event_id, stats_provider=normalized_provider)

        if row is None:
            raise RuntimeError("Stats match link was upserted but could not be reloaded.")
        return _row_to_stats_match_link(row)

    def get_stats_match_link(self, active_event_id: int, stats_provider: str | None = None) -> StatsMatchLinkRecord | None:
        """Return the cached stats-provider match link for one active event."""

        with _connect() as connection:
            _ensure_active_event_exists(connection, active_event_id)
            row = _fetch_stats_match_link_row(connection, active_event_id, stats_provider=stats_provider)

        return _row_to_stats_match_link(row) if row is not None else None

    def list_stats_match_links(self, active_event_id: int) -> list[StatsMatchLinkRecord]:
        """Return all stats-provider match links for one active event."""

        with _connect() as connection:
            _ensure_active_event_exists(connection, active_event_id)
            rows = connection.execute(
                """
                SELECT
                    id,
                    active_event_id,
                    stats_provider,
                    stats_match_id,
                    stats_url,
                    confidence,
                    method,
                    payload_json,
                    created_at,
                    updated_at
                FROM stats_match_links
                WHERE active_event_id = ?
                """,
                (active_event_id,),
            ).fetchall()

        return [_row_to_stats_match_link(row) for row in rows]

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

    def prune_old_data(
        self,
        days_threshold: int = 14,
        sent_alerts_days: int = 30,
        small_changes_days: int = 7,
    ) -> dict[str, int]:
        """Prune inactive events, old sent alerts, expired cache, and pending small changes.

        Returns a dictionary with the counts of deleted rows per table.
        """
        now = datetime.now(timezone.utc)
        cutoff_iso = (now - timedelta(days=days_threshold)).isoformat()
        sent_alerts_cutoff_iso = (now - timedelta(days=sent_alerts_days)).isoformat()
        small_changes_cutoff_iso = (now - timedelta(days=small_changes_days)).isoformat()
        now_iso = now.isoformat()

        stats = {}
        with _connect() as conn:
            # 1. Delete inactive active_events older than threshold.
            cursor = conn.execute(
                "DELETE FROM active_events WHERE is_active = 0 AND last_seen_at < ?",
                (cutoff_iso,),
            )
            stats["active_events_pruned"] = cursor.rowcount

            # 2. Delete sent_alerts older than threshold.
            cursor = conn.execute(
                "DELETE FROM sent_alerts WHERE sent_at < ?",
                (sent_alerts_cutoff_iso,),
            )
            stats["sent_alerts_pruned"] = cursor.rowcount

            # 3. Delete expired stats payload caches.
            cursor = conn.execute(
                "DELETE FROM stats_payload_cache WHERE expires_at < ?",
                (now_iso,),
            )
            stats["expired_cache_pruned"] = cursor.rowcount

            # 4. Clean up expired live watches.
            cursor = conn.execute(
                "DELETE FROM live_watch_entries WHERE created_at < ?",
                (cutoff_iso,),
            )
            stats["expired_live_watches_pruned"] = cursor.rowcount

            # 5. Delete pending small changes older than threshold.
            cursor = conn.execute(
                "DELETE FROM small_changes WHERE status = 'pending' AND created_at < ?",
                (small_changes_cutoff_iso,),
            )
            stats["small_changes_pruned"] = cursor.rowcount

        return stats

    def run_db_vacuum(self) -> bool:
        """Execute SQLite VACUUM to reclaim unused disk space.

        Returns True if successful, False otherwise.
        """
        try:
            conn = sqlite3.connect(DB_FILE_PATH, timeout=30)
            conn.isolation_level = None  # autocommit mode
            conn.execute("VACUUM")
            conn.close()
            logger.info("Database VACUUM executed successfully.")
            return True
        except Exception as e:
            logger.exception("Failed to execute VACUUM: %s", e)
            return False

def _process_dirty_chats(connection: sqlite3.Connection) -> None:
    """Compile subscriptions bitmap for dirty chats in Python (Option B)."""
    try:
        dirty_rows = connection.execute("SELECT chat_id FROM dirty_chats").fetchall()
    except sqlite3.OperationalError:
        return
    if not dirty_rows:
        return

    from core.flags import ids_to_hex
    now_iso = _utc_now_iso()
    
    for row in dirty_rows:
        chat_id = int(row["chat_id"])
        
        # Compile odds subscriptions
        odds_rows = connection.execute(
            """
            SELECT tc.unified_competition_id 
            FROM competition_subscriptions cs
            INNER JOIN tracked_competitions tc ON tc.id = cs.tracked_competition_id
            WHERE cs.telegram_chat_id = ? AND cs.enabled = 1 AND tc.unified_competition_id IS NOT NULL
            """,
            (chat_id,)
        ).fetchall()
        odds_ids = sorted(list({int(r[0]) for r in odds_rows}))
        odds_hex = ids_to_hex(odds_ids)

        # Compile stats subscriptions
        stats_rows = connection.execute(
            """
            SELECT sll.unified_competition_id
            FROM stats_league_subscriptions sls
            INNER JOIN stats_league_links sll 
                ON sll.stats_provider = sls.stats_provider AND sll.stats_league_id = sls.stats_league_id
            WHERE sls.telegram_chat_id = ? AND sls.enabled = 1 AND sll.unified_competition_id IS NOT NULL
            """,
            (chat_id,)
        ).fetchall()
        stats_ids = sorted(list({int(r[0]) for r in stats_rows}))
        stats_hex = ids_to_hex(stats_ids)

        connection.execute(
            """
            INSERT OR REPLACE INTO chat_subscriptions_bitmap (chat_id, tracked_odds_leagues_hex, tracked_stats_leagues_hex, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, odds_hex, stats_hex, now_iso)
        )
        
    connection.execute("DELETE FROM dirty_chats")

@contextmanager
def _connect():
    """Open a repository connection and always close it after use."""

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_FILE_PATH, timeout=30)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        # WAL: better read/write concurrency and fewer fsyncs than the default
        # rollback journal (idempotent: a no-op once the DB file is already WAL).
        # synchronous=NORMAL is safe under WAL; busy_timeout avoids spurious
        # "database is locked" errors. All cheap to re-assert per connection.
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        
        # _initialize_schema is an idempotent self-heal (creates missing tables
        # and runs legacy-data migrations); it must run on each connect so a DB
        # that drifts into a legacy state gets repaired.
        _initialize_schema(connection)
        yield connection
        _process_dirty_chats(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _enforce_stats_payload_cache_limit(connection: sqlite3.Connection) -> int:
    """Keep only the newest stats payload cache rows.

    The cache already has TTL pruning, but long TTLs across many providers can
    still grow the table. This FIFO cap removes oldest fetched rows first.
    Returns the number of rows deleted.
    """

    row = connection.execute("SELECT COUNT(*) AS total FROM stats_payload_cache").fetchone()
    total = int(row["total"] if row is not None else 0)
    overflow = max(0, total - STATS_PAYLOAD_CACHE_MAX_ROWS)
    if overflow <= 0:
        return 0
    cursor = connection.execute(
        """
        DELETE FROM stats_payload_cache
        WHERE cache_key IN (
            SELECT cache_key
            FROM stats_payload_cache
            ORDER BY fetched_at ASC, cache_key ASC
            LIMIT ?
        )
        """,
        (overflow,),
    )
    return cursor.rowcount


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
            consecutive_unavailable_refreshes INTEGER NOT NULL DEFAULT 0,
            last_unavailable_refresh_at TEXT,
            last_unavailable_reason TEXT,
            last_unavailable_notification_at TEXT,
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

        CREATE TABLE IF NOT EXISTS stats_league_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracked_competition_id INTEGER NOT NULL,
            stats_provider TEXT NOT NULL,
            stats_league_id TEXT NOT NULL,
            stats_league_name TEXT NOT NULL,
            stats_country_name TEXT,
            confidence REAL NOT NULL DEFAULT 1.0,
            payload_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tracked_competition_id, stats_provider),
            FOREIGN KEY(tracked_competition_id) REFERENCES tracked_competitions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_stats_league_links_provider
        ON stats_league_links(stats_provider, stats_league_id);

        CREATE TABLE IF NOT EXISTS stats_league_subscriptions (
            telegram_chat_id INTEGER NOT NULL,
            stats_provider TEXT NOT NULL,
            stats_league_id TEXT NOT NULL,
            stats_league_name TEXT NOT NULL,
            stats_country_name TEXT,
            source_url TEXT,
            payload_json TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (telegram_chat_id, stats_provider, stats_league_id)
        );

        CREATE INDEX IF NOT EXISTS idx_stats_league_subscriptions_provider
        ON stats_league_subscriptions(stats_provider, stats_league_id, enabled);

        CREATE TABLE IF NOT EXISTS stats_match_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            active_event_id INTEGER NOT NULL,
            stats_provider TEXT NOT NULL,
            stats_match_id TEXT NOT NULL,
            stats_url TEXT,
            confidence REAL NOT NULL DEFAULT 0.0,
            method TEXT NOT NULL,
            payload_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(active_event_id, stats_provider),
            FOREIGN KEY(active_event_id) REFERENCES active_events(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_stats_match_links_provider
        ON stats_match_links(stats_provider, stats_match_id);

        CREATE TABLE IF NOT EXISTS stats_payload_cache (
            cache_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_stats_payload_cache_expires
        ON stats_payload_cache(expires_at);

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

        CREATE TABLE IF NOT EXISTS live_watch_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            league_hint TEXT,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'watching',
            matched_platform TEXT,
            matched_event_id TEXT,
            matched_minute TEXT,
            created_at TEXT NOT NULL,
            fired_at TEXT,
            fired_platforms TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_live_watch_chat_status
        ON live_watch_entries(chat_id, status);

        CREATE TABLE IF NOT EXISTS live_watch_settings (
            chat_id INTEGER PRIMARY KEY,
            alert_goals INTEGER NOT NULL DEFAULT 1,
            alert_red_cards INTEGER NOT NULL DEFAULT 1,
            alert_yellow_cards INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS peak_digest_subscriptions (
            chat_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id INTEGER PRIMARY KEY,
            timezone TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_user_event_baselines_active_event
        ON user_event_baselines(active_event_id);

        CREATE INDEX IF NOT EXISTS idx_small_changes_active_event
        ON small_changes(active_event_id);

        CREATE INDEX IF NOT EXISTS idx_sent_alerts_active_event
        ON sent_alerts(active_event_id);

        CREATE INDEX IF NOT EXISTS idx_stats_match_links_active_event
        ON stats_match_links(active_event_id);
        """
    )

    # Check stats_league_links unique constraint and migrate if old
    row_league = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='stats_league_links'"
    ).fetchone()
    if row_league and "UNIQUE(tracked_competition_id)" in row_league[0].replace(" ", ""):
        connection.executescript(
            """
            -- Rename existing table to old
            ALTER TABLE stats_league_links RENAME TO stats_league_links_old;
            
            -- Create new table with updated unique constraint
            CREATE TABLE stats_league_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tracked_competition_id INTEGER NOT NULL,
                stats_provider TEXT NOT NULL,
                stats_league_id TEXT NOT NULL,
                stats_league_name TEXT NOT NULL,
                stats_country_name TEXT,
                confidence REAL NOT NULL DEFAULT 1.0,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(tracked_competition_id, stats_provider),
                FOREIGN KEY(tracked_competition_id) REFERENCES tracked_competitions(id) ON DELETE CASCADE
            );
            
            -- Copy existing data
            INSERT OR IGNORE INTO stats_league_links (
                id, tracked_competition_id, stats_provider, stats_league_id, 
                stats_league_name, stats_country_name, confidence, 
                payload_json, created_at, updated_at
            )
            SELECT 
                id, tracked_competition_id, stats_provider, stats_league_id, 
                stats_league_name, stats_country_name, confidence, 
                payload_json, created_at, updated_at
            FROM stats_league_links_old;
            
            -- Drop old table
            DROP TABLE stats_league_links_old;
            
            -- Recreate index
            CREATE INDEX IF NOT EXISTS idx_stats_league_links_provider
            ON stats_league_links(stats_provider, stats_league_id);
            """
        )

    # Check stats_match_links unique constraint and migrate if old
    row_match = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='stats_match_links'"
    ).fetchone()
    if row_match and "UNIQUE(active_event_id)" in row_match[0].replace(" ", ""):
        connection.executescript(
            """
            -- Rename existing table to old
            ALTER TABLE stats_match_links RENAME TO stats_match_links_old;
            
            -- Create new table with updated unique constraint
            CREATE TABLE stats_match_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                active_event_id INTEGER NOT NULL,
                stats_provider TEXT NOT NULL,
                stats_match_id TEXT NOT NULL,
                stats_url TEXT,
                confidence REAL NOT NULL DEFAULT 0.0,
                method TEXT NOT NULL,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(active_event_id, stats_provider),
                FOREIGN KEY(active_event_id) REFERENCES active_events(id) ON DELETE CASCADE
            );
            
            -- Copy existing data
            INSERT OR IGNORE INTO stats_match_links (
                id, active_event_id, stats_provider, stats_match_id, 
                stats_url, confidence, method, payload_json, 
                created_at, updated_at
            )
            SELECT 
                id, active_event_id, stats_provider, stats_match_id, 
                stats_url, confidence, method, payload_json, 
                created_at, updated_at
            FROM stats_match_links_old;
            
            -- Drop old table
            DROP TABLE stats_match_links_old;
            
            -- Recreate index
            CREATE INDEX IF NOT EXISTS idx_stats_match_links_provider
            ON stats_match_links(stats_provider, stats_match_id);
            """
        )

    _ensure_column(
        connection,
        "tracked_competitions",
        "consecutive_unavailable_refreshes",
        "INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(
        connection,
        "tracked_competitions",
        "last_unavailable_refresh_at",
        "TEXT",
    )
    _ensure_column(
        connection,
        "tracked_competitions",
        "last_unavailable_reason",
        "TEXT",
    )
    _ensure_column(
        connection,
        "tracked_competitions",
        "last_unavailable_notification_at",
        "TEXT",
    )
    for _live_watch_column in (
        "kickoff_at",
        "prematch_seen_at",
        "prematch_platform",
        "fired_platforms",
        "prematch_fired_platforms",
        "countdown_fired_at",
        "live_state_json",
    ):
        _ensure_column(connection, "live_watch_entries", _live_watch_column, "TEXT")
    _ensure_column(connection, "live_watch_entries", "chat_local_id", "INTEGER")
    # Pre-kickoff reminder opt-in (default OFF): per league + per match.
    _ensure_column(connection, "tracked_competitions", "reminders_enabled", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "active_events", "reminder_enabled", "INTEGER NOT NULL DEFAULT 0")

    # 1. Create unified_competitions table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS unified_competitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )

    # 1b. League registry fields: public slug + traits (country / gender / age).
    _ensure_column(connection, "unified_competitions", "public_id", "TEXT")
    _ensure_column(connection, "unified_competitions", "display_name", "TEXT")
    _ensure_column(connection, "unified_competitions", "country", "TEXT")
    _ensure_column(connection, "unified_competitions", "gender", "TEXT")
    _ensure_column(connection, "unified_competitions", "age_group", "TEXT")
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_competitions_public_id
        ON unified_competitions(public_id) WHERE public_id IS NOT NULL
        """
    )

    # 1c. Do-not-auto-merge exceptions between two physical competitions.
    #     Keyed by the STABLE natural identity (platform + external_id), NOT by
    #     unified ids (those get reassigned on every merge). Order is canonical
    #     (a <= b) so a pair is stored once regardless of argument order. Written
    #     by /unlink_league (one row per remaining league member) and cleared by a
    #     manual /link_league override.
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS unified_merge_exceptions (
            platform_a TEXT NOT NULL,
            external_id_a TEXT NOT NULL,
            platform_b TEXT NOT NULL,
            external_id_b TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (platform_a, external_id_a, platform_b, external_id_b)
        );
        """
    )

    # 2. Add unified_competition_id column to tracked_competitions
    _ensure_column(
        connection,
        "tracked_competitions",
        "unified_competition_id",
        "INTEGER REFERENCES unified_competitions(id) ON DELETE SET NULL",
    )

    # 3. Backfill unified_competition_id for existing tracked_competitions
    now_iso = _utc_now_iso()
    rows = connection.execute(
        "SELECT id, competition_name FROM tracked_competitions WHERE unified_competition_id IS NULL"
    ).fetchall()
    for row in rows:
        tc_id = row["id"]
        tc_name = row["competition_name"].strip()
        # Find if a unified competition with this exact name already exists
        uc_row = connection.execute(
            "SELECT id FROM unified_competitions WHERE name = ?", (tc_name,)
        ).fetchone()
        if uc_row:
            uc_id = uc_row["id"]
        else:
            uc_id = _insert_unified_competition(connection, tc_name)
        connection.execute(
            "UPDATE tracked_competitions SET unified_competition_id = ? WHERE id = ?",
            (uc_id, tc_id),
        )

    # 4. Registry backfill: rows created before the registry get slug + traits.
    #    Runs on every connect (cheap when empty) so it also self-heals rows
    #    inserted by older code paths.
    pending_registry = connection.execute(
        "SELECT id, name FROM unified_competitions WHERE public_id IS NULL ORDER BY id"
    ).fetchall()
    if pending_registry:
        from core.league_naming import extract_league_traits, league_slug

        for row in pending_registry:
            base = league_slug(row["name"]) or f"league-{row['id']}"
            slug = base
            suffix = 2
            while connection.execute(
                "SELECT 1 FROM unified_competitions WHERE public_id = ?", (slug,)
            ).fetchone() is not None:
                slug = f"{base}-{suffix}"
                suffix += 1
            traits = extract_league_traits(row["name"])
            connection.execute(
                """
                UPDATE unified_competitions
                SET public_id = ?, display_name = COALESCE(display_name, name),
                    country = ?, gender = ?, age_group = ?, updated_at = ?
                WHERE id = ?
                """,
                (slug, traits["country"], traits["gender"], traits["age_group"], now_iso, row["id"]),
            )

    # 5. Stats links live at the unified-league level so every platform of the
    #    same league inherits them. Backfill from the tracked competition, then
    #    resolve duplicates per (unified, provider) keeping the best link.
    _ensure_column(
        connection,
        "stats_league_links",
        "unified_competition_id",
        "INTEGER REFERENCES unified_competitions(id) ON DELETE CASCADE",
    )
    # Dedupe BEFORE backfilling: the unique index may already exist, so the
    # backfill UPDATE must not produce (unified, provider) collisions. Resolve
    # each row's unified via its tracked competition and keep the best link.
    connection.execute(
        """
        DELETE FROM stats_league_links
        WHERE id IN (
            SELECT sll.id
            FROM stats_league_links sll
            LEFT JOIN tracked_competitions tc ON tc.id = sll.tracked_competition_id
            WHERE COALESCE(sll.unified_competition_id, tc.unified_competition_id) IS NOT NULL
        )
        AND id NOT IN (
            SELECT keep_id FROM (
                SELECT sll.id AS keep_id, ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(sll.unified_competition_id, tc.unified_competition_id),
                                 sll.stats_provider
                    ORDER BY sll.confidence DESC, sll.updated_at DESC, sll.id DESC
                ) AS rn
                FROM stats_league_links sll
                LEFT JOIN tracked_competitions tc ON tc.id = sll.tracked_competition_id
                WHERE COALESCE(sll.unified_competition_id, tc.unified_competition_id) IS NOT NULL
            ) WHERE rn = 1
        )
        """
    )
    connection.execute(
        """
        UPDATE stats_league_links
        SET unified_competition_id = (
            SELECT tc.unified_competition_id FROM tracked_competitions tc
            WHERE tc.id = stats_league_links.tracked_competition_id
        )
        WHERE unified_competition_id IS NULL
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_stats_league_links_unified_provider
        ON stats_league_links(unified_competition_id, stats_provider)
        WHERE unified_competition_id IS NOT NULL
        """
    )

    # --- NUCELAR MIGRATION BITS & HEXADECIMAL OPTIMIZATIONS ---
    # 1. Ensure binary flags and array JSON columns exist on unified_competitions
    _ensure_column(connection, "unified_competitions", "odds_providers_mask", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "unified_competitions", "stats_providers_mask", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "unified_competitions", "odds_external_ids", "TEXT")
    _ensure_column(connection, "unified_competitions", "odds_source_urls", "TEXT")
    _ensure_column(connection, "unified_competitions", "stats_external_ids", "TEXT")

    # 2. Create the unified chat_subscriptions table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_subscriptions (
            chat_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            settings_mask INTEGER NOT NULL DEFAULT 7,
            change_threshold_percent REAL NOT NULL DEFAULT 20.0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, target_type, target_id)
        );
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_subscriptions_target
        ON chat_subscriptions(target_type, target_id);
        """
    )

    # 3. Create the unified events table (static metadata)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_competition_id INTEGER NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            scheduled_at TEXT,
            event_urls TEXT,
            status_flags INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY(unified_competition_id) REFERENCES unified_competitions(id) ON DELETE CASCADE
        );
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_unified_competition
        ON events(unified_competition_id, status_flags, scheduled_at);
        """
    )

    # 4. Create the event_odds_snapshots table (odds time series)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS event_odds_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            odds_home REAL,
            odds_draw REAL,
            odds_away REAL,
            odds_btts_yes REAL,
            odds_btts_no REAL,
            markets_mask INTEGER NOT NULL DEFAULT 0,
            markets_json TEXT,
            extracted_at TEXT NOT NULL,
            FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
        );
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_event_odds_snapshots_event
        ON event_odds_snapshots(event_id, platform, extracted_at DESC);
        """
    )

    # 5. Create event_payloads_debug table
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS event_payloads_debug (
            event_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            compressed_raw_payload BLOB,
            saved_at TEXT NOT NULL,
            PRIMARY KEY(event_id, platform),
            FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
        );
        """
    )

    # 6. Ensure live_watch_entries status_flags and bitmask columns exist
    _ensure_column(connection, "live_watch_entries", "status_flags", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(connection, "live_watch_entries", "fired_odds_mask", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "live_watch_entries", "fired_stats_mask", "INTEGER NOT NULL DEFAULT 0")

    # 7. BACKFILL MIGRATIONS
    from core.flags import (
        OddsProviderFlags,
        StatsProviderFlags,
        SubscriptionFlags,
        LiveWatchStatusFlags,
        MatchStatusFlags,
        MarketFlags
    )

    ODDS_PROVIDERS_ORDER = [
        '1xbet_http', 'betovo_http', 'solcasino_http', 'bet365', 'mrpunter_http',
        'mystake_http', 'betsson_http', 'betwarrior_http', 'bz_http'
    ]

    STATS_PROVIDERS_ORDER = [
        'sportradar_statshub', 'sofascore_http', 'flashscore_http', 'footystats_http',
        'svenskfotboll_http', 'palloliitto', 'norway_nff_http', 'romania_frf_http',
        'slovakia_sportnet_http', 'algeria_lnff_http'
    ]

    # A. Backfill unified_competitions odds providers bitmask & arrays
    tc_rows = connection.execute(
        "SELECT platform, competition_external_id, source_url, unified_competition_id FROM tracked_competitions"
    ).fetchall()
    for row in tc_rows:
        uc_id = row["unified_competition_id"]
        if uc_id is None:
            continue
        platform = row["platform"]
        ext_id = row["competition_external_id"]
        source_url = row["source_url"]

        uc_row = connection.execute(
            "SELECT odds_providers_mask, odds_external_ids, odds_source_urls FROM unified_competitions WHERE id = ?",
            (uc_id,)
        ).fetchone()

        if uc_row:
            mask = uc_row["odds_providers_mask"] or 0
            try:
                ext_ids = json.loads(uc_row["odds_external_ids"]) if uc_row["odds_external_ids"] else [None] * len(ODDS_PROVIDERS_ORDER)
            except Exception:
                ext_ids = [None] * len(ODDS_PROVIDERS_ORDER)
            try:
                urls = json.loads(uc_row["odds_source_urls"]) if uc_row["odds_source_urls"] else [None] * len(ODDS_PROVIDERS_ORDER)
            except Exception:
                urls = [None] * len(ODDS_PROVIDERS_ORDER)

            if platform in ODDS_PROVIDERS_ORDER:
                idx = ODDS_PROVIDERS_ORDER.index(platform)
                mask |= (1 << idx)
                ext_ids[idx] = ext_id
                urls[idx] = source_url

                connection.execute(
                    """
                    UPDATE unified_competitions
                    SET odds_providers_mask = ?, odds_external_ids = ?, odds_source_urls = ?
                    WHERE id = ?
                    """,
                    (mask, json.dumps(ext_ids), json.dumps(urls), uc_id)
                )

    # B. Backfill unified_competitions stats providers bitmask & arrays
    sll_rows = connection.execute(
        "SELECT stats_provider, stats_league_id, unified_competition_id FROM stats_league_links"
    ).fetchall()
    for row in sll_rows:
        uc_id = row["unified_competition_id"]
        if uc_id is None:
            continue
        provider = row["stats_provider"]
        league_id = row["stats_league_id"]

        uc_row = connection.execute(
            "SELECT stats_providers_mask, stats_external_ids FROM unified_competitions WHERE id = ?",
            (uc_id,)
        ).fetchone()

        if uc_row:
            mask = uc_row["stats_providers_mask"] or 0
            try:
                ext_ids = json.loads(uc_row["stats_external_ids"]) if uc_row["stats_external_ids"] else [None] * len(STATS_PROVIDERS_ORDER)
            except Exception:
                ext_ids = [None] * len(STATS_PROVIDERS_ORDER)

            if provider in STATS_PROVIDERS_ORDER:
                idx = STATS_PROVIDERS_ORDER.index(provider)
                mask |= (1 << idx)
                ext_ids[idx] = league_id

                connection.execute(
                    """
                    UPDATE unified_competitions
                    SET stats_providers_mask = ?, stats_external_ids = ?
                    WHERE id = ?
                    """,
                    (mask, json.dumps(ext_ids), uc_id)
                )

    # C. Backfill chat_subscriptions
    # Odds target
    sub_odds_rows = connection.execute(
        """
        SELECT cs.telegram_chat_id, cs.notify_new_events, cs.notify_odds_changes, cs.change_threshold_percent, cs.enabled, tc.unified_competition_id
        FROM competition_subscriptions cs
        JOIN tracked_competitions tc ON tc.id = cs.tracked_competition_id
        """
    ).fetchall()
    for row in sub_odds_rows:
        chat_id = row["telegram_chat_id"]
        uc_id = row["unified_competition_id"]
        if uc_id is None:
            continue

        mask = SubscriptionFlags.NONE
        if row["notify_odds_changes"]:
            mask |= SubscriptionFlags.NOTIFY_ODDS_CHANGES
        if row["notify_new_events"]:
            mask |= SubscriptionFlags.NOTIFY_NEW_EVENTS
        mask |= SubscriptionFlags.ALERT_GOALS | SubscriptionFlags.ALERT_RED_CARDS

        connection.execute(
            """
            INSERT OR IGNORE INTO chat_subscriptions (
                chat_id, target_type, target_id, settings_mask, change_threshold_percent, enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (chat_id, 'odds', uc_id, int(mask), row["change_threshold_percent"], row["enabled"])
        )

    # Stats target
    sub_stats_rows = connection.execute(
        "SELECT telegram_chat_id, stats_provider, stats_league_id, enabled FROM stats_league_subscriptions"
    ).fetchall()
    for row in sub_stats_rows:
        chat_id = row["telegram_chat_id"]
        provider = row["stats_provider"]
        league_id = row["stats_league_id"]

        uc_row = connection.execute(
            "SELECT unified_competition_id FROM stats_league_links WHERE stats_provider = ? AND stats_league_id = ?",
            (provider, league_id)
        ).fetchone()
        if uc_row and uc_row["unified_competition_id"]:
            uc_id = uc_row["unified_competition_id"]
            mask = SubscriptionFlags.NOTIFY_LINEUPS
            connection.execute(
                """
                INSERT OR IGNORE INTO chat_subscriptions (
                    chat_id, target_type, target_id, settings_mask, change_threshold_percent, enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (chat_id, 'stats', uc_id, int(mask), 20.0, row["enabled"])
            )

    # D. Backfill events and event_odds_snapshots
    active_evt_rows = connection.execute(
        """
        SELECT ae.id, ae.home, ae.away, ae.scheduled_at, ae.event_url, ae.odds_home, ae.odds_draw, ae.odds_away, ae.is_active, ae.reminder_sent_at, ae.reminder_enabled, tc.unified_competition_id, ae.platform
        FROM active_events ae
        JOIN tracked_competitions tc ON tc.id = ae.tracked_competition_id
        """
    ).fetchall()
    for row in active_evt_rows:
        ae_id = row["id"]
        uc_id = row["unified_competition_id"]
        if uc_id is None:
            continue

        evt_row = connection.execute("SELECT id FROM events WHERE id = ?", (ae_id,)).fetchone()
        if not evt_row:
            event_urls = {row["platform"]: row["event_url"]}
            status_flags = MatchStatusFlags.PREMATCH_INACTIVE
            if row["is_active"]:
                status_flags |= MatchStatusFlags.PREMATCH_ACTIVE
            if row["reminder_sent_at"]:
                status_flags |= MatchStatusFlags.REMINDER_SENT

            connection.execute(
                """
                INSERT OR IGNORE INTO events (
                    id, unified_competition_id, home, away, scheduled_at, event_urls, status_flags, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (ae_id, uc_id, row["home"], row["away"], row["scheduled_at"], json.dumps(event_urls), int(status_flags))
            )

            markets_mask = MarketFlags.MARKET_1X2 if (row["odds_home"] is not None) else MarketFlags.NONE
            connection.execute(
                """
                INSERT OR IGNORE INTO event_odds_snapshots (
                    event_id, platform, odds_home, odds_draw, odds_away, odds_btts_yes, odds_btts_no, markets_mask, extracted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (ae_id, row["platform"], row["odds_home"], row["odds_draw"], row["odds_away"], None, None, int(markets_mask))
            )

    # E. Backfill live_watch_entries status_flags
    lw_rows = connection.execute(
        "SELECT id, status, fired_platforms FROM live_watch_entries WHERE status_flags = 1 AND (status != 'watching' OR fired_platforms IS NOT NULL)"
    ).fetchall()
    for row in lw_rows:
        lw_id = row["id"]
        status = row["status"]
        fired_platforms = row["fired_platforms"]

        status_flags = LiveWatchStatusFlags.WATCHING
        if status == "fired":
            status_flags = LiveWatchStatusFlags.FIRED

        fired_mask = OddsProviderFlags.NONE
        if fired_platforms:
            for p in fired_platforms.split(","):
                p_clean = p.strip().lower()
                for member in OddsProviderFlags:
                    if member.name.lower() == p_clean or member.name.lower() + "_http" == p_clean:
                        fired_mask |= member

        connection.execute(
            """
            UPDATE live_watch_entries
            SET status_flags = ?, fired_odds_mask = ?
            WHERE id = ?
            """,
            (int(status_flags), int(fired_mask), lw_id)
        )

    # F. Create Triggers to automatically synchronize legacy tables to new binary schema tables
    connection.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS t_active_events_insert AFTER INSERT ON active_events
        BEGIN
            INSERT OR REPLACE INTO events (id, unified_competition_id, home, away, scheduled_at, event_urls, status_flags, created_at)
            VALUES (
                NEW.id,
                COALESCE(
                    (SELECT unified_competition_id FROM tracked_competitions WHERE id = NEW.tracked_competition_id),
                    (SELECT id FROM unified_competitions WHERE name = NEW.competition_external_id LIMIT 1),
                    1
                ),
                NEW.home,
                NEW.away,
                NEW.scheduled_at,
                json_object(NEW.platform, NEW.event_url),
                (CASE WHEN NEW.is_active THEN 1 ELSE 0 END) | (CASE WHEN NEW.reminder_sent_at IS NOT NULL THEN 16 ELSE 0 END),
                NEW.created_at
            );

            INSERT OR REPLACE INTO event_odds_snapshots (event_id, platform, odds_home, odds_draw, odds_away, markets_mask, markets_json, extracted_at)
            VALUES (
                NEW.id,
                NEW.platform,
                NEW.odds_home,
                NEW.odds_draw,
                NEW.odds_away,
                (CASE WHEN NEW.odds_home IS NOT NULL THEN 1 ELSE 0 END),
                NEW.markets_json,
                NEW.updated_at
            );
        END;

        CREATE TRIGGER IF NOT EXISTS t_active_events_update AFTER UPDATE ON active_events
        BEGIN
            UPDATE events SET
                home = NEW.home,
                away = NEW.away,
                scheduled_at = NEW.scheduled_at,
                event_urls = json_set(COALESCE(event_urls, '{}'), '$.' || NEW.platform, NEW.event_url),
                status_flags = (CASE WHEN NEW.is_active THEN 1 ELSE 0 END) | (CASE WHEN NEW.reminder_sent_at IS NOT NULL THEN 16 ELSE 0 END)
            WHERE id = NEW.id;

            INSERT OR REPLACE INTO event_odds_snapshots (event_id, platform, odds_home, odds_draw, odds_away, markets_mask, markets_json, extracted_at)
            VALUES (
                NEW.id,
                NEW.platform,
                NEW.odds_home,
                NEW.odds_draw,
                NEW.odds_away,
                (CASE WHEN NEW.odds_home IS NOT NULL THEN 1 ELSE 0 END) | (CASE WHEN NEW.markets_json IS NOT NULL THEN 2 ELSE 0 END),
                NEW.markets_json,
                NEW.updated_at
            );
        END;

        CREATE TRIGGER IF NOT EXISTS t_active_events_delete AFTER DELETE ON active_events
        BEGIN
            DELETE FROM events WHERE id = OLD.id;
            DELETE FROM event_odds_snapshots WHERE event_id = OLD.id;
        END;

        CREATE TRIGGER IF NOT EXISTS t_competition_subscriptions_insert AFTER INSERT ON competition_subscriptions
        BEGIN
            INSERT OR REPLACE INTO chat_subscriptions (chat_id, target_type, target_id, settings_mask, change_threshold_percent, enabled, created_at, updated_at)
            VALUES (
                NEW.telegram_chat_id,
                'odds',
                COALESCE((SELECT unified_competition_id FROM tracked_competitions WHERE id = NEW.tracked_competition_id), 1),
                (CASE WHEN NEW.notify_odds_changes THEN 1 ELSE 0 END) | (CASE WHEN NEW.notify_new_events THEN 2 ELSE 0 END) | 4 | 8,
                NEW.change_threshold_percent,
                NEW.enabled,
                NEW.created_at,
                NEW.updated_at
            );
        END;

        CREATE TRIGGER IF NOT EXISTS t_competition_subscriptions_update AFTER UPDATE ON competition_subscriptions
        BEGIN
            UPDATE chat_subscriptions SET
                settings_mask = (CASE WHEN NEW.notify_odds_changes THEN 1 ELSE 0 END) | (CASE WHEN NEW.notify_new_events THEN 2 ELSE 0 END) | 4 | 8,
                change_threshold_percent = NEW.change_threshold_percent,
                enabled = NEW.enabled,
                updated_at = NEW.updated_at
            WHERE chat_id = NEW.telegram_chat_id
              AND target_type = 'odds'
              AND target_id = COALESCE((SELECT unified_competition_id FROM tracked_competitions WHERE id = NEW.tracked_competition_id), 1);
        END;

        CREATE TRIGGER IF NOT EXISTS t_competition_subscriptions_delete AFTER DELETE ON competition_subscriptions
        BEGIN
            DELETE FROM chat_subscriptions
            WHERE chat_id = OLD.telegram_chat_id
              AND target_type = 'odds'
              AND target_id = COALESCE((SELECT unified_competition_id FROM tracked_competitions WHERE id = OLD.tracked_competition_id), 1);
        END;

        CREATE TRIGGER IF NOT EXISTS t_stats_league_subscriptions_insert AFTER INSERT ON stats_league_subscriptions
        BEGIN
            INSERT OR REPLACE INTO chat_subscriptions (chat_id, target_type, target_id, settings_mask, change_threshold_percent, enabled, created_at, updated_at)
            VALUES (
                NEW.telegram_chat_id,
                'stats',
                COALESCE(
                    (SELECT unified_competition_id FROM stats_league_links WHERE stats_provider = NEW.stats_provider AND stats_league_id = NEW.stats_league_id LIMIT 1),
                    1
                ),
                64,
                20.0,
                NEW.enabled,
                NEW.created_at,
                NEW.updated_at
            );
        END;

        CREATE TRIGGER IF NOT EXISTS t_stats_league_subscriptions_update AFTER UPDATE ON stats_league_subscriptions
        BEGIN
            UPDATE chat_subscriptions SET
                enabled = NEW.enabled,
                updated_at = NEW.updated_at
            WHERE chat_id = NEW.telegram_chat_id
              AND target_type = 'stats'
              AND target_id = COALESCE(
                  (SELECT unified_competition_id FROM stats_league_links WHERE stats_provider = NEW.stats_provider AND stats_league_id = NEW.stats_league_id LIMIT 1),
                  1
              );
        END;

        CREATE TRIGGER IF NOT EXISTS t_stats_league_subscriptions_delete AFTER DELETE ON stats_league_subscriptions
        BEGIN
            DELETE FROM chat_subscriptions
            WHERE chat_id = OLD.telegram_chat_id
              AND target_type = 'stats'
              AND target_id = COALESCE(
                  (SELECT unified_competition_id FROM stats_league_links WHERE stats_provider = OLD.stats_provider AND stats_league_id = OLD.stats_league_id LIMIT 1),
                  1
              );
        END;

        CREATE TRIGGER IF NOT EXISTS t_live_watch_entries_insert AFTER INSERT ON live_watch_entries
        BEGIN
            UPDATE live_watch_entries SET
                status_flags = (CASE WHEN NEW.status = 'fired' THEN 2 WHEN NEW.status = 'cancelled' THEN 4 ELSE 1 END),
                fired_odds_mask = COALESCE(fired_odds_mask, 0)
            WHERE id = NEW.id;
        END;

        CREATE TRIGGER IF NOT EXISTS t_live_watch_entries_update AFTER UPDATE OF status, fired_platforms ON live_watch_entries
        BEGIN
            UPDATE live_watch_entries SET
                status_flags = (CASE WHEN NEW.status = 'fired' THEN 2 WHEN NEW.status = 'cancelled' THEN 4 ELSE 1 END)
            WHERE id = NEW.id;
        END;
        """
    )

    # G. Subscriptions Hexadecimal Bitmap Schema & Triggers
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_subscriptions_bitmap (
            chat_id INTEGER PRIMARY KEY,
            tracked_odds_leagues_hex TEXT,
            tracked_stats_leagues_hex TEXT,
            updated_at TEXT NOT NULL
        );
        """
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS dirty_chats (
            chat_id INTEGER PRIMARY KEY
        );
        """
    )

    connection.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS t_dirty_chats_insert_odds AFTER INSERT ON competition_subscriptions
        BEGIN
            INSERT OR IGNORE INTO dirty_chats (chat_id) VALUES (NEW.telegram_chat_id);
        END;

        CREATE TRIGGER IF NOT EXISTS t_dirty_chats_update_odds AFTER UPDATE ON competition_subscriptions
        BEGIN
            INSERT OR IGNORE INTO dirty_chats (chat_id) VALUES (NEW.telegram_chat_id);
            INSERT OR IGNORE INTO dirty_chats (chat_id) VALUES (OLD.telegram_chat_id);
        END;

        CREATE TRIGGER IF NOT EXISTS t_dirty_chats_delete_odds AFTER DELETE ON competition_subscriptions
        BEGIN
            INSERT OR IGNORE INTO dirty_chats (chat_id) VALUES (OLD.telegram_chat_id);
        END;

        CREATE TRIGGER IF NOT EXISTS t_dirty_chats_insert_stats AFTER INSERT ON stats_league_subscriptions
        BEGIN
            INSERT OR IGNORE INTO dirty_chats (chat_id) VALUES (NEW.telegram_chat_id);
        END;

        CREATE TRIGGER IF NOT EXISTS t_dirty_chats_update_stats AFTER UPDATE ON stats_league_subscriptions
        BEGIN
            INSERT OR IGNORE INTO dirty_chats (chat_id) VALUES (NEW.telegram_chat_id);
            INSERT OR IGNORE INTO dirty_chats (chat_id) VALUES (OLD.telegram_chat_id);
        END;

        CREATE TRIGGER IF NOT EXISTS t_dirty_chats_delete_stats AFTER DELETE ON stats_league_subscriptions
        BEGIN
            INSERT OR IGNORE INTO dirty_chats (chat_id) VALUES (OLD.telegram_chat_id);
        END;
        """
    )

    # H. Ensure status_flags and backfill for small_changes
    _ensure_column(connection, "small_changes", "status_flags", "INTEGER NOT NULL DEFAULT 16")
    connection.execute(
        """
        UPDATE small_changes
        SET status_flags = CASE WHEN status = 'confirmed' THEN 32 WHEN status = 'dismissed' THEN 64 ELSE 16 END
        WHERE status_flags = 16 AND status != 'pending'
        """
    )

    # I. Backfill dirty chats for existing databases
    connection.execute(
        """
        INSERT OR IGNORE INTO dirty_chats (chat_id)
        SELECT DISTINCT telegram_chat_id FROM (
            SELECT telegram_chat_id FROM competition_subscriptions
            UNION
            SELECT telegram_chat_id FROM stats_league_subscriptions
        ) WHERE telegram_chat_id NOT IN (SELECT chat_id FROM chat_subscriptions_bitmap)
        """
    )




def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    existing_columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return

    connection.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
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
            consecutive_unavailable_refreshes,
            last_unavailable_refresh_at,
            last_unavailable_reason,
            last_unavailable_notification_at,
            created_at,
            updated_at,
            unified_competition_id
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
            consecutive_unavailable_refreshes,
            last_unavailable_refresh_at,
            last_unavailable_reason,
            last_unavailable_notification_at,
            created_at,
            updated_at,
            unified_competition_id
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
            tc.consecutive_unavailable_refreshes AS tracked_consecutive_unavailable_refreshes,
            tc.last_unavailable_refresh_at AS tracked_last_unavailable_refresh_at,
            tc.last_unavailable_reason AS tracked_last_unavailable_reason,
            tc.last_unavailable_notification_at AS tracked_last_unavailable_notification_at,
            tc.created_at AS tracked_created_at,
            tc.updated_at AS tracked_updated_at,
            tc.unified_competition_id AS tracked_unified_competition_id,
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
            tc.consecutive_unavailable_refreshes AS tracked_consecutive_unavailable_refreshes,
            tc.last_unavailable_refresh_at AS tracked_last_unavailable_refresh_at,
            tc.last_unavailable_reason AS tracked_last_unavailable_reason,
            tc.last_unavailable_notification_at AS tracked_last_unavailable_notification_at,
            tc.created_at AS tracked_created_at,
            tc.updated_at AS tracked_updated_at,
            tc.unified_competition_id AS tracked_unified_competition_id,
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


def _fetch_active_event_row_by_id(
    connection: sqlite3.Connection,
    active_event_id: int,
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
        WHERE id = ?
          AND is_active = 1
        LIMIT 1
        """,
        (active_event_id,),
    ).fetchone()


def _fetch_stats_league_link_row(
    connection: sqlite3.Connection,
    tracked_competition_id: int,
    stats_provider: str | None = None,
) -> sqlite3.Row | None:
    if stats_provider:
        normalized_provider = _normalize_platform(stats_provider)
        return connection.execute(
            """
            SELECT
                id,
                tracked_competition_id,
                stats_provider,
                stats_league_id,
                stats_league_name,
                stats_country_name,
                confidence,
                payload_json,
                created_at,
                updated_at
            FROM stats_league_links
            WHERE tracked_competition_id = ?
              AND stats_provider = ?
            LIMIT 1
            """,
            (tracked_competition_id, normalized_provider),
        ).fetchone()
    return connection.execute(
        """
        SELECT
            id,
            tracked_competition_id,
            stats_provider,
            stats_league_id,
            stats_league_name,
            stats_country_name,
            confidence,
            payload_json,
            created_at,
            updated_at
        FROM stats_league_links
        WHERE tracked_competition_id = ?
        LIMIT 1
        """,
        (tracked_competition_id,),
    ).fetchone()


def _fetch_stats_league_subscription_row(
    connection: sqlite3.Connection,
    chat_id: int,
    stats_provider: str,
    stats_league_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            telegram_chat_id,
            stats_provider,
            stats_league_id,
            stats_league_name,
            stats_country_name,
            source_url,
            payload_json,
            enabled,
            created_at,
            updated_at
        FROM stats_league_subscriptions
        WHERE telegram_chat_id = ?
          AND stats_provider = ?
          AND stats_league_id = ?
        LIMIT 1
        """,
        (chat_id, stats_provider, stats_league_id),
    ).fetchone()


def _fetch_stats_match_link_row(
    connection: sqlite3.Connection,
    active_event_id: int,
    stats_provider: str | None = None,
) -> sqlite3.Row | None:
    if stats_provider:
        normalized_provider = _normalize_platform(stats_provider)
        return connection.execute(
            """
            SELECT
                id,
                active_event_id,
                stats_provider,
                stats_match_id,
                stats_url,
                confidence,
                method,
                payload_json,
                created_at,
                updated_at
            FROM stats_match_links
            WHERE active_event_id = ?
              AND stats_provider = ?
            LIMIT 1
            """,
            (active_event_id, normalized_provider),
        ).fetchone()
    return connection.execute(
        """
        SELECT
            id,
            active_event_id,
            stats_provider,
            stats_match_id,
            stats_url,
            confidence,
            method,
            payload_json,
            created_at,
            updated_at
        FROM stats_match_links
        WHERE active_event_id = ?
        LIMIT 1
        """,
        (active_event_id,),
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
            ae.scheduled_at,
            sc.previous_odds_home,
            sc.previous_odds_draw,
            sc.previous_odds_away,
            sc.current_odds_home,
            sc.current_odds_draw,
            sc.current_odds_away,
            sc.max_change_percent,
            sc.payload_json,
            sc.status,
            sc.status_flags,
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
            ae.scheduled_at,
            sc.previous_odds_home,
            sc.previous_odds_draw,
            sc.previous_odds_away,
            sc.current_odds_home,
            sc.current_odds_draw,
            sc.current_odds_away,
            sc.max_change_percent,
            sc.payload_json,
            sc.status,
            sc.status_flags,
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
            SELECT id, external_event_id, raw_payload_json
            FROM active_events
            WHERE tracked_competition_id = ? AND is_active = 1
            ORDER BY external_event_id
            """,
            (tracked_competition_id,),
        ).fetchall()

    placeholders = ", ".join("?" for _ in current_event_ids)
    return connection.execute(
        f"""
        SELECT id, external_event_id, raw_payload_json
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


def _ensure_active_event_exists(
    connection: sqlite3.Connection,
    active_event_id: int,
) -> None:
    row = _fetch_active_event_row_by_id(connection, active_event_id)
    if row is None:
        raise ValueError(f"No active event found with id={active_event_id}.")


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


def _loads_json_object(raw_value: Any) -> dict[str, Any]:
    normalized = (str(raw_value).strip() if raw_value is not None else "")
    if not normalized:
        return {}

    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        return {}

    return payload if isinstance(payload, dict) else {}


def _is_past_scheduled_at(raw_value: str | None, reference: datetime) -> bool:
    if raw_value is None:
        return False

    parsed = _parse_utc_datetime(str(raw_value))
    if parsed is None:
        return False

    return parsed <= reference


def _is_future_or_unscheduled(raw_value: str | None, reference: datetime) -> bool:
    if raw_value is None:
        return True

    parsed = _parse_utc_datetime(raw_value)
    if parsed is None:
        return True

    return parsed > reference


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _platform_to_odds_flag(platform: str) -> int:
    from core.flags import OddsProviderFlags
    p_clean = platform.strip().lower()
    p_name = p_clean.replace('_http', '').upper()
    if p_name == '1XBET':
        p_name = 'XBET'
    try:
        return int(getattr(OddsProviderFlags, p_name))
    except AttributeError:
        return 0


def _provider_to_stats_flag(provider: str) -> int:
    from core.flags import StatsProviderFlags
    p_clean = provider.strip().lower()
    p_name = p_clean.replace('_http', '').replace('_statshub', '').replace('_nff', '').replace('_frf', '').replace('_sportnet', '').replace('_lnff', '').upper()
    if p_name == 'NORWAY_NFF':
        p_name = 'NORWAY'
    elif p_name == 'ROMANIA_FRF':
        p_name = 'ROMANIA'
    elif p_name == 'SLOVAKIA_SPORTNET':
        p_name = 'SLOVAKIA'
    elif p_name == 'ALGERIA_LNFF':
        p_name = 'ALGERIA'
    try:
        return int(getattr(StatsProviderFlags, p_name))
    except AttributeError:
        return 0


def _row_to_live_watch(row: sqlite3.Row) -> LiveWatchEntry:
    return LiveWatchEntry(
        id=int(row["id"]),
        chat_id=int(row["chat_id"]),
        home=row["home"],
        away=row["away"],
        league_hint=row["league_hint"],
        note=row["note"],
        status=row["status"],
        matched_platform=row["matched_platform"],
        matched_event_id=row["matched_event_id"],
        matched_minute=row["matched_minute"],
        created_at=row["created_at"],
        fired_at=row["fired_at"],
        kickoff_at=row["kickoff_at"] if "kickoff_at" in row.keys() else None,
        prematch_seen_at=row["prematch_seen_at"] if "prematch_seen_at" in row.keys() else None,
        prematch_platform=row["prematch_platform"] if "prematch_platform" in row.keys() else None,
        fired_platforms=row["fired_platforms"] if "fired_platforms" in row.keys() else None,
        prematch_fired_platforms=row["prematch_fired_platforms"] if "prematch_fired_platforms" in row.keys() else None,
        countdown_fired_at=row["countdown_fired_at"] if "countdown_fired_at" in row.keys() else None,
        chat_local_id=row["chat_local_id"] if "chat_local_id" in row.keys() else None,
        live_state_json=row["live_state_json"] if "live_state_json" in row.keys() else None,
        status_flags=int(row["status_flags"]) if "status_flags" in row.keys() and row["status_flags"] is not None else 1,
        fired_odds_mask=int(row["fired_odds_mask"]) if "fired_odds_mask" in row.keys() and row["fired_odds_mask"] is not None else 0,
        fired_stats_mask=int(row["fired_stats_mask"]) if "fired_stats_mask" in row.keys() and row["fired_stats_mask"] is not None else 0,
    )





def _remove_chat_subscription(
    connection: sqlite3.Connection,
    chat_id: int,
    tracked_competition_id: int,
) -> UntrackCompetitionResult:
    """Remove one chat subscription (within a connection) and disable orphans."""

    now_iso = _utc_now_iso()
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

    for table in ("user_event_baselines", "small_changes", "sent_alerts"):
        connection.execute(
            f"""
            DELETE FROM {table}
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


def _propagate_unified_subscriptions(
    connection: sqlite3.Connection,
    unified_competition_id: int | None,
) -> int:
    """Spread each chat's league subscription to EVERY platform of the league.

    Subscriptions are conceptually per unified league (decision: track via one
    platform -> inherit all current and future platform links). Storage stays in
    ``competition_subscriptions`` (per tracked comp) so the poller/alerts pipeline
    is untouched; this keeps that storage consistent with the league-level model.
    Returns the number of subscriptions created.
    """

    if unified_competition_id is None:
        return 0
    now_iso = _utc_now_iso()
    cursor = connection.execute(
        """
        INSERT INTO competition_subscriptions (
            telegram_chat_id, tracked_competition_id, notify_new_events,
            notify_odds_changes, change_threshold_percent, enabled, created_at, updated_at
        )
        SELECT s.telegram_chat_id, tc.id, s.notify_new_events,
               s.notify_odds_changes, s.change_threshold_percent, 1, ?, ?
        FROM (
            SELECT cs.telegram_chat_id,
                   MAX(cs.notify_new_events) AS notify_new_events,
                   MAX(cs.notify_odds_changes) AS notify_odds_changes,
                   MAX(cs.change_threshold_percent) AS change_threshold_percent
            FROM competition_subscriptions cs
            INNER JOIN tracked_competitions x ON x.id = cs.tracked_competition_id
            WHERE x.unified_competition_id = ? AND cs.enabled = 1
            GROUP BY cs.telegram_chat_id
        ) s
        CROSS JOIN tracked_competitions tc
        WHERE tc.unified_competition_id = ? AND tc.enabled = 1
          AND NOT EXISTS (
            SELECT 1 FROM competition_subscriptions e
            WHERE e.telegram_chat_id = s.telegram_chat_id
              AND e.tracked_competition_id = tc.id
          )
        """,
        (now_iso, now_iso, unified_competition_id, unified_competition_id),
    )
    return int(cursor.rowcount or 0)


def _insert_unified_competition(connection: sqlite3.Connection, name: str) -> int:
    """Insert a unified competition with its registry fields (public slug + traits).

    Every code path that creates a unified competition must go through here so the
    league registry (public_id / country / gender / age_group) stays complete.
    """

    from core.league_naming import extract_league_traits, league_slug

    clean = str(name).strip()
    base_name = clean
    suffix = 2
    while connection.execute(
        "SELECT 1 FROM unified_competitions WHERE name = ?", (clean,)
    ).fetchone() is not None:
        clean = f"{base_name} ({suffix})"
        suffix += 1

    now_iso = _utc_now_iso()
    # The name column is UNIQUE too: suffix it when taken (e.g. /unlink_league
    # splits a platform off a league that keeps the same name).
    base_name = clean
    name_suffix = 2
    while connection.execute(
        "SELECT 1 FROM unified_competitions WHERE name = ?", (clean,)
    ).fetchone() is not None:
        clean = f"{base_name} ({name_suffix})"
        name_suffix += 1
    base = league_slug(clean) or "league"
    slug = base
    suffix = 2
    while connection.execute(
        "SELECT 1 FROM unified_competitions WHERE public_id = ?", (slug,)
    ).fetchone() is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    traits = extract_league_traits(clean)
    cursor = connection.execute(
        """
        INSERT INTO unified_competitions (
            name, public_id, display_name, country, gender, age_group, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (clean, slug, clean, traits["country"], traits["gender"], traits["age_group"], now_iso, now_iso),
    )
    return int(cursor.lastrowid)


def _find_or_create_unified_competition_id(connection: sqlite3.Connection, name: str) -> int:
    """Auto-merge a league into an existing unified ONLY on safe signals.

    Safe = identical name, canonical-equal (word order/aliases, preserving the
    gender/age discriminators), or anagram-equal. The loose fuzzy similarity is
    NO LONGER an auto-merge signal — it caused false positives (Women vs U20,
    Australia "Cup" vs "Svenska Cup"); it is exposed as a *suggestion* instead
    (see :meth:`suggest_similar_unified`), so the user confirms with /link_league.
    """

    from core.league_naming import anagram_key, extract_league_traits, normalize_league_name

    name_clean = name.strip()
    target_norm = normalize_league_name(name_clean)
    target_anagram = anagram_key(name_clean)
    target_traits = extract_league_traits(name_clean)
    # A name with <2 canonical tokens and no country ("Cup") is too generic to
    # auto-merge: every country has one. Require an exact-name match for those.
    too_generic = len(target_norm.split()) < 2 and not target_traits["country"]

    rows = connection.execute("SELECT id, name FROM unified_competitions").fetchall()
    for r in rows:
        cand_traits = extract_league_traits(r["name"])
        # Hard guard: explicit different countries are different leagues.
        if target_traits["country"] and cand_traits["country"] and target_traits["country"] != cand_traits["country"]:
            continue
        # 1. Exact (case-insensitive) — strongest signal, always wins.
        if r["name"].strip().lower() == name_clean.lower():
            return r["id"]
        if too_generic:
            continue
        # 2. Canonical match: "USL League 2" == "USL League Two", word shuffle
        #    ("NPL League" == "League NPL"), "Estados Unidos" == "USA". Preserves
        #    gender/age, so Women never equals U20.
        if target_norm and normalize_league_name(r["name"]) == target_norm:
            return r["id"]
        # 3. Anagram match: same characters once canonicalised (extra tolerance to
        #    spacing/order). Discriminators are encoded in the chars, so it is safe.
        if target_anagram and anagram_key(r["name"]) == target_anagram:
            return r["id"]

    # No safe match -> new unified competition (fuzzy stays a suggestion only).
    return _insert_unified_competition(connection, name_clean)


tracking_repository = SqliteTrackingRepository()


__all__ = [
    "ActiveEventRecord",
    "ActiveEventUpsert",
    "CompetitionSubscription",
    "ConfirmedCompetitionTrackRequest",
    "DB_FILE_PATH",
    "EventBaseline",
    "LiveWatchEntry",
    "LiveWatchSettings",
    "PendingCompetitionTrackRequest",
    "SmallChangeRecord",
    "SqliteTrackingRepository",
    "StatsLeagueLink",
    "StatsLeagueSubscription",
    "StatsMatchLinkRecord",
    "TrackedCompetition",
    "TrackedCompetitionSubscription",
    "UntrackCompetitionResult",
    "tracking_repository",
]
