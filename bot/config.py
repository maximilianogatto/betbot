"""Configuration helpers for environment-based application settings."""

from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv

PATH_TO_ENV = os.path.join(os.path.dirname(__file__), "..", ".env")


@dataclass
class Settings:
    """Container for runtime settings used by the tracking bot."""

    telegram_bot_token: str
    log_level: str = "INFO"
    tracking_refresh_interval_seconds: int = 120
    tracking_max_parallel_refreshes: int = 3
    extractor_max_parallel_pages: int = 3
    extractor_page_load_timeout_ms: int = 60_000
    extractor_post_load_wait_ms: int = 4_000
    tracking_default_change_threshold_percent: float = 20.0
    tracking_default_notify_odds_changes: bool = True
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
    tracking_refresh_interval_seconds = _parse_positive_int(
        _first_env_value(
            "TRACKING_REFRESH_INTERVAL_SECONDS",
            "BET365_REFRESH_INTERVAL_SECONDS",
            "BET365_MONITOR_INTERVAL_SECONDS",
            default="120",
        ),
        variable_name="TRACKING_REFRESH_INTERVAL_SECONDS",
    )
    tracking_max_parallel_refreshes = _parse_positive_int(
        _first_env_value(
            "TRACKING_MAX_PARALLEL_REFRESHES",
            "BET365_MAX_PARALLEL_PAGES",
            default="3",
        ),
        variable_name="TRACKING_MAX_PARALLEL_REFRESHES",
    )
    extractor_max_parallel_pages = _parse_positive_int(
        _first_env_value(
            "EXTRACTOR_MAX_PARALLEL_PAGES",
            "BET365_MAX_PARALLEL_PAGES",
            default="3",
        ),
        variable_name="EXTRACTOR_MAX_PARALLEL_PAGES",
    )
    extractor_page_load_timeout_ms = _parse_positive_int(
        _first_env_value(
            "EXTRACTOR_PAGE_LOAD_TIMEOUT_MS",
            "BET365_PAGE_LOAD_TIMEOUT_MS",
            default="60000",
        ),
        variable_name="EXTRACTOR_PAGE_LOAD_TIMEOUT_MS",
    )
    extractor_post_load_wait_ms = _parse_positive_int(
        _first_env_value(
            "EXTRACTOR_POST_LOAD_WAIT_MS",
            "BET365_POST_LOAD_WAIT_MS",
            default="4000",
        ),
        variable_name="EXTRACTOR_POST_LOAD_WAIT_MS",
    )
    tracking_default_change_threshold_percent = _parse_positive_float(
        os.getenv("TRACKING_DEFAULT_CHANGE_THRESHOLD_PERCENT", "20.0"),
        variable_name="TRACKING_DEFAULT_CHANGE_THRESHOLD_PERCENT",
    )
    tracking_default_notify_odds_changes = _parse_bool(
        os.getenv("TRACKING_DEFAULT_NOTIFY_ODDS_CHANGES", "true")
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
        tracking_refresh_interval_seconds=tracking_refresh_interval_seconds,
        tracking_max_parallel_refreshes=tracking_max_parallel_refreshes,
        extractor_max_parallel_pages=extractor_max_parallel_pages,
        extractor_page_load_timeout_ms=extractor_page_load_timeout_ms,
        extractor_post_load_wait_ms=extractor_post_load_wait_ms,
        tracking_default_change_threshold_percent=tracking_default_change_threshold_percent,
        tracking_default_notify_odds_changes=tracking_default_notify_odds_changes,
        enable_monitoring=enable_monitoring,
        monitor_interval_seconds=monitor_interval_seconds,
        monitor_log_to_file=monitor_log_to_file,
        monitor_chromium_ram_alert_mb=monitor_chromium_ram_alert_mb,
    )


def _first_env_value(*names: str, default: str) -> str:
    """Return the first non-empty environment variable among the provided names."""

    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value

    return default


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
