"""Extractor adapter for 1xBet-compatible LineFeed HTTP endpoints."""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

from core.extractor_base import Extractor
from core.extractor_base import LeagueDiscoveryOption
from core.models import CompetitionExtraction, EventSnapshot
from extractors.xbet_http.client import (
    XBetHttpClient,
    base_url_from_linefeed_url,
    build_champ_url,
    build_game_url,
    build_sports_short_url,
    extract_champ_id,
    normalize_linefeed_base_url,
)
from extractors.xbet_http.discovery import build_league_options_from_sports_short
from extractors.xbet_http.parser import parse_champ_zip_payload
from extractors.xbet_http.settings import XBetHttpSettings


SUPPORTED_HOSTS = {
    "1xbetarge.com",
    "www.1xbetarge.com",
    "spinbetter.com",
    "www.spinbetter.com",
}


class XBetChampClient(Protocol):
    async def fetch_champ_zip(self, url: str) -> dict[str, Any]:
        """Fetch one GetChampZip envelope."""

    async def fetch_sports_short_zip(self, url: str) -> dict[str, Any]:
        """Fetch one GetSportsShortZip envelope."""


class XBetHttpExtractor(Extractor):
    """Expose 1xBet/SpinBetter prematch LineFeed data through the common interface."""

    name = "1xbet_http"
    display_name = "1xBet HTTP"
    supported_domains = tuple(sorted(SUPPORTED_HOSTS))
    supported_capabilities = ("ligas", "eventos 1X2", "handicap", "totales")
    supports_league_discovery = True

    def __init__(
        self,
        settings: XBetHttpSettings | None = None,
        client: XBetChampClient | None = None,
    ) -> None:
        self.settings = settings or XBetHttpSettings()
        self._client = client or XBetHttpClient(self.settings)

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        parsed = urlparse((url or "").strip())
        if parsed.netloc.lower() not in SUPPORTED_HOSTS:
            return False
        if not parsed.path.rstrip("/").endswith("/LineFeed/GetChampZip"):
            return False
        champ_id = extract_champ_id(url)
        return champ_id is not None

    async def extract_league(self, url: str) -> CompetitionExtraction:
        if not self.can_handle_url(url):
            raise ValueError("The URL must be a supported 1xBet-compatible GetChampZip URL.")

        champ_id = extract_champ_id(url)
        if champ_id is None:
            raise ValueError("GetChampZip URL must include champ=<league_id>.")

        base_url = base_url_from_linefeed_url(url)
        source_url = build_champ_url(
            base_url=base_url,
            champ_id=champ_id,
            language=_language_from_url(url) or self.settings.language,
        )

        payload = await self._client.fetch_champ_zip(source_url)
        extraction = parse_champ_zip_payload(
            payload,
            source_url=source_url,
            event_url_builder=lambda event_id: build_game_url(
                base_url=base_url,
                event_id=event_id,
                language=_language_from_url(source_url) or self.settings.language,
            ),
        )

        return extraction

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError("1xBet HTTP match extraction is not implemented yet.")

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        sports_url = build_sports_short_url(
            base_url=self.settings.base_url,
            sport_id=self.settings.sport_id,
            language=self.settings.language,
            country_group=self.settings.discovery_country_group,
        )
        payload = await self._client.fetch_sports_short_zip(sports_url)
        return build_league_options_from_sports_short(
            payload,
            platform=self.name,
            platform_display_name=self.display_name,
            base_url=normalize_linefeed_base_url(self.settings.base_url),
            language=self.settings.language,
            country_name=country_name,
            query=query,
            limit=limit,
        )

def _language_from_url(url: str) -> str | None:
    raw_values = parse_qs(urlparse(url).query).get("lng")
    if not raw_values:
        return None
    language = str(raw_values[0]).strip()
    return language or None
