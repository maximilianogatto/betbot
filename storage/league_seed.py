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
    _insert_unified_competition,
    _utc_now_iso,
)

logger = logging.getLogger(__name__)

SEED_VERSION = 2
SEED_FILE_PATH = PROJECT_ROOT / "seeds" / "leagues.json"


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def _platform_dict(row) -> dict[str, Any]:
    return {
        "platform": row["platform"],
        "competition_external_id": row["competition_external_id"],
        "competition_name": row["competition_name"],
        "source_url": row["source_url"],
        "metadata_json": row["metadata_json"],
        "needs_name_resolution": int(row["needs_name_resolution"] or 0),
        "enabled": int(row["enabled"] or 0),
        "reminders_enabled": int(row["reminders_enabled"] or 0),
    }


def export_league_seed() -> dict[str, Any]:
    """Read the registry (leagues + platform links + stats links) into a dict.

    Format v2 is registry-centric: one entry per unified league (keyed by its
    ``public_id``) holding its platform links and league-level stats links.
    Platforms without a unified league go under ``unlinked_platforms``.
    """

    with _connect() as connection:
        leagues: list[dict[str, Any]] = []
        for uc in connection.execute(
            """
            SELECT id, name, public_id, display_name, country, gender, age_group
            FROM unified_competitions ORDER BY name
            """
        ).fetchall():
            platforms = [
                _platform_dict(r)
                for r in connection.execute(
                    """
                    SELECT platform, competition_external_id, competition_name,
                           source_url, metadata_json, needs_name_resolution,
                           enabled, reminders_enabled
                    FROM tracked_competitions
                    WHERE unified_competition_id = ?
                    ORDER BY platform, competition_external_id
                    """,
                    (uc["id"],),
                ).fetchall()
            ]
            stats_links = [
                {
                    "stats_provider": r["stats_provider"],
                    "stats_league_id": r["stats_league_id"],
                    "stats_league_name": r["stats_league_name"],
                    "stats_country_name": r["stats_country_name"],
                    "confidence": r["confidence"],
                    "payload_json": r["payload_json"],
                }
                for r in connection.execute(
                    """
                    SELECT stats_provider, stats_league_id, stats_league_name,
                           stats_country_name, confidence, payload_json
                    FROM stats_league_links
                    WHERE unified_competition_id = ?
                    ORDER BY stats_provider
                    """,
                    (uc["id"],),
                ).fetchall()
            ]
            leagues.append({
                "public_id": uc["public_id"],
                "name": uc["name"],
                "display_name": uc["display_name"],
                "country": uc["country"],
                "gender": uc["gender"],
                "age_group": uc["age_group"],
                "platforms": platforms,
                "stats_links": stats_links,
            })

        unlinked = [
            _platform_dict(r)
            for r in connection.execute(
                """
                SELECT platform, competition_external_id, competition_name,
                       source_url, metadata_json, needs_name_resolution,
                       enabled, reminders_enabled
                FROM tracked_competitions
                WHERE unified_competition_id IS NULL
                ORDER BY platform, competition_external_id
                """
            ).fetchall()
        ]

    return {
        "version": SEED_VERSION,
        "exported_at": _utc_now_iso(),
        "leagues": leagues,
        "unlinked_platforms": unlinked,
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


def _flatten_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Convert a v2 (registry-centric) seed into the flat v1 import shape."""

    unified_names: list[str] = []
    tracked: list[dict[str, Any]] = []
    stats_links: list[dict[str, Any]] = []
    for league in data.get("leagues") or []:
        name = str(league.get("name") or "").strip()
        if not name:
            continue
        unified_names.append(name)
        platforms = league.get("platforms") or []
        for platform_entry in platforms:
            tracked.append({**platform_entry, "unified_name": name})
        # Stats links are league-level; anchor them to the league's first
        # platform (the link's tracked_competition_id column is NOT NULL).
        anchor = platforms[0] if platforms else None
        if anchor is None:
            continue
        for link in league.get("stats_links") or []:
            stats_links.append({
                **link,
                "platform": anchor.get("platform"),
                "competition_external_id": anchor.get("competition_external_id"),
            })
    for platform_entry in data.get("unlinked_platforms") or []:
        tracked.append({**platform_entry, "unified_name": None})
    return {
        "unified_competitions": unified_names,
        "tracked_competitions": tracked,
        "stats_league_links": stats_links,
    }


def _apply_registry_fields(data: dict[str, Any], *, overwrite: bool) -> None:
    """Apply v2 registry fields (public_id / traits) to the unified leagues."""

    now_iso = _utc_now_iso()
    with _connect() as connection:
        for league in data.get("leagues") or []:
            name = str(league.get("name") or "").strip()
            public_id = str(league.get("public_id") or "").strip()
            if not name:
                continue
            row = connection.execute(
                "SELECT id, public_id FROM unified_competitions WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                continue
            if public_id and (overwrite or not row["public_id"]):
                taken = connection.execute(
                    "SELECT 1 FROM unified_competitions WHERE public_id = ? AND id != ?",
                    (public_id, row["id"]),
                ).fetchone()
                if taken is None:
                    connection.execute(
                        "UPDATE unified_competitions SET public_id = ?, updated_at = ? WHERE id = ?",
                        (public_id, now_iso, row["id"]),
                    )
            assignments = []
            values: list[Any] = []
            for field in ("display_name", "country", "gender", "age_group"):
                value = league.get(field)
                if value is None:
                    continue
                if overwrite:
                    assignments.append(f"{field} = ?")
                else:
                    assignments.append(f"{field} = COALESCE({field}, ?)")
                values.append(value)
            if assignments:
                connection.execute(
                    f"UPDATE unified_competitions SET {', '.join(assignments)}, updated_at = ? WHERE id = ?",
                    (*values, now_iso, row["id"]),
                )


def import_league_seed(data: dict[str, Any], *, overwrite: bool = False) -> dict[str, int]:
    """Upsert the seed into the DB using natural keys (accepts formats v1 and v2).

    ``overwrite=False`` (default) preserves rows that already exist (only fills in
    a missing unified link); ``overwrite=True`` refreshes their generic fields too.
    Subscriptions / active events / any user data are never touched.
    """

    version = int(data.get("version") or 1)
    flat = _flatten_v2(data) if version >= 2 else data
    counts = _import_flat(flat, overwrite=overwrite)
    if version >= 2:
        _apply_registry_fields(data, overwrite=overwrite)
    return counts


def _import_flat(data: dict[str, Any], *, overwrite: bool = False) -> dict[str, int]:
    """Upsert flat (v1-shaped) league data into the DB."""

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
            unified_ids[clean] = _insert_unified_competition(connection, clean)
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
            unified_ids[clean] = _insert_unified_competition(connection, clean)
            counts["unified_created"] += 1
            return unified_ids[clean]

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

            # The link belongs to the unified league: look it up (and insert it)
            # at league level so other platforms of the league share one row.
            uc_row = connection.execute(
                "SELECT unified_competition_id FROM tracked_competitions WHERE id = ?",
                (tracked_id,),
            ).fetchone()
            link_uid = uc_row["unified_competition_id"] if uc_row else None
            existing = None
            if link_uid is not None:
                existing = connection.execute(
                    "SELECT id FROM stats_league_links WHERE unified_competition_id = ? AND stats_provider = ?",
                    (link_uid, provider),
                ).fetchone()
            if existing is None:
                existing = connection.execute(
                    "SELECT id FROM stats_league_links WHERE tracked_competition_id = ? AND stats_provider = ?",
                    (tracked_id, provider),
                ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO stats_league_links (
                        tracked_competition_id, unified_competition_id, stats_provider,
                        stats_league_id, stats_league_name, stats_country_name,
                        confidence, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tracked_id, link_uid, provider,
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
