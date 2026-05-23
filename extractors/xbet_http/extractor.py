"""Extractor adapter for 1xBet-compatible LineFeed HTTP endpoints."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from core.extractor_base import Extractor
from core.models import CompetitionExtraction, EventSnapshot
from extractors.xbet_http.settings import XBetHttpSettings


SUPPORTED_HOSTS = {
    "1xbetarge.com",
    "www.1xbetarge.com",
    "spinbetter.com",
    "www.spinbetter.com",
}


class XBetHttpExtractor(Extractor):
    """Expose 1xBet/SpinBetter prematch LineFeed data through the common interface."""

    name = "1xbet_http"
    display_name = "1xBet HTTP"
    supported_domains = tuple(sorted(SUPPORTED_HOSTS))
    supported_capabilities = ("ligas", "eventos 1X2", "handicap", "totales")

    def __init__(self, settings: XBetHttpSettings | None = None) -> None:
        self.settings = settings or XBetHttpSettings()

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        parsed = urlparse((url or "").strip())
        if parsed.netloc.lower() not in SUPPORTED_HOSTS:
            return False
        if not parsed.path.rstrip("/").endswith("/LineFeed/GetChampZip"):
            return False
        champ_id = _extract_champ_id(url)
        return champ_id is not None

    async def extract_league(self, url: str) -> CompetitionExtraction:
        raise NotImplementedError("1xBet HTTP league extraction is not implemented yet.")

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError("1xBet HTTP match extraction is not implemented yet.")


def _extract_champ_id(url: str) -> str | None:
    query = parse_qs(urlparse(url).query)
    raw_values = query.get("champ")
    if not raw_values:
        return None
    champ_id = str(raw_values[0]).strip()
    return champ_id or None
