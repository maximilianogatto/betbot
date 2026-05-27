"""Discovery endpoint wrappers.

These functions expose sport/date/tournament-tree navigation without leaking raw
URL templates to callers. They return raw gismo JSON and are intentionally thin:
transport is handled by `http_client`, normalization by `normalizers` or
`tournament_navigation`.
"""

from __future__ import annotations

from typing import Any

from sandbox.sportradar_http.endpoints.catalog import call_endpoint


def get_sport_overview(client: Any, *, sport_id: int = 1, date: str, cursor: int = 0) -> dict[str, Any]:
    """Return sport-level fixtures for a date.

    Endpoint: `unified_sport_matches/{sport_id}/{date}/{cursor}`.
    Useful for discovering fixtures without scraping HTML.
    """

    return call_endpoint(client, "unified_sport_matches", sport_id=sport_id, date=date, cursor=cursor)


def get_sport_matches_markets(client: Any, *, sport_id: int = 1, date: str, cursor: int = 0) -> dict[str, Any]:
    """Return sport-level fixture market references for a date."""

    return call_endpoint(client, "unified_sport_matches_markets", sport_id=sport_id, date=date, cursor=cursor)


def get_sport_prevnext(client: Any, *, sport_id: int = 1, date: str, cursor: int = 0) -> dict[str, Any]:
    """Return previous/next cursor metadata for sport fixtures."""

    return call_endpoint(client, "sport_matches_prevnext", sport_id=sport_id, date=date, cursor=cursor)


def get_stats_sport_prevnext(client: Any, *, sport_id: int = 1, date: str, cursor: int = 0) -> dict[str, Any]:
    """Return stats-aware previous/next cursor metadata for sport fixtures."""

    return call_endpoint(client, "stats_sport_matches_prevnext", sport_id=sport_id, date=date, cursor=cursor)


def get_config_tree_mini(client: Any, *, category_id: int = 67, depth: int = 0, sport_id: int = 1) -> dict[str, Any]:
    """Return navigation tree metadata for sports/categories/leagues."""

    return call_endpoint(client, "config_tree_mini", category_id=category_id, depth=depth, sport_id=sport_id)
