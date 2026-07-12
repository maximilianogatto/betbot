from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Sequence

from core.models import EventBaseline, SmallChangeRecord
from core.ports.baselines import BaselinesPort
from adapters.storage.connection import open_connection

def _row_to_event_baseline(row: sqlite3.Row) -> EventBaseline:
    return EventBaseline(
        telegram_chat_id=int(row["chat_id"]),
        active_event_id=int(row["event_id"]),
        tracked_competition_id=int(row["competition_id"]),
        external_event_id=str(row["external_event_id"]),
        baseline_home=row["odds_home"] if row["odds_home"] is not None else None,
        baseline_draw=row["odds_draw"] if row["odds_draw"] is not None else None,
        baseline_away=row["odds_away"] if row["odds_away"] is not None else None,
        baseline_markets_json=row["markets_json"],
        baseline_set_at=str(row["set_at"]),
        updated_at=str(row["updated_at"]),
    )

def _row_to_small_change_record(row: sqlite3.Row) -> SmallChangeRecord:
    status_str = str(row["status"])
    created_at = str(row["created_at"]) if "created_at" in row.keys() else datetime.now(timezone.utc).isoformat()
    updated_at = str(row["updated_at"]) if "updated_at" in row.keys() else datetime.now(timezone.utc).isoformat()
    
    return SmallChangeRecord(
        id=int(row["id"]),
        telegram_chat_id=int(row["chat_id"]),
        active_event_id=int(row["event_id"]),
        tracked_competition_id=int(row["competition_id"]),
        external_event_id=str(row["external_event_id"]),
        competition_name=str(row["competition_name"]),
        home=str(row["home"]),
        away=str(row["away"]),
        scheduled_label_date=row["scheduled_label_date"],
        scheduled_label_time=row["scheduled_label_time"],
        scheduled_at=row["scheduled_at"],
        baseline_home=row["prev_home"] if row["prev_home"] is not None else None,
        baseline_draw=row["prev_draw"] if row["prev_draw"] is not None else None,
        baseline_away=row["prev_away"] if row["prev_away"] is not None else None,
        current_home=row["cur_home"] if row["cur_home"] is not None else None,
        current_draw=row["cur_draw"] if row["cur_draw"] is not None else None,
        current_away=row["cur_away"] if row["cur_away"] is not None else None,
        max_percent_change=float(row["max_change_percent"]),
        payload_json=row["payload_json"] if "payload_json" in row.keys() else None,
        status=status_str,
        created_at=created_at,
        updated_at=updated_at,
        confirmed_at=updated_at if status_str == "confirmed" else None,
        dismissed_at=updated_at if status_str in ("dismissed", "ignored") else None,
    )


class SQLiteBaselinesAdapter(BaselinesPort):
    """Adapter implementing BaselinesPort using SQLite."""

    def get_event_baseline(
        self,
        chat_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> EventBaseline | None:
        # Port signature: get_event_baseline(self, chat_id, active_event_id)
        # Legacy signature: get_event_baseline(self, chat_id, tracked_competition_id, external_event_id)
        with open_connection() as conn:
            if args:
                if len(args) >= 2 and isinstance(args[1], str): # legacy signature
                    tracked_competition_id = args[0]
                    external_event_id = args[1]
                    event_row = conn.execute(
                        "SELECT id FROM events WHERE competition_id = ? AND external_event_id = ?",
                        (tracked_competition_id, external_event_id)
                    ).fetchone()
                    if not event_row:
                        return None
                    active_event_id = event_row["id"]
                else:
                    active_event_id = args[0]
            else:
                if "active_event_id" in kwargs:
                    active_event_id = kwargs["active_event_id"]
                elif "external_event_id" in kwargs:
                    tracked_competition_id = kwargs["tracked_competition_id"]
                    external_event_id = kwargs["external_event_id"]
                    event_row = conn.execute(
                        "SELECT id FROM events WHERE competition_id = ? AND external_event_id = ?",
                        (tracked_competition_id, external_event_id)
                    ).fetchone()
                    if not event_row:
                        return None
                    active_event_id = event_row["id"]
                else:
                    return None
                
            row = conn.execute(
                """
                SELECT b.chat_id, b.event_id, e.competition_id, e.external_event_id,
                       b.odds_home, b.odds_draw, b.odds_away, b.markets_json,
                       b.set_at, b.updated_at
                FROM baselines b
                INNER JOIN events e ON b.event_id = e.id
                WHERE b.chat_id = ? AND b.event_id = ?
                """,
                (chat_id, active_event_id)
            ).fetchone()
            return _row_to_event_baseline(row) if row else None

    def initialize_event_baselines(
        self,
        chat_id: int,
        tracked_competition_id: int,
        active_events: list[Any],
    ) -> int:
        if not active_events:
            return 0

        now_iso = datetime.now(timezone.utc).isoformat()
        payload = []
        
        with open_connection() as conn:
            for event in active_events:
                # Support both dict and object
                def get_val(obj, key, default=None):
                    if isinstance(obj, dict):
                        return obj.get(key, default)
                    return getattr(obj, key, default)

                comp_id = get_val(event, "competition_id") or get_val(event, "tracked_competition_id")
                if comp_id != tracked_competition_id:
                    continue
                    
                evt_id = get_val(event, "id")
                odds_home = get_val(event, "odds_home")
                odds_draw = get_val(event, "odds_draw")
                odds_away = get_val(event, "odds_away")
                markets_json = get_val(event, "markets_json")
                
                payload.append((
                    chat_id,
                    evt_id,
                    odds_home,
                    odds_draw,
                    odds_away,
                    markets_json,
                    now_iso,
                    now_iso
                ))
                
            if not payload:
                return 0
                
            conn.executemany(
                """
                INSERT OR IGNORE INTO baselines (
                    chat_id, event_id, odds_home, odds_draw, odds_away, markets_json, set_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload
            )
            return len(payload)

    def upsert_event_baseline(
        self,
        chat_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> EventBaseline | None:
        # Port signature: upsert_event_baseline(self, chat_id, active_event_id, tracked_competition_id, external_event_id, home, draw, away, markets_json)
        # Legacy signature: upsert_event_baseline(self, chat_id, tracked_competition_id, external_event_id, *, baseline_home, baseline_draw, baseline_away, baseline_markets_json)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        def get_arg(pos_idx, kw_name, default=None):
            if len(args) > pos_idx:
                return args[pos_idx]
            return kwargs.get(kw_name, default)

        with open_connection() as conn:
            is_legacy = len(args) >= 2 and isinstance(args[1], str)
            
            if is_legacy:
                tracked_competition_id = get_arg(0, "tracked_competition_id")
                external_event_id = get_arg(1, "external_event_id")
                home = kwargs.get("baseline_home")
                draw = kwargs.get("baseline_draw")
                away = kwargs.get("baseline_away")
                markets_json = kwargs.get("baseline_markets_json")
                
                event_row = conn.execute(
                    "SELECT id FROM events WHERE competition_id = ? AND external_event_id = ?",
                    (tracked_competition_id, external_event_id)
                ).fetchone()
                if not event_row:
                    raise ValueError(f"No active event found for competition_id={tracked_competition_id} and external_event_id={external_event_id}")
                active_event_id = event_row["id"]
            else:
                active_event_id = get_arg(0, "active_event_id")
                # tracked_competition_id = get_arg(1, "tracked_competition_id")
                # external_event_id = get_arg(2, "external_event_id")
                home = get_arg(3, "home")
                draw = get_arg(4, "draw")
                away = get_arg(5, "away")
                markets_json = get_arg(6, "markets_json")

            conn.execute(
                """
                INSERT INTO baselines (
                    chat_id, event_id, odds_home, odds_draw, odds_away, markets_json, set_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, event_id) DO UPDATE SET
                    odds_home = excluded.odds_home,
                    odds_draw = excluded.odds_draw,
                    odds_away = excluded.odds_away,
                    markets_json = excluded.markets_json,
                    updated_at = excluded.updated_at
                """,
                (chat_id, active_event_id, home, draw, away, markets_json, now_iso, now_iso)
            )
            
            # For legacy caller, return the baseline record
            row = conn.execute(
                """
                SELECT b.chat_id, b.event_id, e.competition_id, e.external_event_id,
                       b.odds_home, b.odds_draw, b.odds_away, b.markets_json,
                       b.set_at, b.updated_at
                FROM baselines b
                INNER JOIN events e ON b.event_id = e.id
                WHERE b.chat_id = ? AND b.event_id = ?
                """,
                (chat_id, active_event_id)
            ).fetchone()
            return _row_to_event_baseline(row) if row else None

    def list_pending_small_changes(
        self,
        chat_id: int,
    ) -> list[SmallChangeRecord]:
        query = """
            SELECT sc.id, sc.chat_id, sc.event_id, e.competition_id, e.external_event_id,
                   c.name AS competition_name, e.home, e.away, e.scheduled_label_date,
                   e.scheduled_label_time, e.scheduled_at, sc.prev_home, sc.prev_draw,
                   sc.prev_away, sc.cur_home, sc.cur_draw, sc.cur_away, sc.max_change_percent,
                   sc.status, sc.created_at, sc.updated_at
            FROM small_changes sc
            INNER JOIN events e ON sc.event_id = e.id
            INNER JOIN competitions c ON e.competition_id = c.id
            INNER JOIN subscriptions cs ON cs.competition_id = e.competition_id AND cs.chat_id = sc.chat_id
            WHERE sc.chat_id = ? AND sc.status = 'pending' AND cs.enabled = 1 AND c.enabled = 1 AND e.is_active = 1
            ORDER BY sc.updated_at DESC, c.platform, c.name, e.home, e.away
        """
        with open_connection() as conn:
            rows = conn.execute(query, (chat_id,)).fetchall()
            return [_row_to_small_change_record(row) for row in rows]

    def upsert_small_change(
        self,
        chat_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> SmallChangeRecord | None:
        # Port signature: upsert_small_change(chat_id, active_event_id, tracked_competition_id, external_event_id, competition_name, home, away, scheduled_label_date, scheduled_label_time, scheduled_at, baseline_home, baseline_draw, baseline_away, current_home, current_draw, current_away, max_percent_change, payload_json, status)
        # Legacy signature: upsert_small_change(chat_id, tracked_competition_id, external_event_id, *, home, away, scheduled_label_date, scheduled_label_time, baseline_home, baseline_draw, baseline_away, current_home, current_draw, current_away, max_percent_change, status="pending")
        now_iso = datetime.now(timezone.utc).isoformat()
        
        def get_arg(pos_idx, kw_name, default=None):
            if len(args) > pos_idx:
                return args[pos_idx]
            return kwargs.get(kw_name, default)

        with open_connection() as conn:
            is_legacy = len(args) >= 2 and isinstance(args[1], str)
            
            if is_legacy:
                tracked_competition_id = get_arg(0, "tracked_competition_id")
                external_event_id = get_arg(1, "external_event_id")
                base_h = kwargs.get("baseline_home")
                base_d = kwargs.get("baseline_draw")
                base_a = kwargs.get("baseline_away")
                cur_h = kwargs.get("current_home")
                cur_d = kwargs.get("current_draw")
                cur_a = kwargs.get("current_away")
                max_change = kwargs.get("max_percent_change")
                status = kwargs.get("status", "pending")
                
                event_row = conn.execute(
                    "SELECT id FROM events WHERE competition_id = ? AND external_event_id = ?",
                    (tracked_competition_id, external_event_id)
                ).fetchone()
                if not event_row:
                    raise ValueError(f"No active event found for competition_id={tracked_competition_id} and external_event_id={external_event_id}")
                active_event_id = event_row["id"]
            else:
                active_event_id = get_arg(0, "active_event_id")
                # tracked_competition_id = get_arg(1, "tracked_competition_id")
                # external_event_id = get_arg(2, "external_event_id")
                # competition_name = get_arg(3, "competition_name")
                # home = get_arg(4, "home")
                # away = get_arg(5, "away")
                # scheduled_label_date = get_arg(6, "scheduled_label_date")
                # scheduled_label_time = get_arg(7, "scheduled_label_time")
                # scheduled_at = get_arg(8, "scheduled_at")
                base_h = get_arg(9, "baseline_home")
                base_d = get_arg(10, "baseline_draw")
                base_a = get_arg(11, "baseline_away")
                cur_h = get_arg(12, "current_home")
                cur_d = get_arg(13, "current_draw")
                cur_a = get_arg(14, "current_away")
                max_change = get_arg(15, "max_percent_change")
                status = get_arg(17, "status", "pending")

            conn.execute(
                """
                INSERT INTO small_changes (
                    chat_id, event_id, prev_home, prev_draw, prev_away, cur_home, cur_draw, cur_away,
                    max_change_percent, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, event_id) DO UPDATE SET
                    prev_home = excluded.prev_home,
                    prev_draw = excluded.prev_draw,
                    prev_away = excluded.prev_away,
                    cur_home = excluded.cur_home,
                    cur_draw = excluded.cur_draw,
                    cur_away = excluded.cur_away,
                    max_change_percent = excluded.max_change_percent,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (chat_id, active_event_id, base_h, base_d, base_a, cur_h, cur_d, cur_a, max_change, status, now_iso, now_iso)
            )
            
            # Reload for legacy return expectation
            row = conn.execute(
                """
                SELECT sc.id, sc.chat_id, sc.event_id, e.competition_id, e.external_event_id,
                       c.name AS competition_name, e.home, e.away, e.scheduled_label_date,
                       e.scheduled_label_time, e.scheduled_at, sc.prev_home, sc.prev_draw,
                       sc.prev_away, sc.cur_home, sc.cur_draw, sc.cur_away, sc.max_change_percent,
                       sc.status, sc.created_at, sc.updated_at
                FROM small_changes sc
                INNER JOIN events e ON sc.event_id = e.id
                INNER JOIN competitions c ON e.competition_id = c.id
                WHERE sc.chat_id = ? AND sc.event_id = ?
                """,
                (chat_id, active_event_id)
            ).fetchone()
            return _row_to_small_change_record(row) if row else None

    def confirm_small_change(
        self,
        chat_id: int,
        change_id: int,
    ) -> Any:
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            # Load small change details
            sc_row = conn.execute(
                "SELECT * FROM small_changes WHERE id = ? AND chat_id = ?",
                (change_id, chat_id)
            ).fetchone()
            if not sc_row:
                raise ValueError("No encontré ese little change para este chat.")
                
            event_id = sc_row["event_id"]
            
            # Load event markets_json
            evt_row = conn.execute("SELECT markets_json FROM events WHERE id = ?", (event_id,)).fetchone()
            markets_json = evt_row["markets_json"] if evt_row else None
            
            # Insert/replace baseline
            conn.execute(
                """
                INSERT INTO baselines (
                    chat_id, event_id, odds_home, odds_draw, odds_away, markets_json, set_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, event_id) DO UPDATE SET
                    odds_home = excluded.odds_home,
                    odds_draw = excluded.odds_draw,
                    odds_away = excluded.odds_away,
                    markets_json = excluded.markets_json,
                    updated_at = excluded.updated_at
                """,
                (chat_id, event_id, sc_row["cur_home"], sc_row["cur_draw"], sc_row["cur_away"], markets_json, now_iso, now_iso)
            )
            
            # Update status
            conn.execute(
                "UPDATE small_changes SET status = 'confirmed', updated_at = ? WHERE id = ?",
                (now_iso, change_id)
            )
            
            # Reload for legacy return
            row = conn.execute(
                """
                SELECT sc.id, sc.chat_id, sc.event_id, e.competition_id, e.external_event_id,
                       c.name AS competition_name, e.home, e.away, e.scheduled_label_date,
                       e.scheduled_label_time, e.scheduled_at, sc.prev_home, sc.prev_draw,
                       sc.prev_away, sc.cur_home, sc.cur_draw, sc.cur_away, sc.max_change_percent,
                       sc.status, sc.created_at, sc.updated_at
                FROM small_changes sc
                INNER JOIN events e ON sc.event_id = e.id
                INNER JOIN competitions c ON e.competition_id = c.id
                WHERE sc.id = ?
                """,
                (change_id,)
            ).fetchone()
            return _row_to_small_change_record(row) if row else None

    def confirm_all_small_changes(
        self,
        chat_id: int,
    ) -> Any:
        # Port signature: confirm_all_small_changes(self, chat_id) -> int (returns count)
        # Legacy signature: confirm_all_small_changes(self, chat_id) -> list[SmallChangeRecord]
        with open_connection() as conn:
            pending_rows = conn.execute(
                "SELECT id FROM small_changes WHERE chat_id = ? AND status = 'pending'",
                (chat_id,)
            ).fetchall()
            
            confirmed_records = []
            for r in pending_rows:
                rec = self.confirm_small_change(chat_id, r["id"])
                if rec:
                    confirmed_records.append(rec)
                    
            # Return list since legacy relies on list length and checks truthiness
            return confirmed_records

    def resolve_small_change_with_current_baseline(
        self,
        chat_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        # Port signature: resolve_small_change_with_current_baseline(self, chat_id, active_event_id)
        # Legacy signature: resolve_small_change_with_current_baseline(self, chat_id, tracked_competition_id, external_event_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        def get_arg(pos_idx, kw_name, default=None):
            if len(args) > pos_idx:
                return args[pos_idx]
            return kwargs.get(kw_name, default)

        with open_connection() as conn:
            is_legacy = len(args) >= 2 and isinstance(args[1], str)
            
            if is_legacy:
                tracked_competition_id = get_arg(0, "tracked_competition_id")
                external_event_id = get_arg(1, "external_event_id")
                event_row = conn.execute(
                    "SELECT id FROM events WHERE competition_id = ? AND external_event_id = ?",
                    (tracked_competition_id, external_event_id)
                ).fetchone()
                if not event_row:
                    return
                active_event_id = event_row["id"]
            else:
                active_event_id = get_arg(0, "active_event_id")
                
            conn.execute(
                "UPDATE small_changes SET status = 'confirmed', updated_at = ? WHERE chat_id = ? AND event_id = ? AND status = 'pending'",
                (now_iso, chat_id, active_event_id)
            )

    def has_sent_alert(
        self,
        chat_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        # Port signature: has_sent_alert(self, chat_id, active_event_id, alert_type)
        # Legacy signature: has_sent_alert(self, chat_id, tracked_competition_id, external_event_id, alert_type)
        
        def get_arg(pos_idx, kw_name, default=None):
            if len(args) > pos_idx:
                return args[pos_idx]
            return kwargs.get(kw_name, default)

        with open_connection() as conn:
            is_legacy = len(args) >= 3 and isinstance(args[1], str)
            
            if is_legacy:
                tracked_competition_id = get_arg(0, "tracked_competition_id")
                external_event_id = get_arg(1, "external_event_id")
                alert_type = get_arg(2, "alert_type")
                event_row = conn.execute(
                    "SELECT id FROM events WHERE competition_id = ? AND external_event_id = ?",
                    (tracked_competition_id, external_event_id)
                ).fetchone()
                if not event_row:
                    return False
                active_event_id = event_row["id"]
            else:
                active_event_id = get_arg(0, "active_event_id")
                alert_type = get_arg(1, "alert_type")
                
            row = conn.execute(
                "SELECT 1 FROM sent_alerts WHERE chat_id = ? AND event_id = ? AND alert_type = ?",
                (chat_id, active_event_id, alert_type.strip().lower())
            ).fetchone()
            return row is not None

    def mark_sent_alerts(
        self,
        chat_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        # Port signature: mark_sent_alerts(self, chat_id, active_event_ids: list[int], alert_type)
        # Legacy signature: mark_sent_alert(self, chat_id, tracked_competition_id, external_event_id, alert_type)
        # Legacy signature: mark_sent_alerts(self, chat_id, tracked_competition_id, external_event_ids, alert_type)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        def get_arg(pos_idx, kw_name, default=None):
            if len(args) > pos_idx:
                return args[pos_idx]
            return kwargs.get(kw_name, default)

        first_arg = get_arg(0, "tracked_competition_id") or get_arg(0, "active_event_ids")
        is_legacy = isinstance(first_arg, int) and (len(args) >= 3 or "external_event_id" in kwargs or "external_event_ids" in kwargs)

        with open_connection() as conn:
            if is_legacy:
                tracked_competition_id = first_arg
                ext_events = get_arg(1, "external_event_ids") or get_arg(1, "external_event_id")
                alert_type = get_arg(2, "alert_type")
                
                if isinstance(ext_events, str):
                    event_ids = [ext_events]
                else:
                    event_ids = list(ext_events)

                if not event_ids or not alert_type:
                    return

                placeholders = ",".join("?" for _ in event_ids)
                rows = conn.execute(
                    f"SELECT id FROM events WHERE competition_id = ? AND external_event_id IN ({placeholders})",
                    [tracked_competition_id] + event_ids
                ).fetchall()
                for row in rows:
                    conn.execute(
                        "INSERT OR IGNORE INTO sent_alerts (chat_id, event_id, alert_type, sent_at) VALUES (?, ?, ?, ?)",
                        (chat_id, row["id"], alert_type.strip().lower(), now_iso)
                    )
            else:
                active_events = first_arg
                alert_type = get_arg(1, "alert_type")
                
                if active_events is None:
                    return
                
                if isinstance(active_events, int):
                    event_ids = [active_events]
                elif isinstance(active_events, list):
                    event_ids = [getattr(e, "id", e) for e in active_events]
                else:
                    event_ids = [getattr(e, "id", e) for e in list(active_events)]
                
                for ev_id in event_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO sent_alerts (chat_id, event_id, alert_type, sent_at) VALUES (?, ?, ?, ?)",
                        (chat_id, int(ev_id), alert_type.strip().lower(), now_iso)
                    )

    # Alias for legacy singular name
    mark_sent_alert = mark_sent_alerts
