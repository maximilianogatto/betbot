"""Configuration helpers for environment-based application settings."""

from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv

PATH_TO_ENV = os.path.join(os.path.dirname(__file__), "..", ".env")


@dataclass
class Settings:
    """Container for runtime settings used by the Bet365 bot."""

    telegram_bot_token: str
    log_level: str = "INFO"
    bet365_refresh_interval_seconds: int = 120
    bet365_max_parallel_pages: int = 3
    bet365_page_load_timeout_ms: int = 60_000
    bet365_post_load_wait_ms: int = 4_000
    enable_monitoring: bool = False
    monitor_interval_seconds: int = 60
    monitor_log_to_file: bool = False
    monitor_chromium_ram_alert_mb: float = 800.0


def load_settings() -> Settings:
    """Load runtime settings from the local `.env` file."""

    if not load_dotenv(PATH_TO_ENV):
        raise FileNotFoundError(
            f"No se pudo cargar el archivo .env desde la ruta: {PATH_TO_ENV}"
        )

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    bet365_refresh_interval_seconds = _parse_positive_int(
        os.getenv(
            "BET365_REFRESH_INTERVAL_SECONDS",
            os.getenv("BET365_MONITOR_INTERVAL_SECONDS", "120"),
        ),
        variable_name="BET365_REFRESH_INTERVAL_SECONDS",
    )
    bet365_max_parallel_pages = _parse_positive_int(
        os.getenv("BET365_MAX_PARALLEL_PAGES", "3"),
        variable_name="BET365_MAX_PARALLEL_PAGES",
    )
    bet365_page_load_timeout_ms = _parse_positive_int(
        os.getenv("BET365_PAGE_LOAD_TIMEOUT_MS", "60000"),
        variable_name="BET365_PAGE_LOAD_TIMEOUT_MS",
    )
    bet365_post_load_wait_ms = _parse_positive_int(
        os.getenv("BET365_POST_LOAD_WAIT_MS", "4000"),
        variable_name="BET365_POST_LOAD_WAIT_MS",
    )
    enable_monitoring = _parse_bool(os.getenv("ENABLE_MONITORING", "false"))
    monitor_interval_seconds = _parse_positive_int(
        os.getenv("MONITOR_INTERVAL_SECONDS", "60"),
        variable_name="MONITOR_INTERVAL_SECONDS",
    )
    monitor_log_to_file = _parse_bool(os.getenv("MONITOR_LOG_TO_FILE", "false"))
    monitor_chromium_ram_alert_mb = _parse_positive_float(
        os.getenv("MONITOR_CHROMIUM_RAM_ALERT_MB", "800"),
        variable_name="MONITOR_CHROMIUM_RAM_ALERT_MB",
    )

    if not telegram_bot_token:
        raise ValueError(
            "Falta la variable TELEGRAM_BOT_TOKEN. Creá el archivo .env a partir de .env.example."
        )

    return Settings(
        telegram_bot_token=telegram_bot_token,
        log_level=log_level,
        bet365_refresh_interval_seconds=bet365_refresh_interval_seconds,
        bet365_max_parallel_pages=bet365_max_parallel_pages,
        bet365_page_load_timeout_ms=bet365_page_load_timeout_ms,
        bet365_post_load_wait_ms=bet365_post_load_wait_ms,
        enable_monitoring=enable_monitoring,
        monitor_interval_seconds=monitor_interval_seconds,
        monitor_log_to_file=monitor_log_to_file,
        monitor_chromium_ram_alert_mb=monitor_chromium_ram_alert_mb,
    )


def _parse_positive_int(raw_value: str, variable_name: str) -> int:
    """Parse a positive integer environment variable."""

    try:
        parsed_value = int(raw_value.strip())
    except ValueError as error:
        raise ValueError(f"{variable_name} debe ser un número entero positivo.") from error

    if parsed_value <= 0:
        raise ValueError(f"{variable_name} debe ser mayor que cero.")

    return parsed_value


def _parse_positive_float(raw_value: str, variable_name: str) -> float:
    """Parse a positive float environment variable."""

    try:
        parsed_value = float(raw_value.strip())
    except ValueError as error:
        raise ValueError(f"{variable_name} debe ser un número positivo.") from error

    if parsed_value <= 0:
        raise ValueError(f"{variable_name} debe ser mayor que cero.")

    return parsed_value


def _parse_bool(raw_value: str) -> bool:
    """Parse a flexible boolean environment variable."""

    normalized_value = raw_value.strip().lower()
    return normalized_value in {"1", "true", "yes", "on", "si", "sí"}
