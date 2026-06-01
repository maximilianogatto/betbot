"""League discovery from the MrPunter (FSB) navigation tree."""

from __future__ import annotations

import unicodedata
from typing import Any

from core.extractor_base import LeagueDiscoveryOption


def _normalize_text(value: object | None) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    return "".join(ch for ch in raw if not unicodedata.combining(ch))


def _matches_country(country_name: str, country_filter: str) -> bool:
    if not country_filter:
        return True
    normalized = _normalize_text(country_name)
    return country_filter == normalized or country_filter in normalized


def build_league_options(
    navigation: list[dict[str, Any]],
    *,
    platform: str,
    platform_display_name: str,
    sport_id: str = "1",
    country_name: str,
    query: str | None = None,
    limit: int = 80,
) -> list[LeagueDiscoveryOption]:
    """Return soccer leagues whose country matches, with prematch fixture counts."""

    sport = next((s for s in navigation or [] if str(s.get("_id")) == str(sport_id)), None)
    if sport is None:
        return []

    country_filter = _normalize_text(country_name)
    query_filter = _normalize_text(query)

    options: list[LeagueDiscoveryOption] = []
    for country in sport.get("countries") or []:
        region_name = str(country.get("RegionName") or "Desconocido")
        if not _matches_country(region_name, country_filter):
            continue
        for league in country.get("Leagues") or []:
            master_id = league.get("MasterLeagueId")
            if master_id is None:
                continue
            league_name = str(league.get("LeagueName") or master_id)
            if query_filter and query_filter not in _normalize_text(league_name):
                continue
            fixture_count = league.get("fixtureEventsQuantity")
            if not isinstance(fixture_count, int):
                fixture_count = league.get("eventsQuantity") or 0
            options.append(
                LeagueDiscoveryOption(
                    platform=platform,
                    platform_display_name=platform_display_name,
                    country_id=str(country.get("_id")) if country.get("_id") is not None else None,
                    country_name=region_name,
                    league_id=str(master_id),
                    league_name=league_name,
                    source_url=f"mrpunter:league:{master_id}",
                    games_count=int(fixture_count),
                    raw_payload={"source": "fsb_navigation", "master_league_id": str(master_id), "_id": league.get("_id")},
                )
            )

    options.sort(key=lambda option: (option.country_name.lower(), option.league_name.lower()))
    return options[:limit]
