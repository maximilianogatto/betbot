"""Federation stats providers (Norway / Romania / Slovakia / Algeria).

These federations are scraped by the ``bot.special_leagues`` adapters (the
``/no_*``, ``/ro_*``, ``/sk_*``, ``/al_*`` commands). This package wraps each one
as a :class:`~core.stats_provider_base.StatsProvider` so the SAME leagues become
linkable to tracked odds leagues via ``/link_stats`` and feed the combined
``/stats`` report — closing the gap where only Finland/Sweden were linkable.
"""

from __future__ import annotations

from stats_providers.special_federation.provider import (
    AlgeriaFederationStatsProvider,
    NorwayFederationStatsProvider,
    RomaniaFederationStatsProvider,
    SlovakiaFederationStatsProvider,
    SpecialLeagueStatsProvider,
)

__all__ = [
    "SpecialLeagueStatsProvider",
    "NorwayFederationStatsProvider",
    "RomaniaFederationStatsProvider",
    "SlovakiaFederationStatsProvider",
    "AlgeriaFederationStatsProvider",
]
