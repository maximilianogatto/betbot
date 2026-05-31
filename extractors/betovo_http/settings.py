"""Runtime settings for the Betovo (Altenar) prematch HTTP extractor.

Betovo runs the Altenar sportsbook. Its JSON API is the shared Altenar frontend
host (``sb2frontend-altenar2.biahosted.com``) scoped to the operator via the
``integration=betovo`` query parameter — reachable over plain HTTP, no token.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_FRONTEND_HOST = "sb2frontend-altenar2.biahosted.com"
DEFAULT_INTEGRATION = "betovo"
DEFAULT_SITE_ORIGIN = "https://www.betovo848425.com"


@dataclass(frozen=True)
class BetovoHttpSettings:
    """Configuration for Betovo/Altenar prematch polling."""

    frontend_host: str = DEFAULT_FRONTEND_HOST
    integration: str = DEFAULT_INTEGRATION
    site_origin: str = DEFAULT_SITE_ORIGIN
    culture: str = "en-GB"
    country_code: str = "AR"
    timezone_offset: int = 180
    sport_id: int = 66  # Soccer (Altenar internal sport id for this integration)
    timeout_seconds: float = 25.0
    max_attempts: int = 2
    retry_backoff_seconds: float = 0.75
    detail_fetch_concurrency: int = 5

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive.")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative.")
        if self.detail_fetch_concurrency <= 0:
            raise ValueError("detail_fetch_concurrency must be positive.")

    @property
    def api_base(self) -> str:
        return f"https://{self.frontend_host}/api"

    @property
    def common_params(self) -> dict[str, str]:
        return {
            "culture": self.culture,
            "timezoneOffset": str(self.timezone_offset),
            "integration": self.integration,
            "deviceType": "2",
            "numFormat": self.culture,
            "countryCode": self.country_code,
        }


def load_betovo_settings() -> BetovoHttpSettings:
    """Build settings from environment variables (with captured defaults)."""

    return BetovoHttpSettings(
        frontend_host=(os.getenv("BETOVO_FRONTEND_HOST") or DEFAULT_FRONTEND_HOST).strip(),
        integration=(os.getenv("BETOVO_INTEGRATION") or DEFAULT_INTEGRATION).strip(),
        site_origin=(os.getenv("BETOVO_SITE_ORIGIN") or DEFAULT_SITE_ORIGIN).strip().rstrip("/"),
        culture=(os.getenv("BETOVO_CULTURE") or "en-GB").strip(),
        country_code=(os.getenv("BETOVO_COUNTRY_CODE") or "AR").strip(),
        sport_id=int(os.getenv("BETOVO_SPORT_ID", "66")),
    )


def betovo_is_configured() -> bool:
    """Return True when a frontend host + integration are available."""

    host = (os.getenv("BETOVO_FRONTEND_HOST") or DEFAULT_FRONTEND_HOST).strip()
    integration = (os.getenv("BETOVO_INTEGRATION") or DEFAULT_INTEGRATION).strip()
    return bool(host and integration)
