"""Historical/team statistics endpoint wrappers.

These endpoints enrich a match with form, streaks, H2H, scoring/conceding,
injuries and player leaders. They are used by the match and league pipelines to
build compact analysis documents; they do not perform interpretation themselves.
"""

from __future__ import annotations

from typing import Any

from stats_providers.sportradar_http.engine.endpoints.catalog import call_endpoint


def get_h2h(client: Any, *, team_a_id: int, team_b_id: int, match_id: int) -> dict[str, Any]:
    """Return direct H2H evidence for two teams and a match context."""

    return call_endpoint(client, "stats_h2h_versus", team_a_id=team_a_id, team_b_id=team_b_id, match_id=match_id)


def get_team_versus(client: Any, *, team_a_id: int, team_b_id: int) -> dict[str, Any]:
    """Return team-vs-team context payload."""

    return call_endpoint(client, "stats_team_versus", team_a_id=team_a_id, team_b_id=team_b_id)


def get_team_lastx(client: Any, *, team_id: int, count: int = 20) -> dict[str, Any]:
    """Return recent matches for a team."""

    return call_endpoint(client, "stats_team_lastx", team_id=team_id, count=count)


def get_team_nextx(client: Any, *, team_id: int, count: int = 1) -> dict[str, Any]:
    """Return upcoming matches for a team."""

    return call_endpoint(client, "stats_team_nextx", team_id=team_id, count=count)


def get_team_streaks(client: Any, *, team_id: int) -> dict[str, Any]:
    """Return team streak/form signals."""

    return call_endpoint(client, "stats_team_streaks", team_id=team_id)


def get_team_scoring_conceding(
    client: Any,
    *,
    season_id: int,
    team_id: int,
    split_id: int = -1,
) -> dict[str, Any]:
    """Return scoring/conceding distributions for one team in a season."""

    return call_endpoint(
        client,
        "stats_season_teamscoringconceding",
        season_id=season_id,
        team_id=team_id,
        split_id=split_id,
    )


def get_injuries(client: Any, *, season_id: int) -> dict[str, Any]:
    """Return season injuries payload."""

    return call_endpoint(client, "stats_season_injuries", season_id=season_id)


def get_top_goals(client: Any, *, season_id: int, team_id: int | str = "") -> dict[str, Any]:
    """Return top scorers for a season or team."""

    return call_endpoint(client, "stats_season_topgoals", season_id=season_id, team_id=team_id)


def get_top_cards(client: Any, *, season_id: int, team_id: int | str = "") -> dict[str, Any]:
    """Return top cards for a season or team."""

    return call_endpoint(client, "stats_season_topcards", season_id=season_id, team_id=team_id)


def get_top_assists(client: Any, *, season_id: int, team_id: int | str = "") -> dict[str, Any]:
    """Return top assists for a season or team."""

    return call_endpoint(client, "stats_season_topassists", season_id=season_id, team_id=team_id)
