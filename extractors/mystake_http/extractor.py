"""Mystake prematch HTTP extractor.

A league is a Mystake championship id (``ch``). The recommended way to track an
arbitrary league (incl. non-featured ones) is to paste, via ``/track_url``, the
``getprematchgameall/...?games=,<ids>`` URL the site fires when viewing that
league — it carries that league's game ids. The extractor parses those ids,
fetches their odds (``gameall`` works server-side) and groups them by ``ch``;
refreshing re-fetches the same ids for fresh odds.

Tracking forms accepted:
  - a ``getprematchgameall/.../?games=,<ids>`` URL (recommended, any league)
  - ``mystake:champ:<id>`` -> featured/main-league games via ``getprematchtopgames``
  - a ``mystake.bet`` URL carrying ``?ch=<id>``
"""

from __future__ import annotations

from collections import Counter
import re
from urllib.parse import parse_qs, urlparse

from core.extractor_base import Extractor
from core.models import CompetitionExtraction, EventSnapshot, ProviderCapabilities
from extractors.mystake_http.client import MystakeHttpClient
from extractors.mystake_http.parser import build_competition_extraction, decode_json_field
from extractors.mystake_http.settings import MystakeHttpSettings, load_mystake_settings

_SUPPORTED_HOSTS = ("mystake.bet", "analytics-sp.googleserv.tech")
_CHAMP_SCHEME_RE = re.compile(r"^mystake:champ:(\d+)$", re.IGNORECASE)


class MystakeHttpExtractor(Extractor):
    """HTTP extractor for Mystake prematch soccer leagues (championship id)."""

    name = "mystake_http"
    display_name = "Mystake HTTP"
    supported_domains = _SUPPORTED_HOSTS
    supported_capabilities = ("ligas",)
    provider_capabilities = ProviderCapabilities(supports_http=True, supports_browserless=True)
    supports_league_discovery = False  # finalized once league names/tree are captured

    def __init__(self, *, settings: MystakeHttpSettings | None = None) -> None:
        self.settings = settings or load_mystake_settings()

    @classmethod
    def can_handle_url(cls, url: str) -> bool:
        normalized = (url or "").strip().lower()
        if _CHAMP_SCHEME_RE.match(normalized):
            return True
        if "getprematchgameall" in normalized:
            return True
        host = urlparse(normalized).netloc
        return any(domain in host for domain in _SUPPORTED_HOSTS)

    async def extract_league(self, url: str) -> CompetitionExtraction:
        if not self.can_handle_url(url):
            raise ValueError(f"{self.name} cannot handle URL: {url}")
        client = MystakeHttpClient(self.settings)

        # Preferred: a getprematchgameall URL carrying the league's game ids.
        game_ids = _game_ids_from_gameall_url(url)
        if game_ids:
            raw = await client.fetch_games(game_ids)
            champ_id = _dominant_champ_id(raw) or "0"
            return build_competition_extraction(champ_id=champ_id, raw_response=raw, source_url=url)

        # Fallback: featured leagues by championship id via topgames.
        champ_id = _champ_id_from_url(url)
        if champ_id is None:
            raise ValueError(
                "Could not determine the Mystake league from the URL. Paste a "
                "getprematchgameall '?games=,<ids>' URL, or use 'mystake:champ:<id>'."
            )
        topgames = await client.fetch_topgames()
        ids = _game_ids_for_champ(topgames, sport_id=self.settings.sport_id, champ_id=champ_id)
        raw = await client.fetch_games(ids)
        return build_competition_extraction(champ_id=champ_id, raw_response=raw, source_url=url)

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError(f"{self.name} does not support direct match URLs yet.")

    def build_competition_url(self, *, competition_external_id, source_url=None, metadata=None) -> str | None:
        del source_url, metadata
        return f"mystake:champ:{competition_external_id}"


def _game_ids_from_gameall_url(url: str) -> list[int]:
    """Parse the ``games=,a,b,c`` id list from a getprematchgameall URL."""

    if "getprematchgameall" not in (url or "").lower():
        return []
    raw = parse_qs(urlparse(url).query).get("games", [""])[0]
    ids: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if token.isdigit():
            ids.append(int(token))
    return ids


def _dominant_champ_id(raw_response: dict) -> str | None:
    """Return the most common championship id (``ch``) among the games."""

    games = decode_json_field(raw_response.get("game")) if isinstance(raw_response, dict) else []
    counts = Counter(str(g.get("ch")) for g in games or [] if isinstance(g, dict) and g.get("ch") is not None)
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _champ_id_from_url(url: str) -> str | None:
    normalized = (url or "").strip()
    scheme_match = _CHAMP_SCHEME_RE.match(normalized.lower())
    if scheme_match:
        return scheme_match.group(1)
    query = parse_qs(urlparse(normalized).query)
    for key in ("ch", "champ", "league", "tournament"):
        values = query.get(key)
        if values and str(values[0]).isdigit():
            return str(values[0])
    return None


def _game_ids_for_champ(topgames: list, *, sport_id: int, champ_id: str) -> list[int]:
    """Collect game ids belonging to a championship from the topgames feed."""

    ids: list[int] = []
    for sport in topgames or []:
        if not isinstance(sport, dict) or sport.get("id") != sport_id:
            continue
        for entry in sport.get("gmsi") or []:
            if isinstance(entry, dict) and str(entry.get("ch")) == str(champ_id):
                game_id = entry.get("id")
                if game_id is not None:
                    ids.append(int(game_id))
    return ids
