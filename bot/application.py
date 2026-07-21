"""Application factory for the Telegram bot runtime."""

from __future__ import annotations

import os

from telegram.ext import Application, ApplicationBuilder

from bot.config import Settings
from bot.error_handler import handle_error
from bot.handlers import register_handlers
from bot.jobs import (
    start_orchestrated_scheduler,
    stop_orchestrated_scheduler,
)
from core.registry import extractor_registry
from core.stats_provider_base import stats_provider_registry
from extractors import register_default_extractors
from stats_providers import register_default_stats_providers
from services.live_watch import LiveWatchService
from services.stats import StatsService
from services.tracking import TrackingService
from adapters.storage import SqliteStorage  # facade greenfield (PR2-E2-S9)


def create_application(settings: Settings) -> Application:
    """Create and configure the Telegram application instance."""

    extractor_registry.replace_all([])
    registered_extractors = register_default_extractors(extractor_registry, settings=settings)
    stats_provider_registry.replace_all([])
    register_default_stats_providers(stats_provider_registry)
    # PR2-E2-S9: storage greenfield vía facade (compone los adapters por agregado).
    # Los defaults de threshold/notify ahora viven en el esquema (columnas DEFAULT)
    # y se pasan explícitos al crear suscripciones, así que el facade no los recibe.
    tracking_repository = SqliteStorage()
    # seed_if_empty() se omite en greenfield (sembraba el esquema viejo `active_events`/
    # `tracked_competitions`). El seed del registro canónico contra el esquema nuevo
    # queda como follow-up si se decide precargar ligas.

    tracking_service = TrackingService(
        extractor_registry=extractor_registry,
        repository=tracking_repository,
        max_parallel_refreshes=settings.tracking_max_parallel_refreshes,
        remove_missing_after_cycles=settings.tracking_remove_missing_after_cycles,
        odds_change_confirmation_refreshes=settings.odds_change_confirmation_refreshes,
        odds_flap_window_minutes=settings.odds_flap_window_minutes,
        odds_flap_epsilon=settings.odds_flap_epsilon,
        live_refresh_seconds=settings.tracking_live_refresh_seconds,
        odds_fast_path_percent=settings.odds_fast_path_percent,
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

        await start_orchestrated_scheduler(application, settings)

    async def post_shutdown(application: Application) -> None:
        """Stop background monitoring when the bot shuts down."""

        await stop_orchestrated_scheduler(application)
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
