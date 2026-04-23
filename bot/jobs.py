"""Background monitoring loops for the bot runtime.

The project intentionally uses a small async loop instead of a heavier
scheduler so the runtime stays easy to understand and easy to change.
"""

from __future__ import annotations

import asyncio
import logging

from telegram.ext import Application

from monitoring import (
    append_monitor_log,
    format_monitor_log_block,
    get_metric_warnings,
    get_system_metrics,
)
from monitors.tracking import TrackingService

logger = logging.getLogger(__name__)

TRACKING_MONITOR_TASK_KEY = "tracking_monitor_task"
RESOURCE_MONITOR_TASK_KEY = "resource_monitor_task"
LEGACY_MONITOR_TASK_KEY = "bet365_monitor_task"
LEGACY_TRACKING_SERVICE_KEY = "bet365_tracking_service"
TRACKING_SERVICE_KEY = "tracking_service"


async def start_tracking_monitor(application: Application, interval_seconds: int) -> None:
    """Start the background tracking monitor loop once."""

    existing_task = application.bot_data.get(TRACKING_MONITOR_TASK_KEY)

    if isinstance(existing_task, asyncio.Task) and not existing_task.done():
        return

    task = asyncio.create_task(
        _tracking_monitor_loop(application, interval_seconds),
        name="tracking-monitor-loop",
    )
    application.bot_data[TRACKING_MONITOR_TASK_KEY] = task
    application.bot_data[LEGACY_MONITOR_TASK_KEY] = task

    logger.info(
        "Tracking monitor loop started with interval_seconds=%s.",
        interval_seconds,
    )


async def stop_tracking_monitor(application: Application) -> None:
    """Stop the background tracking monitor loop if it is running."""

    task = application.bot_data.get(TRACKING_MONITOR_TASK_KEY)

    if not isinstance(task, asyncio.Task):
        return

    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        logger.info("Tracking monitor loop stopped.")

    application.bot_data.pop(TRACKING_MONITOR_TASK_KEY, None)
    application.bot_data.pop(LEGACY_MONITOR_TASK_KEY, None)


async def start_resource_monitor(
    application: Application,
    *,
    enabled: bool,
    interval_seconds: int,
    log_to_file: bool,
    chromium_ram_alert_mb: float,
) -> None:
    """Start the periodic resource monitor if it is enabled."""

    if not enabled:
        logger.info("Resource monitoring is disabled.")
        return

    existing_task = application.bot_data.get(RESOURCE_MONITOR_TASK_KEY)

    if isinstance(existing_task, asyncio.Task) and not existing_task.done():
        return

    task = asyncio.create_task(
        _resource_monitor_loop(
            interval_seconds=interval_seconds,
            log_to_file=log_to_file,
            chromium_ram_alert_mb=chromium_ram_alert_mb,
        ),
        name="resource-monitor-loop",
    )
    application.bot_data[RESOURCE_MONITOR_TASK_KEY] = task

    logger.info(
        "Resource monitor loop started with interval_seconds=%s log_to_file=%s chromium_ram_alert_mb=%s.",
        interval_seconds,
        log_to_file,
        chromium_ram_alert_mb,
    )


async def stop_resource_monitor(application: Application) -> None:
    """Stop the periodic resource monitor if it is running."""

    task = application.bot_data.get(RESOURCE_MONITOR_TASK_KEY)

    if not isinstance(task, asyncio.Task):
        return

    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        logger.info("Resource monitor loop stopped.")

    application.bot_data.pop(RESOURCE_MONITOR_TASK_KEY, None)


async def _tracking_monitor_loop(application: Application, interval_seconds: int) -> None:
    """Run the periodic scrape and notification cycle forever."""

    tracking_service = application.bot_data.get(TRACKING_SERVICE_KEY) or application.bot_data.get(
        LEGACY_TRACKING_SERVICE_KEY
    )

    if not isinstance(tracking_service, TrackingService):
        logger.error("TrackingService is not configured; monitor loop will not run.")
        return

    while True:
        try:
            summary = await tracking_service.monitor_once(application.bot)
            logger.info(
                "Tracking monitor cycle finished: requested=%s refreshed=%s active_matches=%s new_events=%s odds_changes=%s failed=%s",
                summary.tracks_requested,
                summary.tracks_refreshed,
                summary.active_matches,
                summary.new_events,
                summary.odds_changes,
                len(summary.failed_leagues),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unhandled error during tracking monitor cycle.")

        await asyncio.sleep(interval_seconds)


# Legacy compatibility aliases kept while the bot wiring migrates to neutral names.
start_bet365_monitor = start_tracking_monitor
stop_bet365_monitor = stop_tracking_monitor


async def _resource_monitor_loop(
    *,
    interval_seconds: int,
    log_to_file: bool,
    chromium_ram_alert_mb: float,
) -> None:
    """Log runtime resource metrics in the background forever."""

    while True:
        try:
            metrics = get_system_metrics()
            monitor_block = format_monitor_log_block(metrics)
            logger.info("%s", monitor_block)

            if log_to_file:
                append_monitor_log(monitor_block)

            for warning in get_metric_warnings(
                metrics,
                chromium_ram_warning_mb=chromium_ram_alert_mb,
            ):
                logger.warning("[MONITOR] %s", warning)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unhandled error during resource monitor cycle.")

        await asyncio.sleep(interval_seconds)
