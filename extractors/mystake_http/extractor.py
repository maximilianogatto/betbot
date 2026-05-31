"""Mystake prematch HTTP extractor.

Status: the data layer (client + parser) is complete and tested against the
documented getprematch shape. The tracking-URL scheme and league discovery are
finalized once a real host + sample response are available (set via
MYSTAKE_API_BASE_URL); a league is identified by its ``region`` id.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from core.extractor_base import Extractor, LeagueDiscoveryOption
from core.models import (
    CompetitionExtraction,
    EventSnapshot,
    ProviderCapabilities,
)
from extractors.mystake_http.client import MystakeHttpClient
from extractors.mystake_http.parser import build_competition_extraction
from extractors.mystake_http.settings import MystakeHttpSettings, load_mystake_settings

_SUPPORTED_HOSTS = ("mystake.bet",)
# Tracking forms accepted: a mystake.bet URL carrying ?region=<id> (or league=),
# or the explicit scheme "mystake:region:<id>".
_REGION_SCHEME_RE = re.compile(r"^mystake:region:(\d+)$", re.IGNORECASE)


class MystakeHttpExtractor(Extractor):
    """HTTP extractor for Mystake prematch soccer leagues."""

    name = "mystake_http"
    display_name = "Mystake HTTP"
    supported_domains = _SUPPORTED_HOSTS
    supported_capabilities = ("ligas",)
    provider_capabilities = ProviderCapabilities(supports_http=True, supports_browserless=True)
    supports_league_discovery = False  # enabled once region names are mapped from a live sample

    def __init__(self, *, settings: MystakeHttpSettings | None = None) -> None:
        self.settings = settings or load_mystake_settings()

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        normalized = (url or "").strip().lower()
        if _REGION_SCHEME_RE.match(normalized):
            return True
        host = urlparse(normalized).netloc
        return any(domain in host for domain in _SUPPORTED_HOSTS)

    async def extract_league(self, url: str) -> CompetitionExtraction:
        if not self.can_handle_url(url):
            raise ValueError(f"{self.name} cannot handle URL: {url}")
        region_id = _region_id_from_url(url)
        if region_id is None:
            raise ValueError(
                "Could not determine the Mystake league (region id) from the URL. "
                "Use 'mystake:region:<id>' or a mystake.bet URL with ?region=<id>."
            )
        client = MystakeHttpClient(self.settings)
        raw = await client.fetch_prematch()
        return build_competition_extraction(region_id=region_id, raw_response=raw, source_url=url)

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError(f"{self.name} does not support direct match URLs yet.")

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        # Discovery needs the region->name map, which is read from a live sample.
        raise NotImplementedError(f"{self.name} league discovery is not finalized yet.")


def _region_id_from_url(url: str) -> str | None:
    normalized = (url or "").strip()
    scheme_match = _REGION_SCHEME_RE.match(normalized.lower())
    if scheme_match:
        return scheme_match.group(1)
    query = parse_qs(urlparse(normalized).query)
    for key in ("region", "league", "champ", "tournament"):
        values = query.get(key)
        if values and values[0].isdigit():
            return values[0]
    return None
