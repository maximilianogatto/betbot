"""Parse the Mystake navigation tree (``/api/sport/getheader/<region>``).

The header is the complete prematch directory and the key to browsing leagues
without pasting a URL. Its (double-encoded) JSON shape is::

    {
      "AS": {                       # region group (company region, e.g. "as")
        "Language": 100,
        "Sports": {
          "1": {                    # sport id (1 = Soccer)
            "ID": 1, "Name": "Fútbol",
            "Regions": {
              "8": {                # region == country
                "ID": 8, "Name": "Suecia",
                "Champs": {
                  "258": {          # champ == league (already translated!)
                    "ID": 258, "Name": "Internacional Amistosos",
                    "GameSmallItems": {
                      "71549821": {"ID": 71549821, "Champ": 258, "StartTime": ...},
                      ...
                    }
                  }
                }
              }
            }
          }
        }
      }
    }

Outright/special markets carry negative ``GameSmallItem`` ids; real matches are
positive, so we only keep positive ids for odds fetching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import unicodedata
from typing import Any

from core.extractor_base import LeagueDiscoveryOption


@dataclass(frozen=True)
class LeagueNode:
    """One league (championship) resolved from the header tree."""

    sport_id: int
    sport_name: str
    region_id: str
    region_name: str
    champ_id: str
    champ_name: str
    game_ids: tuple[int, ...] = field(default_factory=tuple)

    @property
    def games_count(self) -> int:
        return len(self.game_ids)


def _sports_for_region_group(tree: Any) -> dict[str, Any]:
    """Return the ``Sports`` dict from the first region group in the tree."""

    if not isinstance(tree, dict):
        return {}
    for group in tree.values():
        if isinstance(group, dict) and isinstance(group.get("Sports"), dict):
            return group["Sports"]
    return {}


def _positive_game_ids(champ: dict[str, Any]) -> tuple[int, ...]:
    items = champ.get("GameSmallItems")
    if not isinstance(items, dict):
        return ()
    ids: list[int] = []
    for entry in items.values():
        if not isinstance(entry, dict):
            continue
        gid = entry.get("ID")
        try:
            value = int(gid)
        except (TypeError, ValueError):
            continue
        if value > 0:  # negative ids are outrights/specials, not 1X2 matches
            ids.append(value)
    return tuple(ids)


def parse_leagues(tree: Any, *, sport_id: int = 1) -> list[LeagueNode]:
    """Flatten the header tree into a list of leagues for one sport."""

    sports = _sports_for_region_group(tree)
    sport = sports.get(str(sport_id))
    if not isinstance(sport, dict):
        return []
    sport_name = str(sport.get("Name") or sport.get("KeyName") or f"Sport {sport_id}")

    leagues: list[LeagueNode] = []
    regions = sport.get("Regions")
    if not isinstance(regions, dict):
        return []
    for region_id, region in regions.items():
        if not isinstance(region, dict):
            continue
        region_name = str(region.get("Name") or region.get("KeyName") or region_id)
        champs = region.get("Champs")
        if not isinstance(champs, dict):
            continue
        for champ_id, champ in champs.items():
            if not isinstance(champ, dict):
                continue
            game_ids = _positive_game_ids(champ)
            if not game_ids:  # skip outright-only / empty leagues
                continue
            leagues.append(
                LeagueNode(
                    sport_id=sport_id,
                    sport_name=sport_name,
                    region_id=str(region_id),
                    region_name=region_name,
                    champ_id=str(champ_id),
                    champ_name=str(champ.get("Name") or champ.get("KeyName") or champ_id),
                    game_ids=game_ids,
                )
            )
    return leagues


def find_champ(tree: Any, *, champ_id: str, sport_id: int | None = None) -> LeagueNode | None:
    """Locate a single league by championship id (searches all sports if needed)."""

    sport_ids: list[int]
    if sport_id is not None:
        sport_ids = [sport_id]
    else:
        sports = _sports_for_region_group(tree)
        sport_ids = [int(sid) for sid in sports.keys() if str(sid).lstrip("-").isdigit()]
    for sid in sport_ids:
        for league in parse_leagues(tree, sport_id=sid):
            if league.champ_id == str(champ_id):
                return league
    return None


def build_league_options(
    tree: Any,
    *,
    platform: str,
    platform_display_name: str,
    sport_id: int = 1,
    country_name: str,
    query: str | None = None,
    limit: int = 80,
) -> list[LeagueDiscoveryOption]:
    """Return leagues matching a country name (and optional text query)."""

    country_filter = _normalize_text(country_name)
    query_filter = _normalize_text(query)

    options: list[LeagueDiscoveryOption] = []
    for league in parse_leagues(tree, sport_id=sport_id):
        if not _matches_country(league.region_name, country_filter):
            continue
        disp_name = f"{league.region_name} · {league.champ_name}" if league.region_name.lower() not in league.champ_name.lower() else league.champ_name
        if query_filter and query_filter not in _normalize_text(disp_name):
            continue
        options.append(
            LeagueDiscoveryOption(
                platform=platform,
                platform_display_name=platform_display_name,
                country_id=league.region_id,
                country_name=league.region_name,
                league_id=league.champ_id,
                league_name=disp_name,
                source_url=f"mystake:champ:{league.champ_id}",
                games_count=league.games_count,
                raw_payload={
                    "source": "getheader",
                    "sport_id": league.sport_id,
                    "region_id": league.region_id,
                    "champ_id": league.champ_id,
                },
            )
        )

    options.sort(key=lambda option: (option.country_name.lower(), option.league_name.lower()))
    return options[:limit]


def _matches_country(country_name: str, country_filter: str) -> bool:
    if not country_filter:
        return True
    normalized = _normalize_text(country_name)
    return country_filter == normalized or country_filter in normalized


def _normalize_text(value: object | None) -> str:
    raw = str(value or "").strip().lower()
    decomposed = unicodedata.normalize("NFKD", raw)
    return "".join(character for character in decomposed if not unicodedata.combining(character))
