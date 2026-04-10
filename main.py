import logging
import sys

from bot.application import create_application
from bot.config import load_settings


def configure_logging(log_level: str) -> None:
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )


def main() -> None:
    try:
        settings = load_settings()
    except ValueError as error:
        print(error)
        sys.exit(1)

    print(f"Settings loaded successfully: {settings}")
    
    configure_logging(settings.log_level)
    logger = logging.getLogger(__name__)

    logger.info("Starting Telegram bot...")

    application = create_application(settings)

    logger.info("Bot is ready. Waiting for messages via polling.")
    application.run_polling()


if __name__ == "__main__":
    main()
