"""Pure defensive parsers for FootyStats public HTML fallback pages."""

from __future__ import annotations

from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any


_LEAGUE_LINK_RE = re.compile(r"^/([a-z0-9-]+)/([a-z0-9-]+)$")
_MATCH_DATA_RE = re.compile(r"\bvar\s+mh_matchData\s*=\s*(\[.*?\]);", re.DOTALL)
_TEAM_LINK_RE = re.compile(
    r"href='/clubs/([a-z0-9-]+)-(\d+)'[^>]*>(?:<span itemprop='name'>)?([^<]+)",
    re.IGNORECASE,
)
_RESERVED_SEGMENTS = {"api", "b", "bet-calculator", "clubs", "matches", "predictions", "premium", "stats"}


class _LeagueLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._path: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        match = _LEAGUE_LINK_RE.match(href)
        if match is None or match.group(1) in _RESERVED_SEGMENTS:
            return
        self._path = href
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._path is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._path is None:
            return
        match = _LEAGUE_LINK_RE.match(self._path)
        if match is not None:
            name = " ".join("".join(self._parts).split())
            if name:
                self.links.append(
                    {
                        "league_id": self._path.lstrip("/"),
                        "country_slug": match.group(1),
                        "league_slug": match.group(2),
                        "league_name": name,
                        "source_path": self._path,
                    }
                )
        self._path = None
        self._parts = []


def discover_public_leagues(html: str) -> list[dict[str, str]]:
    """Extract deduplicated country/league navigation records."""

    parser = _LeagueLinkParser()
    parser.feed(html)
    unique = {item["league_id"]: item for item in parser.links}
    return sorted(unique.values(), key=lambda item: (item["country_slug"], item["league_name"]))


def normalize_public_fixtures(html: str, league_id: str) -> list[dict[str, Any]]:
    """Normalize embedded fixtures into compact provider-native records."""

    teams = _extract_teams(html)
    match = _MATCH_DATA_RE.search(html)
    if match is None:
        return []
    serialized = re.sub(r",\s*([}\]])", r"\1", match.group(1))
    try:
        payload = json.loads(serialized)
    except json.JSONDecodeError:
        return []
    country_slug = league_id.strip("/").split("/", 1)[0]
    fixtures: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        home = teams.get(str(item.get("matchHomeID")), {})
        away = teams.get(str(item.get("matchAwayID")), {})
        source_path = _match_path(country_slug, home.get("slug"), away.get("slug"))
        fixtures.append(
            {
                "match_id": str(item["id"]),
                "provider_match_id": f"public:{source_path}#{item['id']}" if source_path else str(item["id"]),
                "league_id": league_id.strip("/"),
                "home": home.get("name") or f"Team {item.get('matchHomeID')}",
                "home_id": str(item.get("matchHomeID") or ""),
                "away": away.get("name") or f"Team {item.get('matchAwayID')}",
                "away_id": str(item.get("matchAwayID") or ""),
                "start_time_utc": _timestamp_iso(item.get("date")),
                "status": str(item.get("status") or "unknown"),
                "stats_path": source_path,
            }
        )
    fixtures.sort(key=lambda item: item.get("start_time_utc") or "")
    return fixtures


def normalize_public_standings(html: str) -> dict[str, Any]:
    """Normalize the first public league table into BetBot's overview shape."""

    marker = "full-league-table"
    start = html.find(marker)
    if start < 0:
        return {"tables": []}
    end = html.find("</table>", start)
    table = html[start:end] if end >= 0 else html[start:]
    rows: list[dict[str, Any]] = []
    for row_html in re.findall(r"<tr class='[^']*'>(.*?)</tr>", table, flags=re.DOTALL):
        team_match = re.search(r"data-team-id='(\d+)'[^>]*>([^<]+)</a>", row_html)
        if team_match is None:
            continue
        rows.append(
            {
                "position": _cell_int(row_html, "position"),
                "played": _cell_int(row_html, "mp"),
                "wins": _cell_int(row_html, "win"),
                "draws": _cell_int(row_html, "draw"),
                "losses": _cell_int(row_html, "loss"),
                "goals_for": _cell_int(row_html, "gf"),
                "goals_against": _cell_int(row_html, "ga"),
                "goal_difference": _cell_text(row_html, "gd"),
                "points": _cell_int(row_html, "points"),
                "ppg": _cell_float(row_html, "ppg"),
                "clean_sheet_rate": _cell_text(row_html, "cs"),
                "btts_rate": _cell_text(row_html, "btts"),
                "over25_rate": _cell_text(row_html, "over25"),
                "avg_goals": _cell_float(row_html, "avg"),
                "team": {"id": team_match.group(1), "name": _strip_tags(team_match.group(2))},
            }
        )
    return {"tables": [{"name": "Tabla", "rows": rows}] if rows else []}


def normalize_live_scores(payload: Any) -> list[dict[str, Any]]:
    """Normalize the low-cost public live feed."""

    normalized: list[dict[str, Any]] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict) or item.get("match_id") is None:
            continue
        normalized.append(
            {
                "match_id": str(item["match_id"]),
                "score_home": _as_int(item.get("team_a_score")),
                "score_away": _as_int(item.get("team_b_score")),
                "minute": item.get("minute"),
            }
        )
    return normalized


def decode_public_match_id(stats_match_id: str) -> tuple[str | None, str]:
    """Return public path and numeric ID from one encoded provider match ID."""

    value = stats_match_id.removeprefix("public:")
    if "#" not in value:
        return None, value
    path, numeric_id = value.rsplit("#", 1)
    return path or None, numeric_id


def match_title_from_path(path: str | None) -> str:
    """Build a readable fallback title from a public H2H path."""

    slug = (path or "").strip("/").split("/")[-1].removesuffix("-h2h-stats")
    parts = slug.split("-vs-", 1)
    if len(parts) != 2:
        return "Partido FootyStats"
    return " vs ".join(part.replace("-", " ").title() for part in parts)


def _extract_teams(html: str) -> dict[str, dict[str, str]]:
    teams: dict[str, dict[str, str]] = {}
    for slug, team_id, name in _TEAM_LINK_RE.findall(html):
        teams.setdefault(team_id, {"id": team_id, "slug": slug, "name": _strip_tags(name)})
    return teams


def _match_path(country_slug: str, home_slug: str | None, away_slug: str | None) -> str | None:
    if not home_slug or not away_slug:
        return None
    return f"/{country_slug}/{home_slug}-vs-{away_slug}-h2h-stats"


def _cell_text(row_html: str, class_name: str) -> str | None:
    match = re.search(rf"<td class='{class_name}(?: [^']*)?'[^>]*>(.*?)</td>", row_html, flags=re.DOTALL)
    return _strip_tags(match.group(1)) if match else None


def _cell_int(row_html: str, class_name: str) -> int | None:
    return _as_int(_cell_text(row_html, class_name))


def _cell_float(row_html: str, class_name: str) -> float | None:
    try:
        value = _cell_text(row_html, class_name)
        return float(value) if value is not None else None
    except ValueError:
        return None


def _timestamp_iso(value: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _strip_tags(value: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", "", value)).split())


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "decode_public_match_id",
    "discover_public_leagues",
    "match_title_from_path",
    "normalize_live_scores",
    "normalize_public_fixtures",
    "normalize_public_standings",
]
