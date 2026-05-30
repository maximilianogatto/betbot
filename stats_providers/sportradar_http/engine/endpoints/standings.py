"""Standings/form-table endpoint wrappers.

These wrappers provide league table and form-table evidence for feature
generation. Returned payloads stay raw until `normalizers.normalize_standings`
and `normalize_formtable` compact them.
"""

from __future__ import annotations

from typing import Any

from stats_providers.sportradar_http.engine.endpoints.catalog import call_endpoint


def get_season_tables(client: Any, *, season_id: int, table_id: int | str = "") -> dict[str, Any]:
    """Return standings/table payload for a season."""

    return call_endpoint(client, "stats_season_tables", season_id=season_id, table_id=table_id)


def get_formtable(client: Any, *, season_id: int) -> dict[str, Any]:
    """Return form table for a season."""

    return call_endpoint(client, "stats_formtable", season_id=season_id)
