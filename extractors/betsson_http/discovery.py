"""League discovery from the Betsson (OBG) categories tree.

``/widgets/categories/v2`` returns ``data.items.categories[<sport>].regions[<id>]``
with each region's ``competitions``. Every competition node carries an ``events``
map, so we can surface leagues (with an event count) for one country directly from
the tree — no per-league call needed.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from core.extractor_base import LeagueDiscoveryOption


def _normalize_text(value: object | None) -> str:
    raw = str(value or "").strip().lower()
    decomposed = unicodedata.normalize("NFKD", raw)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _matches_country(region: dict[str, Any], country_filter: str) -> bool:
    if not country_filter:
        return True
    for field in ("label", "trackingLabel"):
        normalized = _normalize_text(region.get(field))
        if normalized and (country_filter == normalized or country_filter in normalized):
            return True
    return False


def _football_regions(tree: dict[str, Any], category_id: str) -> dict[str, Any]:
    items = (((tree or {}).get("data") or {}).get("items") or {})
    categories = items.get("categories") or {}
    category = categories.get(str(category_id)) or {}
    regions = category.get("regions")
    return regions if isinstance(regions, dict) else {}


def build_league_options_from_tree(
    tree: dict[str, Any],
    *,
    platform: str,
    platform_display_name: str,
    category_id: str,
    country_name: str,
    query: str | None = None,
    limit: int = 80,
) -> list[LeagueDiscoveryOption]:
    """Return leagues of one country from the OBG categories tree."""

    country_filter = _normalize_text(country_name)
    query_filter = _normalize_text(query)

    options: list[LeagueDiscoveryOption] = []
    for region_id, region in _football_regions(tree, category_id).items():
        if not isinstance(region, dict):
            continue
        if str(region_id) == "0":  # "Partidos Top" pseudo-region (no real competitions)
            continue
        if not _matches_country(region, country_filter):
            continue
        country_label = str(region.get("label") or region.get("trackingLabel") or "Desconocido")
        competitions = region.get("competitions") or {}
        for competition_id, competition in competitions.items():
            if not isinstance(competition, dict) or str(competition_id) == "0":
                continue  # id 0 is the "Todos <país>" aggregate
            league_name = str(competition.get("label") or competition_id)
            if query_filter and query_filter not in _normalize_text(league_name):
                continue
            events = competition.get("events")
            games_count = len(events) if isinstance(events, dict) else None
            options.append(
                LeagueDiscoveryOption(
                    platform=platform,
                    platform_display_name=platform_display_name,
                    country_id=str(region_id),
                    country_name=country_label,
                    league_id=str(competition_id),
                    league_name=league_name,
                    source_url=f"betsson:competition:{competition_id}",
                    games_count=games_count,
                    raw_payload={"source": "obg_categories", "slug": competition.get("slug")},
                )
            )

    options.sort(key=lambda option: (option.country_name.lower(), option.league_name.lower()))
    return options[:limit]


def resolve_competition_id_from_slug(tree: dict[str, Any], slug: str) -> str | None:
    """Resolve a site path slug (``futbol/alemania/alemania-bundesliga``) to a
    competition id via the tree's ``indexBySlug`` map (last id = competition)."""

    items = (((tree or {}).get("data") or {}).get("items") or {})
    index = items.get("indexBySlug") or {}
    normalized = slug.strip("/").lower()
    ids = index.get(normalized)
    if isinstance(ids, list) and len(ids) >= 3:
        return str(ids[-1])
    return None
