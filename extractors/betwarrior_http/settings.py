"""Runtime settings for the BetWarrior (Kambi) prematch HTTP extractor.

BetWarrior runs the Kambi sportsbook. Kambi exposes a public offering API
(``https://eu-offering-api.kambicdn.com/offering/v2018/<offering>/...``) reachable
over plain HTTP with no token; the offering id scopes it to the operator.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_API_HOST = "eu-offering-api.kambicdn.com"
DEFAULT_OFFERING = "bwargbac"  # BetWarrior Argentina (CABA)
DEFAULT_SITE_ORIGIN = "https://caba.betwarrior.bet.ar"


@dataclass(frozen=True)
class BetWarriorHttpSettings:
    """Configuration for BetWarrior/Kambi prematch polling."""

    api_host: str = DEFAULT_API_HOST
    offering: str = DEFAULT_OFFERING
    site_origin: str = DEFAULT_SITE_ORIGIN
    language: str = "es_AR"
    market: str = "AR"
    client_id: str = "2"
    channel_id: str = "1"
    sport_term: str = "football"  # Kambi sport termKey for soccer
    timeout_seconds: float = 25.0
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
    def api_base(self) -> str:
        return f"https://{self.api_host}/offering/v2018/{self.offering}"

    @property
    def common_params(self) -> dict[str, str]:
        return {
            "lang": self.language,
            "market": self.market,
            "client_id": self.client_id,
            "channel_id": self.channel_id,
        }


def load_betwarrior_settings() -> BetWarriorHttpSettings:
    """Build settings from environment variables (with captured defaults)."""

    return BetWarriorHttpSettings(
        api_host=(os.getenv("BETWARRIOR_API_HOST") or DEFAULT_API_HOST).strip(),
        offering=(os.getenv("BETWARRIOR_OFFERING") or DEFAULT_OFFERING).strip(),
        site_origin=(os.getenv("BETWARRIOR_SITE_ORIGIN") or DEFAULT_SITE_ORIGIN).strip().rstrip("/"),
        language=(os.getenv("BETWARRIOR_LANGUAGE") or "es_AR").strip(),
        market=(os.getenv("BETWARRIOR_MARKET") or "AR").strip(),
    )


def betwarrior_is_configured() -> bool:
    """Return True when an api host + offering are available (env or default)."""

    host = (os.getenv("BETWARRIOR_API_HOST") or DEFAULT_API_HOST).strip()
    offering = (os.getenv("BETWARRIOR_OFFERING") or DEFAULT_OFFERING).strip()
    return bool(host and offering)
