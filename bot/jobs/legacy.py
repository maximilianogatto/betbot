"""Legacy background monitoring loops and start/stop wrappers for test compatibility."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from telegram.ext import Application

from monitoring import (
    append_monitor_log,
    format_monitor_log_block,
    get_metric_warnings,
    get_system_metrics,
)
from bot.jobs.resource_monitor import request_chromium_restart
from services.live_watch import LiveWatchService, parse_sheet_fixture_lines, render_live_hit, sheet_timezone
from services.stats import StatsService
from services.tracking import TrackingService
from interfaces.telegram.renderers import format_duration

logger = logging.getLogger(__name__)

TRACKING_MONITOR_TASK_KEY = "tracking_monitor_task"
RESOURCE_MONITOR_TASK_KEY = "resource_monitor_task"
STATS_SESSION_TASK_KEY = "stats_session_refresh_task"
STATS_PREFETCH_TASK_KEY = "stats_prefetch_task"
LIVE_WATCH_TASK_KEY = "live_watch_task"
SHEET_IMPORT_TASK_KEY = "sheet_import_task"
PEAK_DIGEST_TASK_KEY = "peak_digest_task"
DB_PRUNING_TASK_KEY = "db_pruning_task"
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


async def start_sheet_import_monitor(
    application: Application,
    *,
    chat_id: int | None,
    url: str,
    interval_seconds: int = 900,
) -> None:
    """Auto-import the shared Google Sheet into one chat's watchlist on change."""
    if not chat_id:
        logger.info("Sheet auto-import disabled (no LIVE_WATCH_SHEET_CHAT_ID).")
        return
    existing = application.bot_data.get(SHEET_IMPORT_TASK_KEY)
    if isinstance(existing, asyncio.Task) and not existing.done():
        return
    task = asyncio.create_task(
        _sheet_import_loop(application, chat_id=chat_id, url=url, interval_seconds=interval_seconds),
        name="sheet-import-loop",
    )
    application.bot_data[SHEET_IMPORT_TASK_KEY] = task
    logger.info(
        "Sheet auto-import loop started chat_id=%s interval_seconds=%s.", chat_id, interval_seconds
    )


async def stop_sheet_import_monitor(application: Application) -> None:
    task = application.bot_data.get(SHEET_IMPORT_TASK_KEY)
    if not isinstance(task, asyncio.Task):
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Sheet auto-import loop stopped.")
    application.bot_data.pop(SHEET_IMPORT_TASK_KEY, None)


async def _sheet_import_loop(
    application: Application, *, chat_id: int, url: str, interval_seconds: int
) -> None:
    """Poll the sheet; on content change, import new fixtures and notify the chat."""
    import hashlib
    import httpx

    last_hash: str | None = None
    while True:
        try:
            service = application.bot_data.get(LIVE_WATCH_SERVICE_KEY)
            if isinstance(service, LiveWatchService):
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.get(url, timeout=20.0)
                if resp.status_code == 200:
                    digest = hashlib.sha256(resp.text.encode("utf-8")).hexdigest()
                    if digest != last_hash:
                        last_hash = digest
                        try:
                            lines = parse_sheet_fixture_lines(resp.text)
                        except ValueError as err:
                            logger.warning("Sheet auto-import: %s", err)
                            lines = []
                        added = (
                            service.add_fixture_lines(chat_id, lines, times_tz=sheet_timezone())
                            if lines
                            else []
                        )
                        if added:
                            from bot.jobs.tasks import _notify_sheet_import

                            msg = [f"📥 *Auto-import de planilla:* +{len(added)} partido(s) en vigilancia."]
                            for entry in added:
                                hint = f" ({entry.league_hint})" if entry.league_hint else ""
                                disp_id = entry.chat_local_id if entry.chat_local_id is not None else entry.id
                                msg.append(f"  *#{disp_id}* · `{entry.home}` vs `{entry.away}`{hint}")
                            try:
                                await _notify_sheet_import(application.bot, chat_id, "\n".join(msg))
                            except Exception:
                                logger.exception("Sheet auto-import: failed to notify chat %s", chat_id)
                        logger.info("Sheet auto-import: change detected, %s new fixture(s).", len(added))
                else:
                    logger.warning("Sheet auto-import: HTTP %s downloading sheet.", resp.status_code)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unhandled error during sheet auto-import cycle.")
        await asyncio.sleep(interval_seconds)


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
            application,
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
            from adapters.storage import get_storage
            tracking_repository = get_storage()

            purged = await asyncio.to_thread(tracking_repository.purge_expired_stats_payloads)
            logger.info(
                "Stats prefetch cycle finished leagues=%s reports=%s skipped=%s errors=%s purged_cache=%s",
                summary.get("leagues"),
                summary.get("reports"),
                summary.get("skipped"),
                summary.get("errors"),
                purged,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unhandled error during stats prefetch cycle.")
        await asyncio.sleep(interval_seconds)


async def start_peak_digest(
    application: Application,
    *,
    enabled: bool,
    hour_arg: int,
) -> None:
    """Start the daily special-league peak digest push loop if enabled."""
    if not enabled:
        logger.info("Peak digest push is disabled.")
        return

    existing_task = application.bot_data.get(PEAK_DIGEST_TASK_KEY)
    if isinstance(existing_task, asyncio.Task) and not existing_task.done():
        return

    task = asyncio.create_task(
        _peak_digest_loop(application, hour_arg=hour_arg),
        name="peak-digest-loop",
    )
    application.bot_data[PEAK_DIGEST_TASK_KEY] = task
    logger.info("Peak digest push loop started hour_arg=%s.", hour_arg)


async def stop_peak_digest(application: Application) -> None:
    """Stop the daily peak digest push loop if running."""
    task = application.bot_data.get(PEAK_DIGEST_TASK_KEY)
    if not isinstance(task, asyncio.Task):
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Peak digest push loop stopped.")
    application.bot_data.pop(PEAK_DIGEST_TASK_KEY, None)


def _seconds_until_arg_hour(hour_arg: int) -> float:
    """Seconds from now until the next occurrence of hour_arg in ARG time."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    arg = ZoneInfo("America/Argentina/Buenos_Aires")
    now = datetime.now(tz=arg)
    target = now.replace(hour=hour_arg % 24, minute=0, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


async def _peak_digest_loop(application: Application, *, hour_arg: int) -> None:
    """Push the special-league peak digest to subscribed chats once per day."""
    from services.special_peak import build_peak_scores, render_peak_digest
    from adapters.storage import get_storage
    tracking_repository = get_storage()

    while True:
        try:
            await asyncio.sleep(_seconds_until_arg_hour(hour_arg))
        except asyncio.CancelledError:
            raise

        try:
            chat_ids = tracking_repository.list_peak_digest_chats()
            if not chat_ids:
                continue

            from stats_providers.palloliitto.api_client import PalloliittoAPI
            from stats_providers.svenskfotboll_http.client import SvenskfotbollHTTPClient

            fin_api = PalloliittoAPI()
            swe_client = SvenskfotbollHTTPClient()
            try:
                scores = await asyncio.to_thread(
                    build_peak_scores, finland_api=fin_api, sweden_client=swe_client
                )
            finally:
                fin_api.close()
                swe_client.close()

            from core.timezones import resolve_chat_timezone, use_timezone

            for chat_id in chat_ids:
                try:
                    with use_timezone(resolve_chat_timezone(chat_id)):
                        digest = render_peak_digest(scores)
                    await application.bot.send_message(
                        chat_id=chat_id, text=digest, parse_mode="Markdown"
                    )
                except Exception:
                    logger.exception("Failed to send peak digest chat_id=%s", chat_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unhandled error during peak digest cycle.")


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
            summary, merges = await tracking_service.monitor_once()

            from interfaces.telegram.notifications import dispatch_tracking_notifications, notify_league_merges
            from adapters.storage import get_storage
            repository = get_storage()

            await dispatch_tracking_notifications(application.bot, summary, repository)
            if merges:
                await notify_league_merges(application.bot, merges, repository)

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
    application: Application | None = None,
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

            chromium_ram_mb = metrics.get("chromium_child_processes_ram_mb", 0.0)
            if chromium_ram_mb > chromium_ram_alert_mb:
                logger.warning(
                    "[MONITOR] Memory warning threshold breached: %.1f MB > %.1f MB. Requesting graceful Chromium restart...",
                    chromium_ram_mb,
                    chromium_ram_alert_mb,
                )
                requested = await request_chromium_restart(
                    application,
                    reason=f"chromium_ram_mb={chromium_ram_mb:.1f}>{chromium_ram_alert_mb:.1f}",
                )
                logger.warning("[MONITOR] Chromium RAM recovery requested for %d runtime(s).", requested)

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


async def start_db_pruning(
    application: Application,
    *,
    enabled: bool = True,
    interval_seconds: int = 86400,
    days_threshold: int = 14,
) -> None:
    """Start the background database pruning loop."""
    if not enabled:
        logger.info("Database pruning is disabled.")
        return

    existing = application.bot_data.get(DB_PRUNING_TASK_KEY)
    if isinstance(existing, asyncio.Task) and not existing.done():
        return

    task = asyncio.create_task(
        _db_pruning_loop(application, interval_seconds=interval_seconds, days_threshold=days_threshold),
        name="db-pruning-loop",
    )
    application.bot_data[DB_PRUNING_TASK_KEY] = task
    logger.info("Database pruning loop started interval_seconds=%s days_threshold=%s.", interval_seconds, days_threshold)


async def stop_db_pruning(application: Application) -> None:
    """Stop the background database pruning loop if running."""
    task = application.bot_data.pop(DB_PRUNING_TASK_KEY, None)
    if isinstance(task, asyncio.Task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info("Database pruning loop stopped.")


async def _db_pruning_loop(
    application: Application,
    *,
    interval_seconds: int,
    days_threshold: int,
) -> None:
    """Prune database old records periodically."""
    from adapters.storage import get_storage
    tracking_repository = get_storage()

    while True:
        try:
            logger.info("Starting periodic database pruning cycle...")
            stats = await asyncio.to_thread(
                tracking_repository.prune_old_data,
                days_threshold=days_threshold,
                sent_alerts_days=30,
                small_changes_days=7
            )
            logger.info("Database pruning finished: %s", stats)

            # Run VACUUM only on Sundays
            if datetime.now(timezone.utc).weekday() == 6:
                logger.info("It's Sunday. Running database VACUUM...")
                vacuum_success = await asyncio.to_thread(tracking_repository.run_db_vacuum)
                logger.info("Database VACUUM finished: success=%s", vacuum_success)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unhandled error during database pruning cycle.")
        await asyncio.sleep(interval_seconds)
