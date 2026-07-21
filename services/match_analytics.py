"""Pre-match analytics block shared by /fin_match and /swe_match.

Reuses the peak model's :class:`~services.peak_model.LeagueModel` (which already
carries per-team home/away goals + the finished-match list), so it computes —
without any new fetch logic — the things a quick read wants before a game:

* table positions of both sides,
* recent form (last 5, W/D/L) of each,
* head-to-head (if any in the data),
* goal averages: league-wide, league home/away, and per team.

Pure and network-free: a provider adapter builds the LeagueModel, this module
turns it into a :class:`MatchAnalytics` and renders it. ``render_analytics``
takes an ``escape`` callable so the same block works in Markdown (/fin) or
HTML (/swe) without leaking markup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from services.peak_model import LeagueModel, TeamStats


@dataclass
class TeamGoals:
    name: str
    played: int
    scored_avg: Optional[float]
    conceded_avg: Optional[float]
    scored_home_avg: Optional[float]
    scored_away_avg: Optional[float]


@dataclass
class H2HMatch:
    date: str
    home: str
    away: str
    gh: int
    ga: int


@dataclass
class MatchAnalytics:
    n_teams: int
    home_position: Optional[int]
    away_position: Optional[int]
    home_form: list[str]  # most recent first: 'W' | 'D' | 'L'
    away_form: list[str]
    h2h: list[H2HMatch]
    league_avg: Optional[float]       # goals per team per match (overall)
    league_home_avg: Optional[float]  # goals a home team scores per home match
    league_away_avg: Optional[float]  # goals an away team scores per away match
    home_goals: TeamGoals
    away_goals: TeamGoals


def _div(num: float, den: float) -> Optional[float]:
    return (num / den) if den else None


def _team_goals(name: str, t: Optional[TeamStats]) -> TeamGoals:
    if t is None:
        return TeamGoals(name, 0, None, None, None, None)
    played = (t.played_home + t.played_away) or t.played
    return TeamGoals(
        name=name,
        played=played,
        scored_avg=_div(t.gf_home + t.gf_away, played),
        conceded_avg=_div(t.ga_home + t.ga_away, played),
        scored_home_avg=_div(t.gf_home, t.played_home),
        scored_away_avg=_div(t.gf_away, t.played_away),
    )


def _form_for(team_id: str, matches: list, limit: int) -> list[str]:
    rel = [m for m in matches if team_id in (m.home_id, m.away_id)]
    rel.sort(key=lambda m: str(m.date), reverse=True)
    out: list[str] = []
    for m in rel[:limit]:
        gf = m.gh if m.home_id == team_id else m.ga
        ga = m.ga if m.home_id == team_id else m.gh
        out.append("W" if gf > ga else "D" if gf == ga else "L")
    return out


def build_analytics(
    model: LeagueModel,
    home_id: str,
    away_id: str,
    home_name: str,
    away_name: str,
    *,
    h2h_limit: int = 5,
    form_limit: int = 5,
) -> MatchAnalytics:
    """Compute the pre-match analytics from an already-built LeagueModel."""

    th = model.teams.get(home_id)
    ta = model.teams.get(away_id)
    teams = list(model.teams.values())

    tot_gf = sum(t.gf_home + t.gf_away for t in teams)
    tot_pj = sum(t.played_home + t.played_away for t in teams)
    home_gf = sum(t.gf_home for t in teams)
    home_pj = sum(t.played_home for t in teams)
    away_gf = sum(t.gf_away for t in teams)
    away_pj = sum(t.played_away for t in teams)

    name_by_id = {home_id: home_name, away_id: away_name}
    pair = {home_id, away_id}
    h2h_raw = [m for m in model.matches if {m.home_id, m.away_id} == pair]
    h2h_raw.sort(key=lambda m: str(m.date), reverse=True)
    h2h = [
        H2HMatch(
            date=str(m.date),
            home=name_by_id.get(m.home_id, m.home_id),
            away=name_by_id.get(m.away_id, m.away_id),
            gh=m.gh, ga=m.ga,
        )
        for m in h2h_raw[:h2h_limit]
    ]

    return MatchAnalytics(
        n_teams=len(teams),
        home_position=th.position if th else None,
        away_position=ta.position if ta else None,
        home_form=_form_for(home_id, model.matches, form_limit),
        away_form=_form_for(away_id, model.matches, form_limit),
        h2h=h2h,
        league_avg=_div(tot_gf, tot_pj),
        league_home_avg=_div(home_gf, home_pj),
        league_away_avg=_div(away_gf, away_pj),
        home_goals=_team_goals(home_name, th),
        away_goals=_team_goals(away_name, ta),
    )


def _fmt(x: Optional[float]) -> str:
    return f"{x:.2f}" if x is not None else "n/d"


def _form_str(form: list[str]) -> str:
    return "-".join(form) if form else "n/d"


def render_analytics(
    a: MatchAnalytics,
    home_name: str,
    away_name: str,
    *,
    escape: Callable[[str], str] = lambda s: s,
) -> list[str]:
    """Render the analytics block as plain lines (no provider-specific markup)."""

    h = escape(home_name)
    aw = escape(away_name)
    lines = ["", "📊 Análisis pre-match:"]

    if a.home_position or a.away_position:
        hp = f"{a.home_position}º" if a.home_position else "?"
        ap = f"{a.away_position}º" if a.away_position else "?"
        extra = f" (de {a.n_teams})" if a.n_teams else ""
        lines.append(f"📋 Posición: {h} {hp} vs {aw} {ap}{extra}")

    lines.append(f"📈 Forma (últ. 5): {h} {_form_str(a.home_form)} · {aw} {_form_str(a.away_form)}")

    if a.league_avg is not None:
        lines.append(
            f"⚽ Liga: {_fmt(a.league_avg)} gol/equipo · local {_fmt(a.league_home_avg)} · visita {_fmt(a.league_away_avg)}"
        )
    hg, ag = a.home_goals, a.away_goals
    lines.append(f"   {h}: marca {_fmt(hg.scored_avg)} / recibe {_fmt(hg.conceded_avg)} (de local marca {_fmt(hg.scored_home_avg)})")
    lines.append(f"   {aw}: marca {_fmt(ag.scored_avg)} / recibe {_fmt(ag.conceded_avg)} (de visita marca {_fmt(ag.scored_away_avg)})")

    if a.h2h:
        lines.append("🤝 H2H reciente:")
        for m in a.h2h:
            lines.append(f"   {m.date}: {escape(m.home)} {m.gh}-{m.ga} {escape(m.away)}")
    else:
        lines.append("🤝 H2H: sin enfrentamientos en los datos.")
    return lines
