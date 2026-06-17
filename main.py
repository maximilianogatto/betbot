"""Application entry point for the Telegram bot project.

This module is intentionally small: it loads environment-based configuration,
configures console logging, creates the Telegram application, and finally
starts polling.

In the overall architecture, this file is the bridge between local execution
(`python main.py`) and the modular bot package stored under `bot/`. It does
not implement bot commands directly; instead, it delegates that work to
`bot.application.create_application()`.
"""

import logging
import sys

from bot.application import create_application
from bot.config import load_settings


def configure_logging(log_level: str) -> None:
    """Configure console logging for the whole application.

    The project uses Python's standard logging module so that all modules can
    emit messages through a consistent format. This function is called once at
    startup, before the Telegram bot begins polling.

    Args:
        log_level (str): Logging verbosity read from the environment, for
            example `"INFO"` or `"DEBUG"`.

    Returns:
        None: This function mutates the global logging configuration only.

    Side Effects:
        Configures the root logging system for the current Python process.

    Notes:
        A single central logging setup keeps messages from handlers, storage,
        and monitoring code aligned in the console.
    """

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )

    # Silence chatty third-party loggers: httpx/httpcore log one INFO line PER
    # request, which floods journald/disk on a small VPS (this already filled the
    # disk once). App loggers keep the configured level.
    for noisy in ("httpx", "httpcore", "telegram", "telegram.ext", "hpack", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main() -> None:
    """Start the Telegram bot application.

    This function coordinates the complete startup flow:

    1. Load environment variables through `load_settings()`.
    2. Configure logging for every module in the project.
    3. Build the Telegram application through `create_application()`.
    4. Start polling Telegram for incoming updates.

    Returns:
        None: The function starts the long-running polling process.

    Side Effects:
        Reads local configuration from `.env`, initializes the bot runtime,
        and begins network communication with Telegram through polling.

    Raises:
        SystemExit: Exits the program with status code 1 if configuration
            loading fails.

    Notes:
        The actual command logic lives in the handlers registered inside
        `bot.application`. This function exists to keep bootstrapping concerns
        separated from bot behavior.
    """

    try:
        settings = load_settings()
    except (FileNotFoundError, ValueError) as error:
        # Fail fast during startup if configuration is missing or invalid.
        # This is safer than letting the bot run with partial settings.
        print(error)
        sys.exit(1)

    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    logger.info("Iniciando bot de Telegram...")

    # Application creation wires together handlers, error handling, and any
    # shared services stored in `bot_data`.
    application = create_application(settings)

    logger.info("Bot listo. Esperando mensajes por polling.")
    # Polling keeps asking Telegram for new updates inside the event loop.
    # This is the main long-running operation of the bot process.
    application.run_polling()


if __name__ == "__main__":
    main()
