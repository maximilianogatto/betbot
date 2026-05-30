"""Odds/market endpoint wrappers.

`match_markets` is the current odds-provider candidate. It can be useful for
prematch or live markets when priced payloads are present, but some ended or
unpriced matches return an empty market structure. Callers must distinguish
"endpoint responded" from "usable priced odds exist".
"""

from __future__ import annotations

from typing import Any

from stats_providers.sportradar_http.engine.endpoints.catalog import call_endpoint


def get_odds_format(client: Any) -> dict[str, Any]:
    """Return odds format/config payload."""

    return call_endpoint(client, "odds_ukformat")


def get_match_markets(client: Any, *, match_id: int) -> dict[str, Any]:
    """Return match odds/markets for prematch or live usage."""

    return call_endpoint(client, "match_markets", match_id=match_id)


def get_team_markets(client: Any, *, team_id: int) -> dict[str, Any]:
    """Return team market metadata."""

    return call_endpoint(client, "uniqueteam_markets", team_id=team_id)


def get_season_markets(client: Any, *, season_id: int) -> dict[str, Any]:
    """Return season market metadata."""

    return call_endpoint(client, "season_markets", season_id=season_id)
