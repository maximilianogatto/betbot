"""Mystake prematch HTTP extractor.

A league is a Mystake championship id (``ch``). ``extract_league`` discovers the
league's game ids from ``getprematchtopgames`` and fetches their odds via
``getprematchgameall``. This covers the featured/main-league set; full
non-featured listings + league names need the per-league tree (a future capture).

Tracking forms accepted:
  - ``mystake:champ:<id>``  (explicit)
  - a ``mystake.bet`` URL carrying ``?ch=<id>`` (or league/champ/tournament)
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from core.extractor_base import Extractor
from core.models import CompetitionExtraction, EventSnapshot, ProviderCapabilities
from extractors.mystake_http.client import MystakeHttpClient
from extractors.mystake_http.parser import build_competition_extraction
from extractors.mystake_http.settings import MystakeHttpSettings, load_mystake_settings

_SUPPORTED_HOSTS = ("mystake.bet",)
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
        host = urlparse(normalized).netloc
        return any(domain in host for domain in _SUPPORTED_HOSTS)

    async def extract_league(self, url: str) -> CompetitionExtraction:
        if not self.can_handle_url(url):
            raise ValueError(f"{self.name} cannot handle URL: {url}")
        champ_id = _champ_id_from_url(url)
        if champ_id is None:
            raise ValueError(
                "Could not determine the Mystake league (championship id) from the URL. "
                "Use 'mystake:champ:<id>' or a mystake.bet URL with ?ch=<id>."
            )

        client = MystakeHttpClient(self.settings)
        topgames = await client.fetch_topgames()
        game_ids = _game_ids_for_champ(topgames, sport_id=self.settings.sport_id, champ_id=champ_id)
        raw = await client.fetch_games(game_ids)
        return build_competition_extraction(champ_id=champ_id, raw_response=raw, source_url=url)

    async def extract_match(self, url: str) -> EventSnapshot:
        raise NotImplementedError(f"{self.name} does not support direct match URLs yet.")

    def build_competition_url(self, *, competition_external_id, source_url=None, metadata=None) -> str | None:
        del source_url, metadata
        return f"mystake:champ:{competition_external_id}"


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
