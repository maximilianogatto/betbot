from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any

from core.models import TrackedCompetition, PendingCompetitionTrackRequest, TrackedCompetitionSubscription, CompetitionSubscription
from core.ports.competitions import CompetitionsPort
from adapters.storage.connection import open_connection

def _row_to_pending_request(row: sqlite3.Row) -> PendingCompetitionTrackRequest:
    meta = {}
    if row["payload_json"]:
        try:
            meta = json.loads(row["payload_json"])
        except Exception:
            pass
    needs_name_res = meta.get("needs_name_resolution", False)
    
    return PendingCompetitionTrackRequest(
        id=int(row["chat_id"]),
        telegram_chat_id=int(row["chat_id"]),
        platform=str(row["platform"]),
        source_url=str(row["source_url"]),
        competition_external_id=str(row["external_id"]),
        competition_name=str(row["name"]),
        requires_empty_confirmation=bool(row["requires_empty_confirmation"]),
        needs_name_resolution=needs_name_res,
        payload_json=row["payload_json"],
        created_at=str(row["created_at"]),
        expires_at=row["expires_at"] if row["expires_at"] else None,
    )

def _row_to_tracked_competition(row: sqlite3.Row) -> TrackedCompetition:
    meta = {}
    if row["metadata_json"]:
        try:
            meta = json.loads(row["metadata_json"])
        except Exception:
            pass
    needs_name_res = meta.get("needs_name_resolution", row["unified_competition_id"] is None)
    
    return TrackedCompetition(
        id=int(row["id"]),
        platform=str(row["platform"]),
        source_url=str(row["source_url"]),
        competition_external_id=str(row["external_id"]),
        competition_name=str(row["name"]),
        metadata_json=row["metadata_json"],
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

def _sanitize_tracking_state(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        DELETE FROM pending_track_requests
        WHERE TRIM(COALESCE(platform, '')) = ''
           OR TRIM(COALESCE(source_url, '')) = ''
           OR TRIM(COALESCE(external_id, '')) = ''
           OR TRIM(COALESCE(name, '')) = ''
           OR LOWER(TRIM(COALESCE(name, ''))) = 'none'
        """
    )
    connection.execute(
        """
        DELETE FROM competitions
        WHERE TRIM(COALESCE(platform, '')) = ''
           OR TRIM(COALESCE(source_url, '')) = ''
           OR TRIM(COALESCE(external_id, '')) = ''
           OR TRIM(COALESCE(name, '')) = ''
           OR LOWER(TRIM(COALESCE(name, ''))) = 'none'
        """
    )
    connection.execute(
        """
        DELETE FROM events
        WHERE competition_id IN (
            SELECT id
            FROM competitions
            WHERE enabled = 0
        )
        """
    )

def _propagate_unified_subscriptions(
    connection: sqlite3.Connection,
    unified_competition_id: int | None,
) -> int:
    if unified_competition_id is None:
        return 0
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor = connection.execute(
        """
        INSERT INTO subscriptions (
            chat_id, competition_id, notify_new_events,
            notify_odds_changes, change_threshold_percent, reminders_enabled, enabled, created_at, updated_at
        )
        SELECT s.chat_id, tc.id, s.notify_new_events,
               s.notify_odds_changes, s.change_threshold_percent, s.reminders_enabled, 1, ?, ?
        FROM (
            SELECT cs.chat_id,
                   MAX(cs.notify_new_events) AS notify_new_events,
                   MAX(cs.notify_odds_changes) AS notify_odds_changes,
                   MAX(cs.change_threshold_percent) AS change_threshold_percent,
                   MAX(cs.reminders_enabled) AS reminders_enabled
            FROM subscriptions cs
            INNER JOIN competitions x ON x.id = cs.competition_id
            WHERE x.unified_competition_id = ? AND cs.enabled = 1
            GROUP BY cs.chat_id
        ) s
        CROSS JOIN competitions tc
        WHERE tc.unified_competition_id = ? AND tc.enabled = 1
          AND NOT EXISTS (
            SELECT 1 FROM subscriptions e
            WHERE e.chat_id = s.chat_id
              AND e.competition_id = tc.id
          )
        """,
        (now_iso, now_iso, unified_competition_id, unified_competition_id),
    )
    return int(cursor.rowcount or 0)

def _insert_unified_competition(connection: sqlite3.Connection, name: str) -> int:
    from core.league_naming import extract_league_traits, league_slug
    clean = str(name).strip()
    base_name = clean
    suffix = 2
    while connection.execute(
        "SELECT 1 FROM unified_competitions WHERE name = ?", (clean,)
    ).fetchone() is not None:
        clean = f"{base_name} ({suffix})"
        suffix += 1
        
    base = league_slug(clean) or "league"
    slug = base
    suffix = 2
    while connection.execute(
        "SELECT 1 FROM unified_competitions WHERE public_id = ?", (slug,)
    ).fetchone() is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    
    traits = extract_league_traits(clean)
    now_iso = datetime.now(timezone.utc).isoformat()
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
    from core.league_naming import anagram_key, extract_league_traits, normalize_league_name
    name_clean = name.strip()
    target_norm = normalize_league_name(name_clean)
    target_anagram = anagram_key(name_clean)
    target_traits = extract_league_traits(name_clean)
    too_generic = len(target_norm.split()) < 2 and not target_traits["country"]
    
    rows = connection.execute("SELECT id, name FROM unified_competitions").fetchall()
    for r in rows:
        cand_traits = extract_league_traits(r["name"])
        if target_traits["country"] and cand_traits["country"] and target_traits["country"] != cand_traits["country"]:
            continue
        if r["name"].strip().lower() == name_clean.lower():
            return r["id"]
        if too_generic:
            continue
        if target_norm and normalize_league_name(r["name"]) == target_norm:
            return r["id"]
        if target_anagram and anagram_key(r["name"]) == target_anagram:
            return r["id"]
            
    return _insert_unified_competition(connection, name_clean)


class SQLiteCompetitionsAdapter(CompetitionsPort):
    """Adapter implementing CompetitionsPort using SQLite."""

    def create_pending_competition_request(
        self,
        chat_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> PendingCompetitionTrackRequest:
        def get_arg(pos_idx: int, kw_name: str, default: Any = None) -> Any:
            if len(args) > pos_idx:
                return args[pos_idx]
            return kwargs.get(kw_name, default)

        platform = get_arg(0, "platform")
        source_url = get_arg(1, "source_url")
        competition_external_id = get_arg(2, "competition_external_id")
        competition_name = get_arg(3, "competition_name")
        requires_empty_confirmation = get_arg(4, "requires_empty_confirmation", False)
        needs_name_resolution = get_arg(5, "needs_name_resolution", False)
        payload = get_arg(6, "payload_json") or kwargs.get("payload")

        platform = platform.strip().lower()
        source_url = source_url.strip()
        comp_ext_id = competition_external_id.strip()
        comp_name = competition_name.strip()
        now_iso = datetime.now(timezone.utc).isoformat()
        
        meta = {}
        if payload:
            if isinstance(payload, dict):
                meta = dict(payload)
            elif isinstance(payload, str):
                try:
                    meta = json.loads(payload)
                except Exception:
                    pass
        meta["needs_name_resolution"] = needs_name_resolution
        merged_payload_json = json.dumps(meta)
        
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        
        with open_connection() as conn:
            _sanitize_tracking_state(conn)
            conn.execute("DELETE FROM pending_track_requests WHERE chat_id = ?", (chat_id,))
            conn.execute(
                """
                INSERT INTO pending_track_requests (
                    chat_id, platform, source_url, external_id, name,
                    requires_empty_confirmation, payload_json, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id, platform, source_url, comp_ext_id, comp_name,
                    int(requires_empty_confirmation), merged_payload_json, now_iso, expires_at
                )
            )
            row = conn.execute("SELECT * FROM pending_track_requests WHERE chat_id = ?", (chat_id,)).fetchone()
            if not row:
                raise RuntimeError("Failed to reload pending track request after insertion.")
            return _row_to_pending_request(row)

    def get_latest_pending_competition_request(
        self,
        chat_id: int,
    ) -> PendingCompetitionTrackRequest | None:
        with open_connection() as conn:
            _sanitize_tracking_state(conn)
            row = conn.execute("SELECT * FROM pending_track_requests WHERE chat_id = ?", (chat_id,)).fetchone()
            if not row:
                return None
            return _row_to_pending_request(row)

    def confirm_pending_competition_request(
        self,
        chat_id: int,
    ) -> TrackedCompetition:
        with open_connection() as conn:
            _sanitize_tracking_state(conn)
            row = conn.execute("SELECT * FROM pending_track_requests WHERE chat_id = ?", (chat_id,)).fetchone()
            if not row:
                raise ValueError(f"No pending competition track request found for chat_id={chat_id}")
            
            pending = _row_to_pending_request(row)
            
            existing_row = conn.execute(
                "SELECT * FROM competitions WHERE platform = ? AND external_id = ?",
                (pending.platform, pending.competition_external_id)
            ).fetchone()
            
            now_iso = datetime.now(timezone.utc).isoformat()
            
            if existing_row is None:
                uc_id = _find_or_create_unified_competition_id(conn, pending.competition_name)
                
                meta = {}
                meta["needs_name_resolution"] = pending.needs_name_resolution
                meta_json = json.dumps(meta)
                
                cursor = conn.execute(
                    """
                    INSERT INTO competitions (
                        platform, external_id, name, source_url, metadata_json,
                        unified_competition_id, enabled, consecutive_unavailable_refreshes,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
                    """,
                    (
                        pending.platform, pending.competition_external_id, pending.competition_name,
                        pending.source_url, meta_json, uc_id, now_iso, now_iso
                    )
                )
                competition_id = int(cursor.lastrowid)
            else:
                existing = _row_to_tracked_competition(existing_row)
                competition_id = existing.id
                uc_id = existing.unified_competition_id
                if uc_id is None:
                    uc_id = _find_or_create_unified_competition_id(conn, pending.competition_name)
                
                meta = {}
                if existing.metadata_json:
                    try:
                        meta = json.loads(existing.metadata_json)
                    except Exception:
                        pass
                meta["needs_name_resolution"] = pending.needs_name_resolution
                meta_json = json.dumps(meta)
                
                conn.execute(
                    """
                    UPDATE competitions
                    SET source_url = ?,
                        name = ?,
                        metadata_json = ?,
                        unified_competition_id = ?,
                        enabled = 1,
                        consecutive_unavailable_refreshes = 0,
                        last_unavailable_at = NULL,
                        last_unavailable_reason = NULL,
                        last_unavailable_notified_at = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        pending.source_url, pending.competition_name, meta_json, uc_id,
                        now_iso, competition_id
                    )
                )
            
            conn.execute(
                """
                INSERT INTO subscriptions (
                    chat_id, competition_id, notify_new_events, notify_odds_changes,
                    change_threshold_percent, reminders_enabled, enabled, created_at, updated_at
                )
                VALUES (?, ?, 1, 1, 20.0, 0, 1, ?, ?)
                ON CONFLICT(chat_id, competition_id) DO UPDATE SET
                    enabled = 1,
                    updated_at = excluded.updated_at
                """,
                (chat_id, competition_id, now_iso, now_iso)
            )
            
            _propagate_unified_subscriptions(conn, uc_id)
            conn.execute("DELETE FROM pending_track_requests WHERE chat_id = ?", (chat_id,))
            
            updated_row = conn.execute("SELECT * FROM competitions WHERE id = ?", (competition_id,)).fetchone()
            return _row_to_tracked_competition(updated_row)

    def delete_pending_competition_request(
        self,
        chat_id: int,
    ) -> bool:
        with open_connection() as conn:
            _sanitize_tracking_state(conn)
            cursor = conn.execute("DELETE FROM pending_track_requests WHERE chat_id = ?", (chat_id,))
            return cursor.rowcount > 0

    def get_tracked_competition(
        self,
        competition_id: int,
    ) -> TrackedCompetition | None:
        with open_connection() as conn:
            _sanitize_tracking_state(conn)
            row = conn.execute("SELECT * FROM competitions WHERE id = ?", (competition_id,)).fetchone()
            if not row:
                return None
            return _row_to_tracked_competition(row)

    def get_tracked_competition_by_identity(
        self,
        platform: str,
        external_id: str,
    ) -> TrackedCompetition | None:
        platform = platform.strip().lower()
        external_id = external_id.strip()
        with open_connection() as conn:
            _sanitize_tracking_state(conn)
            row = conn.execute(
                "SELECT * FROM competitions WHERE platform = ? AND external_id = ?",
                (platform, external_id)
            ).fetchone()
            if not row:
                return None
            return _row_to_tracked_competition(row)

    def list_tracked_competitions(
        self,
        chat_id: int | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> list[Any]:
        cid = chat_id or kwargs.get("chat_id")
        with open_connection() as conn:
            _sanitize_tracking_state(conn)
            if cid is not None:
                rows = conn.execute(
                    """
                    SELECT s.*, c.platform, c.external_id, c.name, c.source_url, c.metadata_json, c.unified_competition_id, 
                           c.id AS comp_db_id, c.enabled AS comp_enabled, c.last_refreshed_at, c.consecutive_unavailable_refreshes, 
                           c.last_unavailable_at, c.last_unavailable_reason, c.last_unavailable_notified_at, 
                           c.created_at AS comp_created_at, c.updated_at AS comp_updated_at
                    FROM subscriptions s
                    INNER JOIN competitions c ON s.competition_id = c.id
                    WHERE s.chat_id = ? AND s.enabled = 1 AND c.enabled = 1
                    """,
                    (cid,)
                ).fetchall()
                out = []
                for row in rows:
                    comp = TrackedCompetition(
                        id=int(row["comp_db_id"]),
                        platform=str(row["platform"]),
                        source_url=str(row["source_url"]),
                        competition_external_id=str(row["external_id"]),
                        competition_name=str(row["name"]),
                        metadata_json=row["metadata_json"],
                        needs_name_resolution=bool(json.loads(row["metadata_json"] or "{}").get("needs_name_resolution", False)),
                        enabled=bool(row["comp_enabled"]),
                        last_synced_at=row["last_refreshed_at"],
                        consecutive_unavailable_refreshes=int(row["consecutive_unavailable_refreshes"]),
                        last_unavailable_refresh_at=row["last_unavailable_at"],
                        last_unavailable_reason=row["last_unavailable_reason"],
                        last_unavailable_notification_at=row["last_unavailable_notified_at"],
                        created_at=str(row["comp_created_at"]),
                        updated_at=str(row["comp_updated_at"]),
                        unified_competition_id=int(row["unified_competition_id"]) if row["unified_competition_id"] is not None else None,
                    )
                    sub = CompetitionSubscription(
                        telegram_chat_id=int(row["chat_id"]),
                        tracked_competition_id=int(row["competition_id"]),
                        notify_new_events=bool(row["notify_new_events"]),
                        notify_odds_changes=bool(row["notify_odds_changes"]),
                        change_percent_threshold=float(row["change_threshold_percent"]),
                        enabled=bool(row["enabled"]),
                        created_at=str(row["created_at"]),
                        updated_at=str(row["updated_at"]),
                    )
                    out.append(TrackedCompetitionSubscription(tracked_competition=comp, subscription=sub))
                return out
            else:
                rows = conn.execute("SELECT * FROM competitions").fetchall()
                return [_row_to_tracked_competition(row) for row in rows]

    def list_globally_active_competitions(self) -> list[TrackedCompetition]:
        with open_connection() as conn:
            _sanitize_tracking_state(conn)
            rows = conn.execute(
                """
                SELECT * FROM competitions tc
                WHERE tc.enabled = 1
                  AND EXISTS (
                      SELECT 1
                      FROM subscriptions s
                      WHERE s.competition_id = tc.id
                        AND s.enabled = 1
                  )
                """
            ).fetchall()
            return [_row_to_tracked_competition(row) for row in rows]

    def update_tracked_competition(
        self,
        competition_id: int,
        enabled: bool | None = None,
        last_synced_at: str | None = None,
        metadata_json: str | None = None,
        needs_name_resolution: bool | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> TrackedCompetition:
        now_iso = datetime.now(timezone.utc).isoformat()
        source_url = kwargs.get("source_url")
        with open_connection() as conn:
            row = conn.execute("SELECT metadata_json, unified_competition_id FROM competitions WHERE id = ?", (competition_id,)).fetchone()
            if not row:
                raise ValueError(f"Competition with id {competition_id} does not exist.")
            
            meta = {}
            if row["metadata_json"]:
                try:
                    meta = json.loads(row["metadata_json"])
                except Exception:
                    pass
            
            if needs_name_resolution is not None:
                meta["needs_name_resolution"] = needs_name_resolution
                
            new_metadata_json = json.dumps(meta) if meta else None
            if metadata_json is not None:
                new_metadata_json = metadata_json

            updates = ["updated_at = ?"]
            params = [now_iso]
            if enabled is not None:
                updates.append("enabled = ?")
                params.append(int(enabled))
            if last_synced_at is not None:
                updates.append("last_refreshed_at = ?")
                params.append(last_synced_at)
            if new_metadata_json is not None or needs_name_resolution is not None:
                updates.append("metadata_json = ?")
                params.append(new_metadata_json)
            if source_url is not None:
                updates.append("source_url = ?")
                params.append(source_url)
                
            params.append(competition_id)
            conn.execute(
                f"UPDATE competitions SET {', '.join(updates)} WHERE id = ?",
                tuple(params)
            )
            
            updated_row = conn.execute("SELECT * FROM competitions WHERE id = ?", (competition_id,)).fetchone()
            return _row_to_tracked_competition(updated_row)

    def update_tracked_competition_source(
        self,
        competition_id: int,
        source_url: str,
    ) -> None:
        source_url = source_url.strip()
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            conn.execute(
                "UPDATE competitions SET source_url = ?, updated_at = ? WHERE id = ?",
                (source_url, now_iso, competition_id)
            )

    def sanitize_tracking_state(self) -> None:
        with open_connection() as conn:
            _sanitize_tracking_state(conn)

    def auto_track_live_detected_league(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        def get_arg(pos_idx: int, kw_name: str, default: Any = None) -> Any:
            if len(args) > pos_idx:
                return args[pos_idx]
            return kwargs.get(kw_name, default)

        first_val = get_arg(0, "chat_id")
        is_legacy = isinstance(first_val, int)

        if is_legacy:
            chat_id = first_val
            platform = get_arg(1, "platform")
            external_id = get_arg(2, "competition_external_id")
            name = get_arg(3, "competition_name")
            source_url = get_arg(4, "source_url")
        else:
            chat_id = None
            platform = get_arg(0, "platform")
            external_id = get_arg(1, "external_id")
            name = get_arg(2, "name")
            source_url = get_arg(3, "source_url")

        platform = platform.strip().lower()
        external_id = external_id.strip()
        name = name.strip()
        source_url = (source_url or "").strip()
        now_iso = datetime.now(timezone.utc).isoformat()
        
        with open_connection() as conn:
            _sanitize_tracking_state(conn)
            row = conn.execute(
                "SELECT * FROM competitions WHERE platform = ? AND external_id = ?",
                (platform, external_id)
            ).fetchone()
            
            if row is None:
                uc_id = _find_or_create_unified_competition_id(conn, name)
                cursor = conn.execute(
                    """
                    INSERT INTO competitions (
                        platform, external_id, name, source_url, metadata_json,
                        unified_competition_id, enabled, consecutive_unavailable_refreshes,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, NULL, ?, 1, 0, ?, ?)
                    """,
                    (platform, external_id, name, source_url, uc_id, now_iso, now_iso)
                )
                comp_id = int(cursor.lastrowid)
            else:
                existing = _row_to_tracked_competition(row)
                comp_id = existing.id
                uc_id = existing.unified_competition_id
                if uc_id is None:
                    uc_id = _find_or_create_unified_competition_id(conn, existing.competition_name)
                    
                conn.execute(
                    """
                    UPDATE competitions
                    SET enabled = 1,
                        unified_competition_id = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (uc_id, now_iso, comp_id)
                )
                
            if chat_id is not None:
                conn.execute(
                    """
                    INSERT INTO subscriptions (
                        chat_id, competition_id, notify_new_events, notify_odds_changes,
                        change_threshold_percent, reminders_enabled, enabled, created_at, updated_at
                    )
                    VALUES (?, ?, 1, 1, 20.0, 0, 1, ?, ?)
                    ON CONFLICT(chat_id, competition_id) DO UPDATE SET
                        enabled = 1,
                        updated_at = excluded.updated_at
                    """,
                    (chat_id, comp_id, now_iso, now_iso)
                )
                
            if is_legacy:
                return comp_id
                
            updated_row = conn.execute("SELECT * FROM competitions WHERE id = ?", (comp_id,)).fetchone()
            return _row_to_tracked_competition(updated_row)

    def record_unavailable_refresh(
        self,
        competition_id: int,
        reason: str,
    ) -> TrackedCompetition:
        reason = reason.strip()
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            conn.execute(
                """
                UPDATE competitions
                SET consecutive_unavailable_refreshes = consecutive_unavailable_refreshes + 1,
                    last_unavailable_at = ?,
                    last_unavailable_reason = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now_iso, reason, now_iso, competition_id)
            )
            row = conn.execute("SELECT * FROM competitions WHERE id = ?", (competition_id,)).fetchone()
            if not row:
                raise ValueError(f"Competition with id {competition_id} does not exist.")
            return _row_to_tracked_competition(row)

    def should_send_unavailable_refresh_warning(
        self,
        competition_id: int,
        minimum_failures: int = 3,
        cooldown_seconds: int = 86400,
    ) -> bool:
        comp = self.get_tracked_competition(competition_id)
        if comp is None:
            return False
            
        if comp.consecutive_unavailable_refreshes < minimum_failures:
            return False
            
        last_notified = comp.last_unavailable_notification_at
        if last_notified is None:
            return True
            
        try:
            notified_dt = datetime.fromisoformat(last_notified)
        except ValueError:
            return True
            
        if notified_dt.tzinfo is None:
            notified_dt = notified_dt.replace(tzinfo=timezone.utc)
            
        elapsed = (datetime.now(timezone.utc) - notified_dt).total_seconds()
        return elapsed >= cooldown_seconds

    def mark_unavailable_refresh_warning_sent(
        self,
        competition_id: int,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            conn.execute(
                """
                UPDATE competitions
                SET last_unavailable_notified_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now_iso, now_iso, competition_id)
            )

    def create_unified_competition(
        self,
        name: str,
        country_name: str | None = None,
    ) -> int:
        """Crea SIEMPRE una unified NUEVA (paridad legacy: sin fuzzy find).

        El find-or-create durante el tracking vive en `auto_track_live_detected_league`
        / `confirm_pending_competition_request`. Este método explícito debe crear una
        liga nueva: p.ej. `/unlink_league` lo usa para separar una plataforma en su
        propia liga, y si hiciera find-or-create la re-pegaría a la misma unified.
        """
        name_clean = name.strip()
        with open_connection() as conn:
            return _insert_unified_competition(conn, name_clean)

    def link_tracked_competition_to_unified(
        self,
        tracked_id: int,
        unified_id: int,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            row = conn.execute("SELECT id FROM competitions WHERE id = ?", (tracked_id,)).fetchone()
            if not row:
                raise ValueError(f"Tracked competition ID {tracked_id} does not exist.")
            row = conn.execute("SELECT id FROM unified_competitions WHERE id = ?", (unified_id,)).fetchone()
            if not row:
                raise ValueError(f"Unified competition ID {unified_id} does not exist.")
                
            conn.execute(
                "UPDATE competitions SET unified_competition_id = ?, updated_at = ? WHERE id = ?",
                (unified_id, now_iso, tracked_id)
            )
            _propagate_unified_subscriptions(conn, unified_id)

    def merge_unified_competitions(
        self,
        source_unified_id: int,
        target_unified_id: int,
    ) -> None:
        if source_unified_id == target_unified_id:
            raise ValueError("Cannot merge a unified competition into itself.")
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            for uid in (source_unified_id, target_unified_id):
                if conn.execute("SELECT 1 FROM unified_competitions WHERE id = ?", (uid,)).fetchone() is None:
                    raise ValueError(f"Unified competition ID {uid} does not exist.")
            
            conn.execute(
                "UPDATE competitions SET unified_competition_id = ?, updated_at = ? WHERE unified_competition_id = ?",
                (target_unified_id, now_iso, source_unified_id)
            )
            _propagate_unified_subscriptions(conn, target_unified_id)
            conn.execute("DELETE FROM unified_competitions WHERE id = ?", (source_unified_id,))

    # --- Blocklist de auto-merge (unified_merge_exceptions) ---
    @staticmethod
    def _canonical_merge_pair(
        platform_a: str, external_id_a: str, platform_b: str, external_id_b: str
    ) -> tuple[str, str, str, str]:
        """Par en orden canónico (a<=b), independiente del orden de los argumentos."""
        a = (str(platform_a), str(external_id_a))
        b = (str(platform_b), str(external_id_b))
        return (*a, *b) if a <= b else (*b, *a)

    def get_merge_exceptions(self) -> set[tuple[str, str, str, str]]:
        """Pares (plataforma, external_id) bloqueados, como 4-tuplas canónicas."""
        with open_connection() as conn:
            rows = conn.execute(
                "SELECT platform_a, external_id_a, platform_b, external_id_b "
                "FROM unified_merge_exceptions"
            ).fetchall()
        return {
            (r["platform_a"], r["external_id_a"], r["platform_b"], r["external_id_b"])
            for r in rows
        }

    def block_unlinked_competition(self, tracked_id: int, unified_id: int) -> int:
        """Al separar una competencia de una liga, bloquea su re-merge contra CADA
        miembro que quedaba (un par por miembro). Devuelve cuántos pares insertó."""
        with open_connection() as conn:
            target = conn.execute(
                "SELECT platform, external_id FROM competitions WHERE id = ?", (tracked_id,)
            ).fetchone()
            if target is None:
                return 0
            members = conn.execute(
                "SELECT platform, external_id FROM competitions "
                "WHERE unified_competition_id = ? AND id != ?",
                (unified_id, tracked_id),
            ).fetchall()
            now_iso = datetime.now(timezone.utc).isoformat()
            inserted = 0
            for m in members:
                pa, xa, pb, xb = self._canonical_merge_pair(
                    target["platform"], target["external_id"], m["platform"], m["external_id"]
                )
                if (pa, xa) == (pb, xb):
                    continue
                cur = conn.execute(
                    "INSERT OR IGNORE INTO unified_merge_exceptions "
                    "(platform_a, external_id_a, platform_b, external_id_b, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (pa, xa, pb, xb, now_iso),
                )
                inserted += cur.rowcount
        return inserted

    def clear_merge_exceptions_between(self, unified_a_id: int, unified_b_id: int) -> int:
        """Borra los bloqueos entre miembros de dos ligas (override manual /link_league).
        Devuelve cuántas filas borró (para avisar al usuario)."""
        with open_connection() as conn:
            comps_a = conn.execute(
                "SELECT platform, external_id FROM competitions WHERE unified_competition_id = ?",
                (unified_a_id,),
            ).fetchall()
            comps_b = conn.execute(
                "SELECT platform, external_id FROM competitions WHERE unified_competition_id = ?",
                (unified_b_id,),
            ).fetchall()
            deleted = 0
            for ca in comps_a:
                for cb in comps_b:
                    pa, xa, pb, xb = self._canonical_merge_pair(
                        ca["platform"], ca["external_id"], cb["platform"], cb["external_id"]
                    )
                    cur = conn.execute(
                        "DELETE FROM unified_merge_exceptions "
                        "WHERE platform_a=? AND external_id_a=? AND platform_b=? AND external_id_b=?",
                        (pa, xa, pb, xb),
                    )
                    deleted += cur.rowcount
        return deleted

    def relink_unified_by_normalized_name(self) -> int:
        from core.league_naming import normalize_league_name
        moved = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        with open_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, unified_competition_id FROM competitions WHERE enabled = 1"
            ).fetchall()
            
            groups = {}
            for r in rows:
                norm = normalize_league_name(r["name"])
                if not norm:
                    continue
                groups.setdefault(norm, []).append(
                    (r["id"], r["unified_competition_id"], r["name"])
                )
                
            for norm, members in groups.items():
                if len(members) <= 1:
                    continue
                unified_ids = {u for _, u, _ in members if u is not None}
                if unified_ids:
                    target = min(unified_ids)
                else:
                    target = _insert_unified_competition(conn, members[0][2])
                    
                changed = False
                for comp_id, current, _name in members:
                    if current != target:
                        conn.execute(
                            "UPDATE competitions SET unified_competition_id = ?, updated_at = ? WHERE id = ?",
                            (target, now_iso, comp_id)
                        )
                        moved += 1
                        changed = True
                if changed:
                    _propagate_unified_subscriptions(conn, target)
                    
                for uid in unified_ids:
                    if uid == target:
                        continue
                    remaining = conn.execute(
                        "SELECT 1 FROM competitions WHERE unified_competition_id = ? LIMIT 1",
                        (uid,)
                    ).fetchone()
                    if remaining is None:
                        conn.execute("DELETE FROM unified_competitions WHERE id = ?", (uid,))
        return moved

    def suggest_similar_unified(
        self,
        name: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        from core.league_naming import extract_league_traits, normalize_league_name, league_name_similarity
        
        name_clean = name.strip()
        target_norm = normalize_league_name(name_clean)
        if len(target_norm.split()) < 2:
            return []
            
        target = extract_league_traits(name_clean)
        suggestions = []
        with open_connection() as conn:
            rows = conn.execute("SELECT id, name, public_id FROM unified_competitions").fetchall()
            
        for r in rows:
            cand = extract_league_traits(r["name"])
            if target["gender"] != cand["gender"] or target["age_group"] != cand["age_group"]:
                continue
            if target["country"] and cand["country"] and target["country"] != cand["country"]:
                continue
            if normalize_league_name(r["name"]) == target_norm:
                continue
                
            score = league_name_similarity(name_clean, r["name"])
            if score >= 0.8:
                suggestions.append(
                    {"id": r["id"], "name": r["name"], "public_id": r["public_id"], "score": score}
                )
                
        suggestions.sort(key=lambda s: s["score"], reverse=True)
        return suggestions[:limit]

    def list_subscribed_unified_competitions(
        self,
        chat_id: int,
    ) -> list[dict[str, Any]]:
        with open_connection() as conn:
            _sanitize_tracking_state(conn)
            rows = conn.execute(
                """
                SELECT DISTINCT uc.id, uc.name
                FROM unified_competitions uc
                INNER JOIN competitions tc ON tc.unified_competition_id = uc.id
                INNER JOIN subscriptions cs ON cs.competition_id = tc.id
                WHERE cs.chat_id = ?
                  AND cs.enabled = 1
                  AND tc.enabled = 1
                ORDER BY uc.name
                """,
                (chat_id,),
            ).fetchall()
        return [{"id": r["id"], "name": r["name"]} for r in rows]

    def list_tracked_competitions_for_unified(
        self,
        unified_id: int,
    ) -> list[TrackedCompetition]:
        with open_connection() as conn:
            _sanitize_tracking_state(conn)
            rows = conn.execute(
                """
                SELECT * FROM competitions
                WHERE unified_competition_id = ?
                  AND enabled = 1
                """,
                (unified_id,),
            ).fetchall()
            return [_row_to_tracked_competition(row) for row in rows]
