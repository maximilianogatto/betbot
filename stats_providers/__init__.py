"""Stats provider registration.

Stats providers enrich sportsbook events with external context. They are kept
separate from odds extractors so BetBot can compare many odds platforms while
linking them to one or more statistics sources.
"""

from __future__ import annotations

import os

from core.stats_provider_base import StatsProviderRegistry, stats_provider_registry
from stats_providers.footystats_http import FootyStatsHttpStatsProvider
from stats_providers.sportradar_http import SportradarHttpStatsProvider
from stats_providers.palloliitto.provider import PalloliittoStatsProvider
from stats_providers.sofascore_http import SofaScoreHttpStatsProvider
from stats_providers.flashscore_http import FlashscoreHttpStatsProvider
from stats_providers.svenskfotboll_http import SvenskfotbollHttpStatsProvider
from stats_providers.special_federation import (
    AlgeriaFederationStatsProvider,
    NorwayFederationStatsProvider,
    RomaniaFederationStatsProvider,
    SlovakiaFederationStatsProvider,
)


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
    if os.getenv("SVENSKFOTBOLL_ENABLED", "true").strip().lower() not in {"false", "0", "no"}:
        target.register(SvenskfotbollHttpStatsProvider(payload_cache=cache))
    # SofaScore currently exposes public league metadata, but its fixture/report
    # API can return anti-bot `challenge` responses even to Playwright. Keep it
    # registered for old links, but hide it from new Telegram linking unless it
    # is explicitly enabled.
    sofascore = SofaScoreHttpStatsProvider(payload_cache=cache)
    if os.getenv("SOFASCORE_ENABLED", "false").strip().lower() not in {"true", "1", "yes"}:
        sofascore.implemented = False
    target.register(sofascore)
    # Flashscore (HTTP-only via static x-fsign; broadest league coverage).
    if os.getenv("FLASHSCORE_ENABLED", "true").strip().lower() not in {"false", "0", "no"}:
        target.register(FlashscoreHttpStatsProvider(payload_cache=cache))
    # FootyStats public fallback uses plain HTTP. A licensed key can be added
    # later without changing the provider contract.
    if os.getenv("FOOTYSTATS_ENABLED", "true").strip().lower() not in {"false", "0", "no"}:
        from stats_providers.footystats_http.client import FootyStatsHTTPClient

        target.register(
            FootyStatsHttpStatsProvider(
                client=FootyStatsHTTPClient(api_key=os.getenv("FOOTYSTATS_API_KEY")),
                payload_cache=cache,
            )
        )
    return target


__all__ = [
    "SportradarHttpStatsProvider",
    "PalloliittoStatsProvider",
    "FootyStatsHttpStatsProvider",
    "SofaScoreHttpStatsProvider",
    "FlashscoreHttpStatsProvider",
    "SvenskfotbollHttpStatsProvider",
    "NorwayFederationStatsProvider",
    "RomaniaFederationStatsProvider",
    "SlovakiaFederationStatsProvider",
    "AlgeriaFederationStatsProvider",
    "register_default_stats_providers",
]
