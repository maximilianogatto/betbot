"""Mystake prematch HTTP extractor.

A league is a Mystake championship id (``ch``). The full directory — every
sport, country and league (with translated names) plus each league's game ids —
comes from the header tree (``/api/sport/getheader/<region>``), which is served
over plain HTTP with no token. That powers ``/track_league`` discovery: browse
by country, pick a league, done — no URL or manual name needed.

Tracking forms accepted:
  - ``/track_league`` discovery (preferred): ``search_leagues`` -> header tree.
  - ``mystake:champ:<id>`` -> league resolved from the header (name + game ids),
    falling back to the featured ``getprematchtopgames`` feed.
  - a ``getprematchgameall/.../?games=,<ids>`` URL (pasted via ``/track_url``);
    its game ids are fetched directly and the league name is resolved from the
    header by the dominant ``ch``.
  - a ``mystake.bet`` URL carrying ``?ch=<id>``.

Odds are fetched via ``getprematchgameall`` (1X2 + Asian handicap + goal line).
"""

from __future__ import annotations

import asyncio
from collections import Counter
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from core.extractor_base import Extractor, LeagueDiscoveryOption
from core.models import CompetitionExtraction, EventSnapshot, ProviderCapabilities
from extractors.mystake_http import header as header_module
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
    supports_league_discovery = True  # via getheader tree (sports -> regions -> champs)

    # The header (~380KB) lists every league; cache it briefly so a refresh
    # sweep or a discovery search reuses one download instead of one per league.
    _HEADER_TTL_SECONDS = 300.0

    def __init__(self, *, settings: MystakeHttpSettings | None = None) -> None:
        self.settings = settings or load_mystake_settings()
        self._header_cache: dict[str, Any] | None = None
        self._header_cached_at = 0.0
        self._header_lock = asyncio.Lock()

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
            name = await self._resolve_league_name(client, champ_id)
            return build_competition_extraction(
                champ_id=champ_id, raw_response=raw, source_url=url, competition_name=name
            )

        # By championship id: resolve the league (name + full game ids) from the
        # header tree, falling back to the featured topgames feed.
        champ_id = _champ_id_from_url(url)
        if champ_id is None:
            raise ValueError(
                "Could not determine the Mystake league from the URL. Paste a "
                "getprematchgameall '?games=,<ids>' URL, or use 'mystake:champ:<id>'."
            )

        name: str | None = None
        ids: list[int] = []
        try:
            league = header_module.find_champ(
                await self._get_header(client), champ_id=champ_id, sport_id=self.settings.sport_id
            )
        except Exception:  # header is best-effort; fall back to topgames
            league = None
        if league is not None:
            name = f"{league.region_name} · {league.champ_name}" if league.region_name.lower() not in league.champ_name.lower() else league.champ_name
            ids = list(league.game_ids)

        if not ids:
            topgames = await client.fetch_topgames()
            ids = _game_ids_for_champ(topgames, sport_id=self.settings.sport_id, champ_id=champ_id)

        raw = await client.fetch_games(ids)
        return build_competition_extraction(
            champ_id=champ_id, raw_response=raw, source_url=url, competition_name=name
        )

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError(f"{self.name} does not support direct match URLs yet.")

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[LeagueDiscoveryOption]:
        """Discover trackable leagues by country from the header tree."""

        client = MystakeHttpClient(self.settings)
        tree = await self._get_header(client)
        return header_module.build_league_options(
            tree,
            platform=self.name,
            platform_display_name=self.display_name,
            sport_id=self.settings.sport_id,
            country_name=country_name,
            query=query,
            limit=limit,
        )

    async def _resolve_league_name(self, client: MystakeHttpClient, champ_id: str) -> str | None:
        """Best-effort: look up the translated league name for a champ id."""

        if not champ_id or champ_id == "0":
            return None
        try:
            league = header_module.find_champ(
                await self._get_header(client), champ_id=champ_id, sport_id=self.settings.sport_id
            )
        except Exception:
            return None
        if league is None:
            return None
        return f"{league.region_name} · {league.champ_name}" if league.region_name.lower() not in league.champ_name.lower() else league.champ_name

    async def _get_header(self, client: MystakeHttpClient) -> dict[str, Any]:
        """Return the header tree, served from a short-lived in-process cache."""

        async with self._header_lock:
            now = time.monotonic()
            if self._header_cache is not None and (now - self._header_cached_at) < self._HEADER_TTL_SECONDS:
                return self._header_cache
            tree = await client.fetch_header()
            if tree:
                self._header_cache = tree
                self._header_cached_at = now
            return tree

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
