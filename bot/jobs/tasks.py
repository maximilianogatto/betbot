"""Concrete job definitions and orchestrator runner functions for BetBot."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
import time
from typing import Any

from telegram.ext import Application

from runtime.scheduler import OrchestratedScheduler, ScheduledJob
from monitoring import (
    append_monitor_log,
    format_monitor_log_block,
    get_metric_warnings,
    get_system_metrics,
)
from services.live_watch import LiveWatchService, parse_sheet_fixture_lines, render_live_hit, sheet_timezone
from services.stats import StatsService
from services.tracking import TrackingService
from interfaces.telegram.renderers import format_duration
from bot.jobs.resource_monitor import request_chromium_restart

logger = logging.getLogger(__name__)

SCHEDULER_KEY = "orchestrated_scheduler"
TRACKING_SERVICE_KEY = "tracking_service"
STATS_SERVICE_KEY = "stats_service"
LIVE_WATCH_SERVICE_KEY = "live_watch_service"


class TrackingMonitorJob(ScheduledJob):
    """Job that periodically refreshes tracked competition odds."""

    def __init__(self, interval: float, initial_delay: float = 0.0) -> None:
        super().__init__("tracking_monitor", initial_delay)
        self.interval = interval

    def get_interval(self, application: Application) -> float:
        return self.interval

    async def run(self, application: Application) -> None:
        await _orchestrated_tracking_monitor(application)


class ResourceMonitorJob(ScheduledJob):
    """Job that logs system resource usage and manages Chromium memory limits."""

    def __init__(self, interval: float, initial_delay: float = 0.0) -> None:
        super().__init__("resource_monitor", initial_delay)
        self.interval = interval

    def get_interval(self, application: Application) -> float:
        return self.interval

    async def run(self, application: Application) -> None:
        settings = application.bot_data.get("settings")
        if not settings:
            return
        metrics = get_system_metrics()
        monitor_block = format_monitor_log_block(metrics)
        logger.info("%s", monitor_block)
        if settings.monitor_log_to_file:
            append_monitor_log(monitor_block)
        chromium_ram_mb = metrics.get("chromium_child_processes_ram_mb", 0.0)
        if chromium_ram_mb > settings.monitor_chromium_ram_alert_mb:
            logger.warning(
                "[MONITOR] Memory warning threshold breached: %.1f MB > %.1f MB. Requesting graceful Chromium restart...",
                chromium_ram_mb,
                settings.monitor_chromium_ram_alert_mb,
            )
            requested = await request_chromium_restart(
                application,
                reason=f"chromium_ram_mb={chromium_ram_mb:.1f}>{settings.monitor_chromium_ram_alert_mb:.1f}",
            )
            logger.warning("[MONITOR] Chromium RAM recovery requested for %d runtime(s).", requested)
        for warning in get_metric_warnings(metrics, chromium_ram_warning_mb=settings.monitor_chromium_ram_alert_mb):
            logger.warning("[MONITOR] %s", warning)


class DbPruningJob(ScheduledJob):
    """Job that deletes historical database records past the retention limit."""

    def __init__(self, interval: float = 86400, initial_delay: float = 0.0) -> None:
        super().__init__("db_pruning", initial_delay)
        self.interval = interval

    def get_interval(self, application: Application) -> float:
        return self.interval

    async def run(self, application: Application) -> None:
        await _orchestrated_db_pruning(application)


class StatsSessionRefreshJob(ScheduledJob):
    """Job that refreshes active tokens/sessions of statistical providers."""

    def __init__(self, interval: float = 1800, initial_delay: float = 0.0) -> None:
        super().__init__("stats_session_refresh", initial_delay)
        self.interval = interval

    def get_interval(self, application: Application) -> float:
        return self.interval

    async def run(self, application: Application) -> None:
        await _orchestrated_stats_session_refresh(application)


class StatsPrefetchJob(ScheduledJob):
    """Job that pre-warms the cache of statistics databases."""

    def __init__(self, interval: float, initial_delay: float = 90.0) -> None:
        super().__init__("stats_prefetch", initial_delay)
        self.interval = interval

    def get_interval(self, application: Application) -> float:
        return self.interval

    async def run(self, application: Application) -> None:
        await _orchestrated_stats_prefetch(application)


class LiveWatchJob(ScheduledJob):
    """Job that services in-play status of matches with a dynamic interval."""

    def __init__(self, initial_delay: float = 0.0) -> None:
        super().__init__("live_watch", initial_delay)

    def get_interval(self, application: Application) -> float:
        return _live_watch_interval_resolver(application)

    async def run(self, application: Application) -> None:
        await _orchestrated_live_watch(application)


class SheetImportJob(ScheduledJob):
    """Job that imports Google Sheet watchlists when changes are detected."""

    def __init__(self, interval: float, initial_delay: float = 0.0) -> None:
        super().__init__("sheet_import", initial_delay)
        self.interval = interval

    def get_interval(self, application: Application) -> float:
        return self.interval

    async def run(self, application: Application) -> None:
        await _orchestrated_sheet_import(application)


class PeakDigestJob(ScheduledJob):
    """Job that compiles and pushes rotation alerts every morning."""

    def __init__(self, initial_delay: float = 0.0) -> None:
        super().__init__("peak_digest", initial_delay)

    def get_interval(self, application: Application) -> float:
        return _peak_digest_interval_resolver(application)

    async def run(self, application: Application) -> None:
        await _orchestrated_peak_digest(application)


# --- Orchestrated Execution Helper Implementations ---

async def _orchestrated_tracking_monitor(application: Application) -> None:
    tracking_service = application.bot_data.get(TRACKING_SERVICE_KEY)
    if not isinstance(tracking_service, TrackingService):
        return
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


async def _orchestrated_db_pruning(application: Application) -> None:
    from adapters.storage import get_storage
    tracking_repository = get_storage()
    logger.info("Starting database pruning cycle...")
    stats = await asyncio.to_thread(
        tracking_repository.prune_old_data,
        days_threshold=14,
        sent_alerts_days=30,
        small_changes_days=7
    )
    logger.info("Database pruning finished: %s", stats)

    # Run VACUUM only on Sundays
    if datetime.now(timezone.utc).weekday() == 6:
        logger.info("It's Sunday. Running database VACUUM...")
        vacuum_success = await asyncio.to_thread(tracking_repository.run_db_vacuum)
        logger.info("Database VACUUM finished: success=%s", vacuum_success)


async def _orchestrated_stats_session_refresh(application: Application) -> None:
    stats_service = application.bot_data.get(STATS_SERVICE_KEY)
    if not isinstance(stats_service, StatsService):
        return
    await stats_service.ensure_provider_sessions_fresh(min_ttl_seconds=5400.0)


async def _orchestrated_stats_prefetch(application: Application) -> None:
    stats_service = application.bot_data.get(STATS_SERVICE_KEY)
    settings = application.bot_data.get("settings")
    if not isinstance(stats_service, StatsService) or not settings:
        return
    summary = await stats_service.warm_tracked_leagues(ttl_seconds=settings.stats_prefetch_ttl_seconds)
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


async def _orchestrated_live_watch(application: Application) -> None:
    service = application.bot_data.get(LIVE_WATCH_SERVICE_KEY)
    if not isinstance(service, LiveWatchService):
        return
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


def _live_watch_interval_resolver(application: Application) -> float:
    service = application.bot_data.get(LIVE_WATCH_SERVICE_KEY)
    settings = application.bot_data.get("settings")
    default_normal = float(settings.live_watch_interval_seconds if settings else 30.0)
    if isinstance(service, LiveWatchService):
        return service.get_recommended_poll_interval(
            default_normal=default_normal,
            default_fast=10.0
        )
    return default_normal


async def _notify_sheet_import(bot, chat_id: int, text: str) -> None:
    """Send the auto-import notice, chunked and surviving Markdown-breaking names.

    A single send_message fails silently past Telegram's 4096-char limit (a
    full-sheet first import easily exceeds it) or when a team name breaks the
    Markdown parser; either way the user never learns what was added.
    """

    from interfaces.telegram.renderers import split_telegram_message

    for chunk in split_telegram_message(text):
        try:
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode="Markdown")
        except Exception:
            logger.warning(
                "Sheet auto-import: Markdown send failed chat=%s, retrying as plain text",
                chat_id,
            )
            await bot.send_message(chat_id=chat_id, text=chunk)


async def _orchestrated_sheet_import(application: Application) -> None:
    settings = application.bot_data.get("settings")
    if not settings or not settings.live_watch_sheet_chat_id:
        return
    service = application.bot_data.get(LIVE_WATCH_SERVICE_KEY)
    if not isinstance(service, LiveWatchService):
        return
    import httpx
    import hashlib
    url = settings.live_watch_sheet_url
    chat_id = settings.live_watch_sheet_chat_id
    last_hash = application.bot_data.get("sheet_import_last_hash")
    
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=20.0)
        if resp.status_code == 200:
            digest = hashlib.sha256(resp.text.encode("utf-8")).hexdigest()
            if digest != last_hash:
                application.bot_data["sheet_import_last_hash"] = digest
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
                logger.info(
                    "Sheet auto-import: %d line(s) parsed, %d new watch(es) added chat=%s",
                    len(lines),
                    len(added),
                    chat_id,
                )
                if added:
                    msg = [f"📥 *Auto-import de planilla:* +{len(added)} partido(s) en vigilancia."]
                    for entry in added:
                        hint = f" ({entry.league_hint})" if entry.league_hint else ""
                        disp_id = entry.chat_local_id if entry.chat_local_id is not None else entry.id
                        msg.append(f"  *#{disp_id}* · `{entry.home}` vs `{entry.away}`{hint}")
                    try:
                        await _notify_sheet_import(application.bot, chat_id, "\n".join(msg))
                    except Exception:
                        logger.exception("Sheet auto-import: failed to notify chat %s", chat_id)
    except Exception:
        logger.exception("Unhandled error during sheet auto-import cycle.")


async def _orchestrated_peak_digest(application: Application) -> None:
    from services.special_peak import build_peak_scores, render_peak_digest
    from adapters.storage import get_storage
    tracking_repository = get_storage()
    
    try:
        chat_ids = tracking_repository.list_peak_digest_chats()
        if not chat_ids:
            return
        
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
            
        from core.timezones import use_timezone
        from services.timezones import resolve_chat_timezone
        for chat_id in chat_ids:
            try:
                with use_timezone(resolve_chat_timezone(chat_id)):
                    digest = render_peak_digest(scores)
                await application.bot.send_message(
                    chat_id=chat_id, text=digest, parse_mode="Markdown"
                )
            except Exception:
                logger.exception("Failed to send peak digest chat_id=%s", chat_id)
    except Exception:
        logger.exception("Unhandled error during peak digest cycle.")


def _seconds_until_arg_hour(hour_arg: int) -> float:
    """Seconds from now until the next occurrence of hour_arg in America/Argentina/Buenos_Aires timezone."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    arg = ZoneInfo("America/Argentina/Buenos_Aires")
    now = datetime.now(tz=arg)
    target = now.replace(hour=hour_arg % 24, minute=0, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(1.0, (target - now).total_seconds())


def _peak_digest_interval_resolver(application: Application) -> float:
    settings = application.bot_data.get("settings")
    hour_arg = settings.peak_digest_hour_arg if settings else 9
    return _seconds_until_arg_hour(hour_arg)


async def start_orchestrated_scheduler(application: Application, settings: Any) -> None:
    """Initialize and start the unified OrchestratedScheduler."""
    import os
    application.bot_data["settings"] = settings
    
    scheduler = OrchestratedScheduler(application)
    
    # 1. Register Tracking Monitor.
    # El tick externo debe ser tan rápido como el tier más caliente (in-play),
    # si no, el gating por tiers nunca puede refrescar en vivo antes del tick.
    # Los partidos prematch siguen throttleados por sus tiers, así que la carga
    # extra queda acotada a los partidos en vivo.
    tracking_tick_seconds = min(
        settings.tracking_refresh_interval_seconds,
        settings.tracking_live_refresh_seconds,
    )
    scheduler.register_job(TrackingMonitorJob(tracking_tick_seconds))
    
    # 2. Register Resource Monitor
    if settings.enable_monitoring:
        scheduler.register_job(
            ResourceMonitorJob(settings.monitor_interval_seconds)
        )
        
    # 3. Register DB Pruning
    scheduler.register_job(
        DbPruningJob(86400)
    )
    
    # 4. Register Stats Session Refresh
    replay_only = os.getenv("SPORTRADAR_REPLAY_ONLY", "false").strip().lower() in {"true", "1", "yes"}
    if not replay_only:
        scheduler.register_job(
            StatsSessionRefreshJob(1800)
        )
        
    # 5. Register Stats Prefetch
    if settings.stats_prefetch_enabled and not replay_only:
        scheduler.register_job(
            StatsPrefetchJob(settings.stats_prefetch_interval_seconds, initial_delay=90.0)
        )
        
    # 6. Register Live Watch Monitor
    if settings.live_watch_enabled:
        scheduler.register_job(
            LiveWatchJob()
        )
        
    # 7. Register Sheet Import Monitor
    if settings.live_watch_sheet_chat_id:
        scheduler.register_job(
            SheetImportJob(settings.live_watch_sheet_interval_seconds)
        )
    else:
        logger.info(
            "Sheet auto-import disabled: LIVE_WATCH_SHEET_CHAT_ID is not set."
        )
        
    # 8. Register Peak Digest
    if settings.peak_digest_enabled:
        scheduler.register_job(
            PeakDigestJob(initial_delay=_peak_digest_interval_resolver(application))
        )
        
    await scheduler.start()
    application.bot_data[SCHEDULER_KEY] = scheduler


async def stop_orchestrated_scheduler(application: Application) -> None:
    """Stop and remove the unified OrchestratedScheduler."""
    scheduler = application.bot_data.pop(SCHEDULER_KEY, None)
    if isinstance(scheduler, OrchestratedScheduler):
        await scheduler.stop()
