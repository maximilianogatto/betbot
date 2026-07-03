from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any

from core.models import LiveWatchEntry, LiveWatchSettings
from core.ports.live_watch import LiveWatchPort
from adapters.storage.connection import open_connection

def _row_to_live_watch(row: sqlite3.Row) -> LiveWatchEntry:
    return LiveWatchEntry(
        id=int(row["id"]),
        chat_id=int(row["chat_id"]),
        home=str(row["home"]),
        away=str(row["away"]),
        league_hint=row["league_hint"],
        note=row["note"],
        status=str(row["status"]),
        matched_platform=row["matched_platform"],
        matched_event_id=row["matched_event_id"],
        matched_minute=row["matched_minute"],
        created_at=str(row["created_at"]),
        fired_at=row["fired_at"],
        kickoff_at=row["kickoff_at"],
        prematch_seen_at=row["prematch_seen_at"],
        prematch_platform=row["prematch_platform"],
        fired_platforms=row["fired_platforms"],
        prematch_fired_platforms=row["prematch_fired_platforms"],
        countdown_fired_at=row["countdown_fired_at"],
        chat_local_id=row["chat_local_id"],
        live_state_json=row["live_state_json"],
        status_flags=int(row["status_flags"]) if row["status_flags"] is not None else 1,
        fired_odds_mask=int(row["fired_odds_mask"]) if row["fired_odds_mask"] is not None else 0,
        fired_stats_mask=int(row["fired_stats_mask"]) if row["fired_stats_mask"] is not None else 0,
    )

def _platform_to_odds_flag(platform: str) -> int:
    plat = platform.strip().lower()
    if plat == "bet365":
        return 1
    if plat == "bplay":
        return 2
    if plat == "codere":
        return 4
    if plat == "jugadon":
        return 8
    if plat == "betsson":
        return 16
    if plat == "betano":
        return 32
    if plat == "novibet":
        return 64
    if plat == "betovo":
        return 128
    return 0


class SQLiteLiveWatchAdapter(LiveWatchPort):
    """Adapter implementing LiveWatchPort using SQLite."""

    def add_live_watch(
        self,
        chat_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> LiveWatchEntry:
        # Port: add_live_watch(chat_id, home, away, league_hint=None, note=None, kickoff_at=None, chat_local_id=None)
        # Legacy: add_live_watch(chat_id, *, home, away, league_hint=None, note=None, kickoff_at=None)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        def get_arg(pos_idx, kw_name, default=None):
            if len(args) > pos_idx:
                return args[pos_idx]
            return kwargs.get(kw_name, default)

        is_legacy = "home" in kwargs
        
        if is_legacy:
            home = kwargs["home"]
            away = kwargs["away"]
            league_hint = kwargs.get("league_hint")
            note = kwargs.get("note")
            kickoff_at = kwargs.get("kickoff_at")
            chat_local_id = None
        else:
            home = get_arg(0, "home")
            away = get_arg(1, "away")
            league_hint = get_arg(2, "league_hint")
            note = get_arg(3, "note")
            kickoff_at = get_arg(4, "kickoff_at")
            chat_local_id = get_arg(5, "chat_local_id")

        with open_connection() as conn:
            if chat_local_id is None:
                row_max = conn.execute(
                    "SELECT COALESCE(MAX(chat_local_id), 0) as max_id FROM live_watch_entries WHERE chat_id = ?",
                    (chat_id,)
                ).fetchone()
                chat_local_id = (row_max["max_id"] or 0) + 1

            cursor = conn.execute(
                """
                INSERT INTO live_watch_entries (
                    chat_id, chat_local_id, home, away, league_hint, note, status, created_at, kickoff_at, status_flags
                )
                VALUES (?, ?, ?, ?, ?, ?, 'watching', ?, ?, 1)
                """,
                (
                    chat_id,
                    chat_local_id,
                    home.strip(),
                    away.strip(),
                    league_hint,
                    note,
                    now_iso,
                    kickoff_at
                )
            )
            
            row = conn.execute(
                "SELECT * FROM live_watch_entries WHERE id = ?",
                (cursor.lastrowid,)
            ).fetchone()
            return _row_to_live_watch(row)

    def get_live_watch(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> LiveWatchEntry | None:
        # Port: get_live_watch(entry_id)
        # Legacy: get_live_watch(chat_id, watch_id)
        with open_connection() as conn:
            if len(args) >= 2:
                # Legacy signature
                chat_id = args[0]
                entry_id = args[1]
                row = conn.execute(
                    "SELECT * FROM live_watch_entries WHERE id = ? AND chat_id = ?",
                    (entry_id, chat_id)
                ).fetchone()
            else:
                entry_id = args[0] if args else kwargs["entry_id"]
                row = conn.execute(
                    "SELECT * FROM live_watch_entries WHERE id = ?",
                    (entry_id,)
                ).fetchone()
            return _row_to_live_watch(row) if row else None

    def get_live_watch_by_local_id(
        self,
        chat_id: int,
        chat_local_id: int,
    ) -> LiveWatchEntry | None:
        with open_connection() as conn:
            row = conn.execute(
                "SELECT * FROM live_watch_entries WHERE chat_id = ? AND chat_local_id = ?",
                (chat_id, chat_local_id)
            ).fetchone()
            return _row_to_live_watch(row) if row else None

    def list_live_watches(
        self,
        chat_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> list[LiveWatchEntry]:
        # Port: list_live_watches(chat_id, status=None)
        # Legacy: list_live_watches(chat_id, *, status=None)
        status = args[0] if args else kwargs.get("status")
        with open_connection() as conn:
            if status == "watching":
                rows = conn.execute(
                    "SELECT * FROM live_watch_entries WHERE chat_id = ? AND status = 'watching' ORDER BY id",
                    (chat_id,)
                ).fetchall()
            elif status == "fired":
                rows = conn.execute(
                    "SELECT * FROM live_watch_entries WHERE chat_id = ? AND fired_platforms IS NOT NULL AND fired_platforms != '' ORDER BY id",
                    (chat_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM live_watch_entries WHERE chat_id = ? ORDER BY id",
                    (chat_id,)
                ).fetchall()
            return [_row_to_live_watch(row) for row in rows]

    def list_all_active_live_watches(self) -> list[LiveWatchEntry]:
        with open_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM live_watch_entries WHERE status = 'watching' ORDER BY chat_id, id"
            ).fetchall()
            return [_row_to_live_watch(row) for row in rows]

    def remove_live_watch(
        self,
        chat_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        # Port: remove_live_watch(chat_id, entry_id)
        # Legacy: (some callers might pass chat_id and watch_id, same signature)
        entry_id = args[0] if args else kwargs["entry_id"]
        with open_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM live_watch_entries WHERE chat_id = ? AND id = ?",
                (chat_id, entry_id)
            )
            return cursor.rowcount > 0

    def remove_live_watch_by_local_id(
        self,
        chat_id: int,
        chat_local_id: int,
    ) -> bool:
        with open_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM live_watch_entries WHERE chat_id = ? AND chat_local_id = ?",
                (chat_id, chat_local_id)
            )
            return cursor.rowcount > 0

    def clear_live_watches(
        self,
        chat_id: int,
        status: str | None = None,
    ) -> int:
        with open_connection() as conn:
            if status:
                cursor = conn.execute(
                    "DELETE FROM live_watch_entries WHERE chat_id = ? AND status = ?",
                    (chat_id, status.strip().lower())
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM live_watch_entries WHERE chat_id = ?",
                    (chat_id,)
                )
            return cursor.rowcount

    def purge_expired_live_watches(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> int:
        kickoff_grace = kwargs.get("kickoff_grace_hours", 2.0)
        stale = kwargs.get("stale_hours", 16.0)
        fired_retain = kwargs.get("fired_retain_hours", 3.0)
        
        now = datetime.now(timezone.utc)
        kickoff_cutoff = (now - timedelta(hours=kickoff_grace)).isoformat()
        stale_cutoff = (now - timedelta(hours=stale)).isoformat()
        fired_cutoff = (now - timedelta(hours=fired_retain)).isoformat()
        
        with open_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM live_watch_entries
                WHERE (status = 'watching' AND kickoff_at IS NOT NULL AND kickoff_at < ?)
                   OR (status = 'watching' AND kickoff_at IS NULL AND created_at < ?)
                   OR (status = 'fired' AND fired_at IS NOT NULL AND fired_at < ?)
                """,
                (kickoff_cutoff, stale_cutoff, fired_cutoff)
            )
            return cursor.rowcount

    def get_live_watch_settings(
        self,
        chat_id: int,
    ) -> LiveWatchSettings:
        with open_connection() as conn:
            row = conn.execute(
                "SELECT * FROM live_watch_settings WHERE chat_id = ?",
                (chat_id,)
            ).fetchone()
            if not row:
                return LiveWatchSettings(chat_id=chat_id)
            return LiveWatchSettings(
                chat_id=int(row["chat_id"]),
                alert_goals=bool(row["alert_goals"]),
                alert_red_cards=bool(row["alert_red_cards"]),
                alert_yellow_cards=bool(row["alert_yellow_cards"])
            )

    def set_live_watch_settings(
        self,
        chat_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> LiveWatchSettings:
        # Port: set_live_watch_settings(chat_id, alert_goals=None, alert_red_cards=None, alert_yellow_cards=None)
        # Legacy: set_live_watch_settings(chat_id, *, alert_goals=None, alert_red_cards=None, alert_yellow_cards=None)
        def get_arg(pos_idx, kw_name, default=None):
            if len(args) > pos_idx:
                return args[pos_idx]
            return kwargs.get(kw_name, default)

        alert_goals = get_arg(0, "alert_goals")
        alert_red_cards = get_arg(1, "alert_red_cards")
        alert_yellow_cards = get_arg(2, "alert_yellow_cards")

        current = self.get_live_watch_settings(chat_id)
        new_goals = current.alert_goals if alert_goals is None else bool(alert_goals)
        new_reds = current.alert_red_cards if alert_red_cards is None else bool(alert_red_cards)
        new_yellows = current.alert_yellow_cards if alert_yellow_cards is None else bool(alert_yellow_cards)
        now_iso = datetime.now(timezone.utc).isoformat()

        with open_connection() as conn:
            conn.execute(
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
                (chat_id, int(new_goals), int(new_reds), int(new_yellows), now_iso)
            )
            
        return LiveWatchSettings(
            chat_id=chat_id,
            alert_goals=new_goals,
            alert_red_cards=new_reds,
            alert_yellow_cards=new_yellows
        )

    def mark_live_watch_fired(
        self,
        entry_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        # Port: mark_live_watch_fired(entry_id, platforms, live_state=None)
        # Legacy: mark_live_watch_fired(watch_id, *, platform, event_id, minute)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        is_legacy = "platform" in kwargs
        
        with open_connection() as conn:
            row = conn.execute(
                "SELECT fired_platforms, fired_odds_mask, live_state_json FROM live_watch_entries WHERE id = ?",
                (entry_id,)
            ).fetchone()
            current_fired = row["fired_platforms"] if row else None
            current_mask = row["fired_odds_mask"] if row and row["fired_odds_mask"] is not None else 0
            current_state = json.loads(row["live_state_json"]) if row and row["live_state_json"] else {}

            if is_legacy:
                platform = kwargs["platform"]
                event_id = kwargs["event_id"]
                minute = kwargs.get("minute")
                
                flag = _platform_to_odds_flag(platform)
                new_mask = current_mask | flag
                
                if current_fired:
                    plats = [p.strip() for p in current_fired.split(",") if p.strip()]
                    if platform not in plats:
                        plats.append(platform)
                    new_val = ",".join(plats)
                else:
                    new_val = platform
                
                conn.execute(
                    """
                    UPDATE live_watch_entries
                    SET fired_platforms = ?, fired_odds_mask = ?, matched_platform = ?, matched_event_id = ?,
                        matched_minute = ?, fired_at = ?
                    WHERE id = ?
                    """,
                    (new_val, new_mask, platform, event_id, minute, now_iso, entry_id)
                )
            else:
                platforms = args[0] if args else kwargs["platforms"]
                live_state = args[1] if len(args) > 1 else kwargs.get("live_state")
                
                new_mask = current_mask
                plats = [p.strip() for p in current_fired.split(",") if p.strip()] if current_fired else []
                for platform in platforms:
                    if platform not in plats:
                        plats.append(platform)
                    new_mask |= _platform_to_odds_flag(platform)
                new_val = ",".join(plats)

                if live_state:
                    current_state.update(live_state)

                conn.execute(
                    """
                    UPDATE live_watch_entries
                    SET fired_platforms = ?, fired_odds_mask = ?, live_state_json = ?, fired_at = ?
                    WHERE id = ?
                    """,
                    (new_val, new_mask, json.dumps(current_state), now_iso, entry_id)
                )

    def mark_live_watch_prematch_seen(
        self,
        watch_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        # Legacy only method: mark_live_watch_prematch_seen(watch_id, *, platform, event_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        platform = kwargs["platform"]
        event_id = kwargs["event_id"]
        with open_connection() as conn:
            conn.execute(
                """
                UPDATE live_watch_entries
                SET prematch_seen_at = ?, prematch_platform = ?, matched_event_id = COALESCE(matched_event_id, ?)
                WHERE id = ?
                """,
                (now_iso, platform, event_id, watch_id)
            )

    def mark_live_watch_prematch_fired(
        self,
        entry_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        # Port: mark_live_watch_prematch_fired(entry_id, platforms)
        # Legacy: mark_live_watch_prematch_fired(watch_id, *, platform, event_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        is_legacy = "platform" in kwargs
        
        with open_connection() as conn:
            row = conn.execute(
                "SELECT prematch_fired_platforms, fired_odds_mask FROM live_watch_entries WHERE id = ?",
                (entry_id,)
            ).fetchone()
            current_fired = row["prematch_fired_platforms"] if row else None
            current_mask = row["fired_odds_mask"] if row and row["fired_odds_mask"] is not None else 0

            if is_legacy:
                platform = kwargs["platform"]
                event_id = kwargs["event_id"]
                
                flag = _platform_to_odds_flag(platform)
                new_mask = current_mask | flag
                
                if current_fired:
                    plats = [p.strip() for p in current_fired.split(",") if p.strip()]
                    if platform not in plats:
                        plats.append(platform)
                    new_val = ",".join(plats)
                else:
                    new_val = platform
                
                conn.execute(
                    """
                    UPDATE live_watch_entries
                    SET prematch_fired_platforms = ?, fired_odds_mask = ?,
                        prematch_seen_at = ?, prematch_platform = ?, matched_event_id = COALESCE(matched_event_id, ?)
                    WHERE id = ?
                    """,
                    (new_val, new_mask, now_iso, platform, event_id, entry_id)
                )
            else:
                platforms = args[0] if args else kwargs["platforms"]
                
                new_mask = current_mask
                plats = [p.strip() for p in current_fired.split(",") if p.strip()] if current_fired else []
                for platform in platforms:
                    if platform not in plats:
                        plats.append(platform)
                    new_mask |= _platform_to_odds_flag(platform)
                new_val = ",".join(plats)
                
                conn.execute(
                    """
                    UPDATE live_watch_entries
                    SET prematch_fired_platforms = ?, fired_odds_mask = ?, prematch_seen_at = ?
                    WHERE id = ?
                    """,
                    (new_val, new_mask, now_iso, entry_id)
                )

    def mark_live_watch_countdown_fired(
        self,
        entry_id: int,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            conn.execute(
                "UPDATE live_watch_entries SET countdown_fired_at = ? WHERE id = ?",
                (now_iso, entry_id)
            )

    def update_live_watch_platform_state(
        self,
        entry_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        # Port: update_live_watch_platform_state(entry_id, platform, live_state)
        # Legacy: update_live_watch_platform_state(watch_id, *, platform, state) -> dict[str, Any]
        is_legacy = "state" in kwargs
        
        if is_legacy:
            platform = kwargs["platform"]
            state = kwargs["state"]
        else:
            platform = args[0] if args else kwargs["platform"]
            state = args[1] if len(args) > 1 else kwargs["live_state"]

        with open_connection() as conn:
            row = conn.execute(
                "SELECT live_state_json FROM live_watch_entries WHERE id = ?",
                (entry_id,)
            ).fetchone()
            current = json.loads(row["live_state_json"]) if row and row["live_state_json"] else {}
            current[str(platform)] = dict(state)
            
            conn.execute(
                "UPDATE live_watch_entries SET live_state_json = ? WHERE id = ?",
                (json.dumps(current, ensure_ascii=False, sort_keys=True), entry_id)
            )
            return current
