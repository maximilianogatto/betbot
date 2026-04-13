"""Application factory for the Telegram bot runtime."""

from __future__ import annotations

from telegram.ext import Application, ApplicationBuilder

from bot.config import Settings
from bot.error_handler import handle_error
from bot.handlers import register_handlers
from bot.jobs import start_bet365_monitor, stop_bet365_monitor
from monitors.bet365_tracking import Bet365TrackingService
from services.bet365_extractor import Bet365BrowserExtractor, Bet365ExtractorSettings


def create_application(settings: Settings) -> Application:
    """Create and configure the Telegram application instance."""

    extractor = Bet365BrowserExtractor(
        Bet365ExtractorSettings(
            max_parallel_pages=settings.bet365_max_parallel_pages,
            page_load_timeout_ms=settings.bet365_page_load_timeout_ms,
            post_load_wait_ms=settings.bet365_post_load_wait_ms,
        )
    )
    tracking_service = Bet365TrackingService(
        extractor=extractor.extract_league,
        max_parallel_refreshes=settings.bet365_max_parallel_pages,
    )

    async def post_init(application: Application) -> None:
        """Start background monitoring after the bot runtime is ready."""

        await extractor.start()
        await start_bet365_monitor(
            application,
            interval_seconds=settings.bet365_refresh_interval_seconds,
        )

    async def post_shutdown(application: Application) -> None:
        """Stop background monitoring when the bot shuts down."""

        await stop_bet365_monitor(application)
        await extractor.stop()

    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.bot_data["bet365_extractor"] = extractor
    application.bot_data["bet365_tracking_service"] = tracking_service

    register_handlers(application)
    application.add_error_handler(handle_error)

    return application
