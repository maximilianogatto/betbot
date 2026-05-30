"""Sportradar/Statshub stats provider adapter.

The heavy lifting still lives in `stats_providers/sportradar_http/engine`, where the HTTP
bootstrap/replay research is isolated and tested. This adapter is the first
production-facing seam: it translates sandbox outputs into the generic
`StatsProvider` contract without touching bot commands or storage.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any, Callable, TypeVar

from core.stats_models import (
    MatchIdentityCandidate,
    MatchStatsReport,
    StatsFixture,
    StatsLeagueOption,
    StatsMatchLink,
    StatsProviderCapabilities,
)
from core.stats_provider_base import StatsProvider
from stats_providers.sportradar_http.engine.bot_ready.provider import (
    BotReadyMatchRequest,
    BotReadyRuntimeConfig,
    BotReadyTournamentRequest,
    SportradarBotReadyProvider,
)
from stats_providers.sportradar_http.engine.endpoints.discovery import get_config_tree_mini
from stats_providers.sportradar_http.engine.runtime import normalize_bootstrap_mode
from stats_providers.sportradar_http.engine.tournament_navigation import build_tournament_tree


_T = TypeVar("_T")
_MATCH_URL_RE = re.compile(r"/match/(\d+)")

# Matching thresholds. Names are compared per side (home and away) so the pair
# itself disambiguates short, repeated names (e.g. two "Canberra" clubs): a wrong
# fixture fails because its *other* team will not clear the per-side floor.
_PER_SIDE_FLOOR = 0.50
_AUTO_COMBINED = 0.78
_AUTO_GAP = 0.08


class SportradarHttpStatsProvider(StatsProvider):
    """Stats provider backed by Sportradar Statshub HTTP replay.

    The provider supports league discovery, fixture discovery, match linking and
    report generation. It may use a browser only for short-lived bootstrap when
    the cached signed Statshub token is missing or expired.
    """

    name = "sportradar_statshub"
    display_name = "Sportradar Statshub"
    capabilities = StatsProviderCapabilities(
        supports_league_discovery=True,
        supports_fixture_discovery=True,
        supports_live=True,
        supports_h2h=True,
        supports_lineups=False,
        supports_injuries=True,
        supports_odds=True,
        requires_browser_bootstrap=True,
    )

    def __init__(
        self,
        *,
        runtime: SportradarBotReadyProvider | Any | None = None,
        sport_id: int = 1,
        category_id: int = 67,
        runtime_config: BotReadyRuntimeConfig | None = None,
    ) -> None:
        self.sport_id = sport_id
        self.category_id = category_id
        self._runtime_config = runtime_config or _default_runtime_config()
        self._runtime = runtime or SportradarBotReadyProvider(self._runtime_config)

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[StatsLeagueOption]:
        """Search Statshub tournaments by country and optional league query."""

        if hasattr(self._runtime, "search_leagues"):
            raw_options = await self._call(self._runtime.search_leagues, country_name=country_name, query=query, limit=limit)
            return [self._league_option_from_mapping(item) for item in raw_options[:limit]]

        tree = await self._load_tournament_tree()
        country_key = _normalize_text(country_name)
        query_key = _normalize_text(query or "")
        options: list[StatsLeagueOption] = []
        seen: set[tuple[str, str]] = set()
        for item in tree.get("tournaments") or []:
            if not isinstance(item, dict):
                continue
            item_country = _normalize_text(item.get("country_name") or "")
            item_name = _normalize_text(item.get("name") or "")
            if country_key and country_key not in item_country:
                continue
            if query_key and query_key not in item_name:
                continue
            league_id = _string_id(item.get("unique_tournament_id") or item.get("tournament_id") or item.get("season_id"))
            if not league_id:
                continue
            dedupe_key = (league_id, item_name)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            options.append(self._league_option_from_mapping(item))
            if len(options) >= limit:
                break
        return options

    async def list_fixtures(self, league_id: str, *, limit: int | None = None) -> list[StatsFixture]:
        """List known fixtures for one Statshub tournament id."""

        request = BotReadyTournamentRequest(
            sport_id=self.sport_id,
            tournament_id=int(league_id),
            category_id=self.category_id,
            depth=0,
        )
        payload = await self._call(self._runtime.get_tournament_navigation, request)
        raw_fixtures = payload.get("fixtures") if isinstance(payload, dict) else []
        fixtures = [self._fixture_from_mapping(league_id, item) for item in raw_fixtures or []]
        fixtures = [fixture for fixture in fixtures if fixture.match_id]
        if limit is not None:
            return fixtures[:limit]
        return fixtures

    async def resolve_match(
        self,
        candidate: MatchIdentityCandidate,
        *,
        league_id: str | None = None,
    ) -> StatsMatchLink | None:
        """Resolve an odds event to a Statshub match.

        Direct Statshub URLs are trusted. Otherwise a linked league is required
        and fixtures are scored by home/away similarity plus kickoff proximity.
        """

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
        best = ranked[0]
        gap = best.confidence - ranked[1].confidence if len(ranked) > 1 else 1.0
        # Only auto-link when the top candidate is both strong and unambiguous.
        # Otherwise the caller should offer the ranked list for manual selection.
        if best.confidence < _AUTO_COMBINED or gap < _AUTO_GAP:
            return None
        return best

    async def rank_match_candidates(
        self,
        candidate: MatchIdentityCandidate,
        *,
        league_id: str,
        limit: int = 5,
    ) -> list[StatsMatchLink]:
        """Rank league fixtures for an odds event using per-side name scoring.

        A fixture is only a candidate when both the home and away names clear
        `_PER_SIDE_FLOOR`; the combined score then orders the survivors. Returning
        a ranked list lets the caller auto-link a confident top or fall back to
        manual disambiguation when the field is close.
        """

        fixtures = await self.list_fixtures(league_id)
        scored: list[tuple[float, StatsFixture, dict[str, Any]]] = []
        for fixture in fixtures:
            home_score = _name_score(candidate.home, fixture.home)
            away_score = _name_score(candidate.away, fixture.away)
            if min(home_score, away_score) < _PER_SIDE_FLOOR:
                continue
            kickoff_delta = _kickoff_delta_minutes(candidate.scheduled_at, fixture.scheduled_at)
            time_score = _time_score(kickoff_delta)
            combined = (home_score * 0.45) + (away_score * 0.45) + (time_score * 0.10)
            details = {
                "home_similarity": round(home_score, 6),
                "away_similarity": round(away_score, 6),
                "kickoff_delta_minutes": kickoff_delta,
                "time_score": round(time_score, 6),
            }
            scored.append((combined, fixture, details))
        scored.sort(key=lambda item: item[0], reverse=True)
        candidate_payload = {
            "home": candidate.home,
            "away": candidate.away,
            "scheduled_at": candidate.scheduled_at,
            "league_name": candidate.league_name,
            "platform": candidate.platform,
            "external_event_id": candidate.external_event_id,
        }
        return [
            StatsMatchLink(
                provider=self.name,
                stats_match_id=fixture.match_id,
                stats_url=fixture.stats_url or self.build_match_url(fixture.match_id),
                confidence=round(combined, 6),
                method="league_fixture_similarity",
                home_similarity=details["home_similarity"],
                away_similarity=details["away_similarity"],
                kickoff_delta_minutes=details["kickoff_delta_minutes"],
                raw_payload={
                    "candidate": candidate_payload,
                    "fixture": fixture.raw_payload,
                    "score_details": details,
                    "stats_home": fixture.home,
                    "stats_away": fixture.away,
                    "stats_scheduled_at": fixture.scheduled_at,
                },
            )
            for combined, fixture, details in scored[:limit]
        ]

    async def ensure_session_fresh(self, *, min_ttl_seconds: float = 3600.0) -> bool:
        """Proactively refresh the provider token if it expires within the window.

        Returns True when a browser bootstrap was performed. Safe to call from a
        background job so the token is minted off the user-facing request path.
        """

        ensure = getattr(self._runtime, "ensure_fresh_session", None)
        if not callable(ensure):
            return False
        return await self._call(ensure, min_ttl_seconds=min_ttl_seconds)

    async def count_matching_events(
        self,
        league_id: str,
        candidates: list[MatchIdentityCandidate],
    ) -> int:
        """Count how many odds events have a plausible fixture in this league.

        Fixtures are fetched once and each candidate is matched with the same
        per-side floor used by `resolve_match`. Used to validate which of several
        same-named leagues actually holds the tracked teams.
        """

        if not candidates:
            return 0
        fixtures = await self.list_fixtures(league_id)
        matched = 0
        for candidate in candidates:
            for fixture in fixtures:
                home_score = _name_score(candidate.home, fixture.home)
                away_score = _name_score(candidate.away, fixture.away)
                if min(home_score, away_score) >= _PER_SIDE_FLOOR:
                    matched += 1
                    break
        return matched

    async def build_match_report(self, stats_match_id: str) -> MatchStatsReport:
        """Build a compact Telegram-ready report for one Statshub match."""

        payload = await self._call(self._runtime.get_match_report, BotReadyMatchRequest(match_id=int(stats_match_id)))
        snapshot = payload.get("snapshot") if isinstance(payload, dict) else {}
        intelligence = payload.get("intelligence") if isinstance(payload, dict) else {}
        metadata = snapshot.get("metadata") if isinstance(snapshot, dict) else {}
        home = _nested_name(metadata, "home") or "Local"
        away = _nested_name(metadata, "away") or "Visitante"
        markdown = (
            payload.get("intelligence_markdown")
            or payload.get("report_markdown")
            or f"{home} vs {away}\n\nSin reporte disponible."
        )
        return MatchStatsReport(
            provider=self.name,
            match_id=str(stats_match_id),
            title=f"{home} vs {away}",
            markdown=str(markdown).strip(),
            data=payload if isinstance(payload, dict) else {},
            generated_at=datetime.now(UTC).isoformat(),
        )

    def build_match_url(self, stats_match_id: str) -> str | None:
        """Return the public Statshub match URL."""

        if not stats_match_id:
            return None
        return f"https://statshub.sportradar.com/bet365/en/match/{stats_match_id}"

    async def _load_tournament_tree(self) -> dict[str, Any]:
        client = await self._call(self._runtime._client)  # sandbox adapter boundary
        payload = await self._call(
            get_config_tree_mini,
            client,
            sport_id=self.sport_id,
            category_id=self.category_id,
            depth=0,
        )
        persist_state = getattr(self._runtime, "_persist_state", None)
        if callable(persist_state):
            await self._call(persist_state, client)
        return build_tournament_tree(payload)

    async def _call(self, func: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return await asyncio.to_thread(func, *args, **kwargs)

    def _league_option_from_mapping(self, item: dict[str, Any]) -> StatsLeagueOption:
        league_id = _string_id(item.get("unique_tournament_id") or item.get("tournament_id") or item.get("season_id")) or ""
        season_id = _string_id(item.get("season_id") or item.get("current_season_id"))
        return StatsLeagueOption(
            provider=self.name,
            provider_display_name=self.display_name,
            country_name=item.get("country_name"),
            league_id=league_id,
            league_name=str(item.get("name") or f"Tournament {league_id}"),
            season_id=season_id,
            source_url=f"https://statshub.sportradar.com/bet365/en/sport/{self.sport_id}/tournament/{league_id}",
            raw_payload=item,
        )

    def _fixture_from_mapping(self, league_id: str, item: dict[str, Any]) -> StatsFixture:
        home = item.get("home") if isinstance(item.get("home"), dict) else {}
        away = item.get("away") if isinstance(item.get("away"), dict) else {}
        time_data = item.get("time") if isinstance(item.get("time"), dict) else {}
        status = item.get("status") if isinstance(item.get("status"), dict) else {}
        match_id = _string_id(item.get("match_id")) or ""
        return StatsFixture(
            provider=self.name,
            league_id=str(league_id),
            match_id=match_id,
            home=str(home.get("name") or ""),
            away=str(away.get("name") or ""),
            scheduled_at=time_data.get("iso_utc"),
            status=_fixture_status(status),
            stats_url=self.build_match_url(match_id),
            raw_payload=item,
        )


def _extract_match_id(url: str | None) -> str | None:
    if not url:
        return None
    match = _MATCH_URL_RE.search(url)
    return match.group(1) if match else None


def _default_runtime_config() -> BotReadyRuntimeConfig:
    """Build runtime config honoring `SPORTRADAR_BOOTSTRAP_MODE` from `.env`."""

    return BotReadyRuntimeConfig(bootstrap_mode=normalize_bootstrap_mode(None))


def _fixture_status(status: dict[str, Any]) -> str | None:
    if status.get("canceled"):
        return "canceled"
    if status.get("postponed"):
        return "postponed"
    if status.get("in_livescore"):
        return "live"
    return None


def _kickoff_delta_minutes(left: str | None, right: str | None) -> float | None:
    left_dt = _parse_datetime(left)
    right_dt = _parse_datetime(right)
    if left_dt is None or right_dt is None:
        return None
    return abs((left_dt - right_dt).total_seconds()) / 60.0


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
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


def _text_similarity(left: str, right: str) -> float:
    return SequenceMatcher(a=_normalize_text(left), b=_normalize_text(right)).ratio()


def _name_score(left: str, right: str) -> float:
    """Score two team names, tolerant to one side abbreviating the other.

    Sportradar tends to shorten names ("Newcastle") while sportsbooks pad them
    ("Newcastle Olympic Warriors"). Character ratio punishes that length gap, so
    we also measure token containment (are the shorter name's words a subset of
    the longer's?) and keep whichever signal is stronger.
    """

    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    ratio = SequenceMatcher(a=left_norm, b=right_norm).ratio()
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    if not left_tokens or not right_tokens:
        return ratio
    shorter, longer = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )
    containment = len(shorter & longer) / len(shorter)
    return max(ratio, containment)


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\b(fc|cf|club|women|w|u21|u20|u19|reserves?)\b", " ", text.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _string_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _nested_name(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, dict):
        name = value.get("name")
        return str(name) if name else None
    return None


__all__ = ["SportradarHttpStatsProvider"]
