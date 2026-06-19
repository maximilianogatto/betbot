"""Extractor adapter for 1xBet-compatible LineFeed HTTP endpoints."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

from core.extractor_base import Extractor
from core.extractor_base import LeagueDiscoveryOption
from core.models import CompetitionExtraction, EventSnapshot, LiveEventSnapshot, ProviderCapabilities
from extractors.xbet_http.client import (
    XBetHttpClient,
    base_url_from_linefeed_url,
    build_champ_url,
    build_game_url,
    build_live_1x2_url,
    build_sports_short_url,
    extract_champ_id,
    normalize_linefeed_base_url,
)
from extractors.xbet_http.discovery import build_league_options_from_sports_short
from extractors.xbet_http.parser import (
    enrich_event_snapshot_with_game_detail,
    live_events_from_1x2_vzip,
    live_events_from_champ_zip,
    parse_champ_zip_payload,
)
from extractors.xbet_http.settings import XBetHttpSettings


logger = logging.getLogger(__name__)

SUPPORTED_HOSTS = {
    "1xbetarge.com",
    "www.1xbetarge.com",
    "spinbetter.com",
    "www.spinbetter.com",
}


class XBetChampClient(Protocol):
    async def fetch_champ_zip(self, url: str) -> dict[str, Any]:
        """Fetch one GetChampZip envelope."""

    async def fetch_game_zip(self, url: str) -> dict[str, Any]:
        """Fetch one GetGameZip envelope."""

    async def fetch_sports_short_zip(self, url: str) -> dict[str, Any]:
        """Fetch one GetSportsShortZip envelope."""

    async def fetch_live_1x2_zip(self, url: str) -> dict[str, Any]:
        """Fetch one LiveFeed Get1x2_VZip envelope."""


class XBetHttpExtractor(Extractor):
    """Expose 1xBet/SpinBetter prematch LineFeed data through the common interface."""

    name = "1xbet_http"
    display_name = "1xBet"
    supported_domains = tuple(sorted(SUPPORTED_HOSTS))
    supported_capabilities = ("ligas", "eventos 1X2", "handicap", "totales")
    provider_capabilities = ProviderCapabilities(
        supports_http=True,
        supports_live=True,
        supports_deep_markets=True,
        supports_browserless=True,
    )
    supports_league_discovery = True
    supports_live_detection = True  # via LiveFeed Get1x2_VZip

    def __init__(
        self,
        settings: XBetHttpSettings | None = None,
        client: XBetChampClient | None = None,
    ) -> None:
        self.settings = settings or XBetHttpSettings()
        self._client = client or XBetHttpClient(self.settings)

    async def stop(self) -> None:
        # The client may be an injected stub (tests); only close real ones.
        aclose = getattr(self._client, "aclose", None)
        if aclose is not None:
            await aclose()

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

        return await self._enrich_extraction_with_game_details(extraction)

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError("1xBet HTTP match extraction is not implemented yet.")

    async def list_live_events(self) -> list[LiveEventSnapshot]:
        url = build_live_1x2_url(
            base_url=self.settings.base_url,
            sport_id=self.settings.sport_id,
            language=self.settings.language,
            gr=self.settings.live_gr,
            country=self.settings.live_country,
            mode=self.settings.live_mode,
            cfview=self.settings.live_cfview,
            count=self.settings.live_count,
        )
        try:
            payload = await self._client.fetch_live_1x2_zip(url)
            events = live_events_from_1x2_vzip(payload)
        except Exception as e:
            logger.warning("Failed to fetch general 1xBet live feed: %s", e)
            events = []

        try:
            from storage.tracking_repository import tracking_repository
            tracked = tracking_repository.list_globally_active_competitions()
            xbet_leagues = [c for c in tracked if c.platform == self.name and c.enabled]
            if xbet_leagues:
                tasks = []
                for league in xbet_leagues:
                    champ_id = league.competition_external_id
                    live_base = normalize_linefeed_base_url(self.settings.base_url).replace("/LineFeed", "/LiveFeed")
                    live_url = f"{live_base}/GetChampZip?champ={champ_id}&lng={self.settings.language}"
                    tasks.append(self._client.fetch_champ_zip(live_url))
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        continue
                    if isinstance(res, dict):
                        events.extend(live_events_from_champ_zip(res))
        except Exception as e:
            logger.warning("Failed to fetch 1xBet specific live feeds: %s", e)

        seen = set()
        deduped = []
        for e in events:
            if e.external_event_id not in seen:
                seen.add(e.external_event_id)
                deduped.append(e)
        return deduped

    def build_competition_url(
        self,
        *,
        competition_external_id: str,
        source_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if source_url:
            return source_url
        return build_champ_url(
            base_url=self.settings.base_url,
            champ_id=competition_external_id,
            language=self.settings.language,
        )

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

    async def _enrich_extraction_with_game_details(
        self,
        extraction: CompetitionExtraction,
    ) -> CompetitionExtraction:
        if (
            not self.settings.fetch_game_details
            or extraction.is_empty
            or self.settings.max_game_detail_requests == 0
        ):
            return extraction

        enriched_events: list[EventSnapshot] = []
        requests_count = 0
        failures_count = 0
        enriched_count = 0
        limit_reached = False

        for event in extraction.events:
            if not _event_needs_game_detail(event):
                enriched_events.append(event)
                continue
            if requests_count >= self.settings.max_game_detail_requests:
                limit_reached = True
                enriched_events.append(event)
                continue
            if not event.source_url:
                enriched_events.append(event)
                continue

            requests_count += 1
            try:
                payload = await self._client.fetch_game_zip(event.source_url)
            except Exception as error:  # noqa: BLE001 - one failed event must not break the league refresh.
                failures_count += 1
                logger.warning(
                    "1xBet GetGameZip enrichment failed event_id=%s url=%s error=%s",
                    event.external_event_id,
                    event.source_url,
                    error,
                )
                enriched_events.append(event)
                continue

            enriched_event = enrich_event_snapshot_with_game_detail(event, payload)
            if not _event_needs_game_detail(enriched_event):
                enriched_count += 1
            enriched_events.append(enriched_event)

        metadata = {
            **extraction.metadata,
            "game_detail_enabled": True,
            "game_detail_requests": requests_count,
            "game_detail_failures": failures_count,
            "game_detail_markets_enriched": enriched_count,
            "game_detail_limit_reached": limit_reached,
        }
        raw_payload = {
            **extraction.raw_payload,
            "game_detail_requests": requests_count,
            "game_detail_failures": failures_count,
            "game_detail_markets_enriched": enriched_count,
            "game_detail_limit_reached": limit_reached,
        }

        return replace(extraction, events=enriched_events, metadata=metadata, raw_payload=raw_payload)


def _event_needs_game_detail(event: EventSnapshot) -> bool:
    markets = event.markets_payload or {}
    missing_1x2 = any(
        value is None
        for value in (event.odds_1x2.home, event.odds_1x2.draw, event.odds_1x2.away)
    )
    return missing_1x2 or "asian_handicap" not in markets or "goal_line" not in markets


def _language_from_url(url: str) -> str | None:
    raw_values = parse_qs(urlparse(url).query).get("lng")
    if not raw_values:
        return None
    language = str(raw_values[0]).strip()
    return language or None
