"""Runtime settings for the Solcasino (Betby/sptpub) prematch HTTP extractor.

Solcasino runs the Betby sportsbook; odds come from the sptpub snapshot feed
(``https://<api_host>/api/v4/prematch/brand/<brand_id>/<lang>/<version>``).
The brand id + api host were captured from solcasino.io's BTRenderer config and
can be overridden via env vars if Solcasino rotates them.

Note: Solcasino, Rainbet and other clones share the Betby ``c7818b61`` operator
cluster; the brand_id selects Solcasino's own catalog (which often carries more
matches than the sibling clones).
"""

from __future__ import annotations

from dataclasses import dataclass
import os

# Captured from solcasino.io: brand_id from BTRenderer().initialize({...}); api_host
# from its renderer (solcasino.sptpub.com/bt-renderer.min.js -> api-g-c7818b61-607).
DEFAULT_API_HOST = "api-g-c7818b61-607.sptpub.com"
DEFAULT_BRAND_ID = "2392759269461204992"
DEFAULT_SITE_ORIGIN = "https://solcasino.io"


@dataclass(frozen=True)
class SolcasinoHttpSettings:
    """Configuration for Solcasino/Betby prematch polling."""

    api_host: str = DEFAULT_API_HOST
    brand_id: str = DEFAULT_BRAND_ID
    site_origin: str = DEFAULT_SITE_ORIGIN
    language: str = "en"
    feed: str = "prematch"
    sport_id: str = "1"  # Soccer
    timeout_seconds: float = 30.0
    max_attempts: int = 2
    retry_backoff_seconds: float = 0.75

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive.")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative.")

    def feed_url(self, version: int | str = 0) -> str:
        return (
            f"https://{self.api_host}/api/v4/{self.feed}/brand/"
            f"{self.brand_id}/{self.language}/{version}"
        )


def load_solcasino_settings() -> SolcasinoHttpSettings:
    """Build settings from environment variables (with captured defaults)."""

    return SolcasinoHttpSettings(
        api_host=(os.getenv("SOLCASINO_API_HOST") or DEFAULT_API_HOST).strip(),
        brand_id=(os.getenv("SOLCASINO_BRAND_ID") or DEFAULT_BRAND_ID).strip(),
        site_origin=(os.getenv("SOLCASINO_SITE_ORIGIN") or DEFAULT_SITE_ORIGIN).strip().rstrip("/"),
        language=(os.getenv("SOLCASINO_LANGUAGE") or "en").strip(),
        sport_id=(os.getenv("SOLCASINO_SPORT_ID") or "1").strip(),
    )


def solcasino_is_configured() -> bool:
    """Return True when a brand id + api host are available (env or default)."""

    host = (os.getenv("SOLCASINO_API_HOST") or DEFAULT_API_HOST).strip()
    brand = (os.getenv("SOLCASINO_BRAND_ID") or DEFAULT_BRAND_ID).strip()
    return bool(host and brand)
