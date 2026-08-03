"""Jobs package for background task monitoring, scheduled jobs, and orchestration."""

from __future__ import annotations

from runtime.scheduler import OrchestratedScheduler, ScheduledJob
from bot.jobs.tasks import (
    DbPruningJob,
    LiveWatchJob,
    MatchEnrichmentJob,
    PeakDigestJob,
    ResourceMonitorJob,
    SheetImportJob,
    StatsPrefetchJob,
    StatsSessionRefreshJob,
    TrackingMonitorJob,
    start_orchestrated_scheduler,
    stop_orchestrated_scheduler,
)

__all__ = [
    "ScheduledJob",
    "OrchestratedScheduler",
    "TrackingMonitorJob",
    "ResourceMonitorJob",
    "DbPruningJob",
    "StatsSessionRefreshJob",
    "StatsPrefetchJob",
    "LiveWatchJob",
    "MatchEnrichmentJob",
    "SheetImportJob",
    "PeakDigestJob",
    "start_orchestrated_scheduler",
    "stop_orchestrated_scheduler",
]
