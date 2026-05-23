"""League discovery helpers for 1xBet-compatible LineFeed."""

from __future__ import annotations

import unicodedata
from typing import Any

from core.extractor_base import LeagueDiscoveryOption
from extractors.xbet_http.client import build_champ_url


def build_league_options_from_sports_short(
    payload: dict[str, Any],
    *,
    platform: str,
    platform_display_name: str,
    base_url: str,
    language: str,
    country_name: str,
    query: str | None = None,
    limit: int = 80,
) -> list[LeagueDiscoveryOption]:
    """Parse GetSportsShortZip and return leagues matching one country/search."""

    value = payload.get("Value")
    if not isinstance(value, list):
        return []

    country_filter = _normalize_text(country_name)
    query_filter = _normalize_text(query)
    options: list[LeagueDiscoveryOption] = []
    seen: set[tuple[str, str | None]] = set()

    for sport in value:
        if not isinstance(sport, dict):
            continue
        for item in sport.get("L") or []:
            if not isinstance(item, dict):
                continue
            candidates = _extract_options_from_node(
                item,
                parent_country_name=None,
                parent_country_id=None,
                platform=platform,
                platform_display_name=platform_display_name,
                base_url=base_url,
                language=language,
            )
            for candidate in candidates:
                if not _matches_country(candidate.country_name, country_filter):
                    continue
                if query_filter and query_filter not in _normalize_text(candidate.league_name):
                    continue
                key = (candidate.league_id, candidate.country_id)
                if key in seen:
                    continue
                seen.add(key)
                options.append(candidate)
                if len(options) >= limit:
                    return options

    options.sort(key=lambda option: (option.country_name.lower(), option.league_name.lower()))
    return options


def _extract_options_from_node(
    node: dict[str, Any],
    *,
    parent_country_name: str | None,
    parent_country_id: str | None,
    platform: str,
    platform_display_name: str,
    base_url: str,
    language: str,
) -> list[LeagueDiscoveryOption]:
    children = node.get("SC")
    if isinstance(children, list) and children:
        country_name = _safe_str(node.get("L") or node.get("CN") or node.get("CE")) or parent_country_name
        country_id = _safe_str(node.get("CI") or node.get("LI")) or parent_country_id
        options: list[LeagueDiscoveryOption] = []
        for child in children:
            if isinstance(child, dict):
                options.extend(
                    _extract_options_from_node(
                        child,
                        parent_country_name=country_name,
                        parent_country_id=country_id,
                        platform=platform,
                        platform_display_name=platform_display_name,
                        base_url=base_url,
                        language=language,
                    )
                )
        return options

    league_id = _safe_str(node.get("LI"))
    league_name = _safe_str(node.get("L") or node.get("LE"))
    if league_id is None or league_name is None:
        return []

    country_name = _safe_str(node.get("CN") or node.get("CE")) or parent_country_name or "Desconocido"
    country_id = _safe_str(node.get("CI")) or parent_country_id
    source_url = build_champ_url(base_url=base_url, champ_id=league_id, language=language)

    return [
        LeagueDiscoveryOption(
            platform=platform,
            platform_display_name=platform_display_name,
            country_id=country_id,
            country_name=country_name,
            league_id=league_id,
            league_name=league_name,
            source_url=source_url,
            games_count=_coerce_int(node.get("GC")),
            raw_payload={
                "source": "GetSportsShortZip",
                "league_id": league_id,
                "country_id": country_id,
            },
        )
    ]


def _matches_country(country_name: str, country_filter: str) -> bool:
    if not country_filter:
        return True
    normalized_country = _normalize_text(country_name)
    return country_filter == normalized_country or country_filter in normalized_country


def _normalize_text(value: object | None) -> str:
    raw = str(value or "").strip().lower()
    decomposed = unicodedata.normalize("NFKD", raw)
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _safe_str(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _coerce_int(value: object | None) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None
