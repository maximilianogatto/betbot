"""Svenskfotboll HTTP stats provider adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any, Protocol, TypeVar
from zoneinfo import ZoneInfo

from core.stats_models import (
    MatchIdentityCandidate,
    MatchStatsReport,
    StatsFixture,
    StatsLeagueOption,
    StatsMatchLink,
    StatsProviderCapabilities,
)
from core.stats_provider_base import StatsProvider
from stats_providers.svenskfotboll_http.client import SvenskfotbollHTTPClient


_T = TypeVar("_T")
_PER_SIDE_FLOOR = 0.50
_AUTO_COMBINED = 0.78
_AUTO_GAP = 0.08
_SWEDEN_TZ = ZoneInfo("Europe/Stockholm")


class StatsPayloadCache(Protocol):
    def get_cached_stats_payload(self, cache_key: str) -> dict[str, Any] | None: ...

    def set_cached_stats_payload(self, cache_key: str, payload: dict[str, Any], *, ttl_seconds: float) -> None: ...


class SvenskfotbollHttpStatsProvider(StatsProvider):
    """Stats provider backed by Swedish FA HTTP endpoints.

    The provider intentionally avoids Cloudflare-protected match/detail pages.
    It uses API/widget/XML endpoints that were validated in
    `sandbox/svenskfotboll_http`.
    """

    name = "svenskfotboll_http"
    display_name = "Svenskfotboll (Sweden)"
    capabilities = StatsProviderCapabilities(
        supports_league_discovery=True,
        supports_fixture_discovery=True,
        supports_live=True,
        supports_h2h=False,
        supports_lineups=True,
        supports_injuries=False,
        supports_odds=False,
        requires_browser_bootstrap=False,
    )

    def __init__(
        self,
        *,
        client: SvenskfotbollHTTPClient | Any | None = None,
        payload_cache: StatsPayloadCache | None = None,
        cache_ttl_seconds: float = 900.0,
    ) -> None:
        self._client = client or SvenskfotbollHTTPClient()
        self._cache = payload_cache
        self._cache_ttl_seconds = max(0.0, cache_ttl_seconds)

    async def stop(self) -> None:
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
        """Search Swedish FA competitions.

        The country gate accepts common Spanish/English/Swedish spellings to fit
        the existing Telegram flow that first asks for country text.
        """

        if not _looks_like_sweden(country_name):
            return []

        leagues = await self._cached_payload(
            f"search:{_normalize_text(query or '')}:{limit}",
            self._client.search_leagues,
            query,
            limit=limit,
            ttl=self._cache_ttl_seconds,
        )
        options: list[StatsLeagueOption] = []
        for item in leagues or []:
            league_id = str(item.get("competition_id") or "")
            if not league_id:
                continue
            options.append(
                StatsLeagueOption(
                    provider=self.name,
                    provider_display_name=self.display_name,
                    country_name="Sweden",
                    league_id=league_id,
                    league_name=str(item.get("name") or f"Competition {league_id}"),
                    season_id=_season_from_name(item.get("name")),
                    source_url=self.build_league_url(league_id),
                    raw_payload=item,
                )
            )
        return options[:limit]

    async def describe_league(self, league_id: str) -> StatsLeagueOption | None:
        league_id = _league_id_from_reference(league_id) or _split_stats_match_id(league_id)[0] or league_id
        leagues = await self._cached_payload(
            "search::500",
            self._client.search_leagues,
            None,
            limit=500,
            ttl=self._cache_ttl_seconds,
        )
        for item in leagues or []:
            if str(item.get("competition_id") or "") != str(league_id):
                continue
            return StatsLeagueOption(
                provider=self.name,
                provider_display_name=self.display_name,
                country_name="Sweden",
                league_id=str(league_id),
                league_name=str(item.get("name") or f"Competition {league_id}"),
                season_id=_season_from_name(item.get("name")),
                source_url=self.build_league_url(str(league_id)),
                raw_payload=item,
            )
        return None

    async def list_fixtures(self, league_id: str, *, limit: int | None = None) -> list[StatsFixture]:
        """List upcoming fixtures for one Swedish FA competition id."""

        competition_id = _league_id_from_reference(league_id) or _split_stats_match_id(league_id)[0] or league_id
        upcoming = await self._cached_payload(
            f"league:{competition_id}:upcoming",
            self._client.get_upcoming_matches,
            competition_id,
            limit=max(limit or 40, 40),
            ttl=self._cache_ttl_seconds,
        )
        fixtures: list[StatsFixture] = []
        for item in upcoming.get("matches", []) if isinstance(upcoming, dict) else []:
            match_id = str(item.get("match_id") or "")
            if not match_id:
                continue
            stats_match_id = _build_stats_match_id(str(competition_id), match_id)
            fixtures.append(
                StatsFixture(
                    provider=self.name,
                    league_id=str(competition_id),
                    match_id=stats_match_id,
                    home=str(item.get("home") or ""),
                    away=str(item.get("away") or ""),
                    scheduled_at=_local_swedish_to_iso(item.get("start_time_local")),
                    status=None,
                    stats_url=self.build_match_url(stats_match_id),
                    raw_payload=item,
                )
            )
        return fixtures[:limit] if limit is not None else fixtures

    async def get_league_overview(self, league_id: str) -> dict[str, Any] | None:
        """Return compact standings, upcoming fixtures and latest results."""

        competition_id = _league_id_from_reference(league_id) or _split_stats_match_id(league_id)[0] or league_id
        standings, upcoming, latest = await asyncio.gather(
            self._cached_payload(
                f"league:{competition_id}:standings",
                self._client.get_standings,
                competition_id,
                ttl=self._cache_ttl_seconds,
            ),
            self._cached_payload(
                f"league:{competition_id}:upcoming",
                self._client.get_upcoming_matches,
                competition_id,
                ttl=self._cache_ttl_seconds,
            ),
            self._cached_payload(
                f"league:{competition_id}:latest",
                self._client.get_latest_results,
                competition_id,
                ttl=self._cache_ttl_seconds,
            ),
        )
        rows = [
            {
                "position": team.get("position"),
                "played": team.get("played"),
                "points": team.get("points"),
                "goal_difference": team.get("goal_difference"),
                "team": {"name": team.get("team"), "id": team.get("team_id")},
            }
            for team in standings.get("teams", [])
        ]
        return {
            "league_id": str(competition_id),
            "league_name": standings.get("title") or f"Competition {competition_id}",
            "source_url": self.build_league_url(str(competition_id)),
            "standings": {"tables": [{"name": standings.get("title") or "Tabla", "rows": rows}]},
            "fixtures": [
                {
                    "match_id": _build_stats_match_id(str(competition_id), str(match.get("match_id") or "")),
                    "home": {"name": match.get("home")},
                    "away": {"name": match.get("away")},
                    "time": {
                        "iso_utc": _local_swedish_to_iso(match.get("start_time_local")),
                        "local": match.get("start_time_local"),
                    },
                }
                for match in upcoming.get("matches", [])
                if match.get("match_id")
            ],
            "latest_results": latest.get("matches", []),
            "teams": [],
            "top_goals": [],
            "_provider_standings": standings,
            "_provider_upcoming": upcoming,
            "_provider_latest": latest,
        }

    async def resolve_match(
        self,
        candidate: MatchIdentityCandidate,
        *,
        league_id: str | None = None,
    ) -> StatsMatchLink | None:
        direct = _direct_stats_match_id(candidate.stats_url)
        if direct:
            competition_id, match_id = _split_stats_match_id(direct)
            return StatsMatchLink(
                provider=self.name,
                stats_match_id=direct,
                stats_url=self.build_match_url(direct),
                confidence=1.0,
                method="direct_stats_url",
                raw_payload={"competition_id": competition_id, "match_id": match_id},
            )
        if not league_id:
            return None

        scored: list[tuple[float, StatsFixture, float, float, float | None]] = []
        for fixture in await self.list_fixtures(league_id):
            home_score = _name_score(candidate.home, fixture.home)
            away_score = _name_score(candidate.away, fixture.away)
            if min(home_score, away_score) < _PER_SIDE_FLOOR:
                continue
            delta = _kickoff_delta_minutes(candidate.scheduled_at, fixture.scheduled_at)
            time_score = _time_score(delta)
            combined = (home_score * 0.45) + (away_score * 0.45) + (time_score * 0.10)
            scored.append((combined, fixture, home_score, away_score, delta))

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
            method="league_fixture_similarity",
            home_similarity=round(best[2], 6),
            away_similarity=round(best[3], 6),
            kickoff_delta_minutes=best[4],
            raw_payload=best[1].raw_payload,
        )

    async def build_match_report(self, stats_match_id: str) -> MatchStatsReport:
        """Build Telegram-ready report for one Svenskfotboll fixture."""

        competition_id, match_id = _split_stats_match_id(stats_match_id)
        data: dict[str, Any] = {"stats_match_id": stats_match_id, "competition_id": competition_id, "match_id": match_id}
        live = await self._try_live_game_info(match_id) if match_id else None
        data["live"] = live

        standings = upcoming = latest = None
        if competition_id:
            standings, upcoming, latest = await asyncio.gather(
                self._cached_payload(
                    f"league:{competition_id}:standings",
                    self._client.get_standings,
                    competition_id,
                    ttl=self._cache_ttl_seconds,
                ),
                self._cached_payload(
                    f"league:{competition_id}:upcoming",
                    self._client.get_upcoming_matches,
                    competition_id,
                    ttl=self._cache_ttl_seconds,
                ),
                self._cached_payload(
                    f"league:{competition_id}:latest",
                    self._client.get_latest_results,
                    competition_id,
                    ttl=self._cache_ttl_seconds,
                ),
            )
            data.update({"standings": standings, "upcoming": upcoming, "latest": latest})

        fixture = _find_match(match_id, upcoming) or _find_match(match_id, latest)
        home = _pick_team_name(live, fixture, "home") or "Local"
        away = _pick_team_name(live, fixture, "away") or "Visitante"
        title = f"{home} vs {away}"
        markdown = _render_report(
            title=title,
            fixture=fixture,
            live=live,
            standings=standings,
            latest=latest,
            provider_url=self.build_match_url(stats_match_id),
        )
        return MatchStatsReport(
            provider=self.name,
            match_id=stats_match_id,
            title=title,
            markdown=markdown,
            data=data,
            generated_at=datetime.now(UTC).isoformat(),
        )

    def build_match_url(self, stats_match_id: str) -> str | None:
        competition_id, match_id = _split_stats_match_id(stats_match_id)
        if match_id:
            return f"https://www.svenskfotboll.se/widget-go-to/?scr=result&fmid={match_id}"
        if competition_id:
            return self.build_league_url(competition_id)
        return None

    def build_league_url(self, league_id: str) -> str:
        return f"https://www.svenskfotboll.se/widget-go-to/?scr=table&ftid={league_id}"

    async def _try_live_game_info(self, match_id: str | None) -> dict[str, Any] | None:
        if not match_id:
            return None
        try:
            return await self._call(self._client.get_live_game_info, match_id)
        except Exception:
            return None

    async def _cached_payload(
        self,
        cache_key: str,
        func: Callable[..., _T],
        *args: Any,
        ttl: float,
        **kwargs: Any,
    ) -> _T:
        full_key = f"svenskfotboll_http:{cache_key}"
        if self._cache is not None and ttl > 0:
            cached = await self._call(self._cache.get_cached_stats_payload, full_key)
            if cached is not None:
                return cached  # type: ignore[return-value]
        payload = await self._call(func, *args, **kwargs)
        if self._cache is not None and ttl > 0 and isinstance(payload, dict):
            await self._call(self._cache.set_cached_stats_payload, full_key, payload, ttl_seconds=ttl)
        return payload

    async def _call(self, func: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
        return await asyncio.to_thread(func, *args, **kwargs)


def _render_report(
    *,
    title: str,
    fixture: dict[str, Any] | None,
    live: dict[str, Any] | None,
    standings: dict[str, Any] | None,
    latest: dict[str, Any] | None,
    provider_url: str | None,
) -> str:
    lines: list[str] = []
    if fixture and fixture.get("start_time_local"):
        lines.append(f"📅 Fecha: {fixture.get('start_time_local')}")
    if provider_url:
        lines.append(f"🔗 Fuente: {provider_url}")
    if live:
        status = (live.get("status") or {}).get("desc") or "N/A"
        score = live.get("score") or {}
        lines.append(f"📡 Estado live: {status}")
        if score:
            lines.append(f"⚽ Marcador: {score.get('home-team', '?')} - {score.get('away-team', '?')}")
        summary = live.get("event_summary") or {}
        lines.append(
            "📊 Eventos: "
            f"goles={summary.get('goals', 0)} | rojas={summary.get('red_cards', 0)} | corners={summary.get('corners', 0)}"
        )
        stats = live.get("stats") or {}
        if stats:
            lines.append(
                "🎯 Stats live: "
                f"corners {stats.get('home-corners', '?')}-{stats.get('away-corners', '?')} | "
                f"tiros al arco {stats.get('home-shots-on-goal', '?')}-{stats.get('away-shots-on-goal', '?')} | "
                f"rojas {stats.get('home-red-cards', '?')}-{stats.get('away-red-cards', '?')}"
            )
        latest_event = summary.get("latest_event")
        if latest_event:
            lines.append(
                f"🕒 Último evento: {latest_event.get('game-minute-for-web') or latest_event.get('game-time-for-web') or '?'}' "
                f"{latest_event.get('type-desc') or latest_event.get('type') or ''}"
            )
    else:
        lines.append("📡 Live: sin XML disponible todavía para este partido.")

    home = _pick_team_name(live, fixture, "home")
    away = _pick_team_name(live, fixture, "away")
    standing_lines = _standing_context(home, away, standings)
    if standing_lines:
        lines.append("")
        lines.append("🏆 Tabla:")
        lines.extend(standing_lines)

    recent_lines = _recent_context(home, away, latest)
    if recent_lines:
        lines.append("")
        lines.append("🧾 Resultados recientes:")
        lines.extend(recent_lines)

    return "\n".join(lines) if lines else f"No pude recuperar datos para {title}."


def _standing_context(home: str | None, away: str | None, standings: dict[str, Any] | None) -> list[str]:
    teams = standings.get("teams", []) if isinstance(standings, dict) else []
    home_row = _find_team_row(home, teams)
    away_row = _find_team_row(away, teams)
    lines = []
    if home_row:
        lines.append(
            f"- {home_row.get('team')}: {home_row.get('position')}º, "
            f"{home_row.get('points')} pts, DG {home_row.get('goal_difference')}"
        )
    if away_row:
        lines.append(
            f"- {away_row.get('team')}: {away_row.get('position')}º, "
            f"{away_row.get('points')} pts, DG {away_row.get('goal_difference')}"
        )
    return lines


def _recent_context(home: str | None, away: str | None, latest: dict[str, Any] | None, *, limit: int = 5) -> list[str]:
    if not home and not away:
        return []
    matches = latest.get("matches", []) if isinstance(latest, dict) else []
    lines = []
    for match in matches:
        if not _involves_team(match, home) and not _involves_team(match, away):
            continue
        lines.append(
            f"- {match.get('start_time_local')}: {match.get('home')} - {match.get('away')} "
            f"{match.get('score') or ''}".strip()
        )
        if len(lines) >= limit:
            break
    return lines


def _find_team_row(team_name: str | None, teams: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not team_name:
        return None
    scored = [(_name_score(team_name, str(row.get("team") or "")), row) for row in teams]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] >= 0.55 else None


def _find_match(match_id: str | None, document: dict[str, Any] | None) -> dict[str, Any] | None:
    if not match_id or not isinstance(document, dict):
        return None
    for match in document.get("matches", []) or []:
        if str(match.get("match_id") or "") == str(match_id):
            return match
    return None


def _pick_team_name(live: dict[str, Any] | None, fixture: dict[str, Any] | None, side: str) -> str | None:
    if live:
        value = ((live.get(side) or {}).get("name") or (live.get(side) or {}).get("short_name"))
        if value:
            return str(value)
    if fixture and fixture.get(side):
        return str(fixture.get(side))
    return None


def _involves_team(match: dict[str, Any], team_name: str | None) -> bool:
    if not team_name:
        return False
    return _name_score(team_name, str(match.get("home") or "")) >= 0.70 or _name_score(
        team_name,
        str(match.get("away") or ""),
    ) >= 0.70


def _direct_stats_match_id(stats_url: str | None) -> str | None:
    if not stats_url:
        return None
    ftid_match = re.search(r"[?&]ftid=(\d+)", stats_url)
    fmid_match = re.search(r"[?&]fmid=(\d+)", stats_url)
    if ftid_match and fmid_match:
        return _build_stats_match_id(ftid_match.group(1), fmid_match.group(1))
    if fmid_match:
        return fmid_match.group(1)
    match_path = re.search(r"/(\d+)/?(?:\?|$)", stats_url)
    return match_path.group(1) if match_path else None


def _league_id_from_reference(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"[?&]ftid=(\d+)", str(value))
    if match:
        return match.group(1)
    if str(value).strip().isdigit():
        return str(value).strip()
    return None


def _build_stats_match_id(competition_id: str, match_id: str) -> str:
    return f"{competition_id}:{match_id}" if competition_id and match_id else match_id or competition_id


def _split_stats_match_id(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    parts = str(value).split(":", 1)
    if len(parts) == 2:
        return parts[0] or None, parts[1] or None
    return None, str(value)


def _looks_like_sweden(country_name: str) -> bool:
    norm = _normalize_text(country_name)
    return any(token in norm for token in {"sweden", "sverige", "suecia", "svensk", "swe", "sue"})


def _season_from_name(value: Any) -> str | None:
    match = re.search(r"\b(20\d{2})(?:[/\-](\d{2,4}))?\b", str(value or ""))
    if not match:
        return None
    if match.group(2):
        return f"{match.group(1)}/{match.group(2)}"
    return match.group(1)


def _local_swedish_to_iso(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        # Svenskfotboll widget times are Sweden local time. Attach the real
        # Swedish timezone so summer/winter offsets remain correct.
        parsed = datetime.fromisoformat(text.replace(" ", "T"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_SWEDEN_TZ)
        return parsed.isoformat()
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _kickoff_delta_minutes(left: str | None, right: str | None) -> float | None:
    left_dt = _parse_datetime(left)
    right_dt = _parse_datetime(right)
    if left_dt is None or right_dt is None:
        return None
    return abs((left_dt - right_dt).total_seconds()) / 60.0


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


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\b(fc|fk|if|aif|bk|women|w|u23|u21|u20|u19|reserves?)\b", " ", text.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _name_score(left: str, right: str) -> float:
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


__all__ = ["SvenskfotbollHttpStatsProvider"]
