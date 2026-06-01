"""Stats provider registration.

Stats providers enrich sportsbook events with external context. They are kept
separate from odds extractors so BetBot can compare many odds platforms while
linking them to one or more statistics sources.
"""

from __future__ import annotations

import os

from core.stats_provider_base import StatsProviderRegistry, stats_provider_registry
from stats_providers.sportradar_http import SportradarHttpStatsProvider
from stats_providers.palloliitto.provider import PalloliittoStatsProvider


def register_default_stats_providers(
    registry: StatsProviderRegistry | None = None,
    *,
    payload_cache: object | None = None,
) -> StatsProviderRegistry:
    """Register built-in stats providers and return the target registry.

    `payload_cache` (defaults to the shared SQLite repository unless disabled via
    SPORTRADAR_CACHE_ENABLED=false) caches expensive provider payloads so repeated
    reads of a tracked league's stats avoid re-hitting Sportradar (anti-ban).
    """

    target = registry or stats_provider_registry
    cache = payload_cache
    if cache is None and os.getenv("SPORTRADAR_CACHE_ENABLED", "true").strip().lower() not in {"false", "0", "no"}:
        from storage.tracking_repository import tracking_repository

        cache = tracking_repository
    target.register(SportradarHttpStatsProvider(payload_cache=cache))
    target.register(PalloliittoStatsProvider(payload_cache=cache))
    return target


__all__ = [
    "SportradarHttpStatsProvider",
    "PalloliittoStatsProvider",
    "register_default_stats_providers",
]
