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
from monitors.live_watch import LiveWatchService, render_live_hit
from monitors.stats import StatsService
from monitors.tracking import TrackingService, format_duration

logger = logging.getLogger(__name__)

TRACKING_MONITOR_TASK_KEY = "tracking_monitor_task"
RESOURCE_MONITOR_TASK_KEY = "resource_monitor_task"
STATS_SESSION_TASK_KEY = "stats_session_refresh_task"
STATS_PREFETCH_TASK_KEY = "stats_prefetch_task"
LIVE_WATCH_TASK_KEY = "live_watch_task"
TRACKING_SERVICE_KEY = "tracking_service"
STATS_SERVICE_KEY = "stats_service"
LIVE_WATCH_SERVICE_KEY = "live_watch_service"


async def start_live_watch_monitor(
    application: Application,
    *,
    enabled: bool = True,
    interval_seconds: int = 30,
) -> None:
    """Start the live-watch poller loop (detect watched fixtures going in-play)."""

    if not enabled:
        logger.info("Live-watch monitor is disabled.")
        return

    existing_task = application.bot_data.get(LIVE_WATCH_TASK_KEY)
    if isinstance(existing_task, asyncio.Task) and not existing_task.done():
        return

    task = asyncio.create_task(
        _live_watch_loop(application, interval_seconds=interval_seconds),
        name="live-watch-loop",
    )
    application.bot_data[LIVE_WATCH_TASK_KEY] = task
    logger.info("Live-watch monitor loop started with interval_seconds=%s.", interval_seconds)


async def stop_live_watch_monitor(application: Application) -> None:
    """Stop the live-watch poller loop if running."""

    task = application.bot_data.get(LIVE_WATCH_TASK_KEY)
    if not isinstance(task, asyncio.Task):
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Live-watch monitor loop stopped.")
    application.bot_data.pop(LIVE_WATCH_TASK_KEY, None)


async def _live_watch_loop(application: Application, *, interval_seconds: int) -> None:
    """Poll live feeds and alert each chat when a watched fixture goes in-play."""

    service = application.bot_data.get(LIVE_WATCH_SERVICE_KEY)
    if not isinstance(service, LiveWatchService):
        logger.error("LiveWatchService is not configured; live-watch loop will not run.")
        return

    while True:
        try:
            hits = await service.poll_once()
            for hit in hits:
                try:
                    await application.bot.send_message(
                        chat_id=hit.entry.chat_id, text=render_live_hit(hit)
                    )
                except Exception:
                    logger.exception("Failed to send live-watch alert chat_id=%s", hit.entry.chat_id)
            if hits:
                logger.info("Live-watch cycle fired %s alert(s).", len(hits))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unhandled error during live-watch cycle.")
        
        sleep_sec = service.get_recommended_poll_interval(
            default_normal=float(interval_seconds),
            default_fast=10.0
        )
        await asyncio.sleep(sleep_sec)


async def start_tracking_monitor(application: Application, interval_seconds: int) -> None:
    """Start the background tracking monitor loop once."""

    existing_task = application.bot_data.get(TRACKING_MONITOR_TASK_KEY)

    if isinstance(existing_task, asyncio.Task) and not existing_task.done():
        return

    task = asyncio.create_task(
        _tracking_monitor_loop(
            application,
            interval_seconds,
            initial_delay_seconds=interval_seconds,
        ),
        name="tracking-monitor-loop",
    )
    application.bot_data[TRACKING_MONITOR_TASK_KEY] = task

    logger.info(
        "Tracking monitor loop started with interval_seconds=%s initial_delay_seconds=%s.",
        interval_seconds,
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


async def start_stats_session_refresh(
    application: Application,
    *,
    enabled: bool,
    interval_seconds: int,
    min_ttl_seconds: float,
) -> None:
    """Start the background Sportradar token pre-refresh loop if enabled."""

    if not enabled:
        logger.info("Stats session pre-refresh is disabled.")
        return

    existing_task = application.bot_data.get(STATS_SESSION_TASK_KEY)
    if isinstance(existing_task, asyncio.Task) and not existing_task.done():
        return

    task = asyncio.create_task(
        _stats_session_refresh_loop(
            application,
            interval_seconds=interval_seconds,
            min_ttl_seconds=min_ttl_seconds,
        ),
        name="stats-session-refresh-loop",
    )
    application.bot_data[STATS_SESSION_TASK_KEY] = task
    logger.info(
        "Stats session pre-refresh loop started interval_seconds=%s min_ttl_seconds=%s.",
        interval_seconds,
        min_ttl_seconds,
    )


async def stop_stats_session_refresh(application: Application) -> None:
    """Stop the background stats session pre-refresh loop if running."""

    task = application.bot_data.get(STATS_SESSION_TASK_KEY)
    if not isinstance(task, asyncio.Task):
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Stats session pre-refresh loop stopped.")
    application.bot_data.pop(STATS_SESSION_TASK_KEY, None)


async def start_stats_prefetch(
    application: Application,
    *,
    enabled: bool,
    interval_seconds: int,
    ttl_seconds: float,
    initial_delay_seconds: float = 90.0,
) -> None:
    """Start the daily stats prefetch loop (warm tracked leagues) if enabled."""

    if not enabled:
        logger.info("Stats daily prefetch is disabled.")
        return

    existing_task = application.bot_data.get(STATS_PREFETCH_TASK_KEY)
    if isinstance(existing_task, asyncio.Task) and not existing_task.done():
        return

    task = asyncio.create_task(
        _stats_prefetch_loop(
            application,
            interval_seconds=interval_seconds,
            ttl_seconds=ttl_seconds,
            initial_delay_seconds=initial_delay_seconds,
        ),
        name="stats-prefetch-loop",
    )
    application.bot_data[STATS_PREFETCH_TASK_KEY] = task
    logger.info(
        "Stats daily prefetch loop started interval_seconds=%s ttl_seconds=%s.",
        interval_seconds,
        ttl_seconds,
    )


async def stop_stats_prefetch(application: Application) -> None:
    """Stop the daily stats prefetch loop if running."""

    task = application.bot_data.get(STATS_PREFETCH_TASK_KEY)
    if not isinstance(task, asyncio.Task):
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Stats daily prefetch loop stopped.")
    application.bot_data.pop(STATS_PREFETCH_TASK_KEY, None)


async def _stats_prefetch_loop(
    application: Application,
    *,
    interval_seconds: int,
    ttl_seconds: float,
    initial_delay_seconds: float,
) -> None:
    """Warm all stats-linked tracked leagues into the cache once per interval."""

    stats_service = application.bot_data.get(STATS_SERVICE_KEY)
    if not isinstance(stats_service, StatsService):
        logger.error("StatsService is not configured; daily prefetch will not run.")
        return

    if initial_delay_seconds > 0:
        await asyncio.sleep(initial_delay_seconds)

    while True:
        try:
            summary = await stats_service.warm_tracked_leagues(ttl_seconds=ttl_seconds)
            logger.info(
                "Stats prefetch cycle finished leagues=%s reports=%s skipped=%s errors=%s",
                summary.get("leagues"),
                summary.get("reports"),
                summary.get("skipped"),
                summary.get("errors"),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unhandled error during stats prefetch cycle.")
        await asyncio.sleep(interval_seconds)


async def _stats_session_refresh_loop(
    application: Application,
    *,
    interval_seconds: int,
    min_ttl_seconds: float,
) -> None:
    """Keep the stats provider token fresh so it is never minted during /stats."""

    stats_service = application.bot_data.get(STATS_SERVICE_KEY)
    if not isinstance(stats_service, StatsService):
        logger.error("StatsService is not configured; session pre-refresh will not run.")
        return

    while True:
        try:
            # Mint/refresh at startup and well before expiry, off the request path.
            await stats_service.ensure_provider_sessions_fresh(min_ttl_seconds=min_ttl_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unhandled error during stats session pre-refresh cycle.")
        await asyncio.sleep(interval_seconds)


async def _tracking_monitor_loop(
    application: Application,
    interval_seconds: int,
    *,
    initial_delay_seconds: float | None = None,
) -> None:
    """Run the periodic scrape and notification cycle forever."""

    tracking_service = application.bot_data.get(TRACKING_SERVICE_KEY)

    if not isinstance(tracking_service, TrackingService):
        logger.error("TrackingService is not configured; monitor loop will not run.")
        return

    if initial_delay_seconds is None:
        initial_delay_seconds = interval_seconds

    if initial_delay_seconds > 0:
        await asyncio.sleep(initial_delay_seconds)

    while True:
        try:
            summary = await tracking_service.monitor_once(application.bot)
            logger.info(
                "Tracking monitor cycle finished: requested=%s refreshed=%s active_matches=%s new_events=%s odds_changes=%s failed=%s duration=%s duration_seconds=%.2f",
                summary.tracks_requested,
                summary.tracks_refreshed,
                summary.active_matches,
                summary.new_events,
                summary.odds_changes,
                len(summary.failed_leagues),
                format_duration(summary.elapsed_seconds),
                summary.elapsed_seconds,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unhandled error during tracking monitor cycle.")

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
