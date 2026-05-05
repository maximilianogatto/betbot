"""Application factory for the Telegram bot runtime."""

from __future__ import annotations

from telegram.ext import Application, ApplicationBuilder

from bot.config import Settings
from bot.error_handler import handle_error
from bot.handlers import register_handlers
from bot.jobs import (
    start_tracking_monitor,
    start_resource_monitor,
    stop_tracking_monitor,
    stop_resource_monitor,
)
from core.registry import extractor_registry
from extractors import register_default_extractors
from monitors.tracking import TrackingService
from storage.tracking_repository import SqliteTrackingRepository


def create_application(settings: Settings) -> Application:
    """Create and configure the Telegram application instance."""

    extractor_registry.replace_all([])
    registered_extractors = register_default_extractors(extractor_registry, settings=settings)
    tracking_repository = SqliteTrackingRepository(
        default_change_threshold_percent=settings.tracking_default_change_threshold_percent,
        default_notify_odds_changes=settings.tracking_default_notify_odds_changes,
    )

    tracking_service = TrackingService(
        extractor_registry=extractor_registry,
        repository=tracking_repository,
        max_parallel_refreshes=settings.tracking_max_parallel_refreshes,
    )

    async def post_init(application: Application) -> None:
        """Start background monitoring after the bot runtime is ready."""

        for extractor in registered_extractors:
            await extractor.start()
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

    async def post_shutdown(application: Application) -> None:
        """Stop background monitoring when the bot shuts down."""

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

    register_handlers(application)
    application.add_error_handler(handle_error)

    return application
