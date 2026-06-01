"""FootyStats HTTP stats provider with a narrow public-page fallback."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any, Callable, Protocol, TypeVar
from urllib.parse import urljoin, urlparse

from core.stats_models import (
    MatchIdentityCandidate,
    MatchStatsReport,
    StatsFixture,
    StatsLeagueOption,
    StatsMatchLink,
    StatsProviderCapabilities,
)
from core.stats_provider_base import StatsProvider
from stats_providers.footystats_http.client import FootyStatsHTTPClient
from stats_providers.footystats_http.normalizers import (
    decode_public_match_id,
    discover_public_leagues,
    match_title_from_path,
    normalize_live_scores,
    normalize_public_fixtures,
    normalize_public_standings,
)
from stats_providers.footystats_http.reporting import render_match_report


_T = TypeVar("_T")
_PER_SIDE_FLOOR = 0.50
_AUTO_COMBINED = 0.78
_AUTO_GAP = 0.08


class StatsPayloadCache(Protocol):
    """Minimal optional cache contract already implemented by BetBot storage."""

    def get_cached_stats_payload(self, cache_key: str) -> dict[str, Any] | None: ...

    def set_cached_stats_payload(self, cache_key: str, payload: dict[str, Any], *, ttl_seconds: float) -> None: ...


class FootyStatsHttpStatsProvider(StatsProvider):
    """Expose FootyStats public HTTP fallback through BetBot's stats contract.

    Public pages are undocumented, so this adapter deliberately normalizes a
    narrow surface: league discovery, standings, fixtures and live-score AJAX.
    A configured API key is retained by the client for a future licensed mode.
    """

    name = "footystats_http"
    display_name = "FootyStats HTTP"
    capabilities = StatsProviderCapabilities(
        supports_league_discovery=True,
        supports_fixture_discovery=True,
        supports_live=True,
        supports_h2h=False,
        supports_lineups=False,
        supports_injuries=False,
        supports_odds=False,
        requires_browser_bootstrap=False,
    )

    def __init__(
        self,
        *,
        client: FootyStatsHTTPClient | Any | None = None,
        payload_cache: StatsPayloadCache | None = None,
        cache_ttl_seconds: float = 900.0,
    ) -> None:
        self._client = client or FootyStatsHTTPClient()
        self._cache = payload_cache
        self._cache_ttl_seconds = max(0.0, cache_ttl_seconds)

    async def stop(self) -> None:
        """Close pooled HTTP connections."""

        close = getattr(self._client, "close", None)
        if callable(close):
            await asyncio.to_thread(close)

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[StatsLeagueOption]:
        """Search public FootyStats league links by country and optional text."""

        country_key = _normalize_text(country_name)
        query_key = _normalize_text(query or "")
        catalog = await self._catalog()
        options: list[StatsLeagueOption] = []
        for item in catalog:
            if country_key not in _normalize_text(item.get("country_slug")):
                continue
            league_name = str(item.get("league_name") or "")
            if query_key and query_key not in _normalize_text(league_name):
                continue
            league_id = str(item.get("league_id") or "")
            if not league_id:
                continue
            options.append(
                StatsLeagueOption(
                    provider=self.name,
                    provider_display_name=self.display_name,
                    country_name=str(item.get("country_slug") or "").replace("-", " ").title(),
                    league_id=league_id,
                    league_name=league_name,
                    source_url=self.build_league_url(league_id),
                    raw_payload=item,
                )
            )
            if len(options) >= limit:
                break
        if query_key:
            options.sort(key=lambda option: (_normalize_text(option.league_name) != query_key, option.league_name))
        return options

    async def describe_league(self, league_id: str) -> StatsLeagueOption | None:
        """Resolve one public `country/league` path into a discovery option."""

        normalized = league_id.strip("/")
        for item in await self._catalog():
            if item.get("league_id") != normalized:
                continue
            return StatsLeagueOption(
                provider=self.name,
                provider_display_name=self.display_name,
                country_name=str(item.get("country_slug") or "").replace("-", " ").title(),
                league_id=normalized,
                league_name=str(item.get("league_name") or normalized),
                source_url=self.build_league_url(normalized),
                raw_payload=item,
            )
        return None

    async def list_fixtures(self, league_id: str, *, limit: int | None = None) -> list[StatsFixture]:
        """List public embedded fixtures for one FootyStats league page."""

        overview = await self.get_league_overview(league_id)
        documents = overview.get("_provider_fixtures") if isinstance(overview, dict) else []
        fixtures = [
            StatsFixture(
                provider=self.name,
                league_id=league_id.strip("/"),
                match_id=str(item.get("provider_match_id") or item.get("match_id") or ""),
                home=str(item.get("home") or ""),
                away=str(item.get("away") or ""),
                scheduled_at=item.get("start_time_utc"),
                status=item.get("status"),
                stats_url=urljoin("https://footystats.org/", item.get("stats_path") or ""),
                raw_payload=item,
            )
            for item in documents or []
            if item.get("provider_match_id") or item.get("match_id")
        ]
        fixtures.sort(key=lambda fixture: (fixture.status != "incomplete", fixture.scheduled_at or ""))
        return fixtures[:limit] if limit is not None else fixtures

    async def get_league_overview(
        self,
        league_id: str,
        *,
        cache_ttl: float | None = None,
    ) -> dict[str, Any]:
        """Return a compact cached league snapshot; never persist raw HTML."""

        ttl = self._cache_ttl_seconds if cache_ttl is None else cache_ttl
        return await self._cached_payload(
            f"league:{league_id.strip('/')}:overview",
            self._fetch_league_overview,
            league_id.strip("/"),
            ttl=ttl,
        )

    async def resolve_match(
        self,
        candidate: MatchIdentityCandidate,
        *,
        league_id: str | None = None,
    ) -> StatsMatchLink | None:
        """Resolve one odds fixture to a public FootyStats fixture."""

        direct = _public_match_id_from_url(candidate.stats_url)
        if direct:
            return StatsMatchLink(
                provider=self.name,
                stats_match_id=direct,
                stats_url=self.build_match_url(direct),
                confidence=1.0,
                method="direct_stats_url",
            )
        if not league_id:
            return None
        ranked = await self.rank_match_candidates(candidate, league_id=league_id)
        if not ranked:
            return None
        gap = ranked[0].confidence - ranked[1].confidence if len(ranked) > 1 else 1.0
        return ranked[0] if ranked[0].confidence >= _AUTO_COMBINED and gap >= _AUTO_GAP else None

    async def rank_match_candidates(
        self,
        candidate: MatchIdentityCandidate,
        *,
        league_id: str,
        limit: int = 5,
    ) -> list[StatsMatchLink]:
        """Rank embedded fixtures by both teams and kickoff proximity."""

        ranked: list[tuple[float, StatsFixture, float, float, float | None]] = []
        for fixture in await self.list_fixtures(league_id):
            home_score = _name_score(candidate.home, fixture.home)
            away_score = _name_score(candidate.away, fixture.away)
            if min(home_score, away_score) < _PER_SIDE_FLOOR:
                continue
            kickoff_delta = _kickoff_delta_minutes(candidate.scheduled_at, fixture.scheduled_at)
            combined = (home_score * 0.45) + (away_score * 0.45) + (_time_score(kickoff_delta) * 0.10)
            ranked.append((combined, fixture, home_score, away_score, kickoff_delta))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            StatsMatchLink(
                provider=self.name,
                stats_match_id=fixture.match_id,
                stats_url=fixture.stats_url,
                confidence=round(score, 6),
                method="league_fixture_similarity",
                home_similarity=round(home_score, 6),
                away_similarity=round(away_score, 6),
                kickoff_delta_minutes=kickoff_delta,
                raw_payload={
                    "stats_home": fixture.home,
                    "stats_away": fixture.away,
                    "stats_scheduled_at": fixture.scheduled_at,
                    "fixture": fixture.raw_payload,
                },
            )
            for score, fixture, home_score, away_score, kickoff_delta in ranked[:limit]
        ]

    async def build_match_report(
        self,
        stats_match_id: str,
        *,
        cache_ttl: float | None = None,
    ) -> MatchStatsReport:
        """Build one compact public-page report with optional live score."""

        # Reports include the lightweight live-score feed. Keep this cache short
        # even if the daily warm-up asks for a long league TTL.
        ttl = min(30.0, self._cache_ttl_seconds if cache_ttl is None else cache_ttl)
        snapshot = await self._cached_payload(
            f"match:{stats_match_id}:report",
            self._fetch_match_snapshot,
            stats_match_id,
            ttl=ttl,
        )
        match = snapshot.get("match") if isinstance(snapshot.get("match"), dict) else {}
        return MatchStatsReport(
            provider=self.name,
            match_id=stats_match_id,
            title=str(match.get("title") or "Partido FootyStats"),
            markdown=render_match_report(snapshot),
            data=snapshot,
            generated_at=datetime.now(UTC).isoformat(),
        )

    def build_match_url(self, stats_match_id: str) -> str | None:
        """Return the public H2H URL encoded in one provider-native match ID."""

        path, _ = decode_public_match_id(stats_match_id)
        return urljoin("https://footystats.org/", path) if path else None

    def build_league_url(self, league_id: str) -> str:
        """Return one stable public league page URL."""

        return urljoin("https://footystats.org/", league_id.strip("/"))

    async def _catalog(self) -> list[dict[str, Any]]:
        payload = await self._cached_payload("catalog:public", self._fetch_catalog)
        return [item for item in payload.get("leagues") or [] if isinstance(item, dict)]

    def _fetch_catalog(self) -> dict[str, Any]:
        return {"leagues": discover_public_leagues(self._client.get_public_html("/"))}

    def _fetch_league_overview(self, league_id: str) -> dict[str, Any]:
        html = self._client.get_public_html(f"/{league_id}")
        fixtures = normalize_public_fixtures(html, league_id)
        return {
            "league_id": league_id,
            "league_name": _league_name_from_id(league_id),
            "source_url": self.build_league_url(league_id),
            "standings": normalize_public_standings(html),
            "fixtures": [_overview_fixture(item) for item in fixtures],
            "_provider_fixtures": fixtures,
            "top_goals": [],
            "source_mode": "public_html",
        }

    def _fetch_match_snapshot(self, stats_match_id: str) -> dict[str, Any]:
        path, numeric_id = decode_public_match_id(stats_match_id)
        live_scores = normalize_live_scores(self._client.get_live_scores())
        live = next((item for item in live_scores if item.get("match_id") == numeric_id), {})
        return {
            "match": {
                "id": numeric_id,
                "title": match_title_from_path(path),
                "status": "live" if live else "prematch_or_ended",
            },
            "live_state": live,
            "source_mode": "public_html",
            "source_url": self.build_match_url(stats_match_id),
        }

    async def _cached_payload(
        self,
        key: str,
        func: Callable[..., dict[str, Any]],
        *args: Any,
        ttl: float | None = None,
    ) -> dict[str, Any]:
        cache_key = f"footystats_http:{key}"
        if self._cache is not None:
            cached = await asyncio.to_thread(self._cache.get_cached_stats_payload, cache_key)
            if cached is not None:
                return cached
        payload = await asyncio.to_thread(func, *args)
        if self._cache is not None:
            await asyncio.to_thread(
                self._cache.set_cached_stats_payload,
                cache_key,
                payload,
                ttl_seconds=self._cache_ttl_seconds if ttl is None else ttl,
            )
        return payload


def _overview_fixture(item: dict[str, Any]) -> dict[str, Any]:
    start = str(item.get("start_time_utc") or "")
    return {
        "match_id": item.get("provider_match_id") or item.get("match_id"),
        "home": {"id": item.get("home_id"), "name": item.get("home")},
        "away": {"id": item.get("away_id"), "name": item.get("away")},
        "time": {"iso_utc": item.get("start_time_utc"), "date": start[:10], "time": start[11:16]},
        "status": item.get("status"),
    }


def _public_match_id_from_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if not parsed.hostname or not parsed.hostname.endswith("footystats.org"):
        return None
    return f"public:{parsed.path}#{parsed.fragment}" if parsed.fragment else None


def _league_name_from_id(league_id: str) -> str:
    return league_id.strip("/").split("/")[-1].replace("-", " ").title()


def _normalize_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]+", " ", normalized.encode("ascii", "ignore").decode().lower()).strip()


def _name_score(left: str, right: str) -> float:
    left_key = _normalize_text(left)
    right_key = _normalize_text(right)
    if left_key in right_key or right_key in left_key:
        return 0.95
    return SequenceMatcher(a=left_key, b=right_key).ratio()


def _kickoff_delta_minutes(left: str | None, right: str | None) -> float | None:
    try:
        return abs((datetime.fromisoformat(left or "") - datetime.fromisoformat(right or "")).total_seconds()) / 60
    except ValueError:
        return None


def _time_score(delta: float | None) -> float:
    if delta is None:
        return 0.5
    if delta <= 15:
        return 1.0
    if delta <= 120:
        return 0.75
    if delta <= 1440:
        return 0.25
    return 0.0


__all__ = ["FootyStatsHttpStatsProvider"]
