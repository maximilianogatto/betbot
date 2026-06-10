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


def _leaf_leagues(country_node: dict[str, Any]):
    """Yield every leaf league (no child groups) with a prematch event."""

    stack = list(country_node.get("groups") or [])
    while stack:
        node = stack.pop()
        children = node.get("groups") or []
        if children:
            stack.extend(children)
            continue
        if (node.get("eventCount") or 0) > 0:
            yield node


def build_league_options_from_tree(
    group_tree: dict[str, Any],
    *,
    platform: str,
    platform_display_name: str,
    country_name: str,
    query: str | None = None,
    limit: int = 80,
    sport_term: str = "football",
) -> list[LeagueDiscoveryOption]:
    """Return leagues from Kambi's full group tree (complete, unlike listView).

    The tree is sport -> country -> league; ``betoffer/group/<id>.json`` works on
    any league id, so this gives full discovery coverage (every league with a
    prematch event), not just the "starting soon" subset that listView returns.
    """

    country_filter = _normalize_text(country_name)
    query_filter = _normalize_text(query)

    root = group_tree.get("group") if isinstance(group_tree.get("group"), dict) else group_tree
    sports = (root or {}).get("groups") or []
    football = next(
        (s for s in sports if str(s.get("termKey") or "").lower() == sport_term.lower()),
        None,
    )
    if football is None:
        return []

    options: list[LeagueDiscoveryOption] = []
    for country in football.get("groups") or []:
        cname = country.get("name") or country.get("englishName") or "Desconocido"
        if not _matches_country(cname, country_filter):
            continue
        country_id = str(country.get("id")) if country.get("id") is not None else None
        for league in _leaf_leagues(country):
            lname = str(league.get("name") or league.get("englishName") or league.get("id"))
            if query_filter and query_filter not in _normalize_text(lname):
                continue
            league_id = str(league.get("id"))
            options.append(
                LeagueDiscoveryOption(
                    platform=platform,
                    platform_display_name=platform_display_name,
                    country_id=country_id,
                    country_name=cname,
                    league_id=league_id,
                    league_name=lname,
                    source_url=f"betwarrior:group:{league_id}",
                    games_count=int(league.get("eventCount") or 0),
                    raw_payload={"source": "kambi_group_tree", "group_id": league_id},
                )
            )

    options.sort(key=lambda option: (option.country_name.lower(), option.league_name.lower()))
    return options[:limit]
