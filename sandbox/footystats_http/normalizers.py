"""Pure parsers for FootyStats public pages and lightweight AJAX payloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.parse import urlparse


_PUBLIC_PAGE_LINK_RE = re.compile(r"^/([a-z0-9-]+)/([a-z0-9-]+)$")
_SCRIPT_AJAX_RE = re.compile(r"\b(ajax_[a-z0-9_-]+\.php)\b", re.IGNORECASE)
_MATCH_IDS_RE = re.compile(
    r"\bvar\s+ziz\s*=\s*(\d+)\s*;\s*var\s+zizz\s*=\s*(\d+)",
    re.IGNORECASE,
)
_MATCH_DATA_RE = re.compile(r"\bvar\s+mh_matchData\s*=\s*(\[.*?\]);", re.DOTALL)
_OFFICIAL_API_RE = re.compile(r"https://api\.football-data-api\.com/[a-z0-9_-]+", re.IGNORECASE)
_RESERVED_FIRST_SEGMENTS = {
    "api",
    "b",
    "bet-calculator",
    "clubs",
    "download-stats-csv",
    "matches",
    "predictions",
    "premium",
    "stats",
}


@dataclass(frozen=True)
class LeagueRef:
    """One league page discovered from the public FootyStats navigation."""

    country_slug: str
    league_slug: str
    name: str
    path: str

    def to_dict(self) -> dict[str, str]:
        """Serialize this immutable reference for JSON reports."""

        return asdict(self)


@dataclass(frozen=True)
class LiveScore:
    """One compact record returned by the public live-score AJAX endpoint."""

    match_id: str
    home_score: int | None
    away_score: int | None
    minute: str | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this immutable live score for JSON reports."""

        return asdict(self)


class _LeagueLinkParser(HTMLParser):
    """Extract public two-segment league links without external dependencies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[LeagueRef] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        match = _PUBLIC_PAGE_LINK_RE.match(href)
        if match is None or match.group(1) in _RESERVED_FIRST_SEGMENTS:
            return
        self._href = href
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._href is None:
            return
        country_slug, league_slug = _PUBLIC_PAGE_LINK_RE.match(self._href).groups()  # type: ignore[union-attr]
        name = " ".join("".join(self._parts).split())
        if name:
            self.links.append(
                LeagueRef(
                    country_slug=country_slug,
                    league_slug=league_slug,
                    name=name,
                    path=self._href,
                )
            )
        self._href = None
        self._parts = []


def discover_league_links(html: str) -> list[LeagueRef]:
    """Return deduplicated league-page links exposed by one FootyStats page.

    The homepage currently renders the global country -> league navigation in
    HTML, so discovery does not require browser automation or private JSON.
    """

    parser = _LeagueLinkParser()
    parser.feed(html)
    unique: dict[str, LeagueRef] = {}
    for link in parser.links:
        unique.setdefault(link.path, link)
    return sorted(unique.values(), key=lambda item: (item.country_slug, item.name, item.path))


def parse_live_scores(payload: Any) -> list[LiveScore]:
    """Normalize the public ``ajax_livescore.php`` JSON response."""

    if not isinstance(payload, list):
        return []
    scores: list[LiveScore] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("match_id") is None:
            continue
        scores.append(
            LiveScore(
                match_id=str(item["match_id"]),
                home_score=_as_int(item.get("team_a_score")),
                away_score=_as_int(item.get("team_b_score")),
                minute=_as_optional_text(item.get("minute")),
            )
        )
    return scores


def extract_match_page_ids(html: str) -> dict[str, str | None]:
    """Extract public match and competition IDs used by live AJAX polling."""

    match = _MATCH_IDS_RE.search(html)
    if match is None:
        return {"match_id": None, "competition_id": None}
    return {"match_id": match.group(1), "competition_id": match.group(2)}


def extract_embedded_match_data(html: str) -> list[dict[str, Any]]:
    """Parse the compact ``mh_matchData`` array embedded in league HTML."""

    match = _MATCH_DATA_RE.search(html)
    if match is None:
        return []
    # FootyStats currently emits JavaScript arrays with a trailing comma. They
    # are valid in the browser but need a small cleanup before strict JSON.
    serialized = re.sub(r",\s*([}\]])", r"\1", match.group(1))
    try:
        value = json.loads(serialized)
    except json.JSONDecodeError:
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def extract_script_ajax_endpoints(script_text: str) -> list[str]:
    """Return AJAX PHP endpoints referenced by FootyStats frontend code."""

    return sorted({match.group(1).lower() for match in _SCRIPT_AJAX_RE.finditer(script_text)})


def extract_official_api_endpoints(html: str) -> list[str]:
    """Return documented official API endpoint URLs without query strings."""

    return sorted(set(_OFFICIAL_API_RE.findall(html)))


def parse_match_live_panel(html: str) -> dict[str, Any]:
    """Extract the public live score and live stat table from one match page.

    FootyStats renders this panel server-side for live matches. Missing data is
    represented as ``None`` or an empty mapping rather than guessed values.
    """

    ids = extract_match_page_ids(html)
    score_match = re.search(
        r"<p class='ac fs2e bold'>\s*(\d+)\s*<span[^>]*>\s*-\s*</span>\s*(\d+)"
        r"</p><p class='ac semi-bold mt05'>([^<]*)",
        html,
        flags=re.DOTALL,
    )
    stats: dict[str, dict[str, str]] = {}
    stats_source = ""
    if score_match is not None:
        section_start = html.rfind("<section", 0, score_match.start())
        section_end = html.find("</section>", score_match.end())
        stats_source = (
            html[section_start : section_end + len("</section>")]
            if section_start >= 0 and section_end >= 0
            else html
        )
    for label, home_value, away_value in re.findall(
        r"<tr class='row'><td class='item key'[^>]*>(.*?)</td>"
        r"<td class='item stat[^']*'>(.*?)</td><td class='item stat[^']*'>(.*?)</td></tr>",
        stats_source,
        flags=re.DOTALL,
    ):
        stats[_strip_tags(label)] = {
            "home": _strip_tags(home_value),
            "away": _strip_tags(away_value),
        }
    return {
        **ids,
        "is_live_panel_present": score_match is not None,
        "score_home": _as_int(score_match.group(1)) if score_match else None,
        "score_away": _as_int(score_match.group(2)) if score_match else None,
        "minute": _strip_tags(score_match.group(3)).replace("'", "") if score_match else None,
        "stats": stats,
    }


def classify_url(url: str) -> str:
    """Classify one FootyStats-related URL by its stability contract."""

    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host == "api.football-data-api.com":
        return "official_api"
    if host.endswith("footystats.org") and parsed.path.startswith("/ajax_"):
        return "public_ajax"
    if host.endswith("footystats.org"):
        return "public_html"
    return "external"


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _strip_tags(value: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", "", value)).split())
