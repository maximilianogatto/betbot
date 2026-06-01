"""Runtime settings for the MrPunter (FSB) prematch+live HTTP extractor.

MrPunter runs the FSB sportsbook (host ``prod20296-144090624.fssb.io``). The
``/api/eventlist`` endpoints need two JWTs (authorization + session) that are
embedded in the ``/es/spbk/`` HTML — fetchable with plain HTTP, no browser.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_API_HOST = "prod20296-144090624.fssb.io"
DEFAULT_SITE_ORIGIN = "https://mrpunter.com"
# Broad market-type set so events return result + totals (+ handicap when offered).
DEFAULT_MARKET_TYPE_IDS = (
    "ML0,ML39,ML169,ML1633,ML1,ML167,OU200,OU201,OU249,OU39,OU6001,OU1697,OU1633,QA158,QA1693"
)


@dataclass(frozen=True)
class MrPunterHttpSettings:
    """Configuration for MrPunter/FSB polling."""

    api_host: str = DEFAULT_API_HOST
    site_origin: str = DEFAULT_SITE_ORIGIN
    language_path: str = "es"  # path segment used for /<lang>/spbk/
    region_code: str = "AR"
    sport_id: str = "1"  # Football (234 = V-Football / virtual)
    market_type_ids: str = DEFAULT_MARKET_TYPE_IDS
    timeout_seconds: float = 25.0
    max_attempts: int = 2
    retry_backoff_seconds: float = 0.75
    league_fetch_concurrency: int = 5
    token_ttl_seconds: float = 600.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive.")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative.")
        if self.league_fetch_concurrency <= 0:
            raise ValueError("league_fetch_concurrency must be positive.")

    @property
    def api_base(self) -> str:
        return f"https://{self.api_host}/api/eventlist/eu"

    @property
    def spbk_url(self) -> str:
        return f"https://{self.api_host}/{self.language_path}/spbk/"


def load_mrpunter_settings() -> MrPunterHttpSettings:
    """Build settings from environment variables (with captured defaults)."""

    return MrPunterHttpSettings(
        api_host=(os.getenv("MRPUNTER_API_HOST") or DEFAULT_API_HOST).strip(),
        site_origin=(os.getenv("MRPUNTER_SITE_ORIGIN") or DEFAULT_SITE_ORIGIN).strip().rstrip("/"),
        region_code=(os.getenv("MRPUNTER_REGION_CODE") or "AR").strip(),
        sport_id=(os.getenv("MRPUNTER_SPORT_ID") or "1").strip(),
    )


def mrpunter_is_configured() -> bool:
    """Return True when an api host is available (env override or built-in default)."""

    return bool((os.getenv("MRPUNTER_API_HOST") or DEFAULT_API_HOST).strip())
