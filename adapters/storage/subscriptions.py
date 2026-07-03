from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from core.models import (
    CompetitionSubscription,
    TrackedCompetition,
    TrackedCompetitionSubscription,
    StatsLeagueSubscription,
)
from core.ports.subscriptions import SubscriptionsPort
from adapters.storage.connection import open_connection

def _row_to_subscription(row: sqlite3.Row) -> CompetitionSubscription:
    return CompetitionSubscription(
        telegram_chat_id=int(row["chat_id"]),
        tracked_competition_id=int(row["competition_id"]),
        notify_new_events=bool(row["notify_new_events"]),
        notify_odds_changes=bool(row["notify_odds_changes"]),
        change_percent_threshold=float(row["change_threshold_percent"]),
        enabled=bool(row["enabled"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )

def _row_to_tracked_competition(row: sqlite3.Row) -> TrackedCompetition:
    # Resolve needs_name_resolution flag from metadata if available, otherwise default
    metadata_json = row["metadata_json"]
    needs_name_res = False
    if metadata_json:
        try:
            meta = json.loads(metadata_json)
            needs_name_res = meta.get("needs_name_resolution", row["unified_competition_id"] is None)
        except Exception:
            needs_name_res = row["unified_competition_id"] is None
    else:
        needs_name_res = row["unified_competition_id"] is None

    return TrackedCompetition(
        id=int(row["id"]),
        platform=str(row["platform"]),
        source_url=str(row["source_url"]),
        competition_external_id=str(row["external_id"]),
        competition_name=str(row["name"]),
        metadata_json=metadata_json,
        needs_name_resolution=needs_name_res,
        enabled=bool(row["enabled"]),
        last_synced_at=row["last_refreshed_at"] if row["last_refreshed_at"] else None,
        consecutive_unavailable_refreshes=int(row["consecutive_unavailable_refreshes"]),
        last_unavailable_refresh_at=row["last_unavailable_at"] if row["last_unavailable_at"] else None,
        last_unavailable_reason=row["last_unavailable_reason"] if row["last_unavailable_reason"] else None,
        last_unavailable_notification_at=row["last_unavailable_notified_at"] if row["last_unavailable_notified_at"] else None,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        unified_competition_id=int(row["unified_competition_id"]) if row["unified_competition_id"] is not None else None,
    )

def _row_to_stats_league_sub(row: sqlite3.Row) -> StatsLeagueSubscription:
    return StatsLeagueSubscription(
        telegram_chat_id=int(row["chat_id"]),
        stats_provider=str(row["provider"]),
        stats_league_id=str(row["league_id"]),
        stats_league_name=str(row["league_name"]),
        stats_country_name=row["country_name"],
        source_url=row["source_url"],
        payload_json=row["payload_json"],
        enabled=bool(row["enabled"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class SQLiteSubscriptionsAdapter(SubscriptionsPort):
    """Adapter implementing SubscriptionsPort using SQLite."""

    def get_tracked_competition_subscription(
        self,
        chat_id: int,
        tracked_id: int,
    ) -> CompetitionSubscription | None:
        with open_connection() as conn:
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE chat_id = ? AND competition_id = ?",
                (chat_id, tracked_id)
            ).fetchone()
            return _row_to_subscription(row) if row else None

    def get_tracked_competition_subscription_by_identity(
        self,
        chat_id: int,
        platform: str,
        external_id: str,
    ) -> TrackedCompetitionSubscription | None:
        query = """
            SELECT s.*, c.id AS comp_db_id, c.name, c.source_url, c.metadata_json, c.unified_competition_id, 
                   c.enabled AS comp_enabled, c.last_refreshed_at, c.consecutive_unavailable_refreshes, 
                   c.last_unavailable_at, c.last_unavailable_reason, c.last_unavailable_notified_at, 
                   c.created_at AS comp_created_at, c.updated_at AS comp_updated_at
            FROM subscriptions s
            INNER JOIN competitions c ON s.competition_id = c.id
            WHERE s.chat_id = ? AND c.platform = ? AND c.external_id = ?
        """
        with open_connection() as conn:
            row = conn.execute(query, (chat_id, platform, external_id)).fetchone()
            if not row:
                return None
                
            # Construct DTOs
            sub = _row_to_subscription(row)
            
            # Map competition row to expected column names
            comp_row = {
                "id": row["comp_db_id"],
                "platform": platform,
                "external_id": external_id,
                "name": row["name"],
                "source_url": row["source_url"],
                "metadata_json": row["metadata_json"],
                "unified_competition_id": row["unified_competition_id"],
                "enabled": row["comp_enabled"],
                "last_refreshed_at": row["last_refreshed_at"],
                "consecutive_unavailable_refreshes": row["consecutive_unavailable_refreshes"],
                "last_unavailable_at": row["last_unavailable_at"],
                "last_unavailable_reason": row["last_unavailable_reason"],
                "last_unavailable_notified_at": row["last_unavailable_notified_at"],
                "created_at": row["comp_created_at"],
                "updated_at": row["comp_updated_at"]
            }
            # Make a Row-like helper
            class RowMock:
                def __init__(self, d): self.d = d
                def __getitem__(self, k): return self.d[k]
            comp = _row_to_tracked_competition(RowMock(comp_row))
            
            return TrackedCompetitionSubscription(tracked_competition=comp, subscription=sub)

    def get_subscriptions_for_competition(
        self,
        tracked_id: int,
    ) -> list[CompetitionSubscription]:
        with open_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM subscriptions WHERE competition_id = ? AND enabled = 1",
                (tracked_id,)
            ).fetchall()
            return [_row_to_subscription(row) for row in rows]

    def get_enabled_subscription_count(self, *args: Any) -> int:
        # Legacy signature: get_enabled_subscription_count(self, tracked_competition_id: int)
        # Port signature: get_enabled_subscription_count(self)
        with open_connection() as conn:
            if args:
                tracked_competition_id = args[0]
                row = conn.execute(
                    "SELECT COUNT(*) FROM subscriptions WHERE competition_id = ? AND enabled = 1",
                    (tracked_competition_id,)
                ).fetchone()
                return row[0] if row else 0
            else:
                row = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE enabled = 1").fetchone()
                return row[0] if row else 0

    def remove_tracked_competition_subscription(
        self,
        chat_id: int,
        tracked_id: int,
    ) -> bool:
        with open_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM subscriptions WHERE chat_id = ? AND competition_id = ?",
                (chat_id, tracked_id)
            )
            return cursor.rowcount > 0

    def remove_unified_subscription(
        self,
        chat_id: int,
        unified_id: int,
    ) -> bool:
        with open_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM subscriptions 
                WHERE chat_id = ? AND competition_id IN (
                    SELECT id FROM competitions WHERE unified_competition_id = ?
                )
                """,
                (chat_id, unified_id)
            )
            return cursor.rowcount > 0

    def set_change_percent_threshold(
        self,
        chat_id: int,
        tracked_id: int,
        percent: float,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            conn.execute(
                """
                UPDATE subscriptions
                SET change_threshold_percent = ?, updated_at = ?
                WHERE chat_id = ? AND competition_id = ?
                """,
                (percent, now_iso, chat_id, tracked_id)
            )

    def set_odds_notifications(
        self,
        chat_id: int,
        tracked_id: int,
        enabled: bool,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            conn.execute(
                """
                UPDATE subscriptions
                SET notify_odds_changes = ?, updated_at = ?
                WHERE chat_id = ? AND competition_id = ?
                """,
                (1 if enabled else 0, now_iso, chat_id, tracked_id)
            )

    def set_competition_reminders(
        self,
        arg1: int,
        arg2: int | bool,
        arg3: bool | None = None,
    ) -> None:
        # Port signature: set_competition_reminders(self, chat_id, tracked_id, enabled)
        # Legacy signature: set_competition_reminders(self, tracked_competition_id, enabled)
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            if arg3 is not None:
                chat_id = arg1
                tracked_id = int(arg2)
                enabled = bool(arg3)
                
                # Check if subscription exists, if not create one with default values
                existing = conn.execute(
                    "SELECT 1 FROM subscriptions WHERE chat_id = ? AND competition_id = ?",
                    (chat_id, tracked_id)
                ).fetchone()
                
                if existing:
                    conn.execute(
                        """
                        UPDATE subscriptions
                        SET reminders_enabled = ?, updated_at = ?
                        WHERE chat_id = ? AND competition_id = ?
                        """,
                        (1 if enabled else 0, now_iso, chat_id, tracked_id)
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO subscriptions (
                            chat_id, competition_id, notify_new_events, notify_odds_changes,
                            change_threshold_percent, reminders_enabled, enabled, created_at, updated_at
                        )
                        VALUES (?, ?, 1, 1, 20.0, ?, 1, ?, ?)
                        """,
                        (chat_id, tracked_id, 1 if enabled else 0, now_iso, now_iso)
                    )
            else:
                tracked_competition_id = arg1
                enabled = bool(arg2)
                
                conn.execute(
                    "UPDATE competitions SET reminders_enabled = ?, updated_at = ? WHERE id = ?",
                    (1 if enabled else 0, now_iso, tracked_competition_id)
                )

    def competition_reminders_enabled(
        self,
        arg1: int,
        arg2: int | None = None,
    ) -> bool:
        # Port signature: competition_reminders_enabled(self, chat_id, tracked_id)
        # Legacy signature: competition_reminders_enabled(self, tracked_competition_id)
        with open_connection() as conn:
            if arg2 is not None:
                chat_id = arg1
                tracked_id = arg2
                row = conn.execute(
                    "SELECT reminders_enabled FROM subscriptions WHERE chat_id = ? AND competition_id = ?",
                    (chat_id, tracked_id)
                ).fetchone()
                return bool(row["reminders_enabled"]) if row else False
            else:
                tracked_competition_id = arg1
                row = conn.execute(
                    "SELECT reminders_enabled FROM competitions WHERE id = ?",
                    (tracked_competition_id,)
                ).fetchone()
                return bool(row["reminders_enabled"]) if row else False

    def set_event_reminder(
        self,
        arg1: int,
        arg2: int | str,
        arg3: bool,
    ) -> None:
        # Port signature: set_event_reminder(self, chat_id: int, event_id: int, enabled: bool)
        # Legacy signature: set_event_reminder(self, tracked_competition_id: int, external_event_id: str, enabled: bool)
        with open_connection() as conn:
            if isinstance(arg2, str):
                # Legacy signature: tracked_competition_id, external_event_id, enabled
                tracked_competition_id = arg1
                external_event_id = arg2
                enabled = arg3
                
                conn.execute(
                    """
                    UPDATE events
                    SET reminder_enabled = ?, updated_at = ?
                    WHERE competition_id = ? AND external_event_id = ?
                    """,
                    (1 if enabled else 0, datetime.now(timezone.utc).isoformat(), tracked_competition_id, external_event_id)
                )
            else:
                # Port signature: chat_id, event_id, enabled
                chat_id = arg1
                event_id = arg2
                enabled = arg3
                
                # Check if it exists
                existing = conn.execute(
                    "SELECT 1 FROM chat_event_reminders WHERE chat_id = ? AND event_id = ?",
                    (chat_id, event_id)
                ).fetchone()
                
                if existing:
                    conn.execute(
                        "UPDATE chat_event_reminders SET enabled = ? WHERE chat_id = ? AND event_id = ?",
                        (1 if enabled else 0, chat_id, event_id)
                    )
                else:
                    conn.execute(
                        "INSERT INTO chat_event_reminders (chat_id, event_id, enabled) VALUES (?, ?, ?)",
                        (chat_id, event_id, 1 if enabled else 0)
                    )

    def event_reminder_enabled_ids(
        self,
        arg1: int,
    ) -> set[Any]:
        # Port signature: event_reminder_enabled_ids(self, chat_id: int) -> set[int]
        # Legacy signature: event_reminder_enabled_ids(self, tracked_competition_id: int) -> set[str]
        with open_connection() as conn:
            # Check if arg1 exists in competitions table to decide signature
            is_comp = conn.execute("SELECT 1 FROM competitions WHERE id = ?", (arg1,)).fetchone()
            
            if is_comp:
                # Legacy signature: return set[str] of external_event_ids
                rows = conn.execute(
                    "SELECT external_event_id FROM events WHERE competition_id = ? AND reminder_enabled = 1",
                    (arg1,)
                ).fetchall()
                return {str(r["external_event_id"]) for r in rows}
            else:
                # Port signature: return set[int] of event_ids
                rows = conn.execute(
                    "SELECT event_id FROM chat_event_reminders WHERE chat_id = ? AND enabled = 1",
                    (arg1,)
                ).fetchall()
                return {int(r["event_id"]) for r in rows}

    def list_stats_league_subscriptions(
        self,
        chat_id: int,
    ) -> list[StatsLeagueSubscription]:
        with open_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM stats_league_subscriptions WHERE chat_id = ? AND enabled = 1",
                (chat_id,)
            ).fetchall()
            return [_row_to_stats_league_sub(row) for row in rows]

    def upsert_stats_league_subscription(
        self,
        chat_id: int,
        provider: str | None = None,
        stats_league_id: str | None = None,
        stats_league_name: str | None = None,
        stats_country_name: str | None = None,
        source_url: str | None = None,
        enabled: bool = True,
        **kwargs: Any,
    ) -> None:
        provider = provider or kwargs.get("stats_provider")
        if not provider:
            raise TypeError("Missing required argument: 'provider' or 'stats_provider'")
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            existing = conn.execute(
                "SELECT 1 FROM stats_league_subscriptions WHERE chat_id = ? AND provider = ? AND league_id = ?",
                (chat_id, provider, stats_league_id)
            ).fetchone()
            
            if existing:
                conn.execute(
                    """
                    UPDATE stats_league_subscriptions
                    SET league_name = ?, country_name = ?, source_url = ?, enabled = ?, updated_at = ?
                    WHERE chat_id = ? AND provider = ? AND league_id = ?
                    """,
                    (stats_league_name, stats_country_name, source_url, 1 if enabled else 0, now_iso, chat_id, provider, stats_league_id)
                )
            else:
                conn.execute(
                    """
                    INSERT INTO stats_league_subscriptions (
                        chat_id, provider, league_id, league_name, country_name, source_url, enabled, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (chat_id, provider, stats_league_id, stats_league_name, stats_country_name, source_url, 1 if enabled else 0, now_iso, now_iso)
                )

    def list_peak_digest_chats(self) -> list[int]:
        with open_connection() as conn:
            rows = conn.execute("SELECT chat_id FROM peak_digest_subscriptions WHERE enabled = 1").fetchall()
            return [int(row["chat_id"]) for row in rows]

    def set_peak_digest_subscription(
        self,
        chat_id: int,
        enabled: bool,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            existing = conn.execute(
                "SELECT 1 FROM peak_digest_subscriptions WHERE chat_id = ?",
                (chat_id,)
            ).fetchone()
            
            if existing:
                conn.execute(
                    "UPDATE peak_digest_subscriptions SET enabled = ?, updated_at = ? WHERE chat_id = ?",
                    (1 if enabled else 0, now_iso, chat_id)
                )
            else:
                conn.execute(
                    "INSERT INTO peak_digest_subscriptions (chat_id, enabled, updated_at) VALUES (?, ?, ?)",
                    (chat_id, 1 if enabled else 0, now_iso)
                )
