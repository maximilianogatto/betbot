"""Runtime settings for the BZ (m.bz.com) prematch HTTP extractor.

m.bz.com is a Sportradar-id sportsbook (matches/tournaments use ``sr:...`` ids).
Its JSON API is reachable over plain HTTP as long as the ``x-client-type`` and
``x-channel-type`` headers are present (no token/cookie needed).
"""

from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_BASE_URL = "https://m.bz.com"


@dataclass(frozen=True)
class BzHttpSettings:
    """Configuration for BZ prematch polling."""

    base_url: str = DEFAULT_BASE_URL
    client_type: str = "BZ-H5"
    channel_type: str = "0"
    language: str = "en-US"
    sport_id: str = "sr:sport:1"  # Soccer
    status_list: str = "0"  # 0 = Not started (prematch); 1 = live
    page_size: int = 200
    timeout_seconds: float = 25.0
    max_attempts: int = 2
    retry_backoff_seconds: float = 0.75
    odds_fetch_concurrency: int = 5

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive.")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative.")
        if self.odds_fetch_concurrency <= 0:
            raise ValueError("odds_fetch_concurrency must be positive.")

    @property
    def api_base(self) -> str:
        return f"{self.base_url.rstrip('/')}/api"


def load_bz_settings() -> BzHttpSettings:
    """Build settings from environment variables (with working defaults)."""

    return BzHttpSettings(
        base_url=(os.getenv("BZ_API_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/"),
        client_type=(os.getenv("BZ_CLIENT_TYPE") or "BZ-H5").strip(),
        channel_type=(os.getenv("BZ_CHANNEL_TYPE") or "0").strip(),
        language=(os.getenv("BZ_LANGUAGE") or "en-US").strip(),
        sport_id=(os.getenv("BZ_SPORT_ID") or "sr:sport:1").strip(),
    )


def bz_is_configured() -> bool:
    """Return True when a base URL is available (env override or built-in default)."""

    return bool((os.getenv("BZ_API_BASE_URL") or DEFAULT_BASE_URL).strip())
