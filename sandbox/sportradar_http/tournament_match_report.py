"""Helpers for tournament -> selected fixture -> match intelligence flow.

This module is the bridge between navigation and match intelligence. It does not
fetch network data itself; CLI scripts provide compact fixtures and match
intelligence documents.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def select_fixture(
    fixtures: list[dict[str, Any]],
    *,
    match_id: int | None = None,
    fixture_index: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Select one fixture from a tournament fixture list.

    Priority:
        1. explicit `match_id`;
        2. explicit zero-based `fixture_index`;
        3. first upcoming/unplayed fixture;
        4. first fixture in the list.

    Args:
        fixtures: Normalized fixtures from `tournament_navigation`.
        match_id: Optional exact Statshub match id.
        fixture_index: Optional zero-based index in `fixtures`.
        now: Optional clock for deterministic tests.

    Returns:
        Selected fixture dict.

    Raises:
        ValueError: when no fixture can be selected.
        IndexError: when `fixture_index` is out of range.
    """

    if not fixtures:
        raise ValueError("No fixtures available for selection.")
    if match_id is not None:
        for fixture in fixtures:
            if fixture.get("match_id") == match_id:
                return fixture
        raise ValueError(f"Match id not found in tournament fixtures: {match_id}")
    if fixture_index is not None:
        return fixtures[fixture_index]
    reference = now or datetime.now(UTC)
    for fixture in fixtures:
        if _is_upcoming_fixture(fixture, reference):
            return fixture
    return fixtures[0]


def build_tournament_match_package(
    *,
    navigation: dict[str, Any],
    selected_fixture: dict[str, Any],
    match_intelligence: dict[str, Any],
    client_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the compact package a future BetBot command can consume."""

    resolved = navigation.get("resolved_tournament") if isinstance(navigation.get("resolved_tournament"), dict) else {}
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "kind": "tournament_match_report",
        "provider": "sportradar_statshub",
        "tournament": {
            "requested_tournament_id": resolved.get("requested_tournament_id"),
            "unique_tournament_id": resolved.get("unique_tournament_id"),
            "concrete_tournament_id": resolved.get("concrete_tournament_id"),
            "season_id": resolved.get("season_id"),
            "name": ((resolved.get("primary") or {}).get("name") if isinstance(resolved.get("primary"), dict) else None),
            "country": ((resolved.get("primary") or {}).get("country_name") if isinstance(resolved.get("primary"), dict) else None),
        },
        "selected_fixture": selected_fixture,
        "match_id": selected_fixture.get("match_id") or match_intelligence.get("match_id"),
        "match_intelligence": match_intelligence,
        "report_summary": render_tournament_match_report(
            navigation=navigation,
            selected_fixture=selected_fixture,
            match_intelligence=match_intelligence,
        ),
        "client_metrics": client_metrics or {},
    }


def render_tournament_match_report(
    *,
    navigation: dict[str, Any],
    selected_fixture: dict[str, Any],
    match_intelligence: dict[str, Any],
) -> str:
    """Render a compact end-to-end tournament/match report."""

    resolved = navigation.get("resolved_tournament") if isinstance(navigation.get("resolved_tournament"), dict) else {}
    primary = resolved.get("primary") if isinstance(resolved.get("primary"), dict) else {}
    fixture_time = selected_fixture.get("time") if isinstance(selected_fixture.get("time"), dict) else {}
    home = selected_fixture.get("home") if isinstance(selected_fixture.get("home"), dict) else {}
    away = selected_fixture.get("away") if isinstance(selected_fixture.get("away"), dict) else {}
    lines = [
        "# Sportradar Tournament Match Report",
        "",
        f"- Tournament: `{primary.get('country_name')} / {primary.get('name')}`",
        f"- Season id: `{resolved.get('season_id')}`",
        f"- Fixture: `{home.get('name')} vs {away.get('name')}`",
        f"- Match id: `{selected_fixture.get('match_id')}`",
        f"- Kickoff UTC: `{fixture_time.get('iso_utc')}`",
        "",
        "## Match Intelligence",
        "",
        match_intelligence.get("report_summary") or "No match intelligence report available.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _is_upcoming_fixture(fixture: dict[str, Any], now: datetime) -> bool:
    time_data = fixture.get("time") if isinstance(fixture.get("time"), dict) else {}
    result = fixture.get("result") if isinstance(fixture.get("result"), dict) else {}
    uts = time_data.get("uts")
    try:
        kickoff = datetime.fromtimestamp(float(uts), tz=UTC)
    except (TypeError, ValueError, OSError):
        return False
    if result.get("home") is not None or result.get("away") is not None:
        return False
    return kickoff >= now
