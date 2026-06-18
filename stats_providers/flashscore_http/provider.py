"""Flashscore HTTP stats provider.

Implements BetBot's `StatsProvider` contract over Flashscore's (Livesport) feed.
Transport is plain httpx with a static ``x-fsign`` header (no browser, no token,
no curl_cffi). Flashscore's draw is the broadest league coverage — many niche
leagues absent from Sportradar/SofaScore. Originated from `sandbox/flashscore_http`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any, Callable, Protocol, TypeVar

from core.stats_models import (
    MatchIdentityCandidate,
    MatchStatsReport,
    StatsFixture,
    StatsLeagueOption,
    StatsMatchLink,
    StatsProviderCapabilities,
)
from core.stats_provider_base import StatsProvider
from stats_providers.flashscore_http.client import FlashscoreClient
from stats_providers.flashscore_http.parser import (
    parse_day_fixtures,
    parse_incidents,
    parse_records,
    parse_statistics,
)
from stats_providers.flashscore_http.reporting import render_match_report

_T = TypeVar("_T")
_PER_SIDE_FLOOR = 0.50
_AUTO_COMBINED = 0.78
_AUTO_GAP = 0.08


class StatsPayloadCache(Protocol):
    """Minimal optional cache contract already satisfied by BetBot storage."""

    def get_cached_stats_payload(self, cache_key: str) -> dict[str, Any] | None: ...

    def set_cached_stats_payload(self, cache_key: str, payload: dict[str, Any], *, ttl_seconds: float) -> None: ...


class FlashscoreHttpStatsProvider(StatsProvider):
    """Flashscore behind BetBot's stable stats-provider interface (HTTP-only)."""

    name = "flashscore_http"
    display_name = "Flashscore"
    capabilities = StatsProviderCapabilities(
        supports_league_discovery=True,
        supports_fixture_discovery=True,
        supports_live=True,
        supports_h2h=True,
        supports_lineups=False,
        supports_injuries=False,
        supports_odds=False,
        requires_browser_bootstrap=False,
    )

    def __init__(
        self,
        *,
        client: FlashscoreClient | Any | None = None,
        payload_cache: StatsPayloadCache | None = None,
        cache_ttl_seconds: float = 300.0,
        day_offsets: tuple[int, ...] = (-2, -1, 0, 1, 2, 3),
    ) -> None:
        self._client = client or FlashscoreClient()
        self._cache = payload_cache
        self._cache_ttl_seconds = max(0.0, cache_ttl_seconds)
        self._day_offsets = day_offsets

    # ----- discovery + fixtures -----

    async def _all_leagues(self) -> dict[str, dict[str, Any]]:
        """Aggregate day feeds across the window into {league_id: {...matches}}."""

        merged: dict[str, dict[str, Any]] = {}
        for offset in self._day_offsets:
            payload = await self._cached_day(offset)
            for league in payload.get("leagues", []):
                league_id = league.get("league_id")
                if not league_id:
                    continue
                bucket = merged.setdefault(
                    str(league_id),
                    {
                        "league_id": str(league_id),
                        "country": league.get("country"),
                        "league_name": league.get("league_name"),
                        "raw_name": league.get("raw_name"),
                        "matches": [],
                        "_seen": set(),
                    },
                )
                for match in league.get("matches", []):
                    mid = match.get("match_id")
                    if mid and mid not in bucket["_seen"]:
                        bucket["_seen"].add(mid)
                        bucket["matches"].append(match)
        return merged

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[StatsLeagueOption]:
        """Search leagues (with matches in the day window) by country/query."""

        country_key = _normalize_text(country_name)
        query_key = _normalize_text(query or "")
        leagues = await self._all_leagues()
        options: list[StatsLeagueOption] = []
        for league in leagues.values():
            country = _normalize_text(league.get("country"))
            raw = _normalize_text(league.get("raw_name"))
            if country_key and country_key not in country and country_key not in raw:
                continue
            name = str(league.get("league_name") or "")
            if query_key and query_key not in _normalize_text(name):
                continue
            options.append(
                StatsLeagueOption(
                    provider=self.name,
                    provider_display_name=self.display_name,
                    country_name=league.get("country"),
                    league_id=str(league["league_id"]),
                    league_name=name,
                    source_url=self.build_league_url(str(league["league_id"])),
                    raw_payload={"raw_name": league.get("raw_name"), "matches": len(league.get("matches", []))},
                )
            )
        options.sort(key=lambda o: ((o.country_name or "").lower(), o.league_name.lower()))
        return options[:limit]

    async def list_fixtures(self, league_id: str, *, limit: int | None = None) -> list[StatsFixture]:
        """List fixtures of one league across the day window."""

        leagues = await self._all_leagues()
        league = leagues.get(str(league_id))
        if not league:
            return []
        fixtures = [
            StatsFixture(
                provider=self.name,
                league_id=str(league_id),
                match_id=str(m["match_id"]),
                home=str(m.get("home") or ""),
                away=str(m.get("away") or ""),
                scheduled_at=m.get("kickoff_utc"),
                status=m.get("status"),
                stats_url=self.build_match_url(str(m["match_id"])),
                raw_payload=m,
            )
            for m in league.get("matches", [])
            if m.get("match_id")
        ]
        fixtures.sort(key=lambda f: f.scheduled_at or "")
        return fixtures[:limit] if limit is not None else fixtures

    async def get_league_overview(self, league_id: str) -> dict[str, Any] | None:
        """Compact overview: league name + fixtures (Flashscore standings TBD)."""

        leagues = await self._all_leagues()
        league = leagues.get(str(league_id))
        if not league:
            return None
        fixtures = await self.list_fixtures(league_id)
        return {
            "league_id": str(league_id),
            "league_name": league.get("league_name"),
            "country": league.get("country"),
            "source_url": self.build_league_url(str(league_id)),
            "fixtures": [
                {"match_id": f.match_id, "home": f.home, "away": f.away, "scheduled_at": f.scheduled_at, "status": f.status}
                for f in fixtures
            ],
            "standings": None,
        }

    # ----- match resolution + report -----

    async def resolve_match(
        self,
        candidate: MatchIdentityCandidate,
        *,
        league_id: str | None = None,
    ) -> StatsMatchLink | None:
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
        scored: list[tuple[float, StatsFixture, float, float, float | None]] = []
        for fixture in await self.list_fixtures(league_id):
            home_score = _name_score(candidate.home, fixture.home)
            away_score = _name_score(candidate.away, fixture.away)
            if min(home_score, away_score) < _PER_SIDE_FLOOR:
                continue
            kickoff_delta = _kickoff_delta_minutes(candidate.scheduled_at, fixture.scheduled_at)
            combined = (home_score * 0.45) + (away_score * 0.45) + (_time_score(kickoff_delta) * 0.10)
            scored.append((combined, fixture, home_score, away_score, kickoff_delta))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            StatsMatchLink(
                provider=self.name,
                stats_match_id=fixture.match_id,
                stats_url=fixture.stats_url,
                confidence=round(combined, 6),
                method="league_fixture_similarity",
                home_similarity=round(home_score, 6),
                away_similarity=round(away_score, 6),
                kickoff_delta_minutes=kickoff_delta,
                raw_payload={"stats_home": fixture.home, "stats_away": fixture.away, "stats_scheduled_at": fixture.scheduled_at},
            )
            for combined, fixture, home_score, away_score, kickoff_delta in scored[:limit]
        ]

    async def count_matching_events(self, league_id: str, candidates: list[MatchIdentityCandidate]) -> int:
        fixtures = await self.list_fixtures(league_id)
        return sum(
            any(
                min(_name_score(c.home, f.home), _name_score(c.away, f.away)) >= _PER_SIDE_FLOOR
                for f in fixtures
            )
            for c in candidates
        )

    async def build_match_report(self, stats_match_id: str) -> MatchStatsReport:
        snapshot = await self._cached_snapshot(str(stats_match_id))
        match = snapshot.get("match") or {}
        home = match.get("home") or "Local"
        away = match.get("away") or "Visitante"
        return MatchStatsReport(
            provider=self.name,
            match_id=str(stats_match_id),
            title=f"{home} vs {away}",
            markdown=render_match_report(snapshot),
            data=snapshot,
            generated_at=datetime.now(UTC).isoformat(),
        )

    def build_match_url(self, stats_match_id: str) -> str | None:
        return f"https://www.flashscore.com.ar/partido/futbol/{stats_match_id}/" if stats_match_id else None

    def build_league_url(self, league_id: str) -> str:
        return f"https://www.flashscore.com.ar/?league={league_id}"

    # ----- snapshot assembly + caching -----

    async def _build_snapshot(self, match_id: str) -> dict[str, Any]:
        home = away = None
        fixtures_match: StatsFixture | None = None
        # best-effort home/away from the day window
        for league in (await self._all_leagues()).values():
            for m in league.get("matches", []):
                if str(m.get("match_id")) == match_id:
                    home, away = m.get("home"), m.get("away")
                    fixtures_match = m
                    break
            if home:
                break
        stats = parse_statistics(await self._call(self._client.fetch_match_statistics, match_id))
        incidents = parse_incidents(await self._call(self._client.fetch_match_summary, match_id))
        meta_records = parse_records(await self._call(self._client.fetch_match_meta, match_id))
        meta = meta_records[0] if meta_records else {}
        return {
            "match": {
                "match_id": match_id,
                "home": home,
                "away": away,
                "score": _meta_score(meta),
                "status": _meta_status(meta),
                "kickoff_utc": (fixtures_match or {}).get("kickoff_utc"),
            },
            "statistics": stats,
            "incidents": incidents,
            "raw_meta": meta,
        }

    async def _cached_day(self, offset: int) -> dict[str, Any]:
        key = f"day:{offset}:{self._client.settings.timezone_offset}"
        cached = await self._cache_get(key)
        if cached is not None:
            return cached
        text = await self._call(self._client.fetch_day_fixtures, day_offset=offset)
        payload = {"leagues": parse_day_fixtures(text)}
        await self._cache_set(key, payload)
        return payload

    async def _cached_snapshot(self, match_id: str) -> dict[str, Any]:
        key = f"event:{match_id}:snapshot"
        cached = await self._cache_get(key)
        if cached is not None:
            return cached
        payload = await self._build_snapshot(match_id)
        await self._cache_set(key, payload)
        return payload

    async def _cache_get(self, key: str) -> dict[str, Any] | None:
        if self._cache is None or self._cache_ttl_seconds <= 0:
            return None
        return await self._call(self._cache.get_cached_stats_payload, f"{self.name}:{key}")

    async def _cache_set(self, key: str, payload: dict[str, Any]) -> None:
        if self._cache is None or self._cache_ttl_seconds <= 0 or not isinstance(payload, dict):
            return
        await self._call(
            self._cache.set_cached_stats_payload, f"{self.name}:{key}", payload, ttl_seconds=self._cache_ttl_seconds
        )

    async def _call(self, func: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        return await asyncio.to_thread(func, *args, **kwargs)


def _meta_score(meta: dict[str, str]) -> str | None:
    home, away = meta.get("DE"), meta.get("DF")
    return f"{home}-{away}" if home is not None and away is not None else None


def _meta_status(meta: dict[str, str]) -> str | None:
    code = meta.get("DA") or meta.get("DB")
    return {"1": "scheduled", "2": "live", "3": "finished"}.get(str(code), code)


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\b(fc|cf|club|women|w|u21|u20|u19|u17|sub|reserves?)\b", " ", text.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _name_score(left: str, right: str) -> float:
    left_key = _normalize_text(left)
    right_key = _normalize_text(right)
    if not left_key or not right_key:
        return 0.0
    ratio = SequenceMatcher(a=left_key, b=right_key).ratio()
    lt, rt = set(left_key.split()), set(right_key.split())
    if not lt or not rt:
        return ratio
    shorter, longer = (lt, rt) if len(lt) <= len(rt) else (rt, lt)
    return max(ratio, len(shorter & longer) / len(shorter))


def _kickoff_delta_minutes(left: str | None, right: str | None) -> float | None:
    a, b = _parse_dt(left), _parse_dt(right)
    return abs((a - b).total_seconds()) / 60.0 if a and b else None


def _parse_dt(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except (ValueError, AttributeError):
        return None


def _time_score(delta_minutes: float | None) -> float:
    if delta_minutes is None:
        return 0.5
    if delta_minutes <= 5:
        return 1.0
    if delta_minutes <= 30:
        return 0.8
    if delta_minutes <= 120:
        return 0.5
    return 0.2
