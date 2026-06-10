"""Application factory for the Telegram bot runtime."""

from __future__ import annotations

from telegram.ext import Application, ApplicationBuilder

from bot.config import Settings
from bot.error_handler import handle_error
from bot.handlers import register_handlers
from bot.jobs import (
    start_live_watch_monitor,
    start_peak_digest,
    start_stats_prefetch,
    start_stats_session_refresh,
    start_tracking_monitor,
    start_resource_monitor,
    stop_live_watch_monitor,
    stop_peak_digest,
    stop_stats_prefetch,
    stop_stats_session_refresh,
    stop_tracking_monitor,
    stop_resource_monitor,
)
from core.registry import extractor_registry
from core.stats_provider_base import stats_provider_registry
from extractors import register_default_extractors
from stats_providers import register_default_stats_providers
from monitors.live_watch import LiveWatchService
from monitors.stats import StatsService
from monitors.tracking import TrackingService
from storage.tracking_repository import SqliteTrackingRepository
from storage.league_seed import seed_if_empty


def create_application(settings: Settings) -> Application:
    """Create and configure the Telegram application instance."""

    extractor_registry.replace_all([])
    registered_extractors = register_default_extractors(extractor_registry, settings=settings)
    stats_provider_registry.replace_all([])
    register_default_stats_providers(stats_provider_registry)
    tracking_repository = SqliteTrackingRepository(
        default_change_threshold_percent=settings.tracking_default_change_threshold_percent,
        default_notify_odds_changes=settings.tracking_default_notify_odds_changes,
    )
    # Bootstrap a fresh DB (e.g. a new cloud deploy where the gitignored SQLite file
    # didn't travel) from the committed league seed. No-op if the DB already has
    # tracked competitions, so an existing install is never altered.
    seed_if_empty()

    tracking_service = TrackingService(
        extractor_registry=extractor_registry,
        repository=tracking_repository,
        max_parallel_refreshes=settings.tracking_max_parallel_refreshes,
        remove_missing_after_cycles=settings.tracking_remove_missing_after_cycles,
        odds_change_confirmation_refreshes=settings.odds_change_confirmation_refreshes,
        odds_flap_window_minutes=settings.odds_flap_window_minutes,
        odds_flap_epsilon=settings.odds_flap_epsilon,
    )
    stats_service = StatsService(
        provider_registry=stats_provider_registry,
        repository=tracking_repository,
    )
    live_watch_service = LiveWatchService(
        extractor_registry=extractor_registry,
        repository=tracking_repository,
    )

    async def post_init(application: Application) -> None:
        """Start background monitoring after the bot runtime is ready."""

        await start_tracking_monitor(
            application,
            interval_seconds=settings.tracking_refresh_interval_seconds,
        )
        await start_resource_monitor(
            application,
            enabled=settings.enable_monitoring,
            interval_seconds=settings.monitor_interval_seconds,
            log_to_file=settings.monitor_log_to_file,
            chromium_ram_alert_mb=settings.monitor_chromium_ram_alert_mb,
        )
        # Mint/refresh the Sportradar token at startup and well before expiry so
        # the token-bootstrap browser never opens during a user-facing /stats.
        await start_stats_session_refresh(
            application,
            enabled=True,
            interval_seconds=1800,
            min_ttl_seconds=5400.0,
        )
        # Daily prefetch: warm every stats-linked league (overview + reports of its
        # tracked matches) into the cache so /stats never hits the provider on demand.
        await start_stats_prefetch(
            application,
            enabled=settings.stats_prefetch_enabled,
            interval_seconds=settings.stats_prefetch_interval_seconds,
            ttl_seconds=settings.stats_prefetch_ttl_seconds,
        )
        # Poll live feeds and alert when a watched fixture goes in-play.
        await start_live_watch_monitor(
            application,
            enabled=settings.live_watch_enabled,
            interval_seconds=settings.live_watch_interval_seconds,
        )
        # Daily morning push of the special-league peak digest to subscribers.
        await start_peak_digest(
            application,
            enabled=settings.peak_digest_enabled,
            hour_arg=settings.peak_digest_hour_arg,
        )

    async def post_shutdown(application: Application) -> None:
        """Stop background monitoring when the bot shuts down."""

        await stop_peak_digest(application)
        await stop_live_watch_monitor(application)
        await stop_stats_prefetch(application)
        await stop_stats_session_refresh(application)
        await stop_resource_monitor(application)
        await stop_tracking_monitor(application)
        for extractor in reversed(registered_extractors):
            await extractor.stop()

    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.bot_data["tracking_service"] = tracking_service
    application.bot_data["stats_service"] = stats_service
    application.bot_data["live_watch_service"] = live_watch_service

    register_handlers(application)
    application.add_error_handler(handle_error)

    return application
