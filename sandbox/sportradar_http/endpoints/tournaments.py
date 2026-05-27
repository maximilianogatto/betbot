"""Tournament/season endpoint wrappers.

Statshub URLs often expose a user-facing tournament id, while most stats
endpoints require a `season_id`. `tournament_navigation.py` resolves that mapping
first, then these wrappers download season fixtures, teams, summaries and venues.
"""

from __future__ import annotations

from typing import Any

from sandbox.sportradar_http.endpoints.catalog import call_endpoint


def get_tournament_info(client: Any, *, season_id: int) -> dict[str, Any]:
    """Return league/season summary metadata for a tournament season."""

    return call_endpoint(client, "stats_season_leaguesummary", season_id=season_id)


def get_tournament_fixtures(client: Any, *, season_id: int) -> dict[str, Any]:
    """Return all known fixtures for a tournament season."""

    return call_endpoint(client, "stats_season_fixtures2", season_id=season_id)


def get_tournament_meta(client: Any, *, season_id: int) -> dict[str, Any]:
    """Return season metadata for a tournament."""

    return call_endpoint(client, "stats_season_meta", season_id=season_id)


def get_tournament_teams(client: Any, *, season_id: int) -> dict[str, Any]:
    """Return teams participating in a season."""

    return call_endpoint(client, "stats_season_teams2", season_id=season_id)


def get_tournament_venues(client: Any, *, season_id: int) -> dict[str, Any]:
    """Return venues associated with a season."""

    return call_endpoint(client, "stats_season_venues", season_id=season_id)
