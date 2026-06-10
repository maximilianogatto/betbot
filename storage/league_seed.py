"""Portable league seed: export/import the *generic* league knowledge.

The SQLite database (``data/tracking.sqlite3``) is gitignored and does not travel
to a cloud deploy. This module lets the curated, user-agnostic part of it travel
*with the code* instead, as a committed JSON file (``seeds/leagues.json``):

  - ``unified_competitions`` — the cross-platform league grouping (by name).
  - ``tracked_competitions`` — which league on each platform (platform + external
    id + name + source url + metadata + which unified group + reminders flag).
  - ``stats_league_links`` — the league<->stats-provider links.

It deliberately excludes everything user/runtime specific: subscriptions,
active events, baselines, alerts, live-watch entries, peak digests, caches.

Natural keys are used throughout (``unified.name``,
``tracked(platform, competition_external_id)``) so the seed survives a fresh DB
where autoincrement ids differ.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from storage.tracking_repository import (
    DB_FILE_PATH,
    PROJECT_ROOT,
    _connect,
    _utc_now_iso,
)

logger = logging.getLogger(__name__)

SEED_VERSION = 1
SEED_FILE_PATH = PROJECT_ROOT / "seeds" / "leagues.json"


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def export_league_seed() -> dict[str, Any]:
    """Read the generic league data out of the live DB into a plain dict."""

    with _connect() as connection:
        unified = [
            row["name"]
            for row in connection.execute(
                "SELECT name FROM unified_competitions ORDER BY name"
            ).fetchall()
        ]

        tracked_rows = connection.execute(
            """
            SELECT tc.platform, tc.competition_external_id, tc.competition_name,
                   tc.source_url, tc.metadata_json, tc.needs_name_resolution,
                   tc.enabled, tc.reminders_enabled, uc.name AS unified_name
            FROM tracked_competitions tc
            LEFT JOIN unified_competitions uc ON uc.id = tc.unified_competition_id
            ORDER BY tc.platform, tc.competition_external_id
            """
        ).fetchall()
        tracked = [
            {
                "platform": r["platform"],
                "competition_external_id": r["competition_external_id"],
                "competition_name": r["competition_name"],
                "source_url": r["source_url"],
                "metadata_json": r["metadata_json"],
                "needs_name_resolution": int(r["needs_name_resolution"] or 0),
                "enabled": int(r["enabled"] or 0),
                "reminders_enabled": int(r["reminders_enabled"] or 0),
                "unified_name": r["unified_name"],
            }
            for r in tracked_rows
        ]

        stats_rows = connection.execute(
            """
            SELECT tc.platform, tc.competition_external_id,
                   sll.stats_provider, sll.stats_league_id, sll.stats_league_name,
                   sll.stats_country_name, sll.confidence, sll.payload_json
            FROM stats_league_links sll
            INNER JOIN tracked_competitions tc ON tc.id = sll.tracked_competition_id
            ORDER BY tc.platform, tc.competition_external_id, sll.stats_provider
            """
        ).fetchall()
        stats_links = [
            {
                "platform": r["platform"],
                "competition_external_id": r["competition_external_id"],
                "stats_provider": r["stats_provider"],
                "stats_league_id": r["stats_league_id"],
                "stats_league_name": r["stats_league_name"],
                "stats_country_name": r["stats_country_name"],
                "confidence": r["confidence"],
                "payload_json": r["payload_json"],
            }
            for r in stats_rows
        ]

    return {
        "version": SEED_VERSION,
        "exported_at": _utc_now_iso(),
        "unified_competitions": unified,
        "tracked_competitions": tracked,
        "stats_league_links": stats_links,
    }


def write_seed_file(path: Path | None = None) -> Path:
    """Export the generic league data and write it to the seed JSON file."""

    target = Path(path) if path else SEED_FILE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    data = export_league_seed()
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #
def load_seed_file(path: Path | None = None) -> dict[str, Any] | None:
    """Read the seed JSON file, or return None if it does not exist."""

    target = Path(path) if path else SEED_FILE_PATH
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def import_league_seed(data: dict[str, Any], *, overwrite: bool = False) -> dict[str, int]:
    """Upsert the generic league data into the DB using natural keys.

    ``overwrite=False`` (default) preserves rows that already exist (only fills in
    a missing unified link); ``overwrite=True`` refreshes their generic fields too.
    Subscriptions / active events / any user data are never touched.
    """

    counts = {
        "unified_created": 0,
        "tracked_inserted": 0,
        "tracked_updated": 0,
        "tracked_skipped": 0,
        "stats_inserted": 0,
        "stats_updated": 0,
        "stats_skipped": 0,
    }
    now_iso = _utc_now_iso()

    with _connect() as connection:
        # 1. Unified competitions (by unique name) -> name -> id map.
        unified_ids: dict[str, int] = {}
        for name in data.get("unified_competitions") or []:
            clean = str(name).strip()
            if not clean:
                continue
            row = connection.execute(
                "SELECT id FROM unified_competitions WHERE name = ?", (clean,)
            ).fetchone()
            if row is not None:
                unified_ids[clean] = row["id"]
                continue
            cursor = connection.execute(
                "INSERT INTO unified_competitions (name, created_at, updated_at) VALUES (?, ?, ?)",
                (clean, now_iso, now_iso),
            )
            unified_ids[clean] = cursor.lastrowid
            counts["unified_created"] += 1

        def _unified_id(name: str | None) -> int | None:
            if not name:
                return None
            clean = str(name).strip()
            if clean in unified_ids:
                return unified_ids[clean]
            row = connection.execute(
                "SELECT id FROM unified_competitions WHERE name = ?", (clean,)
            ).fetchone()
            if row is not None:
                unified_ids[clean] = row["id"]
                return row["id"]
            cursor = connection.execute(
                "INSERT INTO unified_competitions (name, created_at, updated_at) VALUES (?, ?, ?)",
                (clean, now_iso, now_iso),
            )
            unified_ids[clean] = cursor.lastrowid
            counts["unified_created"] += 1
            return cursor.lastrowid

        # 2. Tracked competitions (by platform + external id).
        tracked_ids: dict[tuple[str, str], int] = {}
        for tc in data.get("tracked_competitions") or []:
            platform = str(tc.get("platform") or "").strip()
            ext_id = str(tc.get("competition_external_id") or "").strip()
            if not platform or not ext_id:
                continue
            uid = _unified_id(tc.get("unified_name"))
            existing = connection.execute(
                "SELECT id, unified_competition_id FROM tracked_competitions "
                "WHERE platform = ? AND competition_external_id = ?",
                (platform, ext_id),
            ).fetchone()

            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO tracked_competitions (
                        platform, competition_external_id, competition_name, source_url,
                        metadata_json, needs_name_resolution, enabled, reminders_enabled,
                        unified_competition_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        platform, ext_id,
                        str(tc.get("competition_name") or ext_id),
                        str(tc.get("source_url") or ""),
                        tc.get("metadata_json"),
                        int(tc.get("needs_name_resolution") or 0),
                        int(tc.get("enabled", 1) or 0),
                        int(tc.get("reminders_enabled") or 0),
                        uid, now_iso, now_iso,
                    ),
                )
                tracked_ids[(platform, ext_id)] = cursor.lastrowid
                counts["tracked_inserted"] += 1
            else:
                tracked_ids[(platform, ext_id)] = existing["id"]
                if overwrite:
                    connection.execute(
                        """
                        UPDATE tracked_competitions
                        SET competition_name = ?, source_url = ?, metadata_json = ?,
                            needs_name_resolution = ?, enabled = ?, reminders_enabled = ?,
                            unified_competition_id = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            str(tc.get("competition_name") or ext_id),
                            str(tc.get("source_url") or ""),
                            tc.get("metadata_json"),
                            int(tc.get("needs_name_resolution") or 0),
                            int(tc.get("enabled", 1) or 0),
                            int(tc.get("reminders_enabled") or 0),
                            uid, now_iso, existing["id"],
                        ),
                    )
                    counts["tracked_updated"] += 1
                else:
                    # Only fill a missing unified link; never clobber existing data.
                    if existing["unified_competition_id"] is None and uid is not None:
                        connection.execute(
                            "UPDATE tracked_competitions SET unified_competition_id = ?, updated_at = ? WHERE id = ?",
                            (uid, now_iso, existing["id"]),
                        )
                    counts["tracked_skipped"] += 1

        # 3. Stats-league links (by tracked id + provider).
        for link in data.get("stats_league_links") or []:
            platform = str(link.get("platform") or "").strip()
            ext_id = str(link.get("competition_external_id") or "").strip()
            provider = str(link.get("stats_provider") or "").strip()
            key = (platform, ext_id)
            tracked_id = tracked_ids.get(key)
            if tracked_id is None:
                row = connection.execute(
                    "SELECT id FROM tracked_competitions WHERE platform = ? AND competition_external_id = ?",
                    (platform, ext_id),
                ).fetchone()
                tracked_id = row["id"] if row else None
            if tracked_id is None or not provider:
                counts["stats_skipped"] += 1
                continue

            existing = connection.execute(
                "SELECT id FROM stats_league_links WHERE tracked_competition_id = ? AND stats_provider = ?",
                (tracked_id, provider),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO stats_league_links (
                        tracked_competition_id, stats_provider, stats_league_id,
                        stats_league_name, stats_country_name, confidence, payload_json,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tracked_id, provider,
                        str(link.get("stats_league_id") or ""),
                        str(link.get("stats_league_name") or ""),
                        link.get("stats_country_name"),
                        float(link.get("confidence") or 1.0),
                        link.get("payload_json"),
                        now_iso, now_iso,
                    ),
                )
                counts["stats_inserted"] += 1
            elif overwrite:
                connection.execute(
                    """
                    UPDATE stats_league_links
                    SET stats_league_id = ?, stats_league_name = ?, stats_country_name = ?,
                        confidence = ?, payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        str(link.get("stats_league_id") or ""),
                        str(link.get("stats_league_name") or ""),
                        link.get("stats_country_name"),
                        float(link.get("confidence") or 1.0),
                        link.get("payload_json"),
                        now_iso, existing["id"],
                    ),
                )
                counts["stats_updated"] += 1
            else:
                counts["stats_skipped"] += 1

    return counts


def _tracked_competitions_count() -> int:
    with _connect() as connection:
        row = connection.execute("SELECT COUNT(*) AS c FROM tracked_competitions").fetchone()
        return int(row["c"]) if row else 0


def seed_if_empty(path: Path | None = None) -> dict[str, int] | None:
    """Bootstrap a fresh DB from the committed seed file.

    Imports the seed only when there are no tracked competitions yet (i.e. a fresh
    cloud deploy), so an existing DB is never altered. Returns the import counts,
    or None when nothing was done.
    """

    try:
        if _tracked_competitions_count() > 0:
            return None
        data = load_seed_file(path)
        if not data:
            logger.info("League seed: no seed file at %s; starting with an empty DB.", path or SEED_FILE_PATH)
            return None
        counts = import_league_seed(data, overwrite=False)
        logger.info(
            "League seed: bootstrapped fresh DB at %s -> %s unified, %s tracked, %s stats links.",
            DB_FILE_PATH, counts["unified_created"], counts["tracked_inserted"], counts["stats_inserted"],
        )
        return counts
    except Exception:  # defensive: never block startup on a seed problem
        logger.exception("League seed: failed to bootstrap from seed file.")
        return None
