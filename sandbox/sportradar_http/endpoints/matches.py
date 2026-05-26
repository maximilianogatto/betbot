from __future__ import annotations

from typing import Any

from sandbox.sportradar_http.endpoints.catalog import call_endpoint


def get_match_info(client: Any, *, match_id: int) -> dict[str, Any]:
    """Return Statshub match metadata: teams, season, kickoff and coverage."""

    return call_endpoint(client, "match_info_statshub", match_id=match_id)


def get_match_snapshot(client: Any, *, match_id: int) -> dict[str, Any]:
    """Return current match snapshot/status/stat document."""

    return call_endpoint(client, "stats_match_get", match_id=match_id)


def get_match_details(client: Any, *, match_id: int) -> dict[str, Any]:
    """Return detailed match statistics/details."""

    return call_endpoint(client, "match_details", match_id=match_id)


def get_match_table_slice(client: Any, *, match_id: int) -> dict[str, Any]:
    """Return table context around teams in a match when available."""

    return call_endpoint(client, "stats_match_tableslice", match_id=match_id)


def get_match_head2head(client: Any, *, match_id: int) -> dict[str, Any]:
    """Return match-specific H2H payload when available."""

    return call_endpoint(client, "stats_match_head2head", match_id=match_id)

