"""Tournament navigation resolver for Statshub.

Purpose:
    Validate and implement the stable navigation path:

        sport -> country/tournament tree -> current season -> fixtures -> match_id

Input data:
    `config_tree_mini` raw payload and, when the tournament is resolved, a
    `stats_season_fixtures2` raw payload.

Output data:
    `tournament_navigation.json` style dict with resolved tournament metadata,
    season id, stage rows, compact fixtures, raw refs, and limitations.

Why this exists:
    Statshub page URLs expose ids such as `/sport/1/tournament/18340`, but most
    stats endpoints require a `season_id`. This module bridges that difference
    without scraping HTML.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sandbox.sportradar_http.normalizers import as_int, doc_data, make_raw_ref, normalize_fixtures


NAVIGATION_SCHEMA_VERSION = 1


def build_tournament_tree(config_tree_payload: dict[str, Any]) -> dict[str, Any]:
    """Build a compact sport -> country -> tournament index from config_tree_mini."""

    data = doc_data(config_tree_payload)
    sports = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    sport_items = []
    country_items = []
    tournament_items = []
    for sport in sports:
        if not isinstance(sport, dict):
            continue
        sport_id = as_int(sport.get("_sid")) or as_int(sport.get("_id"))
        sport_item = {"sport_id": sport_id, "sport_name": sport.get("name")}
        sport_items.append(sport_item)
        for category in sport.get("realcategories") or []:
            if not isinstance(category, dict):
                continue
            country = _compact_country(category, sport_id=sport_id)
            leagues = []
            for tournament in category.get("tournaments") or []:
                if not isinstance(tournament, dict):
                    continue
                item = _compact_tournament(tournament, country=country, sport=sport_item)
                leagues.append(item)
                tournament_items.append(item)
            country_items.append({**country, "leagues": leagues})
    return {
        "schema_version": NAVIGATION_SCHEMA_VERSION,
        "sports": sport_items,
        "countries": country_items,
        "tournaments": tournament_items,
        "raw_ref": make_raw_ref("config_tree_mini", config_tree_payload),
    }


def resolve_tournament(tree: dict[str, Any], tournament_id: int) -> dict[str, Any]:
    """Resolve a URL-facing tournament id to the current season and concrete stage rows."""

    candidates = [
        item
        for item in tree.get("tournaments") or []
        if _matches_tournament_id(item, tournament_id)
    ]
    stages = sorted(candidates, key=lambda item: (item.get("season_id") != item.get("current_season_id"), item.get("name") or ""))
    primary = _choose_primary_tournament(stages)
    if not primary:
        return {
            "requested_tournament_id": tournament_id,
            "found": False,
            "match_kind": None,
            "primary": None,
            "stages": [],
        }
    return {
        "requested_tournament_id": tournament_id,
        "found": True,
        "match_kind": _match_kind(primary, tournament_id),
        "primary": primary,
        "stages": stages,
        "season_id": primary.get("season_id"),
        "current_season_id": primary.get("current_season_id"),
        "unique_tournament_id": primary.get("unique_tournament_id"),
        "concrete_tournament_id": primary.get("tournament_id"),
    }


def build_tournament_navigation_snapshot(
    *,
    sport_id: int,
    tournament_id: int,
    config_tree_payload: dict[str, Any],
    fixtures_payload: dict[str, Any] | None,
    max_fixtures: int | None = None,
) -> dict[str, Any]:
    """Build a compact navigation snapshot from raw tree and fixtures payloads.

    Args:
        sport_id: Sport id from Statshub URLs. Soccer is `1`.
        tournament_id: URL-facing tournament id to resolve.
        config_tree_payload: Raw `config_tree_mini` payload.
        fixtures_payload: Raw `stats_season_fixtures2` payload for the resolved
            season. May be empty when resolution fails.
        max_fixtures: Optional cap for compact fixture output.
    """

    tree = build_tournament_tree(config_tree_payload)
    resolved = resolve_tournament(tree, tournament_id)
    fixtures = normalize_fixtures(fixtures_payload or {}, max_items=max_fixtures)
    return {
        "schema_version": NAVIGATION_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "sportradar_statshub",
        "scope": "tournament_navigation",
        "inputs": {
            "sport_id": sport_id,
            "tournament_id": tournament_id,
        },
        "tree_summary": {
            "sports": len(tree.get("sports") or []),
            "countries": len(tree.get("countries") or []),
            "tournaments": len(tree.get("tournaments") or []),
        },
        "resolved_tournament": resolved,
        "fixtures": fixtures,
        "fixture_count": len(fixtures),
        "raw_refs": {
            "config_tree": tree.get("raw_ref"),
            "fixtures": make_raw_ref("stats_season_fixtures2", fixtures_payload or {}),
        },
        "limitations": [
            "Tournament navigation uses config_tree_mini and season fixtures only.",
            "The URL tournament id can map to a unique tournament id with multiple stage rows.",
            "The selected season is the row whose season_id matches current_season_id when available.",
        ],
    }


def render_tournament_navigation_report(snapshot: dict[str, Any]) -> str:
    """Render resolved tournament, stages and first fixtures as Markdown."""

    resolved = snapshot.get("resolved_tournament") or {}
    primary = resolved.get("primary") or {}
    lines = [
        "# Sportradar Tournament Navigation Report",
        "",
        f"- Generated at: `{snapshot.get('generated_at')}`",
        f"- Requested sport_id: `{(snapshot.get('inputs') or {}).get('sport_id')}`",
        f"- Requested tournament_id: `{(snapshot.get('inputs') or {}).get('tournament_id')}`",
        f"- Found: `{resolved.get('found')}`",
        f"- Match kind: `{resolved.get('match_kind')}`",
        f"- Country: `{primary.get('country_name')}`",
        f"- Tournament: `{primary.get('name')}`",
        f"- Unique tournament id: `{resolved.get('unique_tournament_id')}`",
        f"- Concrete tournament id: `{resolved.get('concrete_tournament_id')}`",
        f"- Season id: `{resolved.get('season_id')}`",
        f"- Fixture count: `{snapshot.get('fixture_count')}`",
        "",
        "## Stages",
        "",
    ]
    for stage in resolved.get("stages") or []:
        lines.append(
            "- {name} | tournament_id={tid} | unique_tournament_id={utid} | season_id={sid} | current={current}".format(
                name=stage.get("name"),
                tid=stage.get("tournament_id"),
                utid=stage.get("unique_tournament_id"),
                sid=stage.get("season_id"),
                current=stage.get("is_current_season"),
            )
        )
    lines.extend(["", "## Fixtures", ""])
    for fixture in (snapshot.get("fixtures") or [])[:20]:
        time = fixture.get("time") or {}
        home = fixture.get("home") or {}
        away = fixture.get("away") or {}
        result = fixture.get("result") or {}
        lines.append(
            "- `{date}` match_id={match_id} {home} vs {away} result={home_score}-{away_score}".format(
                date=time.get("iso_utc") or time.get("date"),
                match_id=fixture.get("match_id"),
                home=home.get("name"),
                away=away.get("name"),
                home_score=result.get("home"),
                away_score=result.get("away"),
            )
        )
    lines.extend(["", "## Limitations", ""])
    for item in snapshot.get("limitations") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _compact_country(category: dict[str, Any], *, sport_id: int | None) -> dict[str, Any]:
    country_code = category.get("cc") if isinstance(category.get("cc"), dict) else {}
    return {
        "sport_id": sport_id,
        "country_id": as_int(category.get("_rcid")) or as_int(category.get("_id")),
        "country_name": category.get("name"),
        "country_code": country_code.get("a2"),
    }


def _compact_tournament(
    tournament: dict[str, Any],
    *,
    country: dict[str, Any],
    sport: dict[str, Any],
) -> dict[str, Any]:
    season_id = as_int(tournament.get("seasonid"))
    current_season_id = as_int(tournament.get("currentseason"))
    return {
        "sport_id": sport.get("sport_id"),
        "sport_name": sport.get("sport_name"),
        "country_id": country.get("country_id"),
        "country_name": country.get("country_name"),
        "country_code": country.get("country_code"),
        "tournament_id": as_int(tournament.get("_tid")) or as_int(tournament.get("_id")),
        "unique_tournament_id": as_int(tournament.get("_utid")),
        "name": tournament.get("name"),
        "season_id": season_id,
        "current_season_id": current_season_id,
        "is_current_season": bool(season_id and current_season_id and season_id == current_season_id),
        "round_by_round": bool(tournament.get("roundbyround")),
    }


def _matches_tournament_id(item: dict[str, Any], tournament_id: int) -> bool:
    return tournament_id in {
        item.get("tournament_id"),
        item.get("unique_tournament_id"),
        item.get("season_id"),
        item.get("current_season_id"),
    }


def _choose_primary_tournament(stages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in stages:
        if item.get("is_current_season"):
            return item
    for item in stages:
        if item.get("season_id"):
            return item
    return stages[0] if stages else None


def _match_kind(item: dict[str, Any], tournament_id: int) -> str | None:
    for key in ("unique_tournament_id", "tournament_id", "season_id", "current_season_id"):
        if item.get(key) == tournament_id:
            return key
    return None
