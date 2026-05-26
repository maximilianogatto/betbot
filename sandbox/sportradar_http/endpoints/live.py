from __future__ import annotations

from typing import Any

from sandbox.sportradar_http.endpoints.catalog import call_endpoint


def get_match_timeline(client: Any, *, match_id: int) -> dict[str, Any]:
    """Return full timeline for a match."""

    return call_endpoint(client, "match_timeline", match_id=match_id)


def get_match_timelinedelta(client: Any, *, match_id: int) -> dict[str, Any]:
    """Return timeline delta feed for a match."""

    return call_endpoint(client, "match_timelinedelta", match_id=match_id)


def get_event_feed(client: Any) -> dict[str, Any]:
    """Return generic event/live polling feed."""

    return call_endpoint(client, "event_get")


def get_match_situation(client: Any, *, match_id: int) -> dict[str, Any]:
    """Return live match situation payload when available."""

    return call_endpoint(client, "stats_match_situation", match_id=match_id)

