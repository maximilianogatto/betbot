"""Background monitoring loop for the Bet365 bot.

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
from monitors.bet365_tracking import Bet365TrackingService

logger = logging.getLogger(__name__)

MONITOR_TASK_KEY = "bet365_monitor_task"
RESOURCE_MONITOR_TASK_KEY = "bet365_resource_monitor_task"


async def start_bet365_monitor(application: Application, interval_seconds: int) -> None:
    """Start the background Bet365 monitoring loop once."""

    existing_task = application.bot_data.get(MONITOR_TASK_KEY)

    if isinstance(existing_task, asyncio.Task) and not existing_task.done():
        return

    task = asyncio.create_task(
        _bet365_monitor_loop(application, interval_seconds),
        name="bet365-monitor-loop",
    )
    application.bot_data[MONITOR_TASK_KEY] = task

    logger.info(
        "Bet365 monitor loop started with interval_seconds=%s.",
        interval_seconds,
    )


async def stop_bet365_monitor(application: Application) -> None:
    """Stop the background Bet365 monitoring loop if it is running."""

    task = application.bot_data.get(MONITOR_TASK_KEY)

    if not isinstance(task, asyncio.Task):
        return

    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        logger.info("Bet365 monitor loop stopped.")

    application.bot_data.pop(MONITOR_TASK_KEY, None)


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
        name="bet365-resource-monitor-loop",
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


async def _bet365_monitor_loop(application: Application, interval_seconds: int) -> None:
    """Run the periodic Bet365 scrape and notification cycle forever."""

    tracking_service = application.bot_data.get("bet365_tracking_service")

    if not isinstance(tracking_service, Bet365TrackingService):
        logger.error("Bet365TrackingService is not configured; monitor loop will not run.")
        return

    while True:
        try:
            summary = await tracking_service.monitor_once(application.bot)
            logger.info(
                "Bet365 monitor cycle finished: requested=%s refreshed=%s active_matches=%s new_events=%s odds_changes=%s failed=%s",
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
            logger.exception("Unhandled error during Bet365 monitor cycle.")

        await asyncio.sleep(interval_seconds)


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
