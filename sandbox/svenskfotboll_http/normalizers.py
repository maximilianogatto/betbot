"""Pure parsers for Svenskfotboll HTTP responses.

The Swedish FA site exposes useful JSON and XML endpoints, but league table and
league fixture widgets return JSON with an embedded HTML table.  These helpers
turn those payloads into compact, JSON-serializable dictionaries without adding
third-party parser dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from html.parser import HTMLParser
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class TableCell:
    """One HTML table cell plus links found inside that cell."""

    text: str
    links: tuple[str, ...] = ()


@dataclass(frozen=True)
class TableRow:
    """One normalized HTML table row."""

    cells: tuple[TableCell, ...]

    @property
    def texts(self) -> list[str]:
        return [cell.text for cell in self.cells]

    @property
    def links(self) -> list[str]:
        return [link for cell in self.cells for link in cell.links]


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[TableRow] = []
        self._current_row: list[TableCell] | None = None
        self._current_cell_text: list[str] | None = None
        self._current_cell_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value for key, value in attrs}
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell_text = []
            self._current_cell_links = []
        elif tag == "a" and self._current_cell_text is not None:
            href = attr_map.get("href")
            if href:
                self._current_cell_links.append(href)

    def handle_data(self, data: str) -> None:
        if self._current_cell_text is not None:
            self._current_cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_cell_text is not None and self._current_row is not None:
            text = _clean_text("".join(self._current_cell_text))
            self._current_row.append(TableCell(text=text, links=tuple(self._current_cell_links)))
            self._current_cell_text = None
            self._current_cell_links = []
        elif tag == "tr" and self._current_row is not None:
            if any(cell.text for cell in self._current_row):
                self.rows.append(TableRow(cells=tuple(self._current_row)))
            self._current_row = None


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def parse_widget_table(html: str) -> list[TableRow]:
    """Parse the HTML table returned by ``/widget.aspx``.

    Args:
        html: Raw HTML string from ``{"html": "..."}``.

    Returns:
        Table rows with text and per-cell links.  Empty rows are omitted.
    """

    parser = _TableHTMLParser()
    parser.feed(html or "")
    return parser.rows


def rows_to_json(rows: list[TableRow]) -> list[dict[str, Any]]:
    """Serialize table rows for debug/report files."""

    return [asdict(row) for row in rows]


def extract_id_from_links(links: list[str], key: str) -> str | None:
    """Return the first query-string id matching ``key`` from row links."""

    for link in links:
        parsed = urlparse(link)
        values = parse_qs(parsed.query).get(key)
        if values:
            return str(values[0])
    return None


def parse_competition_tree(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten ``/api/comp-find/filter`` into unique competition records."""

    records: dict[str, dict[str, Any]] = {}
    for group in payload.get("competitions", []) if isinstance(payload, dict) else []:
        for comp in group.get("comps", []) or []:
            comp_id = str(comp.get("id") or "")
            if not comp_id:
                continue
            current = records.setdefault(
                comp_id,
                {
                    "competition_id": comp_id,
                    "name": comp.get("name") or "",
                    "source_url": comp.get("url") or f"/go-to/?ftid={comp_id}",
                    "categories": [],
                    "association_ids": set(),
                    "gender_ids": set(),
                    "age_category_ids": set(),
                    "football_type_ids": set(),
                    "type_ids": set(),
                },
            )
            current["categories"].append(group.get("category") or "")
            _add_set_value(current["association_ids"], group.get("associationId"))
            _add_set_value(current["gender_ids"], group.get("genderId"))
            _add_set_value(current["age_category_ids"], group.get("ageCategoryId"))
            _add_set_value(current["football_type_ids"], group.get("footballTypeId"))
            _add_set_value(current["type_ids"], group.get("typeId"))

    normalized = []
    for record in records.values():
        item = dict(record)
        item["categories"] = sorted({value for value in item["categories"] if value})
        for key in ("association_ids", "gender_ids", "age_category_ids", "football_type_ids", "type_ids"):
            item[key] = sorted(str(value) for value in item[key] if value is not None and value != "")
        normalized.append(item)
    return sorted(normalized, key=lambda item: (item.get("name") or "").lower())


def _add_set_value(target: set[Any], value: Any) -> None:
    if value is not None and value != "":
        target.add(value)


def search_competitions(
    competitions: list[dict[str, Any]],
    query: str | None = None,
    association_id: str | int | None = None,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Filter flattened competitions by free text and optional association id."""

    terms = [term.casefold() for term in (query or "").split() if term.strip()]
    association = str(association_id) if association_id is not None else None
    results: list[dict[str, Any]] = []
    for item in competitions:
        haystack = " ".join(
            [
                item.get("name") or "",
                " ".join(item.get("categories") or []),
                " ".join(item.get("type_ids") or []),
            ]
        ).casefold()
        if terms and not all(term in haystack for term in terms):
            continue
        if association and association not in [str(value) for value in item.get("association_ids", [])]:
            continue
        results.append(item)
        if len(results) >= limit:
            break
    return results


def parse_standings_widget(html: str, competition_id: str | int) -> dict[str, Any]:
    """Normalize ``scr=tablesmall`` widget HTML."""

    rows = parse_widget_table(html)
    title = rows[0].texts[0] if rows else ""
    teams: list[dict[str, Any]] = []
    for row in rows:
        texts = row.texts
        if len(texts) != 4 or texts[0] in {"Lag", "Gå till detaljerad tabell på svenskfotboll.se"}:
            continue
        teams.append(
            {
                "team": texts[0],
                "played": _to_int(texts[1]),
                "goal_difference": _to_int(texts[2]),
                "points": _to_int(texts[3]),
                "team_id": extract_id_from_links(row.links, "flid"),
            }
        )
    return {
        "competition_id": str(competition_id),
        "title": title,
        "teams": teams,
        "raw_row_count": len(rows),
    }


def parse_matches_widget(html: str, competition_id: str | int, *, result_rows: bool) -> dict[str, Any]:
    """Normalize ``cominginleague`` or ``latestinleague`` widget HTML."""

    rows = parse_widget_table(html)
    title = rows[0].texts[0] if rows else ""
    matches: list[dict[str, Any]] = []
    for row in rows:
        texts = row.texts
        if len(texts) < 2 or texts[0] in {"Tid", "Gå till spelprogram på svenskfotboll.se"}:
            continue
        home, away = _split_match_name(texts[1])
        match = {
            "match_id": extract_id_from_links(row.links, "fmid"),
            "start_time_local": texts[0],
            "home": home,
            "away": away,
        }
        if result_rows and len(texts) >= 3:
            match["score"] = texts[2]
        matches.append(match)
    return {
        "competition_id": str(competition_id),
        "title": title,
        "matches": matches,
        "raw_row_count": len(rows),
    }


def parse_matches_today(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize ``/api/matches-today/games`` JSON."""

    records: list[dict[str, Any]] = []
    for competition in payload.get("competitions", []) if isinstance(payload, dict) else []:
        for game in competition.get("games", []) or []:
            records.append(
                {
                    "match_id": str(game.get("gameId") or ""),
                    "competition_id": str(competition.get("competitionId") or ""),
                    "competition_name": competition.get("name") or "",
                    "home": (game.get("homeTeam") or {}).get("name") or "",
                    "away": (game.get("awayTeam") or {}).get("name") or "",
                    "start_time_local": game.get("date") or "",
                    "date_formatted": game.get("dateFormatted") or "",
                    "location": game.get("location") or "",
                    "score": game.get("score") or {},
                    "status": game.get("status"),
                    "url": game.get("url") or "",
                }
            )
    return records


def parse_livescore_ticker(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize ``/api/livescore-ticker/`` JSON."""

    games: list[dict[str, Any]] = []
    for game in payload.get("games", []) if isinstance(payload, dict) else []:
        home = game.get("homeTeam") or {}
        away = game.get("awayTeam") or {}
        games.append(
            {
                "match_id": str(game.get("id") or ""),
                "url": game.get("url") or "",
                "is_live": bool(game.get("isLive")),
                "is_finished": bool(game.get("isFinished")),
                "is_today": bool(game.get("isToday")),
                "start_time_local": (game.get("dateTime") or {}).get("raw") or "",
                "home": home.get("abbr") or home.get("name") or "",
                "away": away.get("abbr") or away.get("name") or "",
                "score_home": home.get("score"),
                "score_away": away.get("score"),
            }
        )
    return games


def parse_live_overview_xml(xml_text: str) -> dict[str, Any]:
    """Normalize FOGIS ``overview-<association>-<yyyymmdd>.xml``."""

    root = ET.fromstring(xml_text)
    games = [_parse_game_node(node) for node in root.findall(".//game")]
    return {
        "created_at": root.attrib.get("created"),
        "status": root.attrib.get("status"),
        "games": games,
    }


def parse_game_info_xml(xml_text: str) -> dict[str, Any]:
    """Normalize FOGIS ``game-info-<match_id>.xml``.

    Event type codes observed so far include ``G`` for goals, ``C`` for corners,
    and status descriptions such as ``HALFTIME``.  Red cards are exposed in both
    event stream and aggregate stats when coverage is available.
    """

    root = ET.fromstring(xml_text)
    game_node = root.find(".//game")
    if game_node is None:
        return {"status": root.attrib.get("status"), "events": [], "stats": {}}
    game = _parse_game_node(game_node)
    stats_node = game_node.find("stats")
    game["stats"] = dict(stats_node.attrib) if stats_node is not None else {}
    game["events"] = [dict(event.attrib) for event in game_node.findall(".//events/event")]
    game["event_summary"] = summarize_live_events(game["events"])
    return game


def summarize_live_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize important live events for bot alerts."""

    goals = [event for event in events if event.get("type") in {"G", "PG", "PENALTY_GOAL"}]
    red_cards = [event for event in events if "RED" in (event.get("type") or "").upper() or "red" in (event.get("type-desc") or "").casefold()]
    corners = [event for event in events if event.get("type") == "C"]
    return {
        "goals": len(goals),
        "red_cards": len(red_cards),
        "corners": len(corners),
        "latest_event": events[0] if events else None,
    }


def _parse_game_node(game_node: ET.Element) -> dict[str, Any]:
    teams = game_node.findall(".//teams/team")
    home_team = next((team for team in teams if team.attrib.get("home-team") == "true"), None)
    away_team = next((team for team in teams if team.attrib.get("home-team") == "false"), None)
    status_node = game_node.find("status")
    score_node = game_node.find("score")
    tournament_node = game_node.find("tournament")
    return {
        "match_id": game_node.attrib.get("id"),
        "competition_id": game_node.attrib.get("competition-id") or (tournament_node.attrib.get("id") if tournament_node is not None else None),
        "competition_name": tournament_node.attrib.get("name") if tournament_node is not None else None,
        "date": game_node.attrib.get("date"),
        "start": game_node.attrib.get("start"),
        "home": _team_from_node(home_team),
        "away": _team_from_node(away_team),
        "status": dict(status_node.attrib) if status_node is not None else {},
        "score": dict(score_node.attrib) if score_node is not None else {},
    }


def _team_from_node(node: ET.Element | None) -> dict[str, Any]:
    if node is None:
        return {}
    return {
        "team_id": node.attrib.get("id"),
        "name": node.attrib.get("long-name") or node.attrib.get("name") or node.attrib.get("short-name"),
        "short_name": node.attrib.get("short-name"),
        "participation_id": node.attrib.get("participationId"),
    }


def _split_match_name(value: str) -> tuple[str, str]:
    parts = re.split(r"\s+-\s+", value, maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return value, ""


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).replace("+", "").strip())
    except (TypeError, ValueError):
        return None


__all__ = [
    "TableCell",
    "TableRow",
    "extract_id_from_links",
    "parse_competition_tree",
    "parse_game_info_xml",
    "parse_live_overview_xml",
    "parse_livescore_ticker",
    "parse_matches_today",
    "parse_matches_widget",
    "parse_standings_widget",
    "parse_widget_table",
    "rows_to_json",
    "search_competitions",
    "summarize_live_events",
]

