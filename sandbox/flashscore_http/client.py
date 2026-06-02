"""HTTP-only Flashscore (Livesport) feed client.

Flashscore exposes a proprietary feed at ``https://global.flashscore.ninja/<project>/x/feed/<code>``
reachable with **plain httpx** as long as the static header ``x-fsign: SW9D1eZo``
is sent — no browser, no Cloudflare challenge, no token bootstrap, no curl_cffi.

Project id 204 = flashscore.com.ar (Argentina). Responses are a custom text
format: records separated by ``~``, fields by ``¬``, ``KEY÷value`` pairs.
"""

from __future__ import annotations

from dataclasses import dataclass
import httpx

DEFAULT_HOST = "global.flashscore.ninja"
DEFAULT_PROJECT = "204"
FSIGN = "SW9D1eZo"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class FlashscoreSettings:
    host: str = DEFAULT_HOST
    project: str = DEFAULT_PROJECT
    language: str = "es-ar"
    timezone_offset: int = -3  # Argentina
    sport_id: int = 1  # Soccer
    timeout_seconds: float = 20.0


class FlashscoreClient:
    """Fetch raw Flashscore feeds over plain HTTP."""

    def __init__(self, settings: FlashscoreSettings | None = None) -> None:
        self.settings = settings or FlashscoreSettings()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "x-fsign": FSIGN,
            "accept": "*/*",
            "accept-language": f"{self.settings.language},es;q=0.9",
            "referer": "https://www.flashscore.com.ar/",
            "user-agent": _UA,
        }

    def fetch_feed(self, code: str) -> str:
        """Return the raw text body of one feed code (e.g. ``f_1_0_-3_es-ar_1``)."""

        url = f"https://{self.settings.host}/{self.settings.project}/x/feed/{code}"
        with httpx.Client(timeout=self.settings.timeout_seconds, headers=self._headers) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text

    # ----- typed feed shortcuts -----

    def fetch_day_fixtures(self, *, day_offset: int = 0) -> str:
        """Day's matches grouped by league (day_offset 0=today, 1=tomorrow, -1=yesterday)."""

        s = self.settings
        return self.fetch_feed(f"f_{s.sport_id}_{day_offset}_{s.timezone_offset}_{s.language}_1")

    def fetch_match_summary(self, event_id: str) -> str:
        """Match incidents/timeline (goals, cards, subs)."""

        return self.fetch_feed(f"df_sui_{self.settings.sport_id}_{event_id}")

    def fetch_match_statistics(self, event_id: str) -> str:
        """Match statistics (possession, shots, xG, corners, cards...)."""

        return self.fetch_feed(f"df_st_{self.settings.sport_id}_{event_id}")

    def fetch_match_h2h(self, event_id: str) -> str:
        """Head-to-head and recent form for both teams."""

        return self.fetch_feed(f"df_hh_{self.settings.sport_id}_{event_id}")

    def fetch_match_meta(self, event_id: str) -> str:
        """Compact match meta (status, timestamps, current score)."""

        return self.fetch_feed(f"dc_{self.settings.sport_id}_{event_id}")
