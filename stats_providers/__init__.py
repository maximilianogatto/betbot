"""Stats provider registration.

Stats providers enrich sportsbook events with external context. They are kept
separate from odds extractors so BetBot can compare many odds platforms while
linking them to one or more statistics sources.
"""

from __future__ import annotations

from core.stats_provider_base import StatsProviderRegistry, stats_provider_registry
from stats_providers.sportradar_http import SportradarHttpStatsProvider


def register_default_stats_providers(
    registry: StatsProviderRegistry | None = None,
) -> StatsProviderRegistry:
    """Register built-in stats providers and return the target registry."""

    target = registry or stats_provider_registry
    target.register(SportradarHttpStatsProvider())
    return target


__all__ = [
    "SportradarHttpStatsProvider",
    "register_default_stats_providers",
]
