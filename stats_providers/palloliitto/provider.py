"""Suomen Palloliitto (Finnish Football Association) stats provider adapter."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import datetime, UTC
from difflib import SequenceMatcher
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
from stats_providers.palloliitto.api_client import PalloliittoAPI
from difflib import SequenceMatcher

def _title_from_markdown(markdown: str) -> str:
    """First non-empty line of a federation report ('⚽ *Home vs Away*' -> 'Home vs Away')."""
    for line in (markdown or "").splitlines():
        stripped = line.strip().lstrip("⚽").strip().strip("*").strip()
        if stripped:
            return stripped
    return "Reporte"


# Helper matching routines (copied from standard similarity metrics)
def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\b(fc|cf|club|women|w|u21|u20|u19|reserves?)\b", " ", text.lower())
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


# Matching thresholds
_PER_SIDE_FLOOR = 0.50
_AUTO_COMBINED = 0.78
_AUTO_GAP = 0.08


class PalloliittoStatsProvider(StatsProvider):
    """Stats provider backed by Suomen Palloliitto (Finnish FA) HTTP-only REST API.

    Supports league discovery, fixture discovery, standings tables, team details,
    lineups, and match reports with timeline events.
    """

    name = "palloliitto"
    display_name = "Suomen Palloliitto (Finland)"
    capabilities = StatsProviderCapabilities(
        supports_league_discovery=True,
        supports_fixture_discovery=True,
        supports_live=True,
        supports_h2h=True,
        supports_lineups=True,
        supports_injuries=False,
        supports_odds=False,
        requires_browser_bootstrap=False,
    )

    def __init__(self, *, payload_cache: Any = None) -> None:
        self._cache = payload_cache

    async def search_leagues(
        self,
        *,
        country_name: str,
        query: str | None = None,
        limit: int = 80,
    ) -> list[StatsLeagueOption]:
        """Search Finnish leagues by query or country filtering (Finland/Suomi)."""
        
        country_norm = country_name.strip().lower()
        if "fin" not in country_norm and "suo" not in country_norm:
            # This is a Finland-only provider
            return []

        query_norm = _normalize_text(query or "")
        options: list[StatsLeagueOption] = []
        
        with PalloliittoAPI() as api:
            categories = api.get_categories(season="2026")
            
            seen: set[str] = set()
            for cat in categories:
                cat_id = cat.get("category_id")
                name = cat.get("category_name") or cat.get("name") or ""
                
                # Check query match
                if query_norm and query_norm not in _normalize_text(name):

                    continue
                    
                if cat_id in seen:
                    continue
                seen.add(cat_id)
                
                options.append(
                    StatsLeagueOption(
                        provider=self.name,
                        provider_display_name=self.display_name,
                        country_name="Finland",
                        league_id=f"{cat.get('competition_id')}:{cat_id}",
                        league_name=str(name),
                        season_id=cat.get("season_id"),
                        source_url=f"https://tulospalvelu.palloliitto.fi/category/{cat_id}",
                        raw_payload=cat,
                    )
                )
                if len(options) >= limit:
                    break
                    
        return options

    async def list_fixtures(self, league_id: str, *, limit: int | None = None) -> list[StatsFixture]:
        """List matches (fixtures) for the given league compound ID (competition_id:category_id)."""
        
        parts = league_id.split(":")
        if len(parts) != 2:
            return []
            
        comp_id, cat_id = parts[0], parts[1]
        fixtures: list[StatsFixture] = []
        
        with PalloliittoAPI() as api:
            matches = api.get_matches_by_league(competition_id=comp_id, category_id=cat_id)
            for m in matches:
                m_id = m.get("match_id")
                if not m_id:
                    continue
                
                # Format scheduled date
                time_str = f"{m.get('date', '')} {m.get('time', '')}".strip()
                scheduled_iso = None
                if time_str:
                    try:
                        # Torneopal dates are in Europe/Helsinki (+03:00 / +02:00)
                        # We parse and format roughly to ISO
                        scheduled_iso = f"{m.get('date')}T{m.get('time') or '12:00'}:00+03:00"
                    except Exception:
                        scheduled_iso = None

                status = m.get("status")
                # Normalize status for core contract
                norm_status = None
                if status == "Finished" or status == "Played":
                    norm_status = "played"
                elif status == "Live" or m.get("live_period") != "-1":
                    norm_status = "live"
                elif status == "Forfeited" or status == "Cancelled":
                    norm_status = "cancelled"

                fixtures.append(
                    StatsFixture(
                        provider=self.name,
                        league_id=league_id,
                        match_id=str(m_id),
                        home=str(m.get("team_A_name") or m.get("club_A_name") or ""),
                        away=str(m.get("team_B_name") or m.get("club_B_name") or ""),
                        scheduled_at=scheduled_iso,
                        status=norm_status,
                        stats_url=f"https://tulospalvelu.palloliitto.fi/match/{m_id}",
                        raw_payload=m,
                    )
                )
                
        if limit is not None:
            return fixtures[:limit]
        return fixtures

    async def get_league_overview(self, league_id: str) -> dict[str, Any] | None:
        """Return full league overview (standings/fixtures/scorers/teams) for explore_stats."""
        
        parts = league_id.split(":")
        if len(parts) != 2:
            return None
            
        comp_id, cat_id = parts[0], parts[1]
        
        with PalloliittoAPI() as api:
            # Fetch standings (Group 1 by default, or get groups list)
            # Veikkausliiga has group 1
            group_id = "1"
            
            # Retrieve standings
            try:
                raw_standings = api.get_standings(competition_id=comp_id, category_id=cat_id, group_id=group_id)
            except Exception:
                raw_standings = []
                
            try:
                raw_fixtures = api.get_matches_by_league(competition_id=comp_id, category_id=cat_id)
            except Exception:
                raw_fixtures = []

            # Format standings for standard explore rendering
            formatted_rows = []
            for item in raw_standings:
                formatted_rows.append({
                    "position": item.get("current_standing", 0),
                    "played": item.get("matches_played", 0),
                    "points": item.get("points", 0),
                    "goal_difference": item.get("goals_diff", 0),
                    "wins": item.get("matches_won", 0),
                    "draws": item.get("matches_tied", 0),
                    "losses": item.get("matches_lost", 0),
                    "team": {
                        "name": item.get("team_name", "Unknown")
                    },
                    "home": {
                        "points": item.get("points_home", 0),
                        "goals_for": item.get("goals_for_home", 0),
                        "goals_against": item.get("goals_against_home", 0)
                    },
                    "away": {
                        "points": item.get("points_away", 0),
                        "goals_for": item.get("goals_for_away", 0),
                        "goals_against": item.get("goals_against_away", 0)
                    }
                })

            standings_block = {
                "tables": [{
                    "name": f"Grupo {group_id}",
                    "rows": formatted_rows
                }]
            }

            # Format fixtures
            formatted_fixtures = []
            for f in raw_fixtures:
                formatted_fixtures.append({
                    "match_id": str(f.get("match_id")),
                    "home": {"name": f.get("team_A_name") or f.get("club_A_name")},
                    "away": {"name": f.get("team_B_name") or f.get("club_B_name")},
                    "time": {
                        "iso_utc": f"{f.get('date')}T{f.get('time') or '12:00'}:00+03:00",
                        "date": f.get("date"),
                        "time": f.get("time")
                    }
                })

            return {
                "league_id": league_id,
                "league_name": f"Liga {cat_id}",
                "source_url": f"https://tulospalvelu.palloliitto.fi/category/{cat_id}",
                "standings": standings_block,
                "fixtures": formatted_fixtures,
                "teams": [],
                "top_goals": []
            }

    async def resolve_match(
        self,
        candidate: MatchIdentityCandidate,
        *,
        league_id: str | None = None,
    ) -> StatsMatchLink | None:
        """Resolve one sportsbook event to a Palloliitto stats match."""
        
        # Direct URL mapping
        direct_match_id = None
        if candidate.stats_url and "match/" in candidate.stats_url:
            direct_match_id = candidate.stats_url.split("match/")[-1].split("?")[0]
            
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

        # Resolve via name similarity on league fixtures
        fixtures = await self.list_fixtures(league_id)
        scored = []
        
        for f in fixtures:
            home_score = _name_score(candidate.home, f.home)
            away_score = _name_score(candidate.away, f.away)
            
            if min(home_score, away_score) < _PER_SIDE_FLOOR:
                continue
                
            delta = _kickoff_delta_minutes(candidate.scheduled_at, f.scheduled_at)
            t_score = _time_score(delta)
            
            combined = (home_score * 0.45) + (away_score * 0.45) + (t_score * 0.10)

            scored.append((combined, f, home_score, away_score, delta))
            
        if not scored:
            return None
            
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0]
        
        # Unambiguous criteria check
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
        )

    async def build_match_report(self, stats_match_id: str) -> MatchStatsReport:
        """Unified federation report: delegates to the FinlandLeagues adapter so the
        ``/stats`` output matches ``/fin_match`` and every other federation (same
        FORMA/H2H/GOLES/TABLA layout)."""

        def _render() -> str:
            from bot.special_leagues import FinlandLeagues

            adapter = FinlandLeagues(PalloliittoAPI())
            try:
                return adapter.match_report(str(stats_match_id))
            finally:
                adapter.close()

        markdown = await asyncio.to_thread(_render)
        return MatchStatsReport(
            provider=self.name,
            match_id=str(stats_match_id),
            title=_title_from_markdown(markdown),
            markdown=markdown,
            data={"stats_match_id": str(stats_match_id)},
            generated_at=datetime.now(UTC).isoformat(),
        )

    def build_match_url(self, stats_match_id: str) -> str | None:
        """Return the public result service match URL."""
        if not stats_match_id:
            return None
        return f"https://tulospalvelu.palloliitto.fi/match/{stats_match_id}"
