from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Sequence

from core.models import ActiveEventRecord, ActiveEventUpsert
from core.ports.events import EventsPort
from adapters.storage.connection import open_connection

def _row_to_active_event_record(row: sqlite3.Row) -> ActiveEventRecord:
    return ActiveEventRecord(
        id=int(row["id"]),
        tracked_competition_id=int(row["competition_id"]),
        platform=str(row["platform"]),
        competition_external_id=str(row["competition_external_id"]),
        external_event_id=str(row["external_event_id"]),
        home=str(row["home"]),
        away=str(row["away"]),
        scheduled_label_date=row["scheduled_label_date"],
        scheduled_label_time=row["scheduled_label_time"],
        scheduled_at=row["scheduled_at"],
        event_url=row["event_url"],
        odds_home=row["odds_home"] if row["odds_home"] is not None else None,
        odds_draw=row["odds_draw"] if row["odds_draw"] is not None else None,
        odds_away=row["odds_away"] if row["odds_away"] is not None else None,
        markets_json=row["markets_json"],
        raw_payload_json=None,
        alerted=row["reminder_sent_at"] is not None,
        is_active=bool(row["is_active"]),
        first_seen_at=str(row["first_seen_at"]),
        last_seen_at=str(row["last_seen_at"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class SQLiteEventsAdapter(EventsPort):
    """Adapter implementing EventsPort using SQLite."""

    def upsert_active_events(
        self,
        tracked_competition_id: int,
        events: list[ActiveEventUpsert],
    ) -> list[ActiveEventRecord]:
        if not events:
            return []

        now_iso = datetime.now(timezone.utc).isoformat()
        
        with open_connection() as conn:
            # Verify competition exists
            comp = conn.execute("SELECT platform FROM competitions WHERE id = ?", (tracked_competition_id,)).fetchone()
            if not comp:
                raise ValueError(f"No tracked competition found with id={tracked_competition_id}")
            
            platform = comp["platform"]
            
            for event in events:
                ext_id = event.external_event_id.strip()
                home = event.home.strip()
                away = event.away.strip()
                
                if not ext_id or not home or not away:
                    raise ValueError("Each active event must include external_event_id, home, and away.")
                
                # Check for existing event to preserve first_seen_at and missing_seen_count
                existing = conn.execute(
                    "SELECT id, first_seen_at, reminder_sent_at FROM events WHERE platform = ? AND external_event_id = ?",
                    (platform, ext_id)
                ).fetchone()
                
                # Default markets format
                markets_payload = None
                if event.event_url: # Use event_url to match legacy default markets
                    pass
                if event.odds_home is not None or event.odds_draw is not None or event.odds_away is not None:
                    markets_payload = {
                        "1x2": {
                            "home": event.odds_home,
                            "draw": event.odds_draw,
                            "away": event.odds_away
                        }
                    }
                markets_json = json.dumps(markets_payload) if markets_payload else None
                
                if existing:
                    # Update
                    conn.execute(
                        """
                        UPDATE events
                        SET competition_id = ?,
                            home = ?,
                            away = ?,
                            scheduled_at = ?,
                            scheduled_label_date = ?,
                            scheduled_label_time = ?,
                            event_url = ?,
                            odds_home = ?,
                            odds_draw = ?,
                            odds_away = ?,
                            markets_json = ?,
                            is_active = 1,
                            missing_seen_count = 0,
                            last_seen_at = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            tracked_competition_id, home, away,
                            event.scheduled_at, event.scheduled_label_date, event.scheduled_label_time,
                            event.event_url, event.odds_home, event.odds_draw, event.odds_away,
                            markets_json, now_iso, now_iso, existing["id"]
                        )
                    )
                else:
                    # Insert
                    conn.execute(
                        """
                        INSERT INTO events (
                            competition_id, platform, external_event_id, home, away,
                            scheduled_at, scheduled_label_date, scheduled_label_time, event_url,
                            odds_home, odds_draw, odds_away, markets_json,
                            is_active, missing_seen_count, first_seen_at, last_seen_at, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?, ?, ?)
                        """,
                        (
                            tracked_competition_id, platform, ext_id, home, away,
                            event.scheduled_at, event.scheduled_label_date, event.scheduled_label_time,
                            event.event_url, event.odds_home, event.odds_draw, event.odds_away,
                            markets_json, now_iso, now_iso, now_iso, now_iso
                        )
                    )
                    
            # Retrieve and return all active events for this competition
            ext_ids = [e.external_event_id.strip() for e in events]
            placeholders = ",".join("?" for _ in ext_ids)
            rows = conn.execute(
                f"""
                SELECT e.*, c.external_id AS competition_external_id
                FROM events e
                INNER JOIN competitions c ON c.id = e.competition_id
                WHERE e.competition_id = ? AND e.external_event_id IN ({placeholders})
                """,
                [tracked_competition_id] + ext_ids
            ).fetchall()
            
            return [_row_to_active_event_record(row) for row in rows]

    def get_active_events(
        self,
        tracked_competition_id: int,
        exclude_alerted: bool = False,
        limit: int | None = None,
    ) -> list[ActiveEventRecord]:
        query = """
            SELECT e.*, c.external_id AS competition_external_id
            FROM events e
            INNER JOIN competitions c ON c.id = e.competition_id
            WHERE e.competition_id = ? AND e.is_active = 1
        """
        params: list[Any] = [tracked_competition_id]
        
        if exclude_alerted:
            query += " AND e.reminder_sent_at IS NULL"
            
        query += " ORDER BY e.scheduled_at IS NULL, e.scheduled_at, e.home, e.away, e.id"
        
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
            
        with open_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [_row_to_active_event_record(row) for row in rows]

    def get_all_active_events_with_league(
        self,
        chat_id: int,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT e.*, tc.name AS league_name, tc.external_id AS competition_external_id
            FROM events e
            INNER JOIN competitions tc ON e.competition_id = tc.id
            INNER JOIN subscriptions s ON s.competition_id = tc.id
            WHERE e.is_active = 1
              AND s.chat_id = ?
              AND s.enabled = 1
        """
        with open_connection() as conn:
            rows = conn.execute(query, (chat_id,)).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["alerted"] = row["reminder_sent_at"] is not None
                # Adapt fields for SimpleNamespace expectation if needed, or return dict directly
                result.append(d)
            return result

    def get_active_events_for_unified_competition(
        self,
        unified_id: int,
    ) -> list[ActiveEventRecord]:
        query = """
            SELECT e.*, c.external_id AS competition_external_id
            FROM events e
            INNER JOIN competitions c ON c.id = e.competition_id
            WHERE c.unified_competition_id = ? AND e.is_active = 1
            ORDER BY e.scheduled_at IS NULL, e.scheduled_at, e.home, e.away, e.id
        """
        with open_connection() as conn:
            rows = conn.execute(query, (unified_id,)).fetchall()
            return [_row_to_active_event_record(row) for row in rows]

    def get_earliest_kickoffs(
        self,
        arg: Any = 15,
    ) -> Any:
        # Check if caller passed a list of competition IDs (legacy behavior)
        if isinstance(arg, (list, tuple, set)):
            ids = [int(cid) for cid in arg]
            result = {cid: None for cid in ids}
            if not ids:
                return result
            
            floor_iso = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
            placeholders = ",".join("?" for _ in ids)
            
            with open_connection() as conn:
                rows = conn.execute(
                    f"""
                    SELECT competition_id AS cid, MIN(scheduled_at) AS earliest
                    FROM events
                    WHERE is_active = 1
                      AND scheduled_at IS NOT NULL
                      AND scheduled_at >= ?
                      AND competition_id IN ({placeholders})
                    GROUP BY competition_id
                    """,
                    [floor_iso] + ids
                ).fetchall()
            for row in rows:
                result[int(row["cid"])] = row["earliest"]
            return result
            
        else:
            # Port behavior: arg is minutes_threshold
            minutes_threshold = int(arg)
            now = datetime.now(timezone.utc)
            cutoff = (now + timedelta(minutes=minutes_threshold)).isoformat()
            now_iso = now.isoformat()
            
            query = """
                SELECT e.*, c.external_id AS competition_external_id
                FROM events e
                INNER JOIN competitions c ON c.id = e.competition_id
                WHERE e.is_active = 1
                  AND e.scheduled_at IS NOT NULL
                  AND e.scheduled_at >= ?
                  AND e.scheduled_at <= ?
                  AND e.reminder_sent_at IS NULL
            """
            with open_connection() as conn:
                rows = conn.execute(query, (now_iso, cutoff)).fetchall()
                return [dict(row) for row in rows]

    def remove_missing_events(
        self,
        tracked_competition_id: int,
        active_external_ids: list[str],
        max_missing_cycles: int = 3,
    ) -> int:
        normalized_ids = [eid.strip() for eid in active_external_ids if eid and eid.strip()]
        
        with open_connection() as conn:
            # Select all currently active events for this competition
            query = "SELECT id, external_event_id, missing_seen_count FROM events WHERE competition_id = ? AND is_active = 1"
            rows = conn.execute(query, (tracked_competition_id,)).fetchall()
            
            marked_inactive = 0
            
            for row in rows:
                ext_id = row["external_event_id"]
                if ext_id in normalized_ids:
                    continue
                
                # Increment missing count
                next_count = row["missing_seen_count"] + 1
                if next_count >= max(1, max_missing_cycles):
                    # Mark inactive
                    conn.execute(
                        "UPDATE events SET is_active = 0, missing_seen_count = ?, updated_at = ? WHERE id = ?",
                        (next_count, datetime.now(timezone.utc).isoformat(), row["id"])
                    )
                    marked_inactive += 1
                else:
                    conn.execute(
                        "UPDATE events SET missing_seen_count = ?, updated_at = ? WHERE id = ?",
                        (next_count, datetime.now(timezone.utc).isoformat(), row["id"])
                    )
                    
            return marked_inactive

    def remove_past_events(
        self,
        hours_ago: int = 4,
    ) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
        with open_connection() as conn:
            cursor = conn.execute(
                "UPDATE events SET is_active = 0, updated_at = ? WHERE is_active = 1 AND scheduled_at IS NOT NULL AND scheduled_at < ?",
                (datetime.now(timezone.utc).isoformat(), cutoff)
            )
            return cursor.rowcount

    def mark_events_alerted(
        self,
        event_ids: list[int],
    ) -> None:
        if not event_ids:
            return
            
        now_iso = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in event_ids)
        with open_connection() as conn:
            conn.execute(
                f"UPDATE events SET reminder_sent_at = ?, updated_at = ? WHERE id IN ({placeholders})",
                [now_iso, now_iso] + event_ids
            )
