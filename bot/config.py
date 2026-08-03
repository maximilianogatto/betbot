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
    tracking_live_refresh_seconds: int = 20
    tracking_max_parallel_refreshes: int = 3
    extractor_browser_enabled: bool = True
    # Plataformas apagadas a mano (BOT_DISABLED_PLATFORMS). Es una blocklist y
    # no una allowlist a propósito: un extractor nuevo entra habilitado en vez
    # de quedar apagado en silencio por olvidarse de listarlo.
    disabled_platforms: tuple[str, ...] = ()
    extractor_max_parallel_competitions: int = 1
    extractor_max_parallel_pages: int = 3
    extractor_max_parallel_event_pages: int = 1
    extractor_page_reuse_enabled: bool = False
    extractor_browser_restart_after_n_refreshes: int | None = None
    extractor_browser_restart_idle_ttl_seconds: int | None = None
    extractor_page_load_timeout_ms: int = 60_000
    extractor_post_load_wait_ms: int = 4_000
    extractor_headless: bool = True
    extractor_capture_wait_timeout_ms: int = 25_000
    extractor_capture_stable_ms: int = 1_500
    extractor_capture_attempts: int = 2
    extractor_event_capture_wait_timeout_ms: int = 20_000
    extractor_event_capture_stable_ms: int = 1_200
    extractor_event_capture_attempts: int = 1
    extractor_save_debug_payloads: bool = False
    extractor_debug_payload_dir: str | None = None
    extractor_extract_alternative_markets: bool = False
    bet365_allow_legacy_fallback: bool = False
    tracking_default_change_threshold_percent: float = 20.0
    tracking_default_notify_odds_changes: bool = True
    tracking_remove_missing_after_cycles: int = 3
    odds_change_confirmation_refreshes: int = 2
    odds_flap_window_minutes: int = 10
    odds_flap_epsilon: float = 0.01
    odds_fast_path_percent: float = 40.0
    enable_monitoring: bool = True
    monitor_interval_seconds: int = 60
    monitor_log_to_file: bool = False
    monitor_chromium_ram_alert_mb: float = 800.0
    stats_prefetch_enabled: bool = True
    # The Sportradar token pre-refresh opens a browser (Chrome). On a tiny VM
    # where Chrome is heavy/blocked, set STATS_SESSION_REFRESH_ENABLED=false so the
    # token is minted only on-demand (a real /stats call) instead of in a loop.
    stats_session_refresh_enabled: bool = True
    stats_prefetch_interval_seconds: int = 86400
    stats_prefetch_ttl_seconds: float = 90000.0
    live_watch_enabled: bool = True
    live_watch_interval_seconds: int = 15
    live_watch_sheet_url: str = (
        "https://docs.google.com/spreadsheets/d/17QRnS_BmmAz_7F4hvpUytPoD66U65W2f1pgF6q9y7fY/export?format=csv&gid=0"
    )
    live_watch_sheet_chat_id: int | None = None
    live_watch_sheet_interval_seconds: int = 900
    peak_digest_enabled: bool = True
    peak_digest_hour_arg: int = 8


def load_settings() -> Settings:
    """Load runtime settings from the local `.env` file."""

    if not load_dotenv(PATH_TO_ENV):
        raise FileNotFoundError(
            f"No se pudo cargar el archivo .env desde la ruta: {PATH_TO_ENV}"
        )

    # Optional egress proxy (e.g. a userspace WireGuard via `wireproxy` -> VPN) so
    # books that block the datacenter IP become reachable.
    #   - LEGACY (BOT_PROXY_PLATFORMS empty): export ALL_PROXY so EVERY client uses
    #     the proxy (old all-or-nothing behaviour).
    #   - SELECTIVE (BOT_PROXY_PLATFORMS set): do NOT export ALL_PROXY; only the
    #     listed platforms egress through it (see core.net.proxy_for_platform).
    #     Needed because geo-locked AR books (Betsson/BetWarrior) break through a
    #     foreign VPN exit, while MrPunter/Solcasino need it.
    bot_proxy_url = (os.getenv("BOT_PROXY_URL") or "").strip()
    proxy_platforms = (os.getenv("BOT_PROXY_PLATFORMS") or "").strip()
    if bot_proxy_url and not proxy_platforms:
        for _var in ("ALL_PROXY", "all_proxy"):
            os.environ[_var] = bot_proxy_url

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
    tracking_live_refresh_seconds = _parse_positive_int(
        os.getenv("TRACKING_LIVE_REFRESH_SECONDS", "20"),
        variable_name="TRACKING_LIVE_REFRESH_SECONDS",
    )
    tracking_max_parallel_refreshes = _parse_positive_int(
        _first_env_value(
            "TRACKING_MAX_PARALLEL_REFRESHES",
            default="3",
        ),
        variable_name="TRACKING_MAX_PARALLEL_REFRESHES",
    )
    extractor_browser_enabled = _parse_bool(os.getenv("EXTRACTOR_BROWSER_ENABLED", "true"))
    # Se acepta con y sin el sufijo "_http" para que valga escribir "bz" o "bz_http".
    disabled_platforms = tuple(
        name.strip().lower()
        for name in (os.getenv("BOT_DISABLED_PLATFORMS") or "").split(",")
        if name.strip()
    )
    extractor_max_parallel_competitions = _parse_positive_int(
        _first_env_value(
            "EXTRACTOR_MAX_PARALLEL_COMPETITIONS",
            default="1",
        ),
        variable_name="EXTRACTOR_MAX_PARALLEL_COMPETITIONS",
    )
    extractor_max_parallel_pages = _parse_positive_int(
        _first_env_value(
            "EXTRACTOR_MAX_PARALLEL_PAGES",
            "BET365_MAX_PARALLEL_PAGES",
            default="3",
        ),
        variable_name="EXTRACTOR_MAX_PARALLEL_PAGES",
    )
    extractor_max_parallel_event_pages = _parse_positive_int(
        _first_env_value(
            "EXTRACTOR_MAX_PARALLEL_EVENT_PAGES",
            default="1",
        ),
        variable_name="EXTRACTOR_MAX_PARALLEL_EVENT_PAGES",
    )
    extractor_page_reuse_enabled = _parse_bool(
        os.getenv("EXTRACTOR_PAGE_REUSE_ENABLED", "false")
    )
    extractor_browser_restart_after_n_refreshes = _parse_optional_positive_int(
        os.getenv("EXTRACTOR_BROWSER_RESTART_AFTER_N_REFRESHES"),
        variable_name="EXTRACTOR_BROWSER_RESTART_AFTER_N_REFRESHES",
    )
    extractor_browser_restart_idle_ttl_seconds = _parse_optional_positive_int(
        os.getenv("EXTRACTOR_BROWSER_RESTART_IDLE_TTL_SECONDS"),
        variable_name="EXTRACTOR_BROWSER_RESTART_IDLE_TTL_SECONDS",
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
    extractor_headless = _parse_bool(os.getenv("EXTRACTOR_HEADLESS", "true"))
    extractor_capture_wait_timeout_ms = _parse_positive_int(
        os.getenv("EXTRACTOR_CAPTURE_WAIT_TIMEOUT_MS", "25000"),
        variable_name="EXTRACTOR_CAPTURE_WAIT_TIMEOUT_MS",
    )
    extractor_capture_stable_ms = _parse_positive_int(
        os.getenv("EXTRACTOR_CAPTURE_STABLE_MS", "1500"),
        variable_name="EXTRACTOR_CAPTURE_STABLE_MS",
    )
    extractor_capture_attempts = _parse_positive_int(
        os.getenv("EXTRACTOR_CAPTURE_ATTEMPTS", "2"),
        variable_name="EXTRACTOR_CAPTURE_ATTEMPTS",
    )
    extractor_event_capture_wait_timeout_ms = _parse_positive_int(
        os.getenv("EXTRACTOR_EVENT_CAPTURE_WAIT_TIMEOUT_MS", "20000"),
        variable_name="EXTRACTOR_EVENT_CAPTURE_WAIT_TIMEOUT_MS",
    )
    extractor_event_capture_stable_ms = _parse_positive_int(
        os.getenv("EXTRACTOR_EVENT_CAPTURE_STABLE_MS", "1200"),
        variable_name="EXTRACTOR_EVENT_CAPTURE_STABLE_MS",
    )
    extractor_event_capture_attempts = _parse_positive_int(
        os.getenv("EXTRACTOR_EVENT_CAPTURE_ATTEMPTS", "1"),
        variable_name="EXTRACTOR_EVENT_CAPTURE_ATTEMPTS",
    )
    extractor_save_debug_payloads = _parse_bool(
        os.getenv("EXTRACTOR_SAVE_DEBUG_PAYLOADS", "false")
    )
    extractor_debug_payload_dir = _normalize_optional_text(
        os.getenv("EXTRACTOR_DEBUG_PAYLOAD_DIR")
    )
    extractor_extract_alternative_markets = _parse_bool(
        os.getenv("EXTRACTOR_EXTRACT_ALTERNATIVE_MARKETS", "false")
    )
    bet365_allow_legacy_fallback = _parse_bool(
        os.getenv("BET365_ALLOW_LEGACY_FALLBACK", "false")
    )
    tracking_default_change_threshold_percent = _parse_positive_float(
        os.getenv("TRACKING_DEFAULT_CHANGE_THRESHOLD_PERCENT", "20.0"),
        variable_name="TRACKING_DEFAULT_CHANGE_THRESHOLD_PERCENT",
    )
    tracking_default_notify_odds_changes = _parse_bool(
        os.getenv("TRACKING_DEFAULT_NOTIFY_ODDS_CHANGES", "true")
    )
    tracking_remove_missing_after_cycles = _parse_positive_int(
        os.getenv("TRACKING_REMOVE_MISSING_AFTER_CYCLES", "3"),
        variable_name="TRACKING_REMOVE_MISSING_AFTER_CYCLES",
    )
    odds_change_confirmation_refreshes = _parse_positive_int(
        os.getenv("ODDS_CHANGE_CONFIRMATION_REFRESHES", "2"),
        variable_name="ODDS_CHANGE_CONFIRMATION_REFRESHES",
    )
    odds_flap_window_minutes = _parse_positive_int(
        os.getenv("ODDS_FLAP_WINDOW_MINUTES", "10"),
        variable_name="ODDS_FLAP_WINDOW_MINUTES",
    )
    odds_flap_epsilon = _parse_positive_float(
        os.getenv("ODDS_FLAP_EPSILON", "0.01"),
        variable_name="ODDS_FLAP_EPSILON",
    )
    odds_fast_path_percent = _parse_positive_float(
        os.getenv("ODDS_FAST_PATH_PERCENT", "40.0"),
        variable_name="ODDS_FAST_PATH_PERCENT",
    )
    enable_monitoring = _parse_bool(os.getenv("ENABLE_MONITORING", "true"))
    monitor_interval_seconds = _parse_positive_int(
        os.getenv("MONITOR_INTERVAL_SECONDS", "60"),
        variable_name="MONITOR_INTERVAL_SECONDS",
    )
    monitor_log_to_file = _parse_bool(os.getenv("MONITOR_LOG_TO_FILE", "false"))
    monitor_chromium_ram_alert_mb = _parse_positive_float(
        os.getenv("MONITOR_CHROMIUM_RAM_ALERT_MB", "800"),
        variable_name="MONITOR_CHROMIUM_RAM_ALERT_MB",
    )
    stats_prefetch_enabled = _parse_bool(os.getenv("STATS_PREFETCH_ENABLED", "true"))
    stats_session_refresh_enabled = _parse_bool(
        os.getenv("STATS_SESSION_REFRESH_ENABLED", "true")
    )
    stats_prefetch_interval_seconds = _parse_positive_int(
        os.getenv("STATS_PREFETCH_INTERVAL_SECONDS", "86400"),
        variable_name="STATS_PREFETCH_INTERVAL_SECONDS",
    )
    stats_prefetch_ttl_seconds = _parse_positive_float(
        os.getenv("STATS_PREFETCH_TTL_SECONDS", "90000"),
        variable_name="STATS_PREFETCH_TTL_SECONDS",
    )
    live_watch_enabled = _parse_bool(os.getenv("LIVE_WATCH_ENABLED", "true"))
    live_watch_interval_seconds = _parse_positive_int(
        os.getenv("LIVE_WATCH_INTERVAL_SECONDS", "15"),
        variable_name="LIVE_WATCH_INTERVAL_SECONDS",
    )
    _default_sheet_url = (
        "https://docs.google.com/spreadsheets/d/17QRnS_BmmAz_7F4hvpUytPoD66U65W2f1pgF6q9y7fY/export?format=csv&gid=0"
    )
    live_watch_sheet_url = (os.getenv("LIVE_WATCH_SHEET_URL") or _default_sheet_url).strip()
    _sheet_chat_raw = (os.getenv("LIVE_WATCH_SHEET_CHAT_ID") or "").strip()
    try:
        live_watch_sheet_chat_id = int(_sheet_chat_raw) if _sheet_chat_raw else None
    except ValueError:
        live_watch_sheet_chat_id = None
    live_watch_sheet_interval_seconds = _parse_positive_int(
        os.getenv("LIVE_WATCH_SHEET_INTERVAL_SECONDS", "900"),
        variable_name="LIVE_WATCH_SHEET_INTERVAL_SECONDS",
    )
    peak_digest_enabled = _parse_bool(os.getenv("PEAK_DIGEST_ENABLED", "true"))
    peak_digest_hour_arg = _parse_positive_int(
        os.getenv("PEAK_DIGEST_HOUR_ARG", "8"),
        variable_name="PEAK_DIGEST_HOUR_ARG",
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
        extractor_browser_enabled=extractor_browser_enabled,
        disabled_platforms=disabled_platforms,
        extractor_max_parallel_competitions=extractor_max_parallel_competitions,
        extractor_max_parallel_pages=extractor_max_parallel_pages,
        extractor_max_parallel_event_pages=extractor_max_parallel_event_pages,
        extractor_page_reuse_enabled=extractor_page_reuse_enabled,
        extractor_browser_restart_after_n_refreshes=extractor_browser_restart_after_n_refreshes,
        extractor_browser_restart_idle_ttl_seconds=extractor_browser_restart_idle_ttl_seconds,
        extractor_page_load_timeout_ms=extractor_page_load_timeout_ms,
        extractor_post_load_wait_ms=extractor_post_load_wait_ms,
        extractor_headless=extractor_headless,
        extractor_capture_wait_timeout_ms=extractor_capture_wait_timeout_ms,
        extractor_capture_stable_ms=extractor_capture_stable_ms,
        extractor_capture_attempts=extractor_capture_attempts,
        extractor_event_capture_wait_timeout_ms=extractor_event_capture_wait_timeout_ms,
        extractor_event_capture_stable_ms=extractor_event_capture_stable_ms,
        extractor_event_capture_attempts=extractor_event_capture_attempts,
        extractor_save_debug_payloads=extractor_save_debug_payloads,
        extractor_debug_payload_dir=extractor_debug_payload_dir,
        extractor_extract_alternative_markets=extractor_extract_alternative_markets,
        bet365_allow_legacy_fallback=bet365_allow_legacy_fallback,
        tracking_default_change_threshold_percent=tracking_default_change_threshold_percent,
        tracking_default_notify_odds_changes=tracking_default_notify_odds_changes,
        tracking_remove_missing_after_cycles=tracking_remove_missing_after_cycles,
        tracking_live_refresh_seconds=tracking_live_refresh_seconds,
        odds_change_confirmation_refreshes=odds_change_confirmation_refreshes,
        odds_flap_window_minutes=odds_flap_window_minutes,
        odds_flap_epsilon=odds_flap_epsilon,
        odds_fast_path_percent=odds_fast_path_percent,
        enable_monitoring=enable_monitoring,
        monitor_interval_seconds=monitor_interval_seconds,
        monitor_log_to_file=monitor_log_to_file,
        monitor_chromium_ram_alert_mb=monitor_chromium_ram_alert_mb,
        stats_prefetch_enabled=stats_prefetch_enabled,
        stats_session_refresh_enabled=stats_session_refresh_enabled,
        stats_prefetch_interval_seconds=stats_prefetch_interval_seconds,
        live_watch_enabled=live_watch_enabled,
        live_watch_interval_seconds=live_watch_interval_seconds,
        live_watch_sheet_url=live_watch_sheet_url,
        live_watch_sheet_chat_id=live_watch_sheet_chat_id,
        live_watch_sheet_interval_seconds=live_watch_sheet_interval_seconds,
        stats_prefetch_ttl_seconds=stats_prefetch_ttl_seconds,
        peak_digest_enabled=peak_digest_enabled,
        peak_digest_hour_arg=peak_digest_hour_arg,
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


def _parse_optional_positive_int(raw_value: str | None, variable_name: str) -> int | None:
    """Parse one optional positive integer environment variable."""

    if raw_value is None or not raw_value.strip():
        return None

    return _parse_positive_int(raw_value, variable_name)


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


def _normalize_optional_text(raw_value: str | None) -> str | None:
    normalized_value = (raw_value or "").strip()
    return normalized_value or None
