"""League discovery from the BZ match/search feed (tournaments by country)."""

from __future__ import annotations

import unicodedata
from typing import Any

from core.extractor_base import LeagueDiscoveryOption


def _normalize_text(value: object | None) -> str:
    raw = str(value or "").strip().lower()
    decomposed = unicodedata.normalize("NFKD", raw)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _matches_country(country_name: str, country_filter: str) -> bool:
    if not country_filter:
        return True
    normalized = _normalize_text(country_name)
    return country_filter == normalized or country_filter in normalized


def _tournament_external_id(value: Any) -> str:
    text = str(value or "").strip()
    return text.split(":")[-1] if text.startswith("sr:tournament:") else text


def build_league_options(
    search_data: list[dict[str, Any]],
    *,
    platform: str,
    platform_display_name: str,
    country_name: str,
    query: str | None = None,
    limit: int = 80,
) -> list[LeagueDiscoveryOption]:
    """Return tournaments whose country matches, with prematch match counts."""

    country_filter = _normalize_text(country_name)
    query_filter = _normalize_text(query)

    options: list[LeagueDiscoveryOption] = []
    for tournament in search_data or []:
        if not isinstance(tournament, dict):
            continue
        country = str(tournament.get("categoryName") or "Desconocido")
        if not _matches_country(country, country_filter):
            continue
        league_name = str(tournament.get("name") or tournament.get("id"))
        if query_filter and query_filter not in _normalize_text(league_name):
            continue

        external_id = _tournament_external_id(tournament.get("id"))
        match_count = tournament.get("matchCount")
        if not isinstance(match_count, int):
            match_count = len(tournament.get("matches") or [])

        options.append(
            LeagueDiscoveryOption(
                platform=platform,
                platform_display_name=platform_display_name,
                country_id=_category_external_id(tournament.get("categoryId")),
                country_name=country,
                league_id=external_id,
                league_name=league_name,
                source_url=f"bz:tournament:{external_id}",
                games_count=match_count,
                raw_payload={
                    "source": "bz_match_search",
                    "tournament_id": f"sr:tournament:{external_id}",
                    "season_id": tournament.get("currentSeasonId"),
                },
            )
        )

    options.sort(key=lambda option: (option.country_name.lower(), option.league_name.lower()))
    return options[:limit]


def _category_external_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text.split(":")[-1] if text.startswith("sr:category:") else text
