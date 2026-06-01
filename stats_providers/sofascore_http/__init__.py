"""SofaScore HTTP stats provider package."""

from stats_providers.sofascore_http.provider import (
    SofaScoreBotReadyStatsProvider,
    SofaScoreHttpStatsProvider,
)

__all__ = ["SofaScoreHttpStatsProvider", "SofaScoreBotReadyStatsProvider"]
