"""League discovery from a merged Betby snapshot (sports -> categories -> tournaments).

A Betby ``category`` is the country; a ``tournament`` is the league. We scope to
one sport (soccer) by inspecting each tournament's events, and expose leagues as
``LeagueDiscoveryOption`` filtered by country name.
"""

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


def _tournament_counts_by_sport(snapshot: dict[str, Any]) -> dict[str, tuple[str, int]]:
    """Map tournament_id -> (sport_id, match_count) using the events feed."""

    result: dict[str, tuple[str, int]] = {}
    for event in (snapshot.get("events") or {}).values():
        if not isinstance(event, dict):
            continue
        desc = event.get("desc") or {}
        if desc.get("type") != "match":
            continue
        tour_id = str(desc.get("tournament"))
        sport_id = str(desc.get("sport"))
        if not tour_id or tour_id == "None":
            continue
        current_sport, count = result.get(tour_id, (sport_id, 0))
        result[tour_id] = (current_sport or sport_id, count + 1)
    return result


def build_league_options(
    snapshot: dict[str, Any],
    *,
    platform: str,
    platform_display_name: str,
    sport_id: str = "1",
    country_name: str,
    query: str | None = None,
    limit: int = 80,
) -> list[LeagueDiscoveryOption]:
    """Return soccer leagues whose country matches, with live match counts."""

    tournaments = snapshot.get("tournaments") or {}
    categories = snapshot.get("categories") or {}
    counts = _tournament_counts_by_sport(snapshot)

    country_filter = _normalize_text(country_name)
    query_filter = _normalize_text(query)

    options: list[LeagueDiscoveryOption] = []
    for tour_id, tournament in tournaments.items():
        if not isinstance(tournament, dict):
            continue
        sport_and_count = counts.get(str(tour_id))
        if sport_and_count is None:
            continue  # no real matches scheduled
        tour_sport, match_count = sport_and_count
        if str(tour_sport) != str(sport_id):
            continue

        category_id = tournament.get("category_id")
        category = categories.get(str(category_id)) if category_id is not None else None
        country = (category or {}).get("name") if isinstance(category, dict) else None
        country = country or "Desconocido"
        if not _matches_country(country, country_filter):
            continue

        league_name = str(tournament.get("name") or tour_id)
        if query_filter and query_filter not in _normalize_text(league_name):
            continue

        options.append(
            LeagueDiscoveryOption(
                platform=platform,
                platform_display_name=platform_display_name,
                country_id=str(category_id) if category_id is not None else None,
                country_name=str(country),
                league_id=str(tour_id),
                league_name=league_name,
                source_url=f"solcasino:tournament:{tour_id}",
                games_count=match_count,
                raw_payload={"source": "betby_snapshot", "tournament_id": str(tour_id)},
            )
        )

    options.sort(key=lambda option: (option.country_name.lower(), option.league_name.lower()))
    return options[:limit]
