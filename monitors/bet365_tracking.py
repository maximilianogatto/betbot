"""Legacy compatibility wrapper for the generic tracking service.

This module is kept temporarily so older imports do not break while the
project transitions from Bet365-specific service names to neutral ones.
"""

from monitors.tracking import *  # noqa: F401,F403
from monitors.tracking import TrackingService as Bet365TrackingService

__all__ = [
    "Bet365TrackingService",
    "TrackingService",
    "CommandResult",
    "OddsChange",
    "SubscriptionOddsAlert",
    "LeagueRefreshResult",
    "RefreshSummary",
]
