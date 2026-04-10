from dataclasses import dataclass
import os

from dotenv import load_dotenv

PATH_TO_ENV = os.path.join(os.path.dirname(__file__), "..", ".env")

@dataclass
class Settings:
    telegram_bot_token: str
    log_level: str = "INFO"


def load_settings() -> Settings:
    # load_dotenv()
    if not load_dotenv(PATH_TO_ENV):
        raise FileNotFoundError(
            f"No se pudo cargar el archivo .env desde la ruta: {PATH_TO_ENV}"
        )

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    if not telegram_bot_token:
        raise ValueError(
            "Falta la variable TELEGRAM_BOT_TOKEN. Creá el archivo .env a partir de .env.example."
        )

    return Settings(
        telegram_bot_token=telegram_bot_token,
        log_level=log_level,
    )
