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
        if "-vs-" in href or href.endswith("-h2h-stats"):
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
    "normalize_public_match_h2h",
]


def normalize_public_match_h2h(html: str) -> dict[str, Any]:
    """Parse public FootyStats match H2H page HTML into structured stats."""

    # 1. Parse basic team stats (Overall/Home/Away form & PPG)
    teams = _parse_team_stats(html)
    if len(teams) < 2:
        return {}
    home_team = teams[0]
    away_team = teams[1]

    # 2. Parse mini tables (standings stats: mp, win_rate, gf, ga, gd, pts, avg_goals)
    mini_tables = _parse_mini_tables_stats(html, home_team.get("id", ""), away_team.get("id", ""))

    # 3. Parse market probabilities
    markets = _parse_market_stats(html)

    # 4. Parse historical fixtures
    fixtures = _parse_h2h_fixtures(html)

    # 5. Parse H2H tendencies
    h2h_sec_start = -1
    for match in re.finditer(r"<section[^>]*h2h-widget-neo", html):
        h2h_sec_start = match.start()
        break
    if h2h_sec_start == -1:
        h2h_sec_start = html.find("h2h-widget-neo")

    h2h_tendencies: dict[str, int] = {}
    h2h_summary = ""
    if h2h_sec_start != -1:
        content = html[h2h_sec_start:h2h_sec_start + 4000]
        # Match grid-items with stats
        pattern = r"<div class=['\"]grid-item has-indicator[^'\"]*['\"][^>]*><div class=['\"]stat-strong['\"]>(\d+)%<span>([^<]+)</span></div><div class=['\"]stat-text['\"]>([^<]+)</div></div>"
        matches = re.finditer(pattern, content)
        clean_sheets_count = 0
        for m in matches:
            val = int(m.group(1))
            label = m.group(2).strip().lower().replace(" ", "_")
            if label == "clean_sheets":
                clean_sheets_count += 1
                if clean_sheets_count == 1:
                    h2h_tendencies["home_clean_sheets"] = val
                else:
                    h2h_tendencies["away_clean_sheets"] = val
            else:
                h2h_tendencies[label] = val

        # Parse trailing summary text
        summary_match = re.search(r"<p class='h2h-trailing-text[^']*'[^>]*>(.*?)</p>", content, re.DOTALL)
        if summary_match:
            h2h_summary = " ".join(unescape(re.sub(r"<[^>]+>", "", summary_match.group(1))).split())

    return {
        "home": home_team,
        "away": away_team,
        "mini_tables": mini_tables,
        "markets": markets,
        "fixtures": fixtures,
        "h2h_tendencies": h2h_tendencies,
        "h2h_summary": h2h_summary
    }


def _parse_team_stats(html: str) -> list[dict[str, Any]]:
    pos_matches = list(re.finditer(r"League Pos\.\s*<span class='semi-bold'>(\d+)</span>\s*/\s*(\d+)", html))
    teams_data: list[dict[str, Any]] = []
    
    for i, m in enumerate(pos_matches):
        pos_start = m.start()
        header_text = html[max(0, pos_start - 600):pos_start]
        team_link_match = re.search(
            r"href='/clubs/[a-z0-9-]+-(\d+)'[^>]*>(?:<span[^>]*>.*?</span>)?\s*([^<]+)</a>",
            header_text
        )
        team_name = team_link_match.group(2).strip() if team_link_match else f"Team {i+1}"
        team_id = team_link_match.group(1).strip() if team_link_match else ""
        
        pos = int(m.group(1))
        pos_total = int(m.group(2))
        
        form_text = html[m.end():m.end() + 1500]
        form_block_match = re.search(r"neo-border-all.*?</div>\s*</div>\s*</div>\s*</div>", form_text, re.DOTALL)
        
        forms: dict[str, dict[str, Any]] = {}
        if form_block_match:
            block = form_block_match.group(0)
            row_matches = re.finditer(
                r"<div class=['\"]section1 cf bbox['\"]><div class=['\"]col1 dark-gray semi-bold fl ac['\"]>([^<]+)</div><div class=['\"]col2 dark-gray fl ac['\"]><ul class=['\"]form-run['\"]>(.*?)</ul></div><div class=['\"]col3 dark-gray fl ac['\"]><div class=['\"]form-box(?: [^\"]*)?['\"]>([\d\.]+)</div></div></div>",
                block,
                re.DOTALL
            )
            for row in row_matches:
                row_type = row.group(1).strip()
                form_lis = re.findall(r"<li class='form-run [^']*'>([WDL])</li>", row.group(2))
                try:
                    ppg = float(row.group(3))
                except ValueError:
                    ppg = 0.0
                forms[row_type.lower()] = {
                    "form": "".join(form_lis),
                    "ppg": ppg
                }
        
        teams_data.append({
            "name": team_name,
            "id": team_id,
            "league_pos": pos,
            "league_pos_total": pos_total,
            "stats": forms
        })
        
    return teams_data


def _parse_market_stats(html: str) -> dict[str, Any]:
    table_match = re.search(r"<table class='[^']*stats-to-odds-table'>(.*?)</table>", html, re.DOTALL)
    if not table_match:
        return {}
    
    table_content = table_match.group(1)
    rows = re.findall(r"<tr>(.*?)</tr>", table_content, re.DOTALL)
    markets = {}
    for row in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(tds) >= 3:
            market_name = re.sub(r"<[^>]+>", "", tds[0]).strip()
            stat_val = re.sub(r"<[^>]+>", "", tds[2]).strip()
            stat_val = stat_val.replace("%", "").strip()
            
            key = market_name.lower().replace(" ", "_")
            markets[key] = {
                "name": market_name,
                "value": stat_val
            }
    return markets


def _parse_h2h_fixtures(html: str) -> list[dict[str, Any]]:
    sliding_idx = html.find("class='sliding-fixtures")
    if sliding_idx == -1:
        sliding_idx = html.find('class="sliding-fixtures')
    if sliding_idx == -1:
        return []
    
    content = html[sliding_idx:sliding_idx + 15000]
    anchors = re.findall(r"<a href='#' class='fixture[^']*'.*?</a>", content, re.DOTALL)
    fixtures = []
    
    for anchor in anchors:
        time_match = re.search(r"<time[^>]*datetime='([^']*)'[^>]*>(.*?)</time>", anchor)
        dt = time_match.group(1) if time_match else ""
        date_str = time_match.group(2).strip() if time_match else ""
        
        divs = re.findall(r"<div class='team[^']*'>(.*?)</div>", anchor, re.DOTALL)
        if len(divs) >= 2:
            teams = []
            for div in divs:
                span_match = re.search(r"(.*?)\s*<span>(\d+)</span>", div)
                if span_match:
                    name = re.sub(r"<[^>]+>", "", span_match.group(1)).strip()
                    try:
                        score = int(span_match.group(2))
                    except ValueError:
                        score = 0
                    teams.append({"name": name, "score": score})
                else:
                    teams.append({"name": div.strip(), "score": 0})
            
            fixtures.append({
                "datetime": dt,
                "date_display": date_str,
                "home": teams[0]["name"],
                "home_score": teams[0]["score"],
                "away": teams[1]["name"],
                "away_score": teams[1]["score"]
            })
            
    return fixtures


def _parse_mini_tables_stats(html: str, home_id: str, away_id: str) -> dict[str, dict[str, Any]]:
    tables = re.findall(r"<table[^>]*class=['\"][^'\"]*miniTableNeo[^'\"]*['\"][^>]*>(.*?)</table>", html, re.DOTALL)
    
    stats = {
        "home": {"home": {}, "away": {}, "overall": {}},
        "away": {"home": {}, "away": {}, "overall": {}}
    }
    
    if len(tables) < 3:
        return stats
        
    table_types = ["home", "away", "overall"]
    
    for i, table_type in enumerate(table_types):
        table_content = tables[i]
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_content, re.DOTALL)
        for row in rows:
            club_match = re.search(r"href=['\"]/clubs/[a-z0-9-]+-(\d+)['\"]", row)
            if not club_match:
                continue
            row_team_id = club_match.group(1)
            
            target = None
            if home_id and row_team_id == home_id:
                target = stats["home"][table_type]
            elif away_id and row_team_id == away_id:
                target = stats["away"][table_type]
            else:
                continue
                
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            cleaned_tds = [" ".join(unescape(re.sub(r"<[^>]+>", "", td)).split()).strip() for td in tds]
            if len(cleaned_tds) >= 9:
                try:
                    target["pos"] = int(cleaned_tds[0])
                except ValueError:
                    target["pos"] = cleaned_tds[0]
                try:
                    target["mp"] = int(cleaned_tds[2])
                except ValueError:
                    target["mp"] = 0
                target["win_rate"] = cleaned_tds[3]
                try:
                    target["gf"] = int(cleaned_tds[4])
                except ValueError:
                    target["gf"] = 0
                try:
                    target["ga"] = int(cleaned_tds[5])
                except ValueError:
                    target["ga"] = 0
                target["gd"] = cleaned_tds[6]
                try:
                    target["pts"] = int(cleaned_tds[7])
                except ValueError:
                    target["pts"] = 0
                target["avg_goals"] = cleaned_tds[8]
                
    return stats

