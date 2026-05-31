"""Runtime settings for the Mystake prematch HTTP extractor.

The real REST host (e.g. ``https://analytics-sp.<region>.com``) is intentionally
not committed: capture it once from mystake.bet DevTools (Network -> getprematch)
and provide it via ``MYSTAKE_API_BASE_URL``. The extractor only registers when
that variable is set, so production is unaffected until it is configured.
"""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class MystakeHttpSettings:
    """Configuration for Mystake prematch polling."""

    base_url: str = ""
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


def load_mystake_settings() -> MystakeHttpSettings:
    """Build settings from environment variables."""

    return MystakeHttpSettings(
        base_url=(os.getenv("MYSTAKE_API_BASE_URL") or "").strip().rstrip("/"),
        region=(os.getenv("MYSTAKE_REGION") or "as").strip(),
        sport_id=int(os.getenv("MYSTAKE_SPORT_ID", "1")),
        language=int(os.getenv("MYSTAKE_LANGUAGE", "28")),
    )


def mystake_is_configured() -> bool:
    """Return True when a real REST host is configured."""

    return bool((os.getenv("MYSTAKE_API_BASE_URL") or "").strip())
