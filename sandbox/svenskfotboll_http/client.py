"""Experimental HTTP client for Svenskfotboll / Swedish FA.

This client deliberately avoids DOM scraping.  It uses:

* JSON APIs on ``www.svenskfotboll.se`` for discovery, matches today and ticker.
* ``/widget.aspx`` for competition standings, upcoming fixtures and latest
  results.  The response is JSON with an HTML table, parsed by
  ``normalizers.py``.
* FOGIS livescore XML on ``c01.fogis.se`` for live game state, events and
  aggregate stats.

It is sandbox-only.  A future production provider can reuse this file once the
coverage is validated against real tracked leagues.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from sandbox.svenskfotboll_http.normalizers import (
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
    """Endpoint map discovered during the sandbox investigation."""

    filter_criteria: str = "/api/comp-find/getfiltercriteria"
    competitions_filter: str = "/api/comp-find/filter"
    matches_today: str = "/api/matches-today/games/"
    matches_today_filter: str = "/api/matches-today/filter/"
    livescore_ticker: str = "/api/livescore-ticker/"
    widget: str = "/widget.aspx"
    live_overview_pattern: str = "overview-{association_id}-{yyyymmdd}.xml"
    live_game_info_pattern: str = "game-info-{match_id}.xml"
    live_changes_pattern: str = "changes-{association_id}.xml"


class SvenskfotbollHTTPClient:
    """Small HTTP-only client for Swedish FA data.

    Args:
        base_url: Main Svenskfotboll host.
        live_xml_base_url: FOGIS livescore XML base host.
        timeout: Per-request timeout in seconds.
        client: Optional ``httpx.Client`` injected by tests.
    """

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
        """Return association/gender/age filters from ``comp-find``."""

        return self._get_json(self.endpoints.filter_criteria)

    def get_competition_tree(self) -> dict[str, Any]:
        """Return the full competition tree.

        The raw response is large, but it is the main discovery source for
        ``competition_id``/``ftid`` values.
        """

        return self._get_json(self.endpoints.competitions_filter)

    def search_leagues(
        self,
        query: str | None = None,
        *,
        association_id: str | int | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Search competitions by name/category and optional association."""

        competitions = parse_competition_tree(self.get_competition_tree())
        return search_competitions(competitions, query=query, association_id=association_id, limit=limit)

    def get_matches_today(self, *, association_id: str | int = 1, date_offset: int = 0) -> list[dict[str, Any]]:
        """Return normalized matches for the site's matches-today endpoint."""

        payload = self._get_json(
            self.endpoints.matches_today,
            params={"associationId": association_id, "dateOffset": date_offset},
        )
        return parse_matches_today(payload)

    def get_livescore_ticker(self) -> list[dict[str, Any]]:
        """Return compact live ticker games from the JSON ticker endpoint."""

        return parse_livescore_ticker(self._get_json(self.endpoints.livescore_ticker))

    def get_standings(self, competition_id: str | int) -> dict[str, Any]:
        """Return compact standings for one competition id (``ftid``)."""

        html = self._get_widget_html("tablesmall", competition_id)
        return parse_standings_widget(html, competition_id)

    def get_upcoming_matches(self, competition_id: str | int, *, limit: int = 20) -> dict[str, Any]:
        """Return upcoming fixtures for one competition id (``ftid``)."""

        html = self._get_widget_html("cominginleague", competition_id, limit=limit)
        return parse_matches_widget(html, competition_id, result_rows=False)

    def get_latest_results(self, competition_id: str | int, *, limit: int = 20) -> dict[str, Any]:
        """Return latest results for one competition id (``ftid``)."""

        html = self._get_widget_html("latestinleague", competition_id, limit=limit)
        return parse_matches_widget(html, competition_id, result_rows=True)

    def get_live_overview(self, *, association_id: str | int = 1, day: date | None = None) -> dict[str, Any]:
        """Return live overview XML normalized to JSON-compatible dicts."""

        target_day = day or date.today()
        yyyymmdd = target_day.strftime("%Y%m%d")
        path = self.endpoints.live_overview_pattern.format(association_id=association_id, yyyymmdd=yyyymmdd)
        response = self.client.get(f"{self.live_xml_base_url}/{path}", headers={"Accept": "application/xml,text/xml,*/*"})
        response.raise_for_status()
        return parse_live_overview_xml(response.text)

    def get_live_game_info(self, match_id: str | int) -> dict[str, Any]:
        """Return one FOGIS live game XML normalized to compact dict."""

        path = self.endpoints.live_game_info_pattern.format(match_id=match_id)
        response = self.client.get(f"{self.live_xml_base_url}/{path}", headers={"Accept": "application/xml,text/xml,*/*"})
        response.raise_for_status()
        return parse_game_info_xml(response.text)

    def get_live_changes(self, *, association_id: str | int = 1) -> str:
        """Return raw ``changes-<association>.xml``.

        This file lists changed live XML documents and can be polled to avoid
        refetching every game blindly.
        """

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

