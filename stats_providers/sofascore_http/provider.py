"""SofaScore HTTP stats provider.

Implements BetBot's `StatsProvider` contract over SofaScore's public API. The
transport is `curl_cffi` (browser TLS impersonation): plain `httpx` is blocked
with 403, while `curl_cffi` returns JSON with no browser, cookies or token.
Originated from the `sandbox/sofascore_http` research (discovery harness +
feasibility reports live there).
"""

from __future__ import annotations

import asyncio
import json
import logging
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
from stats_providers.sofascore_http.build_match_snapshot import build_snapshot
from stats_providers.sofascore_http.client import SofaScoreHTTPClient
from stats_providers.sofascore_http.normalizers import (
    normalize_fixture,
    normalize_fixture_overview,
    normalize_league_option,
    normalize_standings,
)
from stats_providers.sofascore_http.reporting import render_match_report


_T = TypeVar("_T")
logger = logging.getLogger(__name__)
_SOFASCORE_EVENT_RE = re.compile(r"(?:/event/|#id:)(\d+)")
_SOFASCORE_TOURNAMENT_URL_RE = re.compile(
    r"sofascore\.com/(?:[^/]+/)?football/tournament/"
    r"(?P<country_slug>[^/]+)/(?P<tournament_slug>[^/]+)/(?P<tournament_id>\d+)",
    re.IGNORECASE,
)
_SOFASCORE_SEASON_ID_RE = re.compile(r"(?:#id:|[?&]id=)(?P<season_id>\d+)", re.IGNORECASE)
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)
_PER_SIDE_FLOOR = 0.50
_AUTO_COMBINED = 0.78
_AUTO_GAP = 0.08


class StatsPayloadCache(Protocol):
    """Minimal optional cache contract already satisfied by BetBot storage."""

    def get_cached_stats_payload(self, cache_key: str) -> dict[str, Any] | None: ...

    def set_cached_stats_payload(self, cache_key: str, payload: dict[str, Any], *, ttl_seconds: float) -> None: ...


class SofaScoreHttpStatsProvider(StatsProvider):
    """Validate SofaScore behind BetBot's stable stats-provider interface."""

    name = "sofascore_http"
    display_name = "SofaScore"
    capabilities = StatsProviderCapabilities(
        supports_league_discovery=True,
        supports_fixture_discovery=True,
        supports_live=True,
        supports_h2h=True,
        supports_lineups=True,
        supports_injuries=False,
        supports_odds=True,
        requires_browser_bootstrap=False,
    )

    def __init__(
        self,
        *,
        client: SofaScoreHTTPClient | Any | None = None,
        payload_cache: StatsPayloadCache | None = None,
        cache_ttl_seconds: float = 300.0,
    ) -> None:
        self._client = client or SofaScoreHTTPClient()
        self._cache = payload_cache
        self._cache_ttl_seconds = max(0.0, cache_ttl_seconds)

    async def stop(self) -> None:
        """Close the HTTP session."""

        close = getattr(self._client, "close", None)
        if callable(close):
            await self._call(close)

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[StatsLeagueOption]:
        """Search SofaScore unique tournaments under one country category."""

        country_key = _normalize_text(country_name)
        query_key = _normalize_text(query or "")
        categories = await self._cached_payload("categories:football", self._client.get_categories)
        matching_categories = [
            item for item in categories
            if isinstance(item, dict) and country_key in _normalize_text(item.get("name"))
        ]
        options: list[StatsLeagueOption] = []
        seen: set[str] = set()
        for category in matching_categories:
            category_id = category.get("id")
            if category_id is None:
                continue
            tournaments = await self._cached_payload(
                f"category:{category_id}:tournaments",
                self._client.get_category_tournaments,
                int(category_id),
            )
            for tournament in tournaments:
                normalized = normalize_league_option(tournament)
                league_id = str(normalized.get("league_id") or "")
                league_name = str(normalized.get("league_name") or "")
                if not league_id or league_id in seen:
                    continue
                if query_key and query_key not in _normalize_text(league_name):
                    continue
                seen.add(league_id)
                options.append(
                    StatsLeagueOption(
                        provider=self.name,
                        provider_display_name=self.display_name,
                        country_name=normalized.get("country_name"),
                        league_id=league_id,
                        league_name=league_name,
                        source_url=self.build_league_url(league_id),
                        raw_payload=tournament,
                    )
                )
                if len(options) >= limit:
                    return options
        return options

    async def describe_league(self, league_id: str) -> StatsLeagueOption | None:
        """Resolve one SofaScore league id or public tournament URL.

        Direct URLs are important for Telegram linking because SofaScore country
        discovery is API-backed and can be challenged, while public tournament
        pages still include the tournament and season identity in Next.js data.
        """

        identity = _parse_league_identity(league_id)
        if identity is None:
            return None
        tournament_id = int(identity["tournament_id"])
        season_id = identity.get("season_id")
        raw_payload: dict[str, Any] = {"input": league_id, "parsed_identity": identity}

        page_info: dict[str, Any] = {}
        if _looks_like_sofascore_url(league_id):
            html = await self._call(self._client.get_public_html, league_id)
            page_info = _extract_tournament_page_info(html)
            if not page_info:
                return None
            raw_payload["public_page"] = page_info
            tournament_id = int(page_info.get("tournament_id") or tournament_id)
            season_id = str(page_info.get("season_id") or season_id or "") or None

        season: dict[str, Any] | None = None
        if not page_info:
            season = await self._current_season(tournament_id, preferred_season_id=_safe_int(season_id))
            if season:
                season_id = str(season.get("id") or season_id or "") or None
                raw_payload["season"] = season

        league_name = (
            str(page_info.get("league_name") or "")
            or (str(season.get("name") or "") if season else "")
            or f"SofaScore Tournament {tournament_id}"
        )
        country_name = str(page_info.get("country_name") or "") or None
        return StatsLeagueOption(
            provider=self.name,
            provider_display_name=self.display_name,
            country_name=country_name,
            league_id=_format_league_id(tournament_id, _safe_int(season_id)),
            league_name=league_name,
            season_id=str(season_id) if season_id else None,
            source_url=league_id if _looks_like_sofascore_url(league_id) else self.build_league_url(str(tournament_id)),
            raw_payload=raw_payload,
        )

    async def list_fixtures(self, league_id: str, *, limit: int | None = None) -> list[StatsFixture]:
        """List recent and upcoming fixtures using the current season pages."""

        identity = _parse_league_identity(league_id)
        if identity is None:
            return []
        tournament_id = int(identity["tournament_id"])
        season = await self._current_season(tournament_id, preferred_season_id=_safe_int(identity.get("season_id")))
        if not season:
            return []
        season_id = int(season["id"])
        fixture_docs: list[dict[str, Any]] = []
        for direction in ("next", "last"):
            try:
                fixture_docs.extend(
                    await self._cached_payload(
                        f"tournament:{tournament_id}:season:{season_id}:events:{direction}:0",
                        self._client.get_season_events,
                        tournament_id,
                        season_id,
                        direction=direction,
                        page=0,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "SofaScore fixture page unavailable tournament_id=%s season_id=%s direction=%s reason=%s",
                    tournament_id,
                    season_id,
                    direction,
                    exc,
                )
        fixtures: list[StatsFixture] = []
        for item in _dedupe_events(fixture_docs):
            normalized = normalize_fixture(item)
            match_id = str(normalized.get("match_id") or "")
            if not match_id:
                continue
            fixtures.append(
                StatsFixture(
                    provider=self.name,
                    league_id=str(league_id),
                    match_id=match_id,
                    home=str(normalized.get("home") or ""),
                    away=str(normalized.get("away") or ""),
                    scheduled_at=normalized.get("start_time_utc"),
                    status=normalized.get("status"),
                    stats_url=self.build_match_url(match_id),
                    raw_payload=item,
                )
            )
        fixtures.sort(key=lambda fixture: fixture.scheduled_at or "")
        return fixtures[:limit] if limit is not None else fixtures

    async def get_league_overview(self, league_id: str) -> dict[str, Any] | None:
        """Return compact standings and fixtures for future `/explore_stats` use."""

        identity = _parse_league_identity(league_id)
        if identity is None:
            return None
        tournament_id = int(identity["tournament_id"])
        season = await self._current_season(tournament_id, preferred_season_id=_safe_int(identity.get("season_id")))
        if not season:
            return None
        season_id = int(season["id"])
        try:
            standings = await self._cached_payload(
                f"tournament:{tournament_id}:season:{season_id}:standings",
                self._client.get_season_standings,
                tournament_id,
                season_id,
            )
        except Exception as exc:
            logger.warning(
                "SofaScore standings unavailable tournament_id=%s season_id=%s reason=%s",
                tournament_id,
                season_id,
                exc,
            )
            standings = []
        fixtures = await self.list_fixtures(league_id)
        return {
            "league_id": str(league_id),
            "season_id": str(season_id),
            "league_name": season.get("name") or f"Tournament {league_id}",
            "source_url": self.build_league_url(league_id),
            "standings": normalize_standings(standings),
            "fixtures": [normalize_fixture_overview(fixture.raw_payload or {}) for fixture in fixtures],
            "teams": [],
            "top_goals": [],
        }

    async def resolve_match(
        self,
        candidate: MatchIdentityCandidate,
        *,
        league_id: str | None = None,
    ) -> StatsMatchLink | None:
        """Resolve a sportsbook event to an unambiguous SofaScore event."""

        direct_match_id = _extract_match_id(candidate.stats_url)
        if direct_match_id:
            return StatsMatchLink(
                provider=self.name,
                stats_match_id=direct_match_id,
                stats_url=self.build_match_url(direct_match_id),
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
        """Rank SofaScore fixtures by teams and kickoff proximity."""

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
                raw_payload={
                    "stats_home": fixture.home,
                    "stats_away": fixture.away,
                    "stats_scheduled_at": fixture.scheduled_at,
                    "fixture": fixture.raw_payload,
                },
            )
            for combined, fixture, home_score, away_score, kickoff_delta in scored[:limit]
        ]

    async def count_matching_events(self, league_id: str, candidates: list[MatchIdentityCandidate]) -> int:
        """Count plausible odds-event matches for league ranking validation."""

        fixtures = await self.list_fixtures(league_id)
        return sum(
            any(
                min(_name_score(candidate.home, fixture.home), _name_score(candidate.away, fixture.away))
                >= _PER_SIDE_FLOOR
                for fixture in fixtures
            )
            for candidate in candidates
        )

    async def build_match_report(self, stats_match_id: str) -> MatchStatsReport:
        """Build one compact provider-level report without Telegram logic."""

        event_id = int(stats_match_id)
        snapshot = await self._cached_payload(
            f"event:{event_id}:snapshot",
            build_snapshot,
            self._client,
            event_id,
        )
        match = snapshot.get("match") if isinstance(snapshot, dict) else {}
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
        """Return a stable API URL because a public match slug is not always known."""

        return f"https://www.sofascore.com/api/v1/event/{stats_match_id}" if stats_match_id else None

    def build_league_url(self, league_id: str) -> str:
        """Return a stable API URL for one unique tournament."""

        identity = _parse_league_identity(league_id)
        tournament_id = identity["tournament_id"] if identity else league_id
        return f"https://www.sofascore.com/api/v1/unique-tournament/{tournament_id}/seasons"

    async def _current_season(
        self,
        tournament_id: int,
        *,
        preferred_season_id: int | None = None,
    ) -> dict[str, Any] | None:
        if preferred_season_id is not None:
            return {"id": preferred_season_id, "name": f"Season {preferred_season_id}"}
        seasons = await self._cached_payload(
            f"tournament:{tournament_id}:seasons",
            self._client.get_unique_tournament_seasons,
            tournament_id,
        )
        return seasons[0] if seasons else None

    async def _cached_payload(
        self,
        key: str,
        func: Callable[..., _T],
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        if self._cache is not None and self._cache_ttl_seconds > 0:
            cached = await self._call(self._cache.get_cached_stats_payload, f"{self.name}:{key}")
            if cached is not None:
                return cached  # type: ignore[return-value]
        payload = await self._call(func, *args, **kwargs)
        if self._cache is not None and self._cache_ttl_seconds > 0 and isinstance(payload, dict):
            await self._call(
                self._cache.set_cached_stats_payload,
                f"{self.name}:{key}",
                payload,
                ttl_seconds=self._cache_ttl_seconds,
            )
        return payload

    async def _call(self, func: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        return await asyncio.to_thread(func, *args, **kwargs)


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = event.get("id")
        if event_id is not None:
            deduped[str(event_id)] = event
    return list(deduped.values())


def _extract_match_id(url: str | None) -> str | None:
    match = _SOFASCORE_EVENT_RE.search(url or "")
    return match.group(1) if match else None


def _looks_like_sofascore_url(value: str | None) -> bool:
    return bool(re.search(r"https?://(?:www\.)?sofascore\.com/", value or "", re.IGNORECASE))


def _parse_league_identity(value: str | None) -> dict[str, str] | None:
    text = (value or "").strip()
    if not text:
        return None
    url_match = _SOFASCORE_TOURNAMENT_URL_RE.search(text)
    if url_match:
        identity = {
            "tournament_id": url_match.group("tournament_id"),
            "country_slug": url_match.group("country_slug"),
            "tournament_slug": url_match.group("tournament_slug"),
        }
        season_match = _SOFASCORE_SEASON_ID_RE.search(text)
        if season_match:
            identity["season_id"] = season_match.group("season_id")
        return identity
    parts = text.split(":")
    if not parts or not parts[0].isdigit():
        return None
    identity = {"tournament_id": parts[0]}
    if len(parts) > 1 and parts[1].isdigit():
        identity["season_id"] = parts[1]
    return identity


def _format_league_id(tournament_id: int, season_id: int | None = None) -> str:
    return f"{tournament_id}:{season_id}" if season_id is not None else str(tournament_id)


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _extract_tournament_page_info(html: str) -> dict[str, Any]:
    match = _NEXT_DATA_RE.search(html or "")
    if not match:
        return {}
    try:
        next_data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    if not isinstance(next_data, dict):
        return {}
    props = next_data.get("props") if isinstance(next_data.get("props"), dict) else {}
    page_props = props.get("pageProps") if isinstance(props.get("pageProps"), dict) else {}
    initial = page_props.get("initialProps") if isinstance(page_props.get("initialProps"), dict) else {}
    if not isinstance(initial, dict):
        return {}
    unique = initial.get("uniqueTournament")
    if not isinstance(unique, dict):
        return {}
    info = initial.get("info") if isinstance(initial.get("info"), dict) else {}
    season = info.get("season") if isinstance(info.get("season"), dict) else None
    seasons = initial.get("seasons") if isinstance(initial.get("seasons"), list) else []
    if season is None:
        season = next((item for item in seasons if isinstance(item, dict)), None)
    category = unique.get("category") if isinstance(unique.get("category"), dict) else {}
    country = category.get("country") if isinstance(category.get("country"), dict) else {}
    return {
        "tournament_id": unique.get("id"),
        "league_name": unique.get("name"),
        "league_slug": unique.get("slug"),
        "country_name": country.get("name") or category.get("name"),
        "country_slug": category.get("slug"),
        "season_id": season.get("id") if isinstance(season, dict) else None,
        "season_name": season.get("name") if isinstance(season, dict) else None,
        "has_events": initial.get("hasEvents"),
        "has_home_away_standings": initial.get("hasHomeAwayStandings"),
    }


def _name_score(left: str, right: str) -> float:
    left_key = _normalize_text(left)
    right_key = _normalize_text(right)
    ratio = SequenceMatcher(a=left_key, b=right_key).ratio()
    left_tokens = set(left_key.split())
    right_tokens = set(right_key.split())
    if not left_tokens or not right_tokens:
        return ratio
    shorter, longer = (left_tokens, right_tokens) if len(left_tokens) <= len(right_tokens) else (right_tokens, left_tokens)
    return max(ratio, len(shorter & longer) / len(shorter))


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"\b(fc|cf|club|women|w|u21|u20|u19|reserves?)\b", " ", text.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _kickoff_delta_minutes(left: str | None, right: str | None) -> float | None:
    left_dt = _parse_datetime(left)
    right_dt = _parse_datetime(right)
    return abs((left_dt - right_dt).total_seconds()) / 60.0 if left_dt and right_dt else None


def _parse_datetime(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _time_score(delta_minutes: float | None) -> float:
    if delta_minutes is None:
        return 0.5
    if delta_minutes <= 5:
        return 1.0
    if delta_minutes <= 30:
        return 0.8
    if delta_minutes <= 90:
        return 0.35
    return 0.0


__all__ = ["SofaScoreBotReadyStatsProvider"]


# Backwards-compatible alias (original sandbox/research name).
SofaScoreBotReadyStatsProvider = SofaScoreHttpStatsProvider
