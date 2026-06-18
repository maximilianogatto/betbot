"""Runtime settings for the Betsson (cba.betsson.bet.ar) prematch HTTP extractor.

Betsson Argentina (Córdoba) runs the **OBG / Betsson Group** sportsbook. Its
catalogue (sport -> region -> competition -> events) and odds come from a public
JSON API under ``https://cba.betsson.bet.ar/api/sb/v1/...`` over plain HTTP.

The API requires a small set of *static* brand headers — there is no per-session
bootstrap: ``brandid`` and ``marketcode`` are constants captured from the page, and
``sessiontoken`` is a hard-coded anonymous JWT (userId = all 1s, no expiry). Every
value here can be overridden via environment variables.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_SITE_ORIGIN = "https://cba.betsson.bet.ar"
DEFAULT_BRAND_ID = "46df28af-e0f4-48d6-a3b3-3183b2586c44"
DEFAULT_MARKET_CODE = "ag"  # Argentina (Córdoba)
# Anonymous, non-expiring session JWT minted client-side by the SPA.
DEFAULT_SESSION_TOKEN = (
    "ew0KICAiYWxnIjogIkhTMjU2IiwNCiAgInR5cCI6ICJKV1QiDQp9."
    "ew0KICAianVyaXNkaWN0aW9uIjogIlVua25vd24iLA0KICAidXNlcklkIjogIjExMTExMTExLTExMTEt"
    "MTExMS0xMTExLTExMTExMTExMTExMSIsDQogICJsb2dpblNlc3Npb25JZCI6ICIxMTExMTExMS0xMTEx"
    "LTExMTEtMTExMS0xMTExMTExMTExMTEiDQp9.yuBO_qNKJHtbCWK3z04cEqU59EKU8pZb2kXHhZ7IeuI"
)
# Football (soccer) category id in the OBG taxonomy.
DEFAULT_CATEGORY_ID = "1"


@dataclass(frozen=True)
class BetssonHttpSettings:
    """Configuration for Betsson/OBG prematch + live polling."""

    site_origin: str = DEFAULT_SITE_ORIGIN
    brand_id: str = DEFAULT_BRAND_ID
    market_code: str = DEFAULT_MARKET_CODE
    session_token: str = DEFAULT_SESSION_TOKEN
    category_id: str = DEFAULT_CATEGORY_ID
    language_code: str = "ag"
    currency_code: str = "ARS"
    country_code: str = "AR"
    jurisdiction: str = "Lpcse"
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
        return f"{self.site_origin}/api/sb/v1"

    @property
    def headers(self) -> dict[str, str]:
        """The static brand header set the OBG API validates."""

        return {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "brandid": self.brand_id,
            "marketcode": self.market_code,
            "sessiontoken": self.session_token,
            "x-obg-channel": "Web",
            "x-obg-device": "Mobile",
            "x-sb-channel": "Mobile",
            "x-sb-device-type": "Mobile",
            "x-sb-type": "b2b",
            "x-sb-jurisdiction": self.jurisdiction,
            "x-sb-content-id": self.brand_id,
            "x-sb-currency-code": self.currency_code,
            "x-sb-language-code": self.language_code,
            "x-sb-country-code": self.country_code,
            "origin": self.site_origin,
            "referer": f"{self.site_origin}/apuestas-deportivas",
            "user-agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Chrome/124"
            ),
        }


def load_betsson_settings() -> BetssonHttpSettings:
    """Build settings from environment variables (with captured defaults)."""

    return BetssonHttpSettings(
        site_origin=(os.getenv("BETSSON_SITE_ORIGIN") or DEFAULT_SITE_ORIGIN).strip().rstrip("/"),
        brand_id=(os.getenv("BETSSON_BRAND_ID") or DEFAULT_BRAND_ID).strip(),
        market_code=(os.getenv("BETSSON_MARKET_CODE") or DEFAULT_MARKET_CODE).strip(),
        session_token=(os.getenv("BETSSON_SESSION_TOKEN") or DEFAULT_SESSION_TOKEN).strip(),
    )


def betsson_is_configured() -> bool:
    """Return True when a brand id + market code are available (env or default)."""

    brand = (os.getenv("BETSSON_BRAND_ID") or DEFAULT_BRAND_ID).strip()
    market = (os.getenv("BETSSON_MARKET_CODE") or DEFAULT_MARKET_CODE).strip()
    return bool(brand and market)
