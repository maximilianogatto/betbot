from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from core.models import StatsLeagueLink, StatsMatchLinkRecord
from core.ports.stats_links import StatsLinksPort
from adapters.storage.connection import open_connection

def _row_to_stats_league_link(row: sqlite3.Row) -> StatsLeagueLink:
    return StatsLeagueLink(
        id=int(row["id"]),
        tracked_competition_id=int(row["competition_id"]),
        stats_provider=str(row["provider"]),
        stats_league_id=str(row["league_id"]),
        stats_league_name=str(row["league_name"]),
        stats_country_name=row["country_name"],
        confidence=float(row["confidence"]),
        payload_json=row["payload_json"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )

def _row_to_stats_match_link(row: sqlite3.Row) -> StatsMatchLinkRecord:
    return StatsMatchLinkRecord(
        id=int(row["id"]),
        active_event_id=int(row["event_id"]),
        stats_provider=str(row["provider"]),
        stats_match_id=str(row["match_id"]),
        stats_url=row["url"],
        confidence=float(row["confidence"]),
        method=str(row["method"]),
        payload_json=row["payload_json"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class SQLiteStatsLinksAdapter(StatsLinksPort):
    """Adapter implementing StatsLinksPort using SQLite."""

    def list_stats_league_links(
        self,
        tracked_competition_id: int,
    ) -> list[StatsLeagueLink]:
        """Links de stats de la liga, con HERENCIA entre plataformas.

        Si la competencia pertenece a una liga unificada, devuelve los links de
        TODAS sus plataformas (uno por provider: se prefiere el link propio de la
        competencia consultada y, si no, el de mayor confianza). Así linkear stats
        en una plataforma se hereda al resto de la liga (feature del registro
        canónico). Sin unified, cae a los links propios de la competencia.
        """
        with open_connection() as conn:
            row = conn.execute(
                "SELECT unified_competition_id FROM competitions WHERE id = ?",
                (tracked_competition_id,),
            ).fetchone()
            unified_id = row["unified_competition_id"] if row else None
            if unified_id is not None:
                rows = conn.execute(
                    "SELECT s.* FROM stats_league_links s "
                    "JOIN competitions c ON c.id = s.competition_id "
                    "WHERE c.unified_competition_id = ? "
                    "ORDER BY (s.competition_id = ?) DESC, s.confidence DESC, s.id",
                    (unified_id, tracked_competition_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM stats_league_links WHERE competition_id = ? "
                    "ORDER BY confidence DESC, id",
                    (tracked_competition_id,),
                ).fetchall()
        seen: set[str] = set()
        out: list[StatsLeagueLink] = []
        for row in rows:
            if row["provider"] in seen:
                continue
            seen.add(row["provider"])
            out.append(_row_to_stats_league_link(row))
        return out

    def get_stats_league_link(
        self,
        tracked_competition_id: int,
        stats_provider: str | None = None,
    ) -> StatsLeagueLink | None:
        with open_connection() as conn:
            if stats_provider:
                row = conn.execute(
                    "SELECT * FROM stats_league_links WHERE competition_id = ? AND provider = ?",
                    (tracked_competition_id, stats_provider.strip().lower())
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM stats_league_links WHERE competition_id = ? LIMIT 1",
                    (tracked_competition_id,)
                ).fetchone()
            return _row_to_stats_league_link(row) if row else None

    def upsert_stats_league_link(
        self,
        tracked_competition_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> StatsLeagueLink | None:
        # Port: upsert_stats_league_link(tracked_competition_id, stats_provider, stats_league_id, stats_league_name, stats_country_name=None, confidence=1.0, payload_json=None)
        # Legacy: upsert_stats_league_link(tracked_competition_id, *, stats_provider, stats_league_id, stats_league_name, stats_country_name=None, confidence=1.0, payload=None)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        def get_arg(pos_idx, kw_name, default=None):
            if len(args) > pos_idx:
                return args[pos_idx]
            return kwargs.get(kw_name, default)

        is_legacy = "stats_provider" in kwargs
        
        if is_legacy:
            stats_provider = kwargs["stats_provider"]
            stats_league_id = kwargs["stats_league_id"]
            stats_league_name = kwargs["stats_league_name"]
            stats_country_name = kwargs.get("stats_country_name")
            confidence = kwargs.get("confidence", 1.0)
            payload = kwargs.get("payload")
            payload_json = json.dumps(payload) if payload is not None else None
        else:
            stats_provider = get_arg(0, "stats_provider")
            stats_league_id = get_arg(1, "stats_league_id")
            stats_league_name = get_arg(2, "stats_league_name")
            stats_country_name = get_arg(3, "stats_country_name")
            confidence = get_arg(4, "confidence", 1.0)
            payload_json = get_arg(5, "payload_json")

        with open_connection() as conn:
            conn.execute(
                """
                INSERT INTO stats_league_links (
                    competition_id, provider, league_id, league_name, country_name, confidence, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(competition_id, provider) DO UPDATE SET
                    league_id = excluded.league_id,
                    league_name = excluded.league_name,
                    country_name = excluded.country_name,
                    confidence = excluded.confidence,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    tracked_competition_id,
                    stats_provider.strip().lower(),
                    stats_league_id.strip(),
                    stats_league_name.strip(),
                    stats_country_name,
                    confidence,
                    payload_json,
                    now_iso,
                    now_iso
                )
            )
            
            # Reload for legacy return
            row = conn.execute(
                "SELECT * FROM stats_league_links WHERE competition_id = ? AND provider = ?",
                (tracked_competition_id, stats_provider.strip().lower())
            ).fetchone()
            return _row_to_stats_league_link(row) if row else None

    def delete_stats_league_link(
        self,
        tracked_competition_id: int,
        stats_provider: str | None = None,
    ) -> bool:
        with open_connection() as conn:
            if stats_provider:
                cursor = conn.execute(
                    "DELETE FROM stats_league_links WHERE competition_id = ? AND provider = ?",
                    (tracked_competition_id, stats_provider.strip().lower())
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM stats_league_links WHERE competition_id = ?",
                    (tracked_competition_id,)
                )
            return cursor.rowcount > 0

    def get_stats_match_link(
        self,
        active_event_id: int,
        stats_provider: str,
    ) -> StatsMatchLinkRecord | None:
        with open_connection() as conn:
            row = conn.execute(
                "SELECT * FROM stats_match_links WHERE event_id = ? AND provider = ?",
                (active_event_id, stats_provider.strip().lower())
            ).fetchone()
            return _row_to_stats_match_link(row) if row else None

    def list_stats_match_links(
        self,
        active_event_id: int,
    ) -> list[StatsMatchLinkRecord]:
        with open_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM stats_match_links WHERE event_id = ?",
                (active_event_id,)
            ).fetchall()
            return [_row_to_stats_match_link(row) for row in rows]

    def upsert_stats_match_link(
        self,
        active_event_id: int,
        *args: Any,
        **kwargs: Any,
    ) -> StatsMatchLinkRecord | None:
        # Port: upsert_stats_match_link(active_event_id, stats_provider, stats_match_id, stats_url=None, confidence=1.0, method="manual", payload_json=None)
        # Legacy: upsert_stats_match_link(active_event_id, *, stats_provider, stats_match_id, stats_url, confidence, method, payload=None)
        now_iso = datetime.now(timezone.utc).isoformat()
        
        def get_arg(pos_idx, kw_name, default=None):
            if len(args) > pos_idx:
                return args[pos_idx]
            return kwargs.get(kw_name, default)

        is_legacy = "stats_provider" in kwargs
        
        if is_legacy:
            stats_provider = kwargs["stats_provider"]
            stats_match_id = kwargs["stats_match_id"]
            stats_url = kwargs.get("stats_url")
            confidence = kwargs.get("confidence", 0.0)
            method = kwargs.get("method", "manual")
            payload = kwargs.get("payload")
            payload_json = json.dumps(payload) if payload is not None else None
        else:
            stats_provider = get_arg(0, "stats_provider")
            stats_match_id = get_arg(1, "stats_match_id")
            stats_url = get_arg(2, "stats_url")
            confidence = get_arg(3, "confidence", 1.0)
            method = get_arg(4, "method", "manual")
            payload_json = get_arg(5, "payload_json")

        with open_connection() as conn:
            conn.execute(
                """
                INSERT INTO stats_match_links (
                    event_id, provider, match_id, url, confidence, method, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, provider) DO UPDATE SET
                    match_id = excluded.match_id,
                    url = excluded.url,
                    confidence = excluded.confidence,
                    method = excluded.method,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    active_event_id,
                    stats_provider.strip().lower(),
                    stats_match_id.strip(),
                    stats_url,
                    confidence,
                    method.strip(),
                    payload_json,
                    now_iso,
                    now_iso
                )
            )
            
            # Reload for legacy return
            row = conn.execute(
                "SELECT * FROM stats_match_links WHERE event_id = ? AND provider = ?",
                (active_event_id, stats_provider.strip().lower())
            ).fetchone()
            return _row_to_stats_match_link(row) if row else None
