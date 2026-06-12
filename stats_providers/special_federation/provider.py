"""Generic StatsProvider wrapper over a ``bot.special_leagues`` adapter.

Each federation (Norway/Romania/Slovakia/Algeria) already has a scraper adapter
exposing ``leagues()`` / ``fixtures(code)`` / ``match_report(match_id)``. This
base delegates the :class:`StatsProvider` contract to those methods so the same
leagues become linkable via ``/link_stats`` and feed the combined ``/stats``.

Discovery (per the product decision) = a fixed curated catalog + direct link by
the provider-native id/URL (``describe_league``). Match resolution is fuzzy by
team names + kickoff, mirroring the Svenskfotboll provider.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timezone
from typing import Any

from core.stats_models import (
    MatchIdentityCandidate,
    MatchStatsReport,
    StatsFixture,
    StatsLeagueOption,
    StatsMatchLink,
    StatsProviderCapabilities,
)
from core.stats_provider_base import StatsProvider

# Auto-link thresholds (mirror the Svenskfotboll provider's tuning).
_PER_SIDE_FLOOR = 0.50
_AUTO_COMBINED = 0.72
_AUTO_GAP = 0.08


def _normalize(text: str | None) -> str:
    raw = unicodedata.normalize("NFKD", str(text or "").lower())
    raw = "".join(c for c in raw if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", raw)).strip()


def _name_score(a: str | None, b: str | None) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    ratio = SequenceMatcher(a=na, b=nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    overlap = len(ta & tb) / min(len(ta), len(tb)) if ta and tb else 0.0
    return max(ratio, overlap)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _kickoff_delta_minutes(a: str | None, b: str | None) -> float | None:
    da, db = _parse_iso(a), _parse_iso(b)
    if da is None or db is None:
        return None
    if da.tzinfo and db.tzinfo is None:
        db = db.replace(tzinfo=da.tzinfo)
    elif db.tzinfo and da.tzinfo is None:
        da = da.replace(tzinfo=db.tzinfo)
    return abs((da - db).total_seconds()) / 60.0


def _time_score(delta: float | None) -> float:
    if delta is None:
        return 0.5  # unknown -> neutral, let names decide
    if delta <= 90:
        return 1.0
    if delta >= 24 * 60:
        return 0.0
    return max(0.0, 1.0 - (delta / (24 * 60)))


class SpecialLeagueStatsProvider(StatsProvider):
    """Adapter -> StatsProvider bridge for one scraped federation."""

    name = ""
    display_name = ""
    country_label = ""           # canonical country shown in options
    country_aliases: tuple[str, ...] = ()  # accepted spellings (lowercased)
    capabilities = StatsProviderCapabilities(
        supports_league_discovery=True,
        supports_fixture_discovery=True,
        supports_h2h=True,
        supports_lineups=True,
    )

    def __init__(self, *, payload_cache: object | None = None) -> None:
        self._cache = payload_cache  # accepted for parity; adapters are cheap/per-call

    # --- subclass hooks -------------------------------------------------- #
    def _make_adapter(self):
        raise NotImplementedError

    def _catalog(self) -> list[tuple[str, str]]:
        """Return [(league_id, league_name)] for discovery via a fresh adapter."""
        adapter = self._make_adapter()
        try:
            return [(lg.code, lg.name) for lg in adapter.leagues()]
        finally:
            adapter.close()

    def _reference_from_url(self, text: str) -> str | None:
        """Extract the provider-native league id from a pasted URL (override)."""
        return None

    # --- StatsProvider contract ----------------------------------------- #
    def _matches_country(self, country_name: str | None) -> bool:
        norm = _normalize(country_name)
        return any(norm == alias or alias in norm for alias in self.country_aliases)

    async def search_leagues(
        self, *, country_name: str, query: str | None = None, limit: int = 80
    ) -> list[StatsLeagueOption]:
        if not self._matches_country(country_name):
            return []
        catalog = await asyncio.to_thread(self._catalog)
        q = _normalize(query)
        options: list[StatsLeagueOption] = []
        for league_id, league_name in catalog:
            if q and q not in _normalize(league_name):
                continue
            options.append(self._option(str(league_id), str(league_name)))
        return options[:limit]

    async def describe_league(self, league_id: str) -> StatsLeagueOption | None:
        ref = self._reference_from_url(league_id) or str(league_id).strip()
        if not ref:
            return None
        # Catalog name if known, else the raw reference.
        catalog = await asyncio.to_thread(self._catalog)
        for cid, cname in catalog:
            if str(cid) == ref:
                return self._option(ref, str(cname))
        try:
            name, _rows = await asyncio.to_thread(self._fixtures, ref)
        except Exception:
            name = None
        return self._option(ref, name or f"{self.country_label} · {ref}")

    async def list_fixtures(self, league_id: str, *, limit: int | None = None) -> list[StatsFixture]:
        _name, rows = await asyncio.to_thread(self._fixtures, str(league_id))
        fixtures: list[StatsFixture] = []
        for row in rows:
            mid = str(getattr(row, "match_id", "") or "")
            if not mid:
                continue
            fixtures.append(
                StatsFixture(
                    provider=self.name,
                    league_id=str(league_id),
                    match_id=mid,
                    home=getattr(row, "home", "") or "",
                    away=getattr(row, "away", "") or "",
                    scheduled_at=self._row_iso(row),
                    status=None,
                    stats_url=self.build_match_url(mid),
                    raw_payload={"date_arg": getattr(row, "date_arg", ""), "time_arg": getattr(row, "time_arg", "")},
                )
            )
        return fixtures[:limit] if limit is not None else fixtures

    async def resolve_match(
        self, candidate: MatchIdentityCandidate, *, league_id: str | None = None
    ) -> StatsMatchLink | None:
        if not league_id:
            return None
        scored: list[tuple[float, StatsFixture, float, float, float | None]] = []
        for fixture in await self.list_fixtures(league_id):
            hs = _name_score(candidate.home, fixture.home)
            as_ = _name_score(candidate.away, fixture.away)
            if min(hs, as_) < _PER_SIDE_FLOOR:
                continue
            delta = _kickoff_delta_minutes(candidate.scheduled_at, fixture.scheduled_at)
            combined = (hs * 0.45) + (as_ * 0.45) + (_time_score(delta) * 0.10)
            scored.append((combined, fixture, hs, as_, delta))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        best = scored[0]
        gap = best[0] - scored[1][0] if len(scored) > 1 else 1.0
        if best[0] < _AUTO_COMBINED or gap < _AUTO_GAP:
            return None
        return StatsMatchLink(
            provider=self.name,
            stats_match_id=best[1].match_id,
            stats_url=best[1].stats_url,
            confidence=round(best[0], 6),
            method="federation_fixture_similarity",
            home_similarity=round(best[2], 6),
            away_similarity=round(best[3], 6),
            kickoff_delta_minutes=best[4],
            raw_payload=best[1].raw_payload,
        )

    async def build_match_report(self, stats_match_id: str) -> MatchStatsReport:
        markdown = await asyncio.to_thread(self._match_report, str(stats_match_id))
        title = self._title_from_markdown(markdown)
        return MatchStatsReport(
            provider=self.name,
            match_id=str(stats_match_id),
            title=title,
            markdown=markdown,
            data={"stats_match_id": str(stats_match_id)},
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # --- helpers --------------------------------------------------------- #
    def _option(self, league_id: str, league_name: str) -> StatsLeagueOption:
        return StatsLeagueOption(
            provider=self.name,
            provider_display_name=self.display_name,
            country_name=self.country_label,
            league_id=league_id,
            league_name=league_name,
            source_url=self.build_league_url(league_id),
        )

    def _fixtures(self, league_id: str):
        adapter = self._make_adapter()
        try:
            return adapter.fixtures(league_id)
        finally:
            adapter.close()

    def _match_report(self, match_id: str) -> str:
        adapter = self._make_adapter()
        try:
            return adapter.match_report(match_id)
        finally:
            adapter.close()

    @staticmethod
    def _row_iso(row) -> str | None:
        d = getattr(row, "date_arg", "") or ""
        t = getattr(row, "time_arg", "") or ""
        if not d or d == "N/A":
            return None
        if t and t != "N/A":
            return f"{d}T{t}:00-03:00"  # MatchRow times are Argentina-local
        return d

    @staticmethod
    def _title_from_markdown(markdown: str) -> str:
        for line in (markdown or "").splitlines():
            stripped = line.strip().lstrip("⚽").strip().strip("*").strip()
            if stripped:
                return stripped
        return "Reporte"

    def build_match_url(self, stats_match_id: str) -> str | None:
        return None

    def build_league_url(self, league_id: str) -> str | None:
        return None


# --------------------------------------------------------------------------- #
# Concrete federations
# --------------------------------------------------------------------------- #
class RomaniaFederationStatsProvider(SpecialLeagueStatsProvider):
    name = "romania_frf_http"
    display_name = "FRF (Rumania)"
    country_label = "Rumania"
    country_aliases = ("romania", "rumania", "rumanía", "romana")

    def _make_adapter(self):
        from bot.special_leagues import RomaniaLeagues
        from stats_providers.romania_http.client import RomaniaFRFHTTPClient
        return RomaniaLeagues(RomaniaFRFHTTPClient())


class SlovakiaFederationStatsProvider(SpecialLeagueStatsProvider):
    name = "slovakia_sportnet_http"
    display_name = "Sportnet (Eslovaquia)"
    country_label = "Eslovaquia"
    country_aliases = ("slovakia", "eslovaquia", "slovensko")

    def _make_adapter(self):
        from bot.special_leagues import SlovakiaLeagues
        from stats_providers.slovakia_http.client import SlovakSportnetHTTPClient
        return SlovakiaLeagues(SlovakSportnetHTTPClient())


class AlgeriaFederationStatsProvider(SpecialLeagueStatsProvider):
    name = "algeria_lnff_http"
    display_name = "LNFF (Argelia)"
    country_label = "Argelia"
    country_aliases = ("algeria", "argelia", "algerie", "algérie")

    def _make_adapter(self):
        from bot.special_leagues import AlgeriaLeagues
        from stats_providers.algeria_http.client import AlgeriaLNFFHTTPClient
        return AlgeriaLeagues(AlgeriaLNFFHTTPClient())


_NORWAY_CATALOG: list[tuple[str, str]] = [
    ("NO1", "Toppserien (Damas)"),
]


class NorwayFederationStatsProvider(SpecialLeagueStatsProvider):
    name = "norway_nff_http"
    display_name = "NFF / fotball.no (Noruega)"
    country_label = "Noruega"
    country_aliases = ("norway", "noruega", "norge")

    def _make_adapter(self):
        from bot.special_leagues import NorwayLeagues
        from stats_providers.norway_http.client import NorwayNFFHTTPClient
        return NorwayLeagues(NorwayNFFHTTPClient())

    def _catalog(self) -> list[tuple[str, str]]:
        return list(_NORWAY_CATALOG)

    def _reference_from_url(self, text: str) -> str | None:
        # Accept a fotball.no tournament URL or a bare fiksId for direct linking.
        m = re.search(r"/fotballdata/turnering/\w+/?\?fiksId=(\d+)", str(text))
        if m:
            return m.group(1)
        stripped = str(text or "").strip()
        return stripped if stripped.isdigit() else None

    def build_match_url(self, stats_match_id: str) -> str | None:
        return f"https://www.fotball.no/fotballdata/kamp/?fiksId={stats_match_id}"

    def build_league_url(self, league_id: str) -> str | None:
        if str(league_id).isdigit():
            return f"https://www.fotball.no/fotballdata/turnering/terminliste/?fiksId={league_id}"
        return "https://www.fotball.no/turneringer/toppserien/"
