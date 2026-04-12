"""Application factory for the Telegram bot runtime.

This module builds the `python-telegram-bot` application object used by the
project. It is responsible for connecting configuration, shared services,
command handlers, and the global error handler.

Other modules typically do not instantiate `Application` directly. Instead,
`main.py` calls `create_application()`, which centralizes all startup wiring
in one place.
"""

from telegram.ext import Application, ApplicationBuilder

from bot.config import Settings
from bot.error_handler import handle_error
from bot.handlers import register_handlers
from monitors.tracker import TrackerService
from monitors.watchlist_builder import WeeklyWatchlistBuilder
from services.football_data_provider import create_football_data_provider


def create_application(settings: Settings) -> Application:
    """Create and configure the Telegram application instance.

    This function is the composition root of the bot layer. It creates the
    `Application` object from `python-telegram-bot`, stores shared services in
    `bot_data`, registers command handlers, and attaches the global error
    handler.

    Args:
        settings (Settings): Runtime configuration loaded from environment
            variables, including the Telegram bot token and watchlist options.

    Returns:
        Application: A fully configured Telegram application ready to be
            started with `run_polling()`.

    Side Effects:
        Instantiates shared services and stores them inside the application's
        in-memory state.

    Notes:
        `TrackerService` and `WeeklyWatchlistBuilder` are stored in
        `application.bot_data` so handlers can use domain logic without
        importing storage or provider details directly.
    """

    application = ApplicationBuilder().token(settings.telegram_bot_token).build()
    football_data_provider = create_football_data_provider(
        provider_name=settings.football_data_provider,
        api_key=settings.football_data_api_key,
    )

    # Shared services are attached once during startup and reused by handlers
    # across all updates handled by the bot.
    application.bot_data["tracker_service"] = TrackerService()
    application.bot_data["football_data_provider"] = football_data_provider
    application.bot_data["watchlist_builder"] = WeeklyWatchlistBuilder(
        provider=football_data_provider,
        days_ahead=settings.watchlist_days_ahead,
        imbalance_threshold=settings.watchlist_imbalance_threshold,
    )

    # Handlers are registered before polling starts so every incoming update
    # can be routed to the correct async function.
    register_handlers(application)
    application.add_error_handler(handle_error)

    return application
