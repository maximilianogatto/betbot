"""HTTP-only client for Svenskfotboll / Swedish FA.

The public detail pages are Cloudflare-protected, but the official frontend
exposes enough lightweight endpoints for a useful stats provider:

- `comp-find` JSON for league discovery.
- `widget.aspx` JSON with embedded HTML tables for standings/fixtures/results.
- FOGIS XML for live state and events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from stats_providers.svenskfotboll_http.normalizers import (
    parse_competition_tree,
    parse_game_info_xml,
    parse_live_overview_xml,
    parse_livescore_ticker,
    parse_matches_today,
    parse_matches_widget,
    parse_standings_widget,
    search_competitions,
)


DEFAULT_BASE_URL = "https://www.svenskfotboll.se"
DEFAULT_LIVE_XML_BASE_URL = "https://c01.fogis.se/fogistemplates.se/livescore/xml"


@dataclass(frozen=True)
class SvenskfotbollEndpoints:
    filter_criteria: str = "/api/comp-find/getfiltercriteria"
    competitions_filter: str = "/api/comp-find/filter"
    matches_today: str = "/api/matches-today/games/"
    matches_today_filter: str = "/api/matches-today/filter/"
    livescore_ticker: str = "/api/livescore-ticker/"
    widget: str = "/widget.aspx"
    live_overview_pattern: str = "overview-{association_id}-{yyyymmdd}.xml"
    live_game_info_pattern: str = "game-info-{match_id}.xml"
    live_lineup_pattern: str = "lineup-{match_id}.xml"
    live_changes_pattern: str = "changes-{association_id}.xml"


class SvenskfotbollHTTPClient:
    """Small reusable HTTP client for Swedish FA stats."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        live_xml_base_url: str = DEFAULT_LIVE_XML_BASE_URL,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.live_xml_base_url = live_xml_base_url.rstrip("/")
        self.endpoints = SvenskfotbollEndpoints()
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
                ),
                "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8,es;q=0.7",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "SvenskfotbollHTTPClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def get_filter_criteria(self) -> dict[str, Any]:
        return self._get_json(self.endpoints.filter_criteria)

    def get_competition_tree(self) -> dict[str, Any]:
        return self._get_json(self.endpoints.competitions_filter)

    def search_leagues(
        self,
        query: str | None = None,
        *,
        association_id: str | int | None = None,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        competitions = parse_competition_tree(self.get_competition_tree())
        return search_competitions(competitions, query=query, association_id=association_id, limit=limit)

    def get_matches_today(self, *, association_id: str | int = 1, date_offset: int = 0) -> list[dict[str, Any]]:
        payload = self._get_json(
            self.endpoints.matches_today,
            params={"associationId": association_id, "dateOffset": date_offset},
        )
        return parse_matches_today(payload)

    def get_livescore_ticker(self) -> list[dict[str, Any]]:
        return parse_livescore_ticker(self._get_json(self.endpoints.livescore_ticker))

    def get_standings(self, competition_id: str | int) -> dict[str, Any]:
        html = self._get_widget_html("tablesmall", competition_id)
        return parse_standings_widget(html, competition_id)

    def get_upcoming_matches(self, competition_id: str | int, *, limit: int = 40) -> dict[str, Any]:
        html = self._get_widget_html("cominginleague", competition_id, limit=limit)
        return parse_matches_widget(html, competition_id, result_rows=False)

    def get_latest_results(self, competition_id: str | int, *, limit: int = 40) -> dict[str, Any]:
        html = self._get_widget_html("latestinleague", competition_id, limit=limit)
        return parse_matches_widget(html, competition_id, result_rows=True)

    def get_live_overview(self, *, association_id: str | int = 1, day: date | None = None) -> dict[str, Any]:
        target_day = day or date.today()
        path = self.endpoints.live_overview_pattern.format(
            association_id=association_id,
            yyyymmdd=target_day.strftime("%Y%m%d"),
        )
        response = self.client.get(f"{self.live_xml_base_url}/{path}", headers={"Accept": "application/xml,text/xml,*/*"})
        response.raise_for_status()
        return parse_live_overview_xml(response.text)

    def get_live_game_info(self, match_id: str | int) -> dict[str, Any]:
        path = self.endpoints.live_game_info_pattern.format(match_id=match_id)
        response = self.client.get(f"{self.live_xml_base_url}/{path}", headers={"Accept": "application/xml,text/xml,*/*"})
        response.raise_for_status()
        return parse_game_info_xml(response.text)

    def get_live_lineup_xml(self, match_id: str | int) -> str:
        path = self.endpoints.live_lineup_pattern.format(match_id=match_id)
        response = self.client.get(f"{self.live_xml_base_url}/{path}", headers={"Accept": "application/xml,text/xml,*/*"})
        response.raise_for_status()
        return response.text

    def get_live_changes_xml(self, *, association_id: str | int = 1) -> str:
        path = self.endpoints.live_changes_pattern.format(association_id=association_id)
        response = self.client.get(f"{self.live_xml_base_url}/{path}", headers={"Accept": "application/xml,text/xml,*/*"})
        response.raise_for_status()
        return response.text

    def _get_widget_html(self, screen: str, competition_id: str | int, *, limit: int | None = None) -> str:
        params = {
            "p": "1",
            "scr": screen,
            "ftid": str(competition_id),
            "b1": "#005293",
            "f1": "#FFF",
            "b2": "#00345c",
            "f2": "#FFF",
            "b4": "#00457d",
            "f3": "#FFF",
            "b3": "#005293",
            "bo": "#FFF",
        }
        if limit is not None:
            params["nbr"] = str(limit)
        payload = self._get_json(self.endpoints.widget, params=params)
        return str(payload.get("html") or "")

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        response = self.client.get(
            url,
            params=params,
            headers={
                "Accept": "application/json,text/plain,*/*",
                "Referer": f"{self.base_url}/",
                "Origin": self.base_url,
            },
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object from {url}, got {type(data).__name__}")
        return data


__all__ = ["SvenskfotbollEndpoints", "SvenskfotbollHTTPClient"]

