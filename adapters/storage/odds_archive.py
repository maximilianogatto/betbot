"""Archivo permanente de cuotas pre-match (Fase 0 de research/PROTOCOLO_INVESTIGACION.md).

Vive en una base SEPARADA de tracking.sqlite3 (default `data/odds_archive.sqlite3`,
override con BETBOT_ARCHIVE_DB_PATH) por dos razones:

- Retención infinita garantizada: ningún job de mantenimiento del bot (prune
  diario, VACUUM dominical) conoce esta DB, así que no puede borrarla ni pisarla.
- Es el dataset de research: se puede copiar/backupear el archivo entero sin
  arrastrar estado operativo del bot.

Presupuesto de disco (VPS GCP de 10GB con historial de disco lleno): el
markets_json promedio real mide ~1.2KB y comprime con zlib a ~300B (ratio 0.25
medido sobre los 154 snapshots legacy). Con dedup por hash (solo se inserta un
snapshot prematch cuando el mercado cambió respecto del último archivado) el
crecimiento esperado queda en unos pocos MB/día con los 9 libros activos
(< 1GB/año). `get_archive_stats()` expone filas y bytes para vigilarlo.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from adapters.storage.connection import DATA_DIR, PROJECT_ROOT

SNAPSHOT_TYPE_PREMATCH = "prematch"
SNAPSHOT_TYPE_CLOSING = "closing"


def resolve_archive_db_path() -> Path:
    """Ruta de la DB de archivo (BETBOT_ARCHIVE_DB_PATH o data/odds_archive.sqlite3)."""
    env_path = os.environ.get("BETBOT_ARCHIVE_DB_PATH", "").strip()
    if env_path:
        path = Path(env_path)
        return path if path.is_absolute() else (PROJECT_ROOT / path)
    return DATA_DIR / "odds_archive.sqlite3"


def initialize_archive_schema(connection: sqlite3.Connection) -> None:
    """Create the archive tables and indexes (idempotent)."""
    connection.executescript(
        """
        -- Snapshots de cuotas pre-match, append-only, retención infinita.
        CREATE TABLE IF NOT EXISTS odds_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            external_event_id TEXT NOT NULL,
            competition_external_id TEXT,
            competition_name TEXT,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            kickoff_utc TEXT,
            snapshot_type TEXT NOT NULL DEFAULT 'prematch',  -- prematch | closing
            odds_home REAL, odds_draw REAL, odds_away REAL,
            markets_zjson BLOB,        -- markets_json canónico comprimido (zlib)
            markets_hash TEXT,         -- sha1 de odds+markets, para dedup
            captured_at TEXT NOT NULL, -- cuándo se vieron estas cuotas en el libro
            archived_at TEXT NOT NULL  -- cuándo se escribió esta fila
        );
        CREATE INDEX IF NOT EXISTS idx_odds_snapshots_event
        ON odds_snapshots(platform, external_event_id, id);
        CREATE INDEX IF NOT EXISTS idx_odds_snapshots_kickoff
        ON odds_snapshots(kickoff_utc);
        -- Un solo snapshot "closing" por fixture.
        CREATE UNIQUE INDEX IF NOT EXISTS idx_odds_snapshots_one_closing
        ON odds_snapshots(platform, external_event_id)
        WHERE snapshot_type = 'closing';

        -- Resultado final por fixture (para etiquetar el dataset sin re-scrapear).
        CREATE TABLE IF NOT EXISTS match_results (
            platform TEXT NOT NULL,
            external_event_id TEXT NOT NULL,
            home TEXT NOT NULL,
            away TEXT NOT NULL,
            kickoff_utc TEXT,
            home_score INTEGER,
            away_score INTEGER,
            last_minute TEXT,
            is_final INTEGER NOT NULL DEFAULT 0,
            first_seen_live_at TEXT NOT NULL,
            last_seen_live_at TEXT NOT NULL,
            finalized_at TEXT,
            PRIMARY KEY (platform, external_event_id)
        );
        CREATE INDEX IF NOT EXISTS idx_match_results_open
        ON match_results(is_final, last_seen_live_at);
        """
    )


def compress_markets(markets_payload: dict[str, Any] | None) -> bytes | None:
    """Serialize the markets payload to canonical JSON and zlib-compress it."""
    if not markets_payload:
        return None
    canonical = json.dumps(markets_payload, sort_keys=True, separators=(",", ":"))
    return zlib.compress(canonical.encode("utf-8"), 6)


def decompress_markets(blob: bytes | None) -> dict[str, Any] | None:
    """Inverse of compress_markets."""
    if not blob:
        return None
    payload = json.loads(zlib.decompress(blob).decode("utf-8"))
    return payload if isinstance(payload, dict) else None


def _snapshot_hash(
    odds_home: float | None,
    odds_draw: float | None,
    odds_away: float | None,
    markets_payload: dict[str, Any] | None,
) -> str:
    """Hash estable de cuotas+mercados: si no cambió, no se archiva otra fila."""
    canonical = json.dumps(
        {"1x2": [odds_home, odds_draw, odds_away], "markets": markets_payload or {}},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class OddsArchiveSnapshot:
    """Un snapshot de cuotas de un fixture en un libro, listo para archivar."""

    platform: str
    external_event_id: str
    home: str
    away: str
    kickoff_utc: str | None
    odds_home: float | None
    odds_draw: float | None
    odds_away: float | None
    markets_payload: dict[str, Any] | None = None
    competition_external_id: str | None = None
    competition_name: str | None = None
    captured_at: str | None = None  # default: ahora (UTC)


class SQLiteOddsArchiveAdapter:
    """Adapter SQLite del archivo de cuotas. DB propia, separada del tracking."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else None

    @property
    def db_path(self) -> Path:
        return self._db_path if self._db_path is not None else resolve_archive_db_path()

    @contextmanager
    def _connection(self):
        path = self.db_path
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        initialize_archive_schema(conn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ----- snapshots -----

    def archive_prematch_snapshots(self, snapshots: list[OddsArchiveSnapshot]) -> int:
        """Archiva snapshots prematch, salteando los que no cambiaron.

        Dedup: se compara el hash de cuotas+mercados contra el último snapshot
        archivado del mismo fixture; si es idéntico no se inserta fila nueva
        (la serie temporal solo registra cambios, acotando el disco).
        """
        if not snapshots:
            return 0
        inserted = 0
        now_iso = _utc_now_iso()
        with self._connection() as conn:
            for snap in snapshots:
                current_hash = _snapshot_hash(
                    snap.odds_home, snap.odds_draw, snap.odds_away, snap.markets_payload
                )
                last = conn.execute(
                    """
                    SELECT markets_hash FROM odds_snapshots
                    WHERE platform = ? AND external_event_id = ? AND snapshot_type = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (snap.platform, snap.external_event_id, SNAPSHOT_TYPE_PREMATCH),
                ).fetchone()
                if last is not None and last["markets_hash"] == current_hash:
                    continue
                conn.execute(
                    """
                    INSERT INTO odds_snapshots (
                        platform, external_event_id, competition_external_id,
                        competition_name, home, away, kickoff_utc, snapshot_type,
                        odds_home, odds_draw, odds_away,
                        markets_zjson, markets_hash, captured_at, archived_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snap.platform, snap.external_event_id,
                        snap.competition_external_id, snap.competition_name,
                        snap.home, snap.away, snap.kickoff_utc, SNAPSHOT_TYPE_PREMATCH,
                        snap.odds_home, snap.odds_draw, snap.odds_away,
                        compress_markets(snap.markets_payload), current_hash,
                        snap.captured_at or now_iso, now_iso,
                    ),
                )
                inserted += 1
        return inserted

    def record_closing_snapshot(self, snapshot: OddsArchiveSnapshot) -> bool:
        """Archiva el snapshot de cierre de un fixture (a lo sumo uno por fixture)."""
        now_iso = _utc_now_iso()
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO odds_snapshots (
                    platform, external_event_id, competition_external_id,
                    competition_name, home, away, kickoff_utc, snapshot_type,
                    odds_home, odds_draw, odds_away,
                    markets_zjson, markets_hash, captured_at, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.platform, snapshot.external_event_id,
                    snapshot.competition_external_id, snapshot.competition_name,
                    snapshot.home, snapshot.away, snapshot.kickoff_utc,
                    SNAPSHOT_TYPE_CLOSING,
                    snapshot.odds_home, snapshot.odds_draw, snapshot.odds_away,
                    compress_markets(snapshot.markets_payload),
                    _snapshot_hash(
                        snapshot.odds_home, snapshot.odds_draw,
                        snapshot.odds_away, snapshot.markets_payload,
                    ),
                    snapshot.captured_at or now_iso, now_iso,
                ),
            )
            return cursor.rowcount > 0

    def has_closing_snapshot(self, platform: str, external_event_id: str) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM odds_snapshots
                WHERE platform = ? AND external_event_id = ? AND snapshot_type = ?
                LIMIT 1
                """,
                (platform, external_event_id, SNAPSHOT_TYPE_CLOSING),
            ).fetchone()
            return row is not None

    def get_snapshots(self, platform: str, external_event_id: str) -> list[dict[str, Any]]:
        """Snapshots archivados de un fixture (mercados ya descomprimidos)."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM odds_snapshots
                WHERE platform = ? AND external_event_id = ?
                ORDER BY id
                """,
                (platform, external_event_id),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["markets_payload"] = decompress_markets(item.pop("markets_zjson"))
            result.append(item)
        return result

    # ----- resultados -----

    def list_fixtures_awaiting_result(
        self, *, kickoff_from_iso: str, kickoff_to_iso: str
    ) -> list[dict[str, Any]]:
        """Fixtures archivados con kickoff en la ventana y sin resultado final."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT s.platform, s.external_event_id,
                       MAX(s.home) AS home, MAX(s.away) AS away,
                       MAX(s.kickoff_utc) AS kickoff_utc
                FROM odds_snapshots s
                LEFT JOIN match_results r
                  ON r.platform = s.platform
                 AND r.external_event_id = s.external_event_id
                WHERE s.kickoff_utc IS NOT NULL
                  AND s.kickoff_utc >= ?
                  AND s.kickoff_utc <= ?
                  AND (r.platform IS NULL OR r.is_final = 0)
                GROUP BY s.platform, s.external_event_id
                """,
                (kickoff_from_iso, kickoff_to_iso),
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_live_result(
        self,
        *,
        platform: str,
        external_event_id: str,
        home: str,
        away: str,
        kickoff_utc: str | None,
        home_score: int | None,
        away_score: int | None,
        last_minute: str | None,
        seen_at_iso: str | None = None,
    ) -> None:
        """Actualiza el último marcador visto en vivo de un fixture archivado."""
        seen_iso = seen_at_iso or _utc_now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO match_results (
                    platform, external_event_id, home, away, kickoff_utc,
                    home_score, away_score, last_minute, is_final,
                    first_seen_live_at, last_seen_live_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(platform, external_event_id) DO UPDATE SET
                    home_score = COALESCE(excluded.home_score, match_results.home_score),
                    away_score = COALESCE(excluded.away_score, match_results.away_score),
                    last_minute = COALESCE(excluded.last_minute, match_results.last_minute),
                    kickoff_utc = COALESCE(match_results.kickoff_utc, excluded.kickoff_utc),
                    last_seen_live_at = excluded.last_seen_live_at
                WHERE match_results.is_final = 0
                """,
                (
                    platform, external_event_id, home, away, kickoff_utc,
                    home_score, away_score, last_minute, seen_iso, seen_iso,
                ),
            )

    def finalize_stale_results(
        self,
        *,
        now: datetime | None = None,
        silence_minutes: int = 10,
        full_time_minutes: int = 100,
        no_kickoff_silence_minutes: int = 30,
    ) -> int:
        """Marca como finales los resultados que dejaron de verse en vivo.

        Regla: sin señal live hace >= silence_minutes Y (el último avistaje fue
        pasado el minuto ~90 del partido, o no hay kickoff conocido y el silencio
        supera no_kickoff_silence_minutes). El último marcador visto queda como
        resultado final.
        """
        reference = now or datetime.now(timezone.utc)
        finalized = 0
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM match_results WHERE is_final = 0"
            ).fetchall()
            for row in rows:
                last_seen = _parse_iso_utc(row["last_seen_live_at"])
                if last_seen is None:
                    continue
                if (reference - last_seen) < timedelta(minutes=silence_minutes):
                    continue
                kickoff = _parse_iso_utc(row["kickoff_utc"])
                if kickoff is not None:
                    if last_seen < kickoff + timedelta(minutes=full_time_minutes):
                        continue
                elif (reference - last_seen) < timedelta(minutes=no_kickoff_silence_minutes):
                    continue
                conn.execute(
                    """
                    UPDATE match_results SET is_final = 1, finalized_at = ?
                    WHERE platform = ? AND external_event_id = ?
                    """,
                    (reference.isoformat(), row["platform"], row["external_event_id"]),
                )
                finalized += 1
        return finalized

    def get_result(self, platform: str, external_event_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM match_results WHERE platform = ? AND external_event_id = ?",
                (platform, external_event_id),
            ).fetchone()
            return dict(row) if row is not None else None

    # ----- monitoreo -----

    def get_archive_stats(self) -> dict[str, Any]:
        """Filas por tipo + bytes en disco, para vigilar el crecimiento en el VPS."""
        with self._connection() as conn:
            snapshots = conn.execute(
                "SELECT snapshot_type, COUNT(*) AS n FROM odds_snapshots GROUP BY snapshot_type"
            ).fetchall()
            results = conn.execute(
                "SELECT COUNT(*) AS n, SUM(is_final) AS finals FROM match_results"
            ).fetchone()
        path = self.db_path
        size_bytes = path.stat().st_size if path.exists() else 0
        return {
            "snapshots": {row["snapshot_type"]: int(row["n"]) for row in snapshots},
            "results_total": int(results["n"] or 0),
            "results_final": int(results["finals"] or 0),
            "db_size_bytes": size_bytes,
        }
