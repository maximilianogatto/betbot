"""League discovery from the BetWarrior (Kambi) listView feed.

Each event carries a ``path`` (sport -> country -> league). We group events by
league (``groupId``), take the country from ``path[-2]``, and expose leagues as
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


def _country_from_path(path: Any) -> str | None:
    if not isinstance(path, list) or len(path) < 2:
        return None
    return path[-2].get("name") or path[-2].get("englishName")


def build_league_options(
    list_view: dict[str, Any],
    *,
    platform: str,
    platform_display_name: str,
    country_name: str,
    query: str | None = None,
    limit: int = 80,
) -> list[LeagueDiscoveryOption]:
    """Return leagues whose country matches, with prematch match counts."""

    country_filter = _normalize_text(country_name)
    query_filter = _normalize_text(query)

    leagues: dict[str, dict[str, Any]] = {}
    for item in list_view.get("events") or []:
        event = item.get("event") if isinstance(item.get("event"), dict) else item
        if not isinstance(event, dict):
            continue
        group_id = event.get("groupId")
        if group_id is None:
            continue
        country = _country_from_path(event.get("path")) or "Desconocido"
        entry = leagues.setdefault(
            str(group_id),
            {
                "group_id": str(group_id),
                "league_name": str(event.get("group") or group_id),
                "country": country,
                "country_id": str(event["path"][-2].get("id")) if isinstance(event.get("path"), list) and len(event["path"]) >= 2 else None,
                "count": 0,
            },
        )
        entry["count"] += 1

    options: list[LeagueDiscoveryOption] = []
    for entry in leagues.values():
        if not _matches_country(entry["country"], country_filter):
            continue
        if query_filter and query_filter not in _normalize_text(entry["league_name"]):
            continue
        options.append(
            LeagueDiscoveryOption(
                platform=platform,
                platform_display_name=platform_display_name,
                country_id=entry["country_id"],
                country_name=entry["country"],
                league_id=entry["group_id"],
                league_name=entry["league_name"],
                source_url=f"betwarrior:group:{entry['group_id']}",
                games_count=entry["count"],
                raw_payload={"source": "kambi_listView", "group_id": entry["group_id"]},
            )
        )

    options.sort(key=lambda option: (option.country_name.lower(), option.league_name.lower()))
    return options[:limit]
