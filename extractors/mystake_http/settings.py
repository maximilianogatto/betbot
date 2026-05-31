"""Runtime settings for the Mystake prematch HTTP extractor.

The REST host can rotate; override it with ``MYSTAKE_API_BASE_URL`` if needed.
A league is identified by its championship id (``ch``); games are discovered via
``getprematchtopgames`` and their odds fetched via ``getprematchgameall``.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_BASE_URL = "https://analytics-sp.googleserv.tech"


@dataclass(frozen=True)
class MystakeHttpSettings:
    """Configuration for Mystake prematch polling."""

    base_url: str = DEFAULT_BASE_URL
    api_path: str = "/api/prematch"
    region: str = "as"
    sport_id: int = 1
    language: int = 28
    timeout_seconds: float = 20.0
    max_attempts: int = 2
    retry_backoff_seconds: float = 0.75

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive.")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative.")

    @property
    def prematch_base(self) -> str:
        return f"{self.base_url.rstrip('/')}{self.api_path}"


def load_mystake_settings() -> MystakeHttpSettings:
    """Build settings from environment variables (with working defaults)."""

    base_url = (os.getenv("MYSTAKE_API_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    return MystakeHttpSettings(
        base_url=base_url,
        region=(os.getenv("MYSTAKE_REGION") or "as").strip(),
        sport_id=int(os.getenv("MYSTAKE_SPORT_ID", "1")),
        language=int(os.getenv("MYSTAKE_LANGUAGE", "28")),
    )


def mystake_is_configured() -> bool:
    """Return True when a REST host is available (env override or built-in default)."""

    return bool((os.getenv("MYSTAKE_API_BASE_URL") or DEFAULT_BASE_URL).strip())
