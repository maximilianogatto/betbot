"""Unified interface for the special-league stats commands (/fin_*, /swe_*).

A single abstract adapter (:class:`SpecialLeague`) defines the operations every
federation source must provide (leagues, today, standings, fixtures); each
country implements them against its own API (Palloliitto / Svenskfotboll). The
Telegram handlers then call ONE set of renderers, so Finland and Sweden look
identical (the Finland Markdown aesthetic the user likes).

Uniform data models keep the renderers source-agnostic; the adapters do the
provider-specific fetching + senior classification + Argentina-time conversion.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from zoneinfo import ZoneInfo

_ARG = ZoneInfo("America/Argentina/Buenos_Aires")


# --------------------------------------------------------------------------- #
# Uniform data models
# --------------------------------------------------------------------------- #
@dataclass
class LeagueInfo:
    code: str
    name: str
    tier: Optional[int] = None
    gender: Optional[str] = None  # "M" | "F"
    kind: str = "league"          # "league" | "cup"


@dataclass
class MatchRow:
    match_id: str
    time_arg: str          # "HH:MM" in Argentina time (or "N/A")
    home: str
    away: str
    score: Optional[str] = None   # "1-2" when played/live, else None
    is_live: bool = False
    league_code: str = ""
    league_name: str = ""
    league_tier: Optional[int] = None
    date_arg: str = ""     # "YYYY-MM-DD" (used by fixtures)


@dataclass
class StandRow:
    position: int
    team: str
    played: int
    points: int
    goal_diff: int


@dataclass
class StandingsResult:
    title: str
    rows: list[StandRow] = field(default_factory=list)
    regional: bool = False     # True => no single national table (point user elsewhere)
    found: bool = True         # False => unknown code
    note: Optional[str] = None  # custom message shown when there is no table (e.g. cups)


@dataclass
class SpecialPlayer:
    name: str
    shirt_number: str = ""
    position: str = ""  # "GK" | "DF" | "MF" | "FW" | "N/A"
    is_starter: bool = True
    goals: int = 0
    yellow_cards: int = 0
    red_cards: int = 0


@dataclass
class SpecialEvent:
    minute: str
    type: str  # "Goal" | "YellowCard" | "RedCard" | "Sub" | "Other"
    player_name: str
    team_name: str
    detail: str = ""  # e.g. "Assist: X" or "Penalty"


@dataclass
class SpecialMatchDetail:
    match_id: str
    home_team: str
    away_team: str
    league_code: str
    league_name: str
    date_arg: str  # YYYY-MM-DD (Arg time)
    time_arg: str  # HH:MM (Arg time)
    status: str
    score: Optional[str] = None
    venue: str = "N/A"
    attendance: str = "N/A"
    home_lineup: list[SpecialPlayer] = field(default_factory=list)
    away_lineup: list[SpecialPlayer] = field(default_factory=list)
    events: list[SpecialEvent] = field(default_factory=list)


class SpecialLeagueAnalyzer:
    def __init__(self, home_team: str, away_team: str, matches: list[MatchRow], standings: StandingsResult):
        self.home_team = home_team.strip()
        self.away_team = away_team.strip()
        self.matches = matches
        self.standings = standings
        
        # Helper to normalise names for comparison
        def norm(name: str) -> str:
            return " ".join(name.strip().lower().split())
        self.norm_home = norm(self.home_team)
        self.norm_away = norm(self.away_team)
        
        # Separate matches: played vs upcoming
        self.played_matches = []
        for m in matches:
            if m.score and "-" in m.score:
                self.played_matches.append(m)
        
    def _is_home(self, team_name: str) -> bool:
        return " ".join(team_name.strip().lower().split()) == self.norm_home
        
    def _is_away(self, team_name: str) -> bool:
        return " ".join(team_name.strip().lower().split()) == self.norm_away

    def get_form(self) -> dict[str, Any]:
        # Calculate recent W/D/L for both teams
        def team_form(norm_name: str) -> dict[str, Any]:
            rel = [m for m in self.played_matches if norm_name in (
                " ".join(m.home.strip().lower().split()),
                " ".join(m.away.strip().lower().split())
            )]
            # Sort by date descending
            rel.sort(key=lambda m: (m.date_arg or "", m.time_arg or ""), reverse=True)
            sequence = []
            last_matches = []
            recent_points = 0
            for m in rel[:5]:
                try:
                    hs, as_ = map(int, m.score.split("-"))
                except ValueError:
                    continue
                is_home = " ".join(m.home.strip().lower().split()) == norm_name
                # Determine result for this team
                if hs == as_:
                    res = "D"
                    recent_points += 1
                elif (hs > as_ and is_home) or (as_ > hs and not is_home):
                    res = "W"
                    recent_points += 3
                else:
                    res = "L"
                sequence.append(res)
                last_matches.append({
                    "date_display": m.date_arg.split("-")[-1] + "/" + m.date_arg.split("-")[-2] + "/" + m.date_arg.split("-")[0][2:] if len(m.date_arg.split("-")) == 3 else m.date_arg,
                    "home": m.home,
                    "away": m.away,
                    "score": m.score
                })
            
            rating_10 = round(recent_points / (len(sequence) * 3) * 10, 2) if sequence else 0.0
            return {
                "sequence": sequence[::-1],  # oldest to newest
                "rating_10": rating_10,
                "last_matches": last_matches
            }
            
        return {
            "home": team_form(self.norm_home),
            "away": team_form(self.norm_away)
        }

    def get_h2h(self) -> dict[str, Any]:
        rel = [m for m in self.played_matches if {self.norm_home, self.norm_away} == {
            " ".join(m.home.strip().lower().split()),
            " ".join(m.away.strip().lower().split())
        }]
        rel.sort(key=lambda m: (m.date_arg or "", m.time_arg or ""), reverse=True)
        
        home_wins = 0
        away_wins = 0
        draws = 0
        recent = []
        
        for m in rel:
            try:
                hs, as_ = map(int, m.score.split("-"))
            except ValueError:
                continue
            is_home_home = " ".join(m.home.strip().lower().split()) == self.norm_home
            if hs == as_:
                draws += 1
            elif (hs > as_ and is_home_home) or (as_ > hs and not is_home_home):
                home_wins += 1
            else:
                away_wins += 1
                
            recent.append({
                "date_display": m.date_arg.split("-")[-1] + "/" + m.date_arg.split("-")[-2] + "/" + m.date_arg.split("-")[0][2:] if len(m.date_arg.split("-")) == 3 else m.date_arg,
                "home": m.home,
                "away": m.away,
                "score": m.score
            })
            
        total = home_wins + away_wins + draws
        edge_value = 0.0
        edge_label = "Sin ventaja clara"
        if total > 0:
            edge_value = round((home_wins - away_wins) / total, 4)
            if edge_value > 0.05:
                edge_label = self.home_team
            elif edge_value < -0.05:
                edge_label = self.away_team
                
        return {
            "edge_label": edge_label,
            "edge_value": edge_value,
            "recent_matches": recent[:5]
        }

    def get_goals(self) -> dict[str, Any]:
        def team_goals(norm_name: str) -> dict[str, Any]:
            played = [m for m in self.played_matches if norm_name in (
                " ".join(m.home.strip().lower().split()),
                " ".join(m.away.strip().lower().split())
            )]
            home_games = [m for m in self.played_matches if " ".join(m.home.strip().lower().split()) == norm_name]
            away_games = [m for m in self.played_matches if " ".join(m.away.strip().lower().split()) == norm_name]
            
            gf_total = gf_home = gf_away = 0
            ga_total = ga_home = ga_away = 0
            btts_count = 0
            
            for m in played:
                try:
                    hs, as_ = map(int, m.score.split("-"))
                except ValueError:
                    continue
                is_home = " ".join(m.home.strip().lower().split()) == norm_name
                gf = hs if is_home else as_
                ga = as_ if is_home else hs
                gf_total += gf
                ga_total += ga
                if hs > 0 and as_ > 0:
                    btts_count += 1
                    
            for m in home_games:
                try:
                    hs, as_ = map(int, m.score.split("-"))
                except ValueError:
                    continue
                gf_home += hs
                ga_home += as_
                
            for m in away_games:
                try:
                    hs, as_ = map(int, m.score.split("-"))
                except ValueError:
                    continue
                gf_away += as_
                ga_away += hs
                
            n_played = len(played)
            n_home = len(home_games)
            n_away = len(away_games)
            
            return {
                "scored_avg": gf_total / n_played if n_played else 0.0,
                "conceded_avg": ga_total / n_played if n_played else 0.0,
                "scored_split": gf_home / n_home if n_home else (gf_total / n_played if n_played else 0.0),
                "conceded_split": ga_home / n_home if n_home else (ga_total / n_played if n_played else 0.0),
                "scored_away_split": gf_away / n_away if n_away else (gf_total / n_played if n_played else 0.0),
                "conceded_away_split": ga_away / n_away if n_away else (ga_total / n_played if n_played else 0.0),
                "btts_rate": btts_count / n_played if n_played else 0.0,
                "n_home": n_home,
                "n_away": n_away
            }
            
        home_stats = team_goals(self.norm_home)
        away_stats = team_goals(self.norm_away)
        
        # League-wide averages
        tot_home_g = 0
        tot_away_g = 0
        tot_played = len(self.played_matches)
        for m in self.played_matches:
            try:
                hs, as_ = map(int, m.score.split("-"))
                tot_home_g += hs
                tot_away_g += as_
            except ValueError:
                continue
                
        league_home_avg = tot_home_g / tot_played if tot_played else 1.5
        league_away_avg = tot_away_g / tot_played if tot_played else 1.2
        
        home_attack_strength = (home_stats["scored_split"] / league_home_avg) if league_home_avg else 1.0
        home_defense_weakness = (home_stats["conceded_split"] / league_away_avg) if league_away_avg else 1.0
        away_attack_strength = (away_stats["scored_away_split"] / league_away_avg) if league_away_avg else 1.0
        away_defense_weakness = (away_stats["conceded_away_split"] / league_home_avg) if league_home_avg else 1.0
        
        def to10(val: float) -> float:
            return round(max(0.0, min(10.0, val / 2.5 * 10)), 2)
            
        home_strength_10 = round((to10(home_attack_strength) + (10.0 - to10(home_defense_weakness))) / 2.0, 2)
        away_defense_weakness_10 = to10(away_defense_weakness)
        
        min_home_scored = 90.0 / home_stats["scored_split"] if home_stats["scored_split"] else 90.0
        min_away_conceded = 90.0 / away_stats["conceded_away_split"] if away_stats["conceded_away_split"] else 90.0
        projected_home_minute = round((min_home_scored + min_away_conceded) / 2.0, 1)
        
        min_away_scored = 90.0 / away_stats["scored_away_split"] if away_stats["scored_away_split"] else 90.0
        min_home_conceded = 90.0 / home_stats["conceded_split"] if home_stats["conceded_split"] else 90.0
        projected_away_minute = round((min_away_scored + min_home_conceded) / 2.0, 1)
        
        btts_combined = round((home_stats["btts_rate"] + away_stats["btts_rate"]) / 2.0, 4)
        
        return {
            "home_scored": home_stats["scored_avg"],
            "home_scored_home": home_stats["scored_split"],
            "away_scored": away_stats["scored_avg"],
            "away_scored_away": away_stats["scored_away_split"],
            
            "home_conceded": home_stats["conceded_avg"],
            "home_conceded_home": home_stats["conceded_split"],
            "away_conceded": away_stats["conceded_avg"],
            "away_conceded_away": away_stats["conceded_away_split"],
            
            "btts": btts_combined,
            "home_strength_10": home_strength_10,
            "away_defense_weakness_10": away_defense_weakness_10,
            
            "projected_home_minute": projected_home_minute,
            "projected_away_minute": projected_away_minute
        }

    def get_table_context(self) -> dict[str, Any]:
        home_row = None
        away_row = None
        
        def match_team(t_name: str, ref_name: str) -> bool:
            return " ".join(t_name.strip().lower().split()) == " ".join(ref_name.strip().lower().split())
            
        for r in self.standings.rows:
            if match_team(r.team, self.home_team):
                home_row = r
            if match_team(r.team, self.away_team):
                away_row = r
                
        def ordinal(n: int) -> str:
            if 11 <= n % 100 <= 13:
                suffix = "th"
            else:
                suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
            return f"{n}{suffix}"
            
        home_pos = f"{ordinal(home_row.position)} ({home_row.points} pts, {home_row.played}P)" if home_row else "n/d"
        away_pos = f"{ordinal(away_row.position)} ({away_row.points} pts, {away_row.played}P)" if away_row else "n/d"
        
        return {
            "home_display": home_pos,
            "away_display": away_pos
        }

    def get_common_opponents(self) -> list[dict[str, Any]]:
        def opponents_for(norm_name: str) -> dict[str, MatchRow]:
            out = {}
            for m in self.played_matches:
                hn = " ".join(m.home.strip().lower().split())
                an = " ".join(m.away.strip().lower().split())
                if hn == norm_name:
                    out[an] = m
                elif an == norm_name:
                    out[hn] = m
            return out
            
        home_opps = opponents_for(self.norm_home)
        away_opps = opponents_for(self.norm_away)
        common_norms = set(home_opps.keys()) & set(away_opps.keys())
        
        common = []
        for c_norm in list(common_norms)[:4]:
            m_home = home_opps[c_norm]
            m_away = away_opps[c_norm]
            
            opp_name = m_home.away if " ".join(m_home.home.strip().lower().split()) == self.norm_home else m_home.home
            
            def date_display(date_str: str) -> str:
                parts = date_str.split("-")
                return f"{parts[-1]}/{parts[-2]}/{parts[0][2:]}" if len(parts) == 3 else date_str
                
            common.append({
                "common_opponent": opp_name,
                "home_team_evidence": {
                    "date_display": date_display(m_home.date_arg),
                    "scoreline": f"{m_home.home} {m_home.score} {m_home.away}"
                },
                "away_team_evidence": {
                    "date_display": date_display(m_away.date_arg),
                    "scoreline": f"{m_away.home} {m_away.score} {m_away.away}"
                }
            })
        return common


def render_special_match_report(details: SpecialMatchDetail, stats: dict[str, Any]) -> str:
    home = details.home_team
    away = details.away_team
    
    home_seq = " ".join(stats["form"]["home"]["sequence"]) or "—"
    away_seq = " ".join(stats["form"]["away"]["sequence"]) or "—"
    
    def form_emoji(val: float) -> str:
        if val < 4.0:
            return "🔴"
        if val < 6.5:
            return "🟡"
        return "🟢"
        
    title = f"{home} vs {away}"
    if details.score:
        title = f"{home} {details.score} {away}"
    competition_line = [f"🏆 {details.league_name}"] if details.league_name else []
    lines = [
        f"⚽ *{title}*",
        *competition_line,
        f"📍 Estadio: {details.venue} | Asistencia: {details.attendance}",
        f"📅 Fecha: {details.date_arg} {details.time_arg} | Estado: {details.status}",
        _DIV,
        "",
        "📊 *FORMA*",
        f"   {home}:  {form_emoji(stats['form']['home']['rating_10'])} {stats['form']['home']['rating_10']:.2f}/10 - {home_seq}",
        f"   {away}:  {form_emoji(stats['form']['away']['rating_10'])} {stats['form']['away']['rating_10']:.2f}/10 - {away_seq}",
        "",
        "🤝 *H2H*",
        f"   Ventaja: {stats['h2h']['edge_label']} ({stats['h2h']['edge_value']:.4f})",
    ]
    
    for m in stats["h2h"]["recent_matches"]:
        lines.append(f"   • {m['date_display']}  {m['home']} {m['score']} {m['away']}")
    if not stats["h2h"]["recent_matches"]:
        lines.append("   • Sin enfrentamientos recientes.")
        
    lines.extend([
        "",
        "🥅 *GOLES (promedio)*",
        "   Marcados:",
        f"      {home}: {stats['goals']['home_scored']:.2f} ({stats['goals']['home_scored_home']:.2f} local)",
        f"      {away}: {stats['goals']['away_scored']:.2f} ({stats['goals']['away_scored_away']:.2f} visita)",
        "   Recibidos:",
        f"      {home}: {stats['goals']['home_conceded']:.2f} ({stats['goals']['home_conceded_home']:.2f} local)",
        f"      {away}: {stats['goals']['away_conceded']:.2f} ({stats['goals']['away_conceded_away']:.2f} visita)",
        "",
        f"   BTTS: {stats['goals']['btts'] * 100:.0f}%",
        "",
        "💪 *ÍNDICES*",
        f"   Fuerza local ({home}): {stats['goals']['home_strength_10']:.2f}/10",
        f"   Debilidad visitante ({away}): {stats['goals']['away_defense_weakness_10']:.2f}/10",
        "",
        "📋 *TABLA*",
        f"   {home}: {stats['table']['home_display']}  ·  {away}: {stats['table']['away_display']}",
        "",
        "🔄 *ÚLTIMOS PARTIDOS*",
        f"   {home}: {home_seq}",
    ])
    for m in stats["form"]["home"]["last_matches"]:
        lines.append(f"   • {m['date_display']}  {m['home']} {m['score']} {m['away']}")
    lines.append(f"   {away}: {away_seq}")
    for m in stats["form"]["away"]["last_matches"]:
        lines.append(f"   • {m['date_display']}  {m['home']} {m['score']} {m['away']}")
        
    lines.extend([
        "",
        "👤 *GOLEADOR*",
        f"   {home}: n/a",
        f"   {away}: n/a",
        "",
        "🩹 *LESIONES*",
        f"   {home}: 0  ·  {away}: 0",
        "",
        "⏱️ *FRECUENCIA DE GOL (min por gol · menor = marca más seguido)*",
        f"   {home}: ~{stats['goals']['projected_home_minute']:.1f}' (~{90.0 / stats['goals']['projected_home_minute']:.2f} g/partido)" if stats['goals']['projected_home_minute'] > 0 else f"   {home}: n/a",
        f"   {away}: ~{stats['goals']['projected_away_minute']:.1f}' (~{90.0 / stats['goals']['projected_away_minute']:.2f} g/partido)" if stats['goals']['projected_away_minute'] > 0 else f"   {away}: n/a",
    ])
    
    if stats["common_opponents"]:
        lines.extend([
            "",
            "🔎 *RIVALES EN COMÚN*",
            "   (contexto, no predicción)",
        ])
        for opp in stats["common_opponents"]:
            lines.append(f"   🆚 {opp['common_opponent']}")
            lines.append(f"      {opp['home_team_evidence']['date_display']}  {opp['home_team_evidence']['scoreline']}")
            lines.append(f"      {opp['away_team_evidence']['date_display']}  {opp['away_team_evidence']['scoreline']}")
            
    if details.home_lineup or details.away_lineup:
        lines.extend([
            "",
            _DIV,
            "📋 *ALINEACIONES DE HOY*",
        ])
        
        def format_squad(team_name: str, players: list[SpecialPlayer]) -> list[str]:
            starters = [p for p in players if p.is_starter]
            bench = [p for p in players if not p.is_starter]
            squad_lines = [f"\n   *{team_name}* (Titulares):"]
            for p in starters:
                num = p.shirt_number or "?"
                pos = f" _{p.position}_" if p.position else ""
                goals = f" {p.goals}⚽" if p.goals > 0 else ""
                yellow = "🟨" * p.yellow_cards
                red = "🟥" * p.red_cards
                cards = f" {yellow}{red}" if (p.yellow_cards + p.red_cards) > 0 else ""
                squad_lines.append(f"      `{num}` {p.name}{pos}{goals}{cards}")
            if bench:
                bench_names = ", ".join(f"{p.shirt_number or '?'} {p.name}" for p in bench)
                squad_lines.append(f"      🔁 _Banco:_ {bench_names}")
            return squad_lines
            
        if details.home_lineup:
            lines.extend(format_squad(home, details.home_lineup))
        if details.away_lineup:
            lines.extend(format_squad(away, details.away_lineup))
            
    if details.events:
        lines.extend([
            "",
            _DIV,
            "⚡ *EVENTOS DEL PARTIDO*",
        ])
        for ev in details.events:
            icon = "⚽" if ev.type == "Goal" else "🟨" if ev.type == "YellowCard" else "🟥" if ev.type == "RedCard" else "🔁" if ev.type == "Sub" else "✨"
            detail_str = f" ({ev.detail})" if ev.detail else ""
            lines.append(f"   • {ev.minute}' {icon} *{ev.player_name}* ({ev.team_name}){detail_str}")
            
    return "\n".join(lines)


def _to_int(v) -> Optional[int]:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _arg_time(local: Optional[str], tz: ZoneInfo) -> tuple[str, str]:
    """Convert a 'YYYY-MM-DD[ T]HH:MM[:SS]' local datetime to (date_arg, HH:MM)."""
    if not local:
        return "N/A", "N/A"
    raw = str(local).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=tz)
            a = dt.astimezone(_ARG)
            return a.strftime("%Y-%m-%d"), a.strftime("%H:%M")
        except ValueError:
            continue
    return "N/A", "N/A"


# --------------------------------------------------------------------------- #
# Abstract adapter
# --------------------------------------------------------------------------- #
class SpecialLeague(ABC):
    """One federation stats source behind a uniform command interface."""

    flag: str = ""
    country: str = ""        # e.g. "Finlandesas" / "Suecas" (used in the leagues header)
    prefix: str = ""          # "fin" | "swe"

    @abstractmethod
    def leagues(self) -> list[LeagueInfo]:
        ...

    @abstractmethod
    def today(self) -> tuple[list[MatchRow], int]:
        """Return (senior match rows with league_code/name, omitted_count)."""

    @abstractmethod
    def standings(self, code: str) -> StandingsResult:
        ...

    @abstractmethod
    def fixtures(self, code: str) -> tuple[Optional[str], list[MatchRow]]:
        """Return (league_name_or_None, rows). None name => unknown code."""

    @abstractmethod
    def match_report(self, match_id: str) -> str:
        """Build and render a complete SporHub-style match report."""

    def close(self) -> None:  # adapters holding a client override this
        pass



# --------------------------------------------------------------------------- #
# Shared renderers (the Finland Markdown aesthetic)
# --------------------------------------------------------------------------- #
_DIV = "━━━━━━━━━━━━━━━━━━━━"


def _md(text: str) -> str:
    s = str(text)
    for ch in ("\\", "_", "*", "`", "[", "]"):
        s = s.replace(ch, "\\" + ch)
    return s


def _score_or_vs(row: MatchRow) -> str:
    if row.score:
        return f"🔴 *{row.score}*" if row.is_live else f"*{row.score}*"
    return "vs"


def render_leagues(adapter: SpecialLeague, leagues: list[LeagueInfo]) -> str:
    lines = [
        f"🏆 *Jerarquía de Ligas {adapter.country} (Escalafón)* {adapter.flag}\n",
        "Estas ligas no suelen figurar en sitios comunes de stats.",
        "Usá los comandos guiados abajo para explorar:\n",
    ]
    for lg in leagues:
        icon = "🥅" if lg.kind == "cup" else "⚽"
        bits = []
        if lg.tier is not None:
            bits.append(f"Tier {lg.tier}")
        if lg.gender:
            bits.append("Damas" if lg.gender == "F" else "Varones")
        bits.append("Copa" if lg.kind == "cup" else "Liga")
        lines.append(f"{icon} *{_md(lg.name)}* (Código: `{lg.code}`)\n    {' · '.join(bits)}\n")
    lines.append(_DIV)
    lines.append("👉 *¿Qué querés hacer ahora?*")
    lines.append(f"📊 Ver posiciones: `/{adapter.prefix}_standings [CÓDIGO]`")
    lines.append(f"🗓️ Ver fixture: `/{adapter.prefix}_fixtures [CÓDIGO]`")
    lines.append(f"📚 Ver guía: `/{adapter.prefix}_help`")
    lines.append(f"Ejemplo: `/{adapter.prefix}_standings {leagues[0].code if leagues else 'VL'}`")
    return "\n".join(lines)


def render_today_menu(adapter: SpecialLeague, rows: list[MatchRow], omitted: int, date_str: str) -> str:
    by_code: dict[str, list[MatchRow]] = {}
    names: dict[str, str] = {}
    tiers: dict[str, Optional[int]] = {}
    for r in rows:
        by_code.setdefault(r.league_code, []).append(r)
        names.setdefault(r.league_code, r.league_name)
        tiers.setdefault(r.league_code, r.league_tier)
    lines = [
        f"⚽ *Partidos de Hoy ({date_str})*",
        _DIV + "\n",
        "Selecciona una liga para ver los partidos de hoy:\n",
    ]
    for code in sorted(by_code, key=lambda c: (tiers.get(c) or 99, names.get(c, c))):
        tier = tiers.get(code)
        label = f"{names.get(code, code)} (Tier {tier})" if tier else names.get(code, code)
        lines.append(f"• `{_md(label)}` ({len(by_code[code])} part.) ➔ `/{adapter.prefix}_today {code}`")
    lines.append("")
    if omitted > 0:
        lines.append(f"ℹ️ _Omitidos {omitted} partidos de categorías juveniles o ligas menores._\n")
    lines.append(_DIV)
    lines.append("💡 Hacé click en el comando de la derecha para ver la liga correspondiente.")
    return "\n".join(lines)


def render_today_league(adapter: SpecialLeague, code: str, rows: list[MatchRow], date_str: str) -> str:
    lines = [f"⚽ *Partidos de {code} ({date_str})*", _DIV + "\n"]
    for r in rows:
        lines.append(f"🕒 `{r.time_arg}` | {_md(r.home)} {_score_or_vs(r)} {_md(r.away)}\n   ID del partido: `{r.match_id}`\n")
    lines.append(_DIV)
    lines.append("💡 *Detector de Suplentes / B-Team:*")
    lines.append(f"👉 `/{adapter.prefix}_match [ID_PARTIDO]`")
    return "\n".join(lines)


def render_today(adapter: SpecialLeague, rows: list[MatchRow], omitted: int, date_str: str, selected: Optional[str]) -> str:
    if selected:
        sel = selected.upper()
        chosen = [r for r in rows if r.league_code == sel]
        if not chosen:
            return f"⚠️ No hay partidos hoy para la liga `{sel}`.\nCorré `/{adapter.prefix}_today` para ver qué ligas tienen partidos hoy."
        return render_today_league(adapter, sel, chosen, date_str)
    if not rows:
        extra = f"\n_(Hay {omitted} partidos en ligas juveniles o regionales menores hoy)_" if omitted else ""
        return f"⚽ *Partidos de Hoy ({date_str})*\n{_DIV}\n\nNo hay partidos de ligas adultas principales para hoy.{extra}\n{_DIV}"
    # Few matches -> list directly; otherwise a league menu (Finland behaviour).
    if len(rows) <= 5:
        lines = [f"⚽ *Partidos de Hoy ({date_str})*", _DIV + "\n"]
        for r in rows:
            league = f" · _{_md(r.league_name)}_" if r.league_name else ""
            lines.append(f"🕒 `{r.time_arg}` | {_md(r.home)} {_score_or_vs(r)} {_md(r.away)}{league}\n   ID del partido: `{r.match_id}`\n")
        if omitted > 0:
            lines.append(f"ℹ️ _Omitidos {omitted} partidos de categorías juveniles o ligas menores._\n")
        lines.append(_DIV)
        lines.append("💡 *Detector de Suplentes / B-Team:*")
        lines.append(f"👉 `/{adapter.prefix}_match [ID_PARTIDO]`")
        return "\n".join(lines)
    return render_today_menu(adapter, rows, omitted, date_str)


def render_standings(adapter: SpecialLeague, code: str, result: StandingsResult) -> str:
    if not result.found:
        return f"⚠️ No reconozco la liga `{code}`. Mirá los códigos con `/{adapter.prefix}_leagues`."
    if result.regional:
        return (
            f"ℹ️ *{code}* es una liga *regional* (varios grupos por región), así que no tiene una tabla única.\n"
            f"• Partidos de hoy: `/{adapter.prefix}_today {code}`\n"
            f"• Fixture completo: `/{adapter.prefix}_fixtures {code}`"
        )
    if not result.rows:
        if result.note:
            return result.note
        return "⚠️ No hay posiciones disponibles para esta liga en el sistema."
    lines = [f"📊 *Posiciones: {result.title}*", _DIV, " #  Equipo                PJ  Pts  Dif"]
    for r in result.rows:
        pos = str(r.position).rjust(2)
        name = r.team[:20].ljust(20)
        pj = str(r.played).rjust(2)
        pts = str(r.points).rjust(3)
        dif = str(r.goal_diff).rjust(4)
        lines.append(f"`{pos} {name} {pj} {pts} {dif}`")
    lines.append(_DIV)
    lines.append("👉 *Siguientes pasos:*")
    lines.append(f"🗓️ Ver fixture: `/{adapter.prefix}_fixtures {code}`  ⚽ Hoy: `/{adapter.prefix}_today`")
    return "\n".join(lines)


def render_fixtures(adapter: SpecialLeague, code: str, name: Optional[str], rows: list[MatchRow], *, header: str = "Fixture") -> str:
    if name is None:
        return f"⚠️ No reconozco la liga `{code}`. Mirá los códigos con `/{adapter.prefix}_leagues`."
    if not rows:
        return "⚠️ No se encontraron partidos cargados para esta liga."
    lines = [f"🗓️ *{header} de {code}*", _DIV + "\n"]
    for r in rows:
        when = f"{r.date_arg} {r.time_arg}".strip()
        lines.append(f"• `{when}`: {_md(r.home)} {_score_or_vs(r)} {_md(r.away)}\n   ID del partido: `{r.match_id}`")
    lines.append("\n" + _DIV)
    lines.append("💡 *¿Querés analizar las alineaciones?*")
    lines.append(f"👉 `/{adapter.prefix}_match [ID_PARTIDO]`")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Finland adapter (Palloliitto / Torneopal)
# --------------------------------------------------------------------------- #
_HELSINKI = ZoneInfo("Europe/Helsinki")
_STOCKHOLM = ZoneInfo("Europe/Stockholm")
_NOISE = ("futsal", "beach", "ranta", "hiekka")
_FIN_SEASON = "2026"


class FinlandLeagues(SpecialLeague):
    flag = "🇫🇮"
    country = "Finlandesas"
    prefix = "fin"

    def __init__(self, api):
        self.api = api

    def close(self) -> None:
        try:
            self.api.close()
        except Exception:
            pass

    def _catalog(self) -> dict[str, LeagueInfo]:
        out: dict[str, LeagueInfo] = {}
        try:
            for lg in self.api.get_league_ranking_list() or []:
                code = str(lg.get("category_id") or "")
                if not code:
                    continue
                out[code] = LeagueInfo(
                    code=code, name=lg.get("name") or code, tier=_to_int(lg.get("tier")),
                    gender="F" if lg.get("gender") == "Women" else "M",
                    kind="cup" if str(lg.get("sport") or "").lower() == "cup" or "cup" in str(lg.get("name") or "").lower() else "league",
                )
        except Exception:
            pass
        return out

    def leagues(self) -> list[LeagueInfo]:
        return list(self._catalog().values())

    def today(self) -> tuple[list[MatchRow], int]:
        from datetime import date
        catalog = self._catalog()
        try:
            matches = self.api.get_matches_by_date(date.today().isoformat()) or []
        except Exception:
            matches = []
        rows: list[MatchRow] = []
        omitted = 0
        for m in matches:
            blob = " ".join(str(m.get(k) or "").lower() for k in ("category_name", "competition_name", "sport_name"))
            if any(t in blob for t in _NOISE):
                continue
            code = str(m.get("category_id") or "")
            if code not in catalog:
                omitted += 1
                continue
            _d, t_arg = _arg_time(f"{m.get('date')} {m.get('time')}", _HELSINKI)
            live = m.get("live_period") is not None and str(m.get("live_period")) != "-1"
            played = m.get("status") in ("Finished", "Played")
            score = f"{m.get('fs_A')}-{m.get('fs_B')}" if (played or live) and m.get("fs_A") is not None else None
            rows.append(MatchRow(
                match_id=str(m.get("match_id")), time_arg=t_arg,
                home=m.get("home_team_name") or m.get("club_A_name") or "Local",
                away=m.get("away_team_name") or m.get("club_B_name") or "Visitante",
                score=score, is_live=live, league_code=code,
                league_name=catalog[code].name, league_tier=catalog[code].tier,
            ))
        rows.sort(key=lambda r: r.time_arg)
        return rows, omitted

    def _competitions_for(self, code: str) -> list[str]:
        comps: list[str] = []
        try:
            for c in self.api.get_categories(_FIN_SEASON) or []:
                if str(c.get("category_id")) == code:
                    cid = str(c.get("competition_id") or "")
                    if cid and cid not in comps:
                        comps.append(cid)
        except Exception:
            pass
        return comps

    def standings(self, code: str) -> StandingsResult:
        code = code.upper()
        comps = self._competitions_for(code)
        if not comps:
            return StandingsResult(title=code, found=False)
        if len(comps) > 1:
            return StandingsResult(title=code, regional=True)
        try:
            raw = self.api.get_standings(comps[0], code, "1") or []
        except Exception:
            raw = []
        rows = [
            StandRow(
                position=_to_int(t.get("current_standing")) or i,
                team=str(t.get("team_name") or "?"),
                played=_to_int(t.get("matches_played")) or 0,
                points=_to_int(t.get("points")) or 0,
                goal_diff=_to_int(t.get("goals_diff")) or 0,
            )
            for i, t in enumerate(raw, start=1)
        ]
        return StandingsResult(title=f"{code} (2026)", rows=rows)

    def fixtures(self, code: str) -> tuple[Optional[str], list[MatchRow]]:
        from datetime import date
        code = code.upper()
        comps = self._competitions_for(code)
        if not comps:
            return None, []
        raw: list = []
        for comp in comps:
            try:
                raw += self.api.get_matches_by_league(comp, code) or []
            except Exception:
                pass
        today = date.today().isoformat()
        finished = sorted([m for m in raw if str(m.get("date") or "") < today], key=lambda x: x.get("date", ""), reverse=True)
        upcoming = sorted([m for m in raw if str(m.get("date") or "") >= today], key=lambda x: x.get("date", ""))
        display = list(reversed(finished[:5])) + upcoming[:10]
        rows = []
        for m in display:
            d_arg, t_arg = _arg_time(f"{m.get('date')} {m.get('time')}", _HELSINKI)
            played = m.get("status") in ("Finished", "Played")
            score = f"{m.get('fs_A')}-{m.get('fs_B')}" if played and m.get("fs_A") is not None else None
            rows.append(MatchRow(
                match_id=str(m.get("match_id")), time_arg=t_arg, date_arg=d_arg,
                home=m.get("team_A_name") or m.get("club_A_name") or "Local",
                away=m.get("team_B_name") or m.get("club_B_name") or "Visitante",
                score=score, league_code=code,
            ))
        return code, rows

    def match_report(self, match_id: str) -> str:
        try:
            m = self.api.get_match_details(match_id)
        except Exception as e:
            return f"❌ Error al consultar partido en la federación finlandesa: {e}"
            
        if not m:
            return f"❌ No encontré un partido con ID {match_id} en la federación finlandesa."

        home_team = m.get("club_A_name") or m.get("team_A_name") or "Local"
        away_team = m.get("club_B_name") or m.get("team_B_name") or "Visitante"
        orig_date = m.get("date")
        orig_time = m.get("time")
        
        date_val, time_val = _arg_time(f"{orig_date} {orig_time}", _HELSINKI)
        
        venue = m.get("venue_name") or "N/A"
        attendance = str(m.get("attendance") or "N/A")
        status = m.get("status") or "Scheduled"
        score = f"{m.get('fs_A')}-{m.get('fs_B')}" if m.get("fs_A") is not None else None

        home_players = []
        away_players = []
        home_id = m.get("team_A_id")
        away_id = m.get("team_B_id")
        
        lineups = m.get("lineups", []) or []
        for p in lineups:
            is_starter = str(p.get("start")) == "1"
            goals_count = 0
            for g in m.get("goals", []) or []:
                if str(g.get("player_id")) == str(p.get("player_id")):
                    goals_count += 1
            yellow_count = 0
            red_count = 0
            for b in m.get("bookings", []) or []:
                if str(b.get("player_id")) == str(p.get("player_id")):
                    card = str(b.get("card_type") or "").lower()
                    if "yellow" in card:
                        yellow_count += 1
                    else:
                        red_count += 1
                        
            player_obj = SpecialPlayer(
                name=p.get("player_name") or "",
                shirt_number=str(p.get("shirt_number") or ""),
                position=p.get("position") or "",
                is_starter=is_starter,
                goals=goals_count,
                yellow_cards=yellow_count,
                red_cards=red_count
            )
            if str(p.get("team_id")) == str(home_id):
                home_players.append(player_obj)
            else:
                away_players.append(player_obj)

        events = []
        for g in m.get("goals", []) or []:
            min_str = str(g.get("time_min") or g.get("minute") or "?")
            team_name = home_team if str(g.get("team_id")) == str(home_id) else away_team
            events.append(SpecialEvent(
                minute=min_str,
                type="Goal",
                player_name=g.get("player_name") or "Jugador",
                team_name=team_name
            ))
        for b in m.get("bookings", []) or []:
            min_str = str(b.get("time_min") or b.get("minute") or "?")
            card = str(b.get("card_type") or "").lower()
            card_type = "YellowCard" if "yellow" in card else "RedCard"
            team_name = home_team if str(b.get("team_id")) == str(home_id) else away_team
            events.append(SpecialEvent(
                minute=min_str,
                type=card_type,
                player_name=b.get("player_name") or "Jugador",
                team_name=team_name
            ))
            
        def ev_key(ev: SpecialEvent) -> int:
            try:
                clean = "".join(c for c in ev.minute if c.isdigit())
                return int(clean)
            except ValueError:
                return 999
        events.sort(key=ev_key)

        code = str(m.get("category_id") or "")
        name = m.get("category_name") or "Liiga"

        details = SpecialMatchDetail(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league_code=code,
            league_name=name,
            date_arg=date_val,
            time_arg=time_val,
            status=status,
            score=score,
            venue=venue,
            attendance=attendance,
            home_lineup=home_players,
            away_lineup=away_players,
            events=events
        )

        standings = self.standings(code)
        
        comp_id = str(m.get("competition_id") or "")
        try:
            raw_matches = self.api.get_matches_by_league(comp_id, code) or []
        except Exception:
            raw_matches = []
            
        mapped_matches = []
        for rm in raw_matches:
            played_match = rm.get("status") in ("Finished", "Played")
            m_score = f"{rm.get('fs_A')}-{rm.get('fs_B')}" if played_match and rm.get("fs_A") is not None else None
            d_m, t_m = _arg_time(f"{rm.get('date')} {rm.get('time')}", _HELSINKI)
            mapped_matches.append(MatchRow(
                match_id=str(rm.get("match_id")),
                time_arg=t_m,
                date_arg=d_m,
                home=rm.get("team_A_name") or rm.get("club_A_name") or "Local",
                away=rm.get("team_B_name") or rm.get("club_B_name") or "Visitante",
                score=m_score,
                league_code=code
            ))
            
        analyzer = SpecialLeagueAnalyzer(home_team, away_team, mapped_matches, standings)
        stats = {
            "form": analyzer.get_form(),
            "h2h": analyzer.get_h2h(),
            "goals": analyzer.get_goals(),
            "table": analyzer.get_table_context(),
            "common_opponents": analyzer.get_common_opponents()
        }

        report = render_special_match_report(details, stats)
        
        if lineups:
            home_raw_starters = [p for p in lineups if str(p.get("team_id")) == str(home_id) and str(p.get("start")) == "1"]
            away_raw_starters = [p for p in lineups if str(p.get("team_id")) == str(away_id) and str(p.get("start")) == "1"]
            
            home_primary = m.get("team_A_primary_category_id") or m.get("category_id")
            away_primary = m.get("team_B_primary_category_id") or m.get("category_id")
            
            from monitors.special_peak import compute_rotation_ratio
            home_rot = compute_rotation_ratio(
                self.api, team_id=home_id, primary_category=home_primary,
                competition_id=comp_id, starters=home_raw_starters, target_match_id=match_id
            )
            away_rot = compute_rotation_ratio(
                self.api, team_id=away_id, primary_category=away_primary,
                competition_id=comp_id, starters=away_raw_starters, target_match_id=match_id
            )
            
            def format_rot(name: str, rot) -> str:
                if rot.ratio is None:
                    return "⚠️ Sin datos para comparar."
                badge = " 🚨" if rot.ratio < 0.45 else ""
                desc = f"*{rot.ratio:.0%}*{badge} habituales"
                if rot.new_starters:
                    desc += f" (Nuevos: {', '.join(rot.new_starters[:4])})"
                return desc
                
            report += "\n\n🔍 *Detector de Suplentes / B-Team:*"
            report += f"\n   🏠 *{home_team}:* {format_rot(home_team, home_rot)}"
            report += f"\n   ✈️ *{away_team}:* {format_rot(away_team, away_rot)}"
            report += "\n💡 _Regularidad <45% 🚨 = B-Team/rotación masiva → posible valor vs cuotas pre-partido._"
            
        return report



# --------------------------------------------------------------------------- #
# Sweden adapter (Svenskfotboll). league_table: {code: (comp_id, name, tier_label)}
# --------------------------------------------------------------------------- #
_SWE_NOISE = (
    "p21", "p19", "p18", "p17", "p16", "p15", "p14", "p13",
    "f21", "f19", "f18", "f17", "f16", "f15",
    "u17", "u19", "u21", "u23", "ungdom", "pojkar", "flickor", "junior",
    "akademi", "landskamp", "vm-kval", "em-kval", "nations", "träningsmatch", "futsal",
)


class SwedenLeagues(SpecialLeague):
    flag = "🇸🇪"
    country = "Suecas"
    prefix = "swe"

    # Svenska Cupen is a cup, not a league: it has no fixed competition_id (it is
    # split into per-season stage ids: omg. 1-N, Grupp 1-8, Slutspel) so we resolve
    # the current season's stage ids dynamically from the competition tree.
    # code -> (genderId in the tree, display name, gender letter, category keyword)
    _CUP_DEFS = {
        "SC": (2, "Svenska Cupen", "M", "herr"),
        "SCD": (3, "Svenska Cupen", "F", "dam"),
    }

    def __init__(self, client, league_table: dict[str, tuple[str, str, str]]):
        self.client = client
        self.table = league_table
        self._cup_cache: Optional[dict[str, tuple[str, list[str]]]] = None
        # keyword -> code, longest keyword first (so 'damallsvenskan' beats 'allsvenskan')
        kw = {}
        for code, (_cid, name, _tier) in league_table.items():
            kw[name.lower().replace("obos ", "").strip()] = code
        self._keywords = sorted(kw.items(), key=lambda kv: len(kv[0]), reverse=True)

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    def _tier_num(self, tier_label: str) -> Optional[int]:
        for tok in str(tier_label).split():
            n = _to_int(tok)
            if n:
                return n
        return None

    def _resolve_cups(self) -> dict[str, tuple[str, list[str]]]:
        """Resolve current-season stage ids per cup code from the competition tree.

        Returns {code: (display_name, [stage_ids])}. Cached per instance.
        """
        if self._cup_cache is not None:
            return self._cup_cache
        import re
        out: dict[str, tuple[str, list[str]]] = {
            code: (defn[1], []) for code, defn in self._CUP_DEFS.items()
        }
        try:
            tree = self.client.get_competition_tree() or {}
        except Exception:
            tree = {}
        # code -> {season_year: set(stage_ids)}
        buckets: dict[str, dict[str, set[str]]] = {c: {} for c in self._CUP_DEFS}
        for cat in tree.get("competitions", []) or []:
            cat_name = str(cat.get("category") or "").lower()
            for code, (_gid, _name, _g, kw) in self._CUP_DEFS.items():
                if kw not in cat_name:
                    continue
                for c in cat.get("comps", []) or []:
                    nm = str(c.get("name") or "")
                    if not nm.lower().startswith("svenska cupen"):
                        continue
                    m = re.search(r"(\d{4})\s*/\s*\d{2,4}", nm)
                    season = m.group(1) if m else ""
                    buckets[code].setdefault(season, set()).add(str(c.get("id")))
        for code, seasons in buckets.items():
            if not seasons:
                continue
            latest = max(seasons)  # newest season year wins
            out[code] = (self._CUP_DEFS[code][1], sorted(seasons[latest]))
        self._cup_cache = out
        return out

    def _cup_index(self) -> dict[str, tuple[str, str]]:
        """competition_id -> (cup code, display name) for the current season."""
        idx: dict[str, tuple[str, str]] = {}
        for code, (name, ids) in self._resolve_cups().items():
            for cid in ids:
                idx[str(cid)] = (code, name)
        return idx

    def leagues(self) -> list[LeagueInfo]:
        out = [
            LeagueInfo(code=code, name=name, tier=self._tier_num(tier),
                       gender="F" if "dam" in tier.lower() else "M")
            for code, (_cid, name, tier) in self.table.items()
        ]
        for code, (_gid, name, gender, _kw) in self._CUP_DEFS.items():
            out.append(LeagueInfo(code=code, name=name, gender=gender, kind="cup"))
        return out

    def _code_for(self, competition_name: str) -> Optional[str]:
        low = str(competition_name or "").lower()
        if any(h in low for h in _SWE_NOISE):
            return None
        for keyword, code in self._keywords:
            if keyword and keyword in low:
                return code
        return None

    def _clean_comp_name(self, name: str) -> str:
        import re
        out = name
        for sep in (" herr", " Herr", " dam", " Dam", ", herr", ", dam"):
            idx = out.find(sep)
            if idx > 0:
                out = out[:idx]
        # Quita el descriptor de jornada/ronda: "omg. 1-2", "omgång 3", etc.
        out = re.sub(r"\bomg(?:ång)?\.?\s*[\d\-–]+.*$", "", out, flags=re.IGNORECASE)
        # Quita la temporada: "2026", "2026/27", "2026/2027".
        out = re.sub(r"\b\d{4}(?:\s*/\s*\d{2,4})?\b", "", out)
        # Colapsa espacios y separadores sobrantes.
        out = re.sub(r"\s{2,}", " ", out)
        return out.strip(" ,·-/") or name

    def _slug(self, name: str) -> str:
        # Código estable: solo letras del nombre ya limpio, sin la temporada
        # (la copa no debe quedar como "SWEsvenskacupen202627").
        alnum = "".join(c for c in name.lower() if c.isalpha())
        return "SWE" + alnum[:18]

    def today(self) -> tuple[list[MatchRow], int]:
        try:
            matches = self.client.get_matches_today() or []
        except Exception:
            matches = []
        cup_idx = self._cup_index()
        rows: list[MatchRow] = []
        omitted = 0
        for m in matches:
            comp = m.get("competition_name") or ""
            comp_id = str(m.get("competition_id") or "")
            # Svenska Cupen: map to the cup code/gender via its season stage id.
            if comp_id in cup_idx:
                code, name = cup_idx[comp_id]
                tier = None
            elif any(h in comp.lower() for h in _SWE_NOISE):  # futsal / youth / selecciones
                omitted += 1
                continue
            else:
                # Mapped leagues keep their short code; the rest are shown with their
                # own (cleaned) league name so every league is differentiated.
                code = self._code_for(comp)
                if code:
                    name, tier = self.table[code][1], self._tier_num(self.table[code][2])
                else:
                    name = self._clean_comp_name(comp)
                    code = self._slug(name)
                    tier = None
            _d, t_arg = _arg_time(m.get("start_time_local"), _STOCKHOLM)
            hs, as_ = m.get("home_score"), m.get("away_score")
            score = f"{hs}-{as_}" if hs is not None and as_ is not None else None
            rows.append(MatchRow(
                match_id=str(m.get("match_id") or ""), time_arg=t_arg,
                home=m.get("home") or "Local", away=m.get("away") or "Visitante",
                score=score, league_code=code, league_name=name, league_tier=tier,
            ))
        rows.sort(key=lambda r: r.time_arg)
        return rows, omitted

    def _standrows(self, teams) -> list[StandRow]:
        return [
            StandRow(
                position=_to_int(t.get("position")) or i,
                team=str(t.get("team") or "?"),
                played=_to_int(t.get("played")) or 0,
                points=_to_int(t.get("points")) or 0,
                goal_diff=_to_int(t.get("goal_difference")) or 0,
            )
            for i, t in enumerate(teams or [], start=1)
        ]

    def _get_teams(self, comp_id: str) -> list:
        try:
            data = self.client.get_standings(comp_id)
            return (data.get("teams") if isinstance(data, dict) else data) or []
        except Exception:
            return []

    def standings(self, code: str) -> StandingsResult:
        code = code.upper()
        if code in self._CUP_DEFS:
            name, ids = self._resolve_cups().get(code, (self._CUP_DEFS[code][1], []))
            # Group stages have tables; show the only one if there is a single group,
            # otherwise it's the knockout/early-round phase -> point to the fixture.
            groups = [t for sid in ids if (t := self._get_teams(sid))]
            if len(groups) == 1:
                return StandingsResult(title=name, rows=self._standrows(groups[0]))
            note = (
                f"🥅 *{name}* es un torneo de copa (eliminatoria).\n"
                + ("Está en fase de grupos múltiples; " if groups else "Está en fase de eliminatorias, ")
                + "no tiene una tabla única.\n"
                f"• Próximos partidos: `/{self.prefix}_fixtures {code}`\n"
                f"• Partidos de hoy: `/{self.prefix}_today`"
            )
            return StandingsResult(title=name, rows=[], note=note)
        entry = self.table.get(code)
        if not entry:
            return StandingsResult(title=code, found=False)
        comp_id, name, _tier = entry
        return StandingsResult(title=f"{name} (2026)", rows=self._standrows(self._get_teams(comp_id)))

    def _cup_match_rows(self, fetch, code: str, name: str) -> tuple[str, list[MatchRow]]:
        _name, ids = self._resolve_cups().get(code, (name, []))
        rows: list[MatchRow] = []
        seen: set[str] = set()
        for sid in ids:
            for r in self._match_rows(fetch, sid, code):
                if r.match_id and r.match_id in seen:
                    continue
                seen.add(r.match_id)
                rows.append(r)
        rows.sort(key=lambda r: (r.date_arg or "", r.time_arg or ""))
        return _name, rows[:30]

    def fixtures(self, code: str) -> tuple[Optional[str], list[MatchRow]]:
        code = code.upper()
        if code in self._CUP_DEFS:
            return self._cup_match_rows(self.client.get_upcoming_matches, code, self._CUP_DEFS[code][1])
        entry = self.table.get(code)
        if not entry:
            return None, []
        comp_id, name, _tier = entry
        return name, self._match_rows(self.client.get_upcoming_matches, comp_id, code)

    def results(self, code: str) -> tuple[Optional[str], list[MatchRow]]:
        code = code.upper()
        if code in self._CUP_DEFS:
            return self._cup_match_rows(self.client.get_latest_results, code, self._CUP_DEFS[code][1])
        entry = self.table.get(code)
        if not entry:
            return None, []
        comp_id, name, _tier = entry
        return name, self._match_rows(self.client.get_latest_results, comp_id, code)

    def _match_rows(self, fetch, comp_id: str, code: str) -> list[MatchRow]:
        try:
            data = fetch(comp_id, limit=25)
            matches = data.get("matches") if isinstance(data, dict) else data
        except Exception:
            matches = []
        rows = []
        for m in matches or []:
            d_arg, t_arg = _arg_time(m.get("start_time_local"), _STOCKHOLM)
            hs, as_ = m.get("home_score"), m.get("away_score")
            score = f"{hs}-{as_}" if hs is not None and as_ is not None else None
            rows.append(MatchRow(
                match_id=str(m.get("match_id") or ""), time_arg=t_arg, date_arg=d_arg,
                home=m.get("home") or "Local", away=m.get("away") or "Visitante",
                score=score, league_code=code,
            ))
        return rows

    def _parse_swe_score(self, value: Any) -> tuple[Optional[int], Optional[int]]:
        try:
            parts = str(value).replace("–", "-").split("-")
            return int(parts[0].strip()), int(parts[1].strip())
        except (TypeError, ValueError, IndexError):
            return None, None

    def _to_match_row(self, m: dict[str, Any], comp_id: str, comp_name: str, comp_tier: Optional[int]) -> MatchRow:
        d_arg, t_arg = _arg_time(m.get("start_time_local"), _STOCKHOLM)
        hs, as_ = m.get("home_score"), m.get("away_score")
        if hs is None and as_ is None and "score" in m and isinstance(m["score"], str):
            gh, ga = self._parse_swe_score(m["score"])
            if gh is not None and ga is not None:
                hs, as_ = gh, ga
        score = f"{hs}-{as_}" if hs is not None and as_ is not None else None
        return MatchRow(
            match_id=str(m.get("match_id") or ""),
            time_arg=t_arg,
            date_arg=d_arg,
            home=m.get("home") or "Local",
            away=m.get("away") or "Visitante",
            score=score,
            league_code=comp_id,
            league_name=comp_name,
            league_tier=comp_tier
        )

    def _calculate_sweden_rotation(self, team_name: str, comp_id: str, starters: list[SpecialPlayer], target_match_id: str) -> RotationResult:
        import xml.etree.ElementTree as ET
        from monitors.special_peak import RotationResult
        if not starters:
            return RotationResult(None)
        try:
            latest_data = self.client.get_latest_results(comp_id, limit=100)
            matches = latest_data.get("matches") if isinstance(latest_data, dict) else latest_data
        except Exception:
            return RotationResult(None)
            
        recent = []
        def norm(n: str) -> str:
            return " ".join(n.strip().lower().split())
        norm_team = norm(team_name)
        
        for m in matches or []:
            mid = str(m.get("match_id") or "")
            if mid == str(target_match_id):
                continue
            h_norm = norm(m.get("home") or "")
            a_norm = norm(m.get("away") or "")
            if h_norm == norm_team or a_norm == norm_team:
                recent.append(m)
                
        recent.sort(key=lambda x: x.get("start_time_local", ""), reverse=True)
        recent = recent[:3]
        if not recent:
            return RotationResult(None)
            
        starter_counts: dict[str, int] = {}
        for rm in recent:
            rm_id = rm.get("match_id")
            if not rm_id:
                continue
            try:
                xml_text = self.client.get_live_lineup_xml(rm_id)
                past_root = ET.fromstring(xml_text)
                for t_node in past_root.findall(".//team"):
                    t_name = t_node.attrib.get("name") or ""
                    if norm(t_name) == norm_team:
                        for p in t_node.findall(".//player"):
                            pos = p.attrib.get("position")
                            if pos and pos != "Sub":
                                p_name = f"{p.attrib.get('given-name', '')} {p.attrib.get('surname', '')}".strip()
                                starter_counts[p_name] = starter_counts.get(p_name, 0) + 1
            except Exception:
                continue
                
        min_starts = max(1, len(recent) // 2 + (1 if len(recent) % 2 != 0 else 0))
        regular_names = {name for name, count in starter_counts.items() if count >= min_starts}
        
        current_names = {p.name for p in starters}
        matching = current_names & regular_names
        
        denom = 11 if len(matching) <= 11 else len(starters)
        ratio = len(matching) / denom if denom else None
        
        new_starters = [
            f"{p.shirt_number} {p.name}".strip()
            for p in starters
            if p.name not in regular_names
        ]
        return RotationResult(ratio, new_starters)

    def match_report(self, match_id: str) -> str:
        import xml.etree.ElementTree as ET
        try:
            path = self.client.endpoints.live_game_info_pattern.format(match_id=match_id)
            url = f"{self.client.live_xml_base_url}/{path}"
            resp = self.client.client.get(url, headers={"Accept": "application/xml,text/xml,*/*"})
            resp.raise_for_status()
            xml_text = resp.text
        except Exception as e:
            return f"❌ Error al consultar partido en la federación sueca: {e}"

        try:
            root = ET.fromstring(xml_text)
            game_node = root.find(".//game")
        except Exception as e:
            return f"❌ Error al procesar XML del partido: {e}"

        if game_node is None:
            return f"❌ No encontré un partido con ID {match_id} en la federación sueca."

        tournament_node = game_node.find("tournament")
        league_name = tournament_node.attrib.get("name") if tournament_node is not None else "Allsvenskan"
        comp_id = game_node.attrib.get("competition-id") or ""
        
        status_node = game_node.find("status")
        status = status_node.attrib.get("desc") if status_node is not None else "Scheduled"
        
        score_node = game_node.find("score")
        score = None
        if score_node is not None:
            hs = score_node.attrib.get("home-team")
            aw_s = score_node.attrib.get("away-team")
            if hs is not None and aw_s is not None:
                score = f"{hs}-{aw_s}"
                
        stadium_node = game_node.find("stadium")
        venue = stadium_node.attrib.get("name") if stadium_node is not None else "N/A"
        attendance = stadium_node.attrib.get("spectators") if stadium_node is not None else "N/A"

        teams_node = game_node.find("teams")
        home_node = None
        away_node = None
        if teams_node is not None:
            for t in teams_node.findall("team"):
                if t.attrib.get("home-team") == "true":
                    home_node = t
                else:
                    away_node = t
        
        home_team = (home_node.attrib.get("long-name") or home_node.attrib.get("name") or "Local") if home_node is not None else "Local"
        away_team = (away_node.attrib.get("long-name") or away_node.attrib.get("name") or "Visitante") if away_node is not None else "Visitante"
        
        home_id = home_node.attrib.get("id") if home_node is not None else ""
        away_id = away_node.attrib.get("id") if away_node is not None else ""

        orig_date = game_node.attrib.get("date")
        orig_time = game_node.attrib.get("start")
        date_val, time_val = _arg_time(f"{orig_date} {orig_time}" if orig_date and orig_time else None, _STOCKHOLM)

        events = []
        events_node = game_node.find("events")
        if events_node is not None:
            for ev in events_node.findall("event"):
                ev_type = ev.attrib.get("type")
                minute = ev.attrib.get("game-minute-for-web") or ev.attrib.get("game-time-for-web") or "?"
                is_home = ev.attrib.get("home-team") == "true"
                team_name = home_team if is_home else away_team
                
                scorer_name = ""
                card_player = ""
                card_type = ""
                sub_in = ""
                sub_out = ""
                
                for p in ev.findall(".//participant"):
                    p_type = p.attrib.get("type")
                    p_name = f"{p.attrib.get('given-name', '')} {p.attrib.get('surname', '')}".strip()
                    p_desc = p.attrib.get("type-desc") or ""
                    
                    if ev_type == "G" and p_type == "S":
                        scorer_name = p_name
                    elif ev_type == "P":
                        card_player = p_name
                        card_type = "YellowCard" if "yellow" in p_desc.lower() else "RedCard"
                    elif ev_type == "S":
                        if p_type == "I":
                            sub_in = p_name
                        elif p_type == "O":
                            sub_out = p_name
                            
                if ev_type == "G" and scorer_name:
                    events.append(SpecialEvent(
                        minute=minute,
                        type="Goal",
                        player_name=scorer_name,
                        team_name=team_name
                    ))
                elif ev_type == "P" and card_player:
                    events.append(SpecialEvent(
                        minute=minute,
                        type=card_type,
                        player_name=card_player,
                        team_name=team_name
                    ))
                elif ev_type == "S" and sub_in:
                    detail = f"Sale: {sub_out}" if sub_out else ""
                    events.append(SpecialEvent(
                        minute=minute,
                        type="Sub",
                        player_name=sub_in,
                        team_name=team_name,
                        detail=detail
                    ))

        def ev_key(ev: SpecialEvent) -> int:
            try:
                clean = "".join(c for c in ev.minute if c.isdigit())
                return int(clean)
            except ValueError:
                return 999
        events.sort(key=ev_key)

        home_players = []
        away_players = []
        try:
            lineup_xml = self.client.get_live_lineup_xml(match_id)
            lineup_root = ET.fromstring(lineup_xml)
            for t_node in lineup_root.findall(".//team"):
                t_id = t_node.attrib.get("id") or ""
                is_home = (t_id == home_id) if home_id else (t_node.attrib.get("home-team") == "true")
                target_list = home_players if is_home else away_players
                
                for p in t_node.findall(".//player"):
                    p_name = f"{p.attrib.get('given-name', '')} {p.attrib.get('surname', '')}".strip()
                    shirt_number = p.attrib.get("number") or ""
                    position_raw = p.attrib.get("position") or ""
                    is_starter = (position_raw != "Sub")
                    
                    is_gk = p.attrib.get("is-goalkeeper") == "true"
                    if is_gk:
                        position = "GK"
                    elif is_starter:
                        try:
                            pos_val = int(position_raw)
                            if 2 <= pos_val <= 5:
                                position = "DF"
                            elif 6 <= pos_val <= 9:
                                position = "MF"
                            else:
                                position = "FW"
                        except ValueError:
                            position = "N/A"
                    else:
                        position = "N/A"
                        
                    goals = int(p.attrib.get("goals") or 0)
                    yellow = int(p.attrib.get("bookings") or 0)
                    red = int(p.attrib.get("red-card") or 0)
                    
                    target_list.append(SpecialPlayer(
                        name=p_name,
                        shirt_number=shirt_number,
                        position=position,
                        is_starter=is_starter,
                        goals=goals,
                        yellow_cards=yellow,
                        red_cards=red
                    ))
        except Exception:
            pass

        code = "AL"
        for k, entry in self.table.items():
            if str(entry[0]) == str(comp_id):
                code = k
                break

        standings = self.standings(code)
        
        mapped_matches = []
        if comp_id:
            try:
                latest_data = self.client.get_latest_results(comp_id, limit=300)
                results = latest_data.get("matches") if isinstance(latest_data, dict) else latest_data
            except Exception:
                results = []
                
            try:
                upcoming_data = self.client.get_upcoming_matches(comp_id, limit=100)
                upcoming = upcoming_data.get("matches") if isinstance(upcoming_data, dict) else upcoming_data
            except Exception:
                upcoming = []
                
            for rm in (results or []) + (upcoming or []):
                mapped_matches.append(self._to_match_row(rm, comp_id, league_name, self._tier_num(self.table.get(code, ("", "", ""))[2])))

        details = SpecialMatchDetail(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league_code=code,
            league_name=league_name,
            date_arg=date_val,
            time_arg=time_val,
            status=status,
            score=score,
            venue=venue,
            attendance=attendance,
            home_lineup=home_players,
            away_lineup=away_players,
            events=events
        )

        analyzer = SpecialLeagueAnalyzer(home_team, away_team, mapped_matches, standings)
        stats = {
            "form": analyzer.get_form(),
            "h2h": analyzer.get_h2h(),
            "goals": analyzer.get_goals(),
            "table": analyzer.get_table_context(),
            "common_opponents": analyzer.get_common_opponents()
        }

        report = render_special_match_report(details, stats)
        
        if home_players or away_players:
            home_starters = [p for p in home_players if p.is_starter]
            away_starters = [p for p in away_players if p.is_starter]
            
            home_rot = self._calculate_sweden_rotation(home_team, comp_id, home_starters, match_id)
            away_rot = self._calculate_sweden_rotation(away_team, comp_id, away_starters, match_id)
            
            def format_rot(rot) -> str:
                if rot.ratio is None:
                    return "⚠️ Sin datos para comparar."
                badge = " 🚨" if rot.ratio < 0.45 else ""
                desc = f"*{rot.ratio:.0%}*{badge} habituales"
                if rot.new_starters:
                    desc += f" (Nuevos: {', '.join(rot.new_starters[:4])})"
                return desc
                
            report += "\n\n🔍 *Detector de Suplentes / B-Team:*"
            report += f"\n   🏠 *{home_team}:* {format_rot(home_rot)}"
            report += f"\n   ✈️ *{away_team}:* {format_rot(away_rot)}"
            report += "\n💡 _Regularidad <45% 🚨 = B-Team/rotación masiva → posible valor vs cuotas pre-partido._"

        return report


# --------------------------------------------------------------------------- #
# Romania adapter (FRF Datalake)
# --------------------------------------------------------------------------- #
_RO_BUCHAREST = ZoneInfo("Europe/Bucharest")


class RomaniaLeagues(SpecialLeague):
    flag = "🇷🇴"
    country = "Rumanas"
    prefix = "ro"

    def __init__(self, client):
        self.client = client
        self.table = {
            "RO1": (869, 3844, "SuperLiga Feminină", 1, "F"),
            "RO1PO": (895, 4029, "SuperLiga Play-off", 1, "F"),
            "RO1PL": (896, 4030, "SuperLiga Play-out", 1, "F"),
            "RO2S1": (877, 3895, "Liga 2 Feminin Seria 1", 2, "F"),
            "RO2S2": (877, 3896, "Liga 2 Feminin Seria 2", 2, "F"),
        }

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    def leagues(self) -> list[LeagueInfo]:
        return [
            LeagueInfo(code=code, name=info[2], tier=info[3], gender=info[4])
            for code, info in self.table.items()
        ]

    def _resolve_round(self, series_id: int) -> dict | None:
        try:
            filters = self.client.get_filters()
            tours = filters.get("responseData", {}).get("tours", [])
            series_tours = [t for t in tours if t.get("seriesId") == series_id]
            if not series_tours:
                return None
            curr = next((t for t in series_tours if t.get("isCurrent")), None)
            if not curr:
                series_tours.sort(key=lambda t: (t.get("startDate") or "", t.get("tourRoundId") or 0))
                curr = series_tours[-1]
            return curr
        except Exception:
            return None

    def today(self) -> tuple[list[MatchRow], int]:
        from datetime import date
        today_str = date.today().isoformat()
        rows: list[MatchRow] = []
        omitted = 0

        for code, info in self.table.items():
            comp_season_id, series_id, name, tier, gender = info
            curr_round = self._resolve_round(series_id)
            if not curr_round:
                continue

            try:
                res = self.client.get_matches(
                    season_id=curr_round["seasonId"],
                    stage_id=curr_round["stageId"],
                    series_id=series_id,
                    tour_round_id=curr_round["tourRoundId"]
                )

                resp_data = res.get("responseData", {})
                matches_list = resp_data.get("matches", [])

                for m_group in matches_list:
                    for m in m_group.get("list", []):
                        d_arg, t_arg = _arg_time(m.get("startDate"), _RO_BUCHAREST)
                        if d_arg == today_str:
                            status = m.get("sysCompetitionMatchStatusId")
                            played = status == 3
                            live = status == 2
                            score = None
                            if played or live:
                                score = f"{m.get('homeGoals')}-{m.get('awayGoals')}"

                            rows.append(MatchRow(
                                match_id=str(m.get("matchId")),
                                time_arg=t_arg,
                                date_arg=d_arg,
                                home=m.get("homeClub", {}).get("name", "Local"),
                                away=m.get("awayClub", {}).get("name", "Visitante"),
                                score=score,
                                is_live=live,
                                league_code=code,
                                league_name=name,
                                league_tier=tier
                            ))
            except Exception:
                pass

        rows.sort(key=lambda r: r.time_arg)
        return rows, omitted

    def standings(self, code: str) -> StandingsResult:
        code = code.upper()
        info = self.table.get(code)
        if not info:
            return StandingsResult(title=code, found=False)

        comp_season_id, series_id, name, tier, gender = info
        curr_round = self._resolve_round(series_id)
        if not curr_round:
            return StandingsResult(title=name, found=True)

        try:
            res = self.client.get_matches(
                season_id=curr_round["seasonId"],
                stage_id=curr_round["stageId"],
                series_id=series_id,
                tour_round_id=curr_round["tourRoundId"]
            )

            resp_data = res.get("responseData", {})
            rankings = resp_data.get("rankings", [])
            clubs_ranking = resp_data.get("clubsRanking", [])

            rows = []
            for idx, r in enumerate(rankings, start=1):
                club_id = r[0]
                club_name = next((c["name"] for c in clubs_ranking if str(c["clubId"]) == str(club_id)), f"Club {club_id}")
                played = _to_int(r[1]) or 0
                points = _to_int(r[2]) or 0
                gf = _to_int(r[3]) or 0
                ga = _to_int(r[4]) or 0
                goal_diff = gf - ga

                rows.append(StandRow(
                    position=idx,
                    team=club_name,
                    played=played,
                    points=points,
                    goal_diff=goal_diff
                ))
            return StandingsResult(title=f"{name} (2025/2026)", rows=rows)
        except Exception:
            return StandingsResult(title=name, found=True)

    def _row_from_ro_match(self, m: dict, code: str, name: str, tier) -> MatchRow:
        d_arg, t_arg = _arg_time(m.get("startDate"), _RO_BUCHAREST)
        status = m.get("sysCompetitionMatchStatusId")
        played, live = status == 3, status == 2
        score = f"{m.get('homeGoals')}-{m.get('awayGoals')}" if (played or live) else None
        return MatchRow(
            match_id=str(m.get("matchId")), time_arg=t_arg, date_arg=d_arg,
            home=m.get("homeClub", {}).get("name", "Local"),
            away=m.get("awayClub", {}).get("name", "Visitante"),
            score=score, is_live=live, league_code=code, league_name=name, league_tier=tier,
        )

    def fixtures(self, code: str) -> tuple[Optional[str], list[MatchRow]]:
        from datetime import datetime, timezone
        code = code.upper()
        info = self.table.get(code)
        if not info:
            return None, []
        comp_season_id, series_id, name, tier, gender = info

        try:
            filters = self.client.get_filters()
            tours = [t for t in filters.get("responseData", {}).get("tours", []) if t.get("seriesId") == series_id]
        except Exception:
            tours = []
        if not tours:
            return name, []

        tours.sort(key=lambda t: (t.get("startDate") or ""))
        today_iso = datetime.now(timezone.utc).date().isoformat()
        past = [t for t in tours if (t.get("startDate") or "")[:10] < today_iso]
        future = [t for t in tours if (t.get("startDate") or "")[:10] >= today_iso]
        # Recent results + upcoming rounds (not a single stale round).
        selected = past[-3:] + future[:2]

        rows: list[MatchRow] = []
        seen: set[str] = set()
        for t in selected:
            try:
                res = self.client.get_matches(
                    season_id=t["seasonId"], stage_id=t["stageId"],
                    series_id=series_id, tour_round_id=t["tourRoundId"],
                )
            except Exception:
                continue
            for m_group in res.get("responseData", {}).get("matches", []):
                for m in m_group.get("list", []):
                    mid = str(m.get("matchId"))
                    if mid in seen:
                        continue
                    seen.add(mid)
                    rows.append(self._row_from_ro_match(m, code, name, tier))

        rows.sort(key=lambda r: (r.date_arg, r.time_arg))
        return name, rows

    def match_report(self, match_id: str) -> str:
        try:
            filters = self.client.get_filters()
            tours = filters.get("responseData", {}).get("tours", [])
        except Exception as e:
            return f"❌ Error al consultar filtros de la federación rumana: {e}"

        target_match = None
        series_id = None
        code = None
        name = None
        tier = None
        
        tours.sort(key=lambda t: (t.get("startDate") or ""), reverse=True)
        
        for t in tours:
            try:
                res = self.client.get_matches(
                    season_id=t["seasonId"], stage_id=t["stageId"],
                    series_id=t["seriesId"], tour_round_id=t["tourRoundId"]
                )
                matches_list = res.get("responseData", {}).get("matches", [])
                for m_group in matches_list:
                    for m in m_group.get("list", []):
                        if str(m.get("matchId")) == match_id:
                            target_match = m
                            series_id = t["seriesId"]
                            break
                if target_match:
                    break
            except Exception:
                continue

        if not target_match:
            return f"❌ No encontré un partido con ID {match_id} en la federación rumana."

        for k, info in self.table.items():
            if info[1] == series_id:
                code = k
                name = info[2]
                tier = info[3]
                break
        if not code:
            code = f"RO_{series_id}"
            name = "SuperLiga"
            tier = 1

        d_arg, t_arg = _arg_time(target_match.get("startDate"), _RO_BUCHAREST)
        status = target_match.get("sysCompetitionMatchStatusId")
        played = status == 3
        live = status == 2
        score = f"{target_match.get('homeGoals')}-{target_match.get('awayGoals')}" if (played or live) else None
        
        home_team = target_match.get("homeClub", {}).get("name", "Local")
        away_team = target_match.get("awayClub", {}).get("name", "Visitante")

        series_tours = [t for t in tours if t.get("seriesId") == series_id]
        series_tours.sort(key=lambda t: (t.get("startDate") or ""))
        
        all_series_matches = []
        seen = set()
        for t in series_tours:
            try:
                res = self.client.get_matches(
                    season_id=t["seasonId"], stage_id=t["stageId"],
                    series_id=series_id, tour_round_id=t["tourRoundId"]
                )
                for m_group in res.get("responseData", {}).get("matches", []):
                    for m in m_group.get("list", []):
                        mid = str(m.get("matchId"))
                        if mid in seen:
                            continue
                        seen.add(mid)
                        all_series_matches.append(self._row_from_ro_match(m, code, name, tier))
            except Exception:
                continue

        details = SpecialMatchDetail(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league_code=code,
            league_name=name,
            date_arg=d_arg,
            time_arg=t_arg,
            status="Played" if played else "Scheduled",
            score=score,
            venue="N/A",
            attendance="N/A",
            home_lineup=[],
            away_lineup=[],
            events=[]
        )

        standings = self.standings(code)
        analyzer = SpecialLeagueAnalyzer(home_team, away_team, all_series_matches, standings)
        stats = {
            "form": analyzer.get_form(),
            "h2h": analyzer.get_h2h(),
            "goals": analyzer.get_goals(),
            "table": analyzer.get_table_context(),
            "common_opponents": analyzer.get_common_opponents()
        }

        report = render_special_match_report(details, stats)
        report += "\n\nℹ️ _El detector de alineaciones y eventos en vivo no está disponible para la federación rumana._"
        return report



# --------------------------------------------------------------------------- #
# Slovakia adapter (Sportnet API)
# --------------------------------------------------------------------------- #
_SK_BRATISLAVA = ZoneInfo("Europe/Bratislava")


class SlovakiaLeagues(SpecialLeague):
    flag = "🇸🇰"
    country = "Eslovacas"
    prefix = "sk"

    def __init__(self, client):
        self.client = client
        self.table = {
            # Regular season (the main league shown on futbalsfz.sk/1.liga-zien).
            "SK1": ("6849d25aeba10c40f7f8ff85", "6849d25a9db12b1dbe8c5287", "I. liga ženy", 1, "F"),
            "SK1A": ("6849d25aeba10c40f7f8ff85", "69a0455e2d75b679881fcbd4", "I. liga ženy - Play-off", 1, "F"),
            "SK1B": ("6849d25aeba10c40f7f8ff85", "69a045272d75b679881fcbd3", "I. liga ženy - Play-out", 1, "F"),
        }

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    def leagues(self) -> list[LeagueInfo]:
        return [
            LeagueInfo(code=code, name=info[2], tier=info[3], gender=info[4])
            for code, info in self.table.items()
        ]

    def _convert_time(self, iso_str: str | None) -> tuple[str, str]:
        if not iso_str:
            return "N/A", "N/A"
        try:
            if iso_str.endswith("Z"):
                clean = iso_str.replace("Z", "").split(".")[0].replace("T", " ").strip()
                return _arg_time(clean, ZoneInfo("UTC"))
            else:
                clean = iso_str.split(".")[0].replace("T", " ").strip()
                return _arg_time(clean, _SK_BRATISLAVA)
        except Exception:
            return "N/A", "N/A"

    def _match_row(self, m: dict, code: str, name: str, tier) -> MatchRow:
        d_arg, t_arg = self._convert_time(m.get("startDate"))
        teams = m.get("teams", []) or []
        home = next((t["name"] for t in teams if t.get("additionalProperties", {}).get("homeaway") == "home"), None)
        away = next((t["name"] for t in teams if t.get("additionalProperties", {}).get("homeaway") == "away"), None)
        # Fallback to positional order if homeaway is missing.
        if home is None:
            home = teams[0]["name"] if len(teams) > 0 else "Local"
        if away is None:
            away = teams[1]["name"] if len(teams) > 1 else "Visitante"
        score_list = m.get("score")
        score = f"{score_list[0]}-{score_list[1]}" if score_list and len(score_list) == 2 else None
        return MatchRow(
            match_id=m.get("_id", ""), time_arg=t_arg, date_arg=d_arg,
            home=home, away=away, score=score, is_live=False,
            league_code=code, league_name=name, league_tier=tier,
        )

    def today(self) -> tuple[list[MatchRow], int]:
        from datetime import date
        today_str = date.today().isoformat()
        try:
            matches = self.client.get_matches("6849d25aeba10c40f7f8ff85", limit=300).get("matches") or []
        except Exception:
            matches = []

        by_part = {info[1]: (code, info[2], info[3]) for code, info in self.table.items()}
        rows: list[MatchRow] = []
        omitted = 0
        for m in matches:
            d_arg, _ = self._convert_time(m.get("startDate"))
            if d_arg != today_str:
                continue
            part = m.get("competitionPart", {}) or {}
            pid, pname = part.get("_id"), (part.get("name") or "Liga")
            if any(x in pname.lower() for x in ("futsal", "beach", "halová")):
                omitted += 1
                continue
            if pid in by_part:
                code, name, tier = by_part[pid]
            else:
                code, name, tier = (pid or pname), pname, None
            rows.append(self._match_row(m, code, name, tier))

        rows.sort(key=lambda r: r.time_arg)
        return rows, omitted

    def standings(self, code: str) -> StandingsResult:
        code = code.upper()
        info = self.table.get(code)
        if not info:
            return StandingsResult(title=code, found=False)

        comp_id, part_id, name, tier, gender = info
        try:
            data = self.client.get_part(comp_id, part_id)
            res = data.get("resultsTable", {}).get("results") or []
            rows = []
            for idx, r in enumerate(res, start=1):
                team_name = r.get("team", {}).get("name", "?")
                stats = r.get("stats", {})
                played = stats.get("matches", {}).get("played") or 0
                points = stats.get("points") or 0
                gf = stats.get("goals", {}).get("given") or 0
                ga = stats.get("goals", {}).get("received") or 0
                goal_diff = gf - ga

                rows.append(StandRow(
                    position=idx,
                    team=team_name,
                    played=played,
                    points=points,
                    goal_diff=goal_diff
                ))
            return StandingsResult(title=f"{name} (2025/2026)", rows=rows)
        except Exception:
            return StandingsResult(title=name, found=True)

    def fixtures(self, code: str) -> tuple[Optional[str], list[MatchRow]]:
        from datetime import date
        code = code.upper()
        info = self.table.get(code)
        if not info:
            return None, []

        comp_id, part_id, name, tier, gender = info
        try:
            matches = self.client.get_matches(comp_id, limit=300).get("matches") or []
        except Exception:
            matches = []

        sel = [m for m in matches if (m.get("competitionPart", {}) or {}).get("_id") == part_id]
        today_str = date.today().isoformat()

        def dkey(m: dict) -> str:
            return self._convert_time(m.get("startDate"))[0]

        played = sorted([m for m in sel if dkey(m) != "N/A" and dkey(m) < today_str], key=dkey, reverse=True)
        upcoming = sorted([m for m in sel if dkey(m) == "N/A" or dkey(m) >= today_str], key=dkey)
        display = list(reversed(played[:5])) + upcoming[:15]
        rows = [self._match_row(m, code, name, tier) for m in display]
        return name, rows

    def match_report(self, match_id: str) -> str:
        try:
            m = self.client.get_match_detail(match_id)
        except Exception as e:
            return f"❌ Error al consultar partido en la federación eslovaca: {e}"

        comp_id = m.get("competitionId") or "6849d25aeba10c40f7f8ff85"
        part = m.get("competitionPart", {}) or {}
        part_id = part.get("_id")
        
        code = "SK1"
        for k, info in self.table.items():
            if info[1] == part_id:
                code = k
                break
        
        name = part.get("name") or "I. liga ženy"
        tier = 1

        d_arg, t_arg = self._convert_time(m.get("startDate"))
        status = m.get("status") or "Scheduled"
        score_list = m.get("score")
        score = f"{score_list[0]}-{score_list[1]}" if score_list and len(score_list) == 2 else None
        
        teams = m.get("teams", []) or []
        home_team = next((t["name"] for t in teams if t.get("additionalProperties", {}).get("homeaway") == "home"), None)
        away_team = next((t["name"] for t in teams if t.get("additionalProperties", {}).get("homeaway") == "away"), None)
        if home_team is None:
            home_team = teams[0]["name"] if len(teams) > 0 else "Local"
        if away_team is None:
            away_team = teams[1]["name"] if len(teams) > 1 else "Visitante"
            
        home_id = next((t["_id"] for t in teams if t.get("additionalProperties", {}).get("homeaway") == "home"), None)
        away_id = next((t["_id"] for t in teams if t.get("additionalProperties", {}).get("homeaway") == "away"), None)
        if home_id is None:
            home_id = teams[0]["_id"] if len(teams) > 0 else ""
        if away_id is None:
            away_id = teams[1]["_id"] if len(teams) > 1 else ""

        home_players = []
        away_players = []
        nominations = m.get("nominations", []) or []
        for side in nominations:
            side_team_id = side.get("team", {}).get("_id")
            athletes = side.get("athletes", []) or []
            target_list = home_players if str(side_team_id) == str(home_id) else away_players
            for a in athletes:
                is_sub = a.get("substitute")
                pos_map = {"GK": "GK", "DF": "DF", "MF": "MF", "FW": "FW"}
                pos_raw = a.get("position") or ""
                position = pos_map.get(pos_raw, "N/A")
                
                target_list.append(SpecialPlayer(
                    name=a.get("name") or "",
                    shirt_number=str(a.get("shirtNo") or ""),
                    position=position,
                    is_starter=not is_sub
                ))

        events = []
        protocol = m.get("protocol", {}) or {}
        raw_events = protocol.get("events", []) or []
        for ev in raw_events:
            ev_type = ev.get("eventType") or ev.get("type") or ""
            mapped_type = "Other"
            if "goal" in ev_type.lower():
                mapped_type = "Goal"
            elif "yellow" in ev_type.lower():
                mapped_type = "YellowCard"
            elif "red" in ev_type.lower():
                mapped_type = "RedCard"
            elif "sub" in ev_type.lower():
                mapped_type = "Sub"
                
            minute = str(ev.get("eventTime") or ev.get("time") or "")
            phase = ev.get("phase")
            if phase and phase != "1" and phase != "2":
                minute = f"{minute} ({phase})"
                
            ev_team = ev.get("team")
            if isinstance(ev_team, dict):
                ev_team_id = ev_team.get("_id")
            else:
                ev_team_id = ev_team
            team_name = home_team if str(ev_team_id) == str(home_id) else away_team
            
            p_name = ev.get("player", {}).get("name") or ""
            detail = ""
            if mapped_type == "Sub":
                p_in = ev.get("replacement", {}).get("name") or ""
                p_out = ev.get("playerOut", {}).get("name") or ""
                if p_in:
                    detail = f"Entra: {p_in}"
                elif p_out:
                    detail = f"Sale: {p_out}"
                    
            events.append(SpecialEvent(
                minute=minute,
                type=mapped_type,
                player_name=p_name,
                team_name=team_name,
                detail=detail
            ))

        venue = m.get("venue", {}).get("name") or "N/A"
        attendance = str(m.get("attendance") or "N/A")

        details = SpecialMatchDetail(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league_code=code,
            league_name=name,
            date_arg=d_arg,
            time_arg=t_arg,
            status=status,
            score=score,
            venue=venue,
            attendance=attendance,
            home_lineup=home_players,
            away_lineup=away_players,
            events=events
        )

        standings = self.standings(code)
        try:
            matches_resp = self.client.get_matches(comp_id, limit=300)
            raw_matches = matches_resp.get("matches") or []
        except Exception:
            raw_matches = []
            
        mapped_matches = []
        for rm in raw_matches:
            if (rm.get("competitionPart", {}) or {}).get("_id") == part_id:
                mapped_matches.append(self._match_row(rm, code, name, tier))
                
        analyzer = SpecialLeagueAnalyzer(home_team, away_team, mapped_matches, standings)
        stats = {
            "form": analyzer.get_form(),
            "h2h": analyzer.get_h2h(),
            "goals": analyzer.get_goals(),
            "table": analyzer.get_table_context(),
            "common_opponents": analyzer.get_common_opponents()
        }
        
        return render_special_match_report(details, stats)



# --------------------------------------------------------------------------- #
# Algeria adapter (LNFF Scraper)
# --------------------------------------------------------------------------- #
_AL_ALGIERS = ZoneInfo("Africa/Algiers")


class AlgeriaLeagues(SpecialLeague):
    flag = "🇩🇿"
    country = "Argelinas"
    prefix = "al"

    def __init__(self, client):
        self.client = client
        self.table = {
            "DZ1": "D1 Seniors Damas",
        }

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    def leagues(self) -> list[LeagueInfo]:
        return [
            LeagueInfo(code="DZ1", name="D1 Seniors Damas", tier=1, gender="F")
        ]

    def _al_arg_time(self, local: str | None) -> tuple[str, str]:
        if not local:
            return "N/A", "N/A"
        raw = str(local).strip()
        for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y"):
            try:
                dt = datetime.strptime(raw, fmt).replace(tzinfo=_AL_ALGIERS)
                a = dt.astimezone(_ARG)
                time_str = a.strftime("%H:%M") if "%H:%M" in fmt else "N/A"
                return a.strftime("%Y-%m-%d"), time_str
            except ValueError:
                continue
        return "N/A", "N/A"

    def today(self) -> tuple[list[MatchRow], int]:
        from datetime import date
        today_str = date.today().isoformat()
        rows: list[MatchRow] = []
        omitted = 0

        try:
            matches = self.client.get_matches()
        except Exception:
            matches = []

        for m in matches:
            div = str(m.get("division") or "").lower()
            if "d1" not in div and "nationale une" not in div:
                omitted += 1
                continue

            d_arg, t_arg = self._al_arg_time(m.get("date_raw"))
            if d_arg == today_str:
                score_raw = m.get("score_raw")
                score = score_raw.replace(" ", "") if score_raw and "-" in score_raw else None
                slug = m.get("match_url", "").rstrip("/").split("/")[-1] if m.get("match_url") else ""
                if not slug:
                    import uuid
                    slug = str(uuid.uuid4())

                rows.append(MatchRow(
                    match_id=slug,
                    time_arg=t_arg,
                    date_arg=d_arg,
                    home=m.get("home", "Local"),
                    away=m.get("away", "Visitante"),
                    score=score,
                    is_live=False,
                    league_code="DZ1",
                    league_name="D1 Seniors Damas",
                    league_tier=1,
                ))
        rows.sort(key=lambda r: r.time_arg)
        return rows, omitted

    def standings(self, code: str) -> StandingsResult:
        code = code.upper()
        if code != "DZ1":
            return StandingsResult(title=code, found=False)

        try:
            matches = self.client.get_matches()
        except Exception:
            matches = []

        teams_data = {}
        for m in matches:
            div = str(m.get("division") or "").lower()
            if "d1" not in div and "nationale une" not in div:
                continue

            home = m.get("home", "").strip()
            away = m.get("away", "").strip()
            if not home or not away:
                continue

            for t in (home, away):
                if t not in teams_data:
                    teams_data[t] = {
                        "team": t,
                        "played": 0,
                        "wins": 0,
                        "draws": 0,
                        "losses": 0,
                        "gf": 0,
                        "ga": 0,
                        "points": 0
                    }

            score_raw = m.get("score_raw") or ""
            import re
            match = re.search(r"^\s*(\d+)\s*-\s*(\d+)\s*$", score_raw)
            if match:
                hg = int(match.group(1))
                ag = int(match.group(2))

                t_home = teams_data[home]
                t_away = teams_data[away]

                t_home["played"] += 1
                t_away["played"] += 1

                t_home["gf"] += hg
                t_home["ga"] += ag
                t_away["gf"] += ag
                t_away["ga"] += hg

                if hg > ag:
                    t_home["wins"] += 1
                    t_home["points"] += 3
                    t_away["losses"] += 1
                elif hg < ag:
                    t_away["wins"] += 1
                    t_away["points"] += 3
                    t_home["losses"] += 1
                else:
                    t_home["draws"] += 1
                    t_home["points"] += 1
                    t_away["draws"] += 1
                    t_away["points"] += 1

        # Sort: 1. Points, 2. GD, 3. GF, 4. Name
        sorted_teams = sorted(
            teams_data.values(),
            key=lambda x: (x["points"], x["gf"] - x["ga"], x["gf"], x["team"].lower()),
            reverse=True
        )

        rows = []
        for idx, t in enumerate(sorted_teams, start=1):
            rows.append(StandRow(
                position=idx,
                team=t["team"],
                played=t["played"],
                points=t["points"],
                goal_diff=t["gf"] - t["ga"]
            ))

        return StandingsResult(title="D1 Seniors Damas (2024/2025)", rows=rows)

    def fixtures(self, code: str) -> tuple[Optional[str], list[MatchRow]]:
        code = code.upper()
        if code != "DZ1":
            return None, []

        try:
            matches = self.client.get_matches()
        except Exception:
            matches = []

        d1_matches = []
        for m in matches:
            div = str(m.get("division") or "").lower()
            if "d1" not in div and "nationale une" not in div:
                continue
            d1_matches.append(m)

        parsed_list = []
        for m in d1_matches:
            d_arg, t_arg = self._al_arg_time(m.get("date_raw"))
            parsed_list.append((m, d_arg, t_arg))

        parsed_list.sort(key=lambda x: (x[1] == "N/A", x[1], x[2]))

        finished = []
        upcoming = []
        for m, d_arg, t_arg in parsed_list:
            score_raw = m.get("score_raw")
            import re
            has_score = score_raw and re.search(r"\d+\s*-\s*\d+", score_raw)
            score = score_raw.replace(" ", "") if has_score else None
            slug = m.get("match_url", "").rstrip("/").split("/")[-1] if m.get("match_url") else ""
            if not slug:
                import uuid
                slug = str(uuid.uuid4())

            row = MatchRow(
                match_id=slug,
                time_arg=t_arg,
                date_arg=d_arg,
                home=m.get("home", "Local"),
                away=m.get("away", "Visitante"),
                score=score,
                is_live=False,
                league_code="DZ1",
            )
            if has_score:
                finished.append(row)
            else:
                upcoming.append(row)

        display = finished[-5:] + upcoming[:10]
        return "D1 Seniors Damas", display

    def match_report(self, match_id: str) -> str:
        try:
            matches = self.client.get_matches()
        except Exception as e:
            return f"❌ Error al consultar partidos de la federación argelina: {e}"

        target = None
        for m in matches:
            slug = m.get("match_url", "").rstrip("/").split("/")[-1] if m.get("match_url") else ""
            if slug == match_id:
                target = m
                break
        if not target:
            return f"❌ No encontré un partido con ID {match_id} en la federación argelina."

        d_arg, t_arg = self._al_arg_time(target.get("date_raw"))
        score_raw = target.get("score_raw")
        import re
        has_score = score_raw and re.search(r"\d+\s*-\s*\d+", score_raw)
        score = score_raw.replace(" ", "") if has_score else None
        
        home_team = target.get("home", "Local").strip()
        away_team = target.get("away", "Visitante").strip()

        details = SpecialMatchDetail(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league_code="DZ1",
            league_name="D1 Seniors Damas",
            date_arg=d_arg,
            time_arg=t_arg,
            status="Played" if score else "Scheduled",
            score=score,
            venue="N/A",
            attendance="N/A",
            home_lineup=[],
            away_lineup=[],
            events=[]
        )

        standings = self.standings("DZ1")
        
        d1_matches = []
        for m in matches:
            div = str(m.get("division") or "").lower()
            if "d1" not in div and "nationale une" not in div:
                continue
            
            d_m, t_m = self._al_arg_time(m.get("date_raw"))
            s_raw = m.get("score_raw")
            h_s = s_raw.replace(" ", "") if s_raw and "-" in s_raw else None
            
            d1_matches.append(MatchRow(
                match_id=m.get("match_url", ""),
                time_arg=t_m,
                date_arg=d_m,
                home=m.get("home", "Local"),
                away=m.get("away", "Visitante"),
                score=h_s,
                league_code="DZ1",
            ))

        analyzer = SpecialLeagueAnalyzer(home_team, away_team, d1_matches, standings)
        stats = {
            "form": analyzer.get_form(),
            "h2h": analyzer.get_h2h(),
            "goals": analyzer.get_goals(),
            "table": analyzer.get_table_context(),
            "common_opponents": analyzer.get_common_opponents()
        }

        report = render_special_match_report(details, stats)
        report += "\n\nℹ️ _El detector de alineaciones y eventos en vivo no está disponible para la federación argelina._"
        return report



# Norway adapter (NFF Scraper)
# --------------------------------------------------------------------------- #
_NO_OSLO = ZoneInfo("Europe/Oslo")


from html.parser import HTMLParser

class NorwayMatchDetailParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_player_list = False
        self.current_list_index = 0  # 0: Home starters, 1: Home subs, 2: Away starters, 3: Away subs
        self.players = {0: [], 1: [], 2: [], 3: []}
        
        self.in_player_item = False
        self.current_player = None
        
        self.in_h4 = False
        self.h4_text = []
        
        self.in_shirt_number = False
        self.shirt_text = []
        
        self.in_player_link = False
        self.player_name_parts = []
        
        self.venue = "N/A"
        self.attendance = "N/A"
        self.in_meta_label = False
        self.meta_label = ""
        self.in_meta_value = False
        self.meta_value_parts = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        
        if tag == "h4":
            self.in_h4 = True
            self.h4_text = []
        elif tag in ("ul", "ol") and "a_matchPlayerList" in cls:
            self.in_player_list = True
        elif tag == "li" and self.in_player_list:
            self.in_player_item = True
            self.current_player = {
                "name": "",
                "shirt_number": "",
                "goals": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "events": []
            }
        elif tag == "span" and "a_playerNumber" in cls and self.in_player_item:
            self.in_shirt_number = True
            self.shirt_text = []
        elif tag == "a" and "/person/profil/" in attrs_dict.get("href", "") and self.in_player_item:
            self.in_player_link = True
            self.player_name_parts = []
        elif tag == "svg" and self.in_player_item:
            icon = attrs_dict.get("data-icon", "").lower() or cls.lower()
            if "yellowcard" in icon:
                self.current_player["yellow_cards"] += 1
            elif "redcard" in icon:
                self.current_player["red_cards"] += 1
            elif "soccer" in icon or "ball" in icon or "goal" in icon:
                self.current_player["goals"] += 1
        elif tag == "i" and self.in_player_item:
            icon = cls.lower()
            if "yellow" in icon:
                self.current_player["yellow_cards"] += 1
            elif "red" in icon:
                self.current_player["red_cards"] += 1
            elif "soccer" in icon or "ball" in icon or "goal" in icon:
                self.current_player["goals"] += 1
        elif tag == "span" and "a_matchInfoLabel" in cls:
            self.in_meta_label = True
            self.meta_label = ""
        elif tag == "span" and "a_matchInfoValue" in cls:
            self.in_meta_value = True
            self.meta_value_parts = []

    def handle_endtag(self, tag):
        if tag == "h4":
            self.in_h4 = False
            txt = "".join(self.h4_text).strip().lower()
            if "innbyttere" in txt:
                if self.current_list_index == 0:
                    self.current_list_index = 1
                elif self.current_list_index == 2:
                    self.current_list_index = 3
        elif tag in ("ul", "ol") and self.in_player_list:
            self.in_player_list = False
            if self.current_list_index == 1:
                self.current_list_index = 2
            elif self.current_list_index == 0:
                self.current_list_index = 2
        elif tag == "li" and self.in_player_item:
            self.in_player_item = False
            if self.current_player and self.current_player["name"]:
                self.players[self.current_list_index].append(self.current_player)
            self.current_player = None
        elif tag == "span" and self.in_shirt_number:
            self.in_shirt_number = False
            if self.current_player:
                self.current_player["shirt_number"] = "".join(self.shirt_text).strip()
        elif tag == "a" and self.in_player_link:
            self.in_player_link = False
            if self.current_player:
                self.current_player["name"] = "".join(self.player_name_parts).strip()
        elif tag == "span" and self.in_meta_label:
            self.in_meta_label = False
        elif tag == "span" and self.in_meta_value:
            self.in_meta_value = False
            val = "".join(self.meta_value_parts).strip()
            lbl = self.meta_label.strip().lower()
            if "tilskuere" in lbl or "attendance" in lbl or "tilskuer" in lbl:
                self.attendance = val
            elif "stadion" in lbl or "stadium" in lbl or "bane" in lbl:
                self.venue = val

    def handle_data(self, data):
        if self.in_h4:
            self.h4_text.append(data)
        elif self.in_shirt_number:
            self.shirt_text.append(data)
        elif self.in_player_link:
            self.player_name_parts.append(data)
        elif self.in_meta_label:
            self.meta_label += data
        elif self.in_meta_value:
            self.meta_value_parts.append(data)


class NorwayLeagues(SpecialLeague):
    flag = "🇳🇴"
    country = "Noruegas"
    prefix = "no"

    def __init__(self, client):
        self.client = client
        self.table = {
            "NO1": "Toppserien",
        }

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    def leagues(self) -> list[LeagueInfo]:
        return [
            LeagueInfo(code="NO1", name="Toppserien", tier=1, gender="F")
        ]

    def _oslo_arg_time(self, date_str: str | None, time_str: str | None) -> tuple[str, str]:
        if not date_str or not time_str:
            return "N/A", "N/A"
        raw_date = str(date_str).strip()
        raw_time = str(time_str).strip()
        
        for fmt in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(f"{raw_date} {raw_time}", fmt).replace(tzinfo=_NO_OSLO)
                a = dt.astimezone(_ARG)
                return a.strftime("%Y-%m-%d"), a.strftime("%H:%M")
            except ValueError:
                continue

        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw_date, fmt).replace(tzinfo=_NO_OSLO)
                a = dt.astimezone(_ARG)
                return a.strftime("%Y-%m-%d"), "N/A"
            except ValueError:
                continue

        return "N/A", "N/A"

    def _extract_fiks_id(self, row: list[dict[str, Any]]) -> str:
        import urllib.parse

        def _fiks_from(href: str) -> str | None:
            try:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                return qs["fiksId"][0] if "fiksId" in qs else None
            except Exception:
                return None

        # The MATCH id lives in the /fotballdata/kamp/ link. A row also carries
        # fiksId for the tournament, teams and venue; grabbing the first match
        # returned the TOURNAMENT id, which 404s on the match-detail URL.
        for cell in row:
            for href in cell.get("hrefs", []):
                if "/fotballdata/kamp/" in href:
                    fiks = _fiks_from(href)
                    if fiks:
                        return fiks
        if len(row) > 8:
            txt = row[8].get("text", "").strip()
            if txt.isdigit():
                return txt
        return ""

    def today(self) -> tuple[list[MatchRow], int]:
        from datetime import date
        today_date_str = date.today().strftime("%d.%m.%Y")
        today_iso = date.today().isoformat()
        rows: list[MatchRow] = []
        omitted = 0

        try:
            tables = self.client.get_tables("https://www.fotball.no/fotballdata/dagens-kamper/")
        except Exception:
            tables = []

        target_table = None
        for t in tables:
            first_row = t.get("rows", [[]])[0]
            first_row_text = [cell.get("text", "").lower() for cell in first_row]
            if "hjemmelag" in first_row_text and "bortelag" in first_row_text:
                target_table = t
                break

        noise = ("u21", "u19", "u17", "u16", "u15", "u14", "futsal", "landskamp",
                 "norge ", "menn u", "kvinner u", "gutter", "jenter")
        if target_table:
            for row in target_table["rows"][1:]:
                if len(row) < 5:
                    continue
                tournament = row[0].get("text", "")
                t_low = tournament.lower()
                if any(n in t_low for n in noise):  # selecciones / juveniles / futsal
                    omitted += 1
                    continue

                # Toppserien keeps its code; the rest are shown differentiated.
                if "toppserien" in t_low:
                    code, name, tier = "NO1", "Toppserien", 1
                else:
                    name = tournament.strip()
                    code = "NO" + "".join(c for c in t_low if c.isalnum())[:18]
                    tier = None

                time_str = row[1].get("text", "")
                home = row[2].get("text", "Local")
                away = row[4].get("text", "Visitante")
                score_raw = row[3].get("text", "")

                d_arg, t_arg = self._oslo_arg_time(today_date_str, time_str)

                import re
                has_score = score_raw and re.search(r"\d+\s*-\s*\d+", score_raw)
                score = score_raw.replace(" ", "") if has_score else None
                match_id = self._extract_fiks_id(row)

                rows.append(MatchRow(
                    match_id=match_id,
                    time_arg=t_arg,
                    date_arg=d_arg,
                    home=home,
                    away=away,
                    score=score,
                    is_live=False,
                    league_code=code,
                    league_name=name,
                    league_tier=tier,
                ))

        rows.sort(key=lambda r: r.time_arg)
        return rows, omitted

    def standings(self, code: str) -> StandingsResult:
        code = code.upper()
        if code != "NO1":
            return StandingsResult(title=code, found=False)

        try:
            tables = self.client.get_tables("https://www.fotball.no/turneringer/toppserien/")
        except Exception:
            tables = []

        target_table = None
        for t in tables:
            first_row = t.get("rows", [[]])[0]
            first_row_text = [cell.get("text", "").lower() for cell in first_row]
            if "plass" in first_row_text and "lag" in first_row_text and "poeng" in first_row_text:
                target_table = t
                break

        if not target_table:
            return StandingsResult(title="Toppserien", found=True)

        rows = []
        for row in target_table["rows"]:
            if len(row) < 7:
                continue
            plass_text = row[0].get("text", "").strip()
            if not plass_text.isdigit():
                continue

            pos = int(plass_text)
            team = row[1].get("text", "")
            played = _to_int(row[2].get("text", "")) or 0
            
            points_text = row[len(row) - 1].get("text", "")
            points = _to_int(points_text) or 0
            
            diff_text = row[len(row) - 2].get("text", "").replace("−", "-").strip()
            goal_diff = _to_int(diff_text) or 0

            rows.append(StandRow(
                position=pos,
                team=team,
                played=played,
                points=points,
                goal_diff=goal_diff
            ))

        return StandingsResult(title="Toppserien (2026)", rows=rows)

    def fixtures(self, code: str) -> tuple[Optional[str], list[MatchRow]]:
        code = code.upper()
        if code != "NO1":
            return None, []

        try:
            tables = self.client.get_tables("https://www.fotball.no/turneringer/toppserien/")
        except Exception:
            tables = []

        target_table = None
        for t in tables:
            first_row = t.get("rows", [[]])[0]
            first_row_text = [cell.get("text", "").lower() for cell in first_row]
            if "runde" in first_row_text and "dato" in first_row_text and "hjemmelag" in first_row_text:
                target_table = t
                break

        if not target_table:
            return "Toppserien", []

        all_matches = []
        for row in target_table["rows"]:
            if len(row) < 7:
                continue
            runde_text = row[0].get("text", "").strip()
            if not runde_text.isdigit():
                continue

            date_str = row[1].get("text", "")
            time_str = row[3].get("text", "")
            home = row[4].get("text", "Local")
            score_raw = row[5].get("text", "")
            away = row[6].get("text", "Visitante")
            
            d_arg, t_arg = self._oslo_arg_time(date_str, time_str)
            match_id = self._extract_fiks_id(row)

            import re
            has_score = score_raw and re.search(r"\d+\s*-\s*\d+", score_raw)
            score = score_raw.replace(" ", "") if has_score else None

            all_matches.append((
                MatchRow(
                    match_id=match_id,
                    time_arg=t_arg,
                    date_arg=d_arg,
                    home=home,
                    away=away,
                    score=score,
                    is_live=False,
                    league_code="NO1",
                ),
                has_score
            ))

        finished = []
        upcoming = []
        for row_match, has_score in all_matches:
            if has_score:
                finished.append(row_match)
            else:
                upcoming.append(row_match)

        display = finished[-5:] + upcoming[:10]
        return "Toppserien", display

    def match_report(self, match_id: str) -> str:
        url = f"https://www.fotball.no/fotballdata/kamp/?fiksId={match_id}"
        try:
            html = self.client.get_html(url)
        except Exception as e:
            return f"❌ Error al consultar partido en la federación noruega: {e}"

        if not html or not isinstance(html, str):
            html = "<html><title>Local - Visitante</title></html>"

        parser = NorwayMatchDetailParser()
        parser.feed(html)

        home_lineup = []
        away_lineup = []
        events = []

        for p in parser.players[0]:
            home_lineup.append(SpecialPlayer(
                name=p["name"],
                shirt_number=p["shirt_number"],
                is_starter=True,
                goals=p["goals"],
                yellow_cards=p["yellow_cards"],
                red_cards=p["red_cards"]
            ))
        for p in parser.players[1]:
            home_lineup.append(SpecialPlayer(
                name=p["name"],
                shirt_number=p["shirt_number"],
                is_starter=False,
                goals=p["goals"],
                yellow_cards=p["yellow_cards"],
                red_cards=p["red_cards"]
            ))

        for p in parser.players[2]:
            away_lineup.append(SpecialPlayer(
                name=p["name"],
                shirt_number=p["shirt_number"],
                is_starter=True,
                goals=p["goals"],
                yellow_cards=p["yellow_cards"],
                red_cards=p["red_cards"]
            ))
        for p in parser.players[3]:
            away_lineup.append(SpecialPlayer(
                name=p["name"],
                shirt_number=p["shirt_number"],
                is_starter=False,
                goals=p["goals"],
                yellow_cards=p["yellow_cards"],
                red_cards=p["red_cards"]
            ))

        for p in home_lineup:
            if p.goals > 0:
                for _ in range(p.goals):
                    events.append(SpecialEvent(minute="--", type="Goal", player_name=p.name, team_name="Local"))
            if p.yellow_cards > 0:
                for _ in range(p.yellow_cards):
                    events.append(SpecialEvent(minute="--", type="YellowCard", player_name=p.name, team_name="Local"))
            if p.red_cards > 0:
                for _ in range(p.red_cards):
                    events.append(SpecialEvent(minute="--", type="RedCard", player_name=p.name, team_name="Local"))
                    
        for p in away_lineup:
            if p.goals > 0:
                for _ in range(p.goals):
                    events.append(SpecialEvent(minute="--", type="Goal", player_name=p.name, team_name="Visitante"))
            if p.yellow_cards > 0:
                for _ in range(p.yellow_cards):
                    events.append(SpecialEvent(minute="--", type="YellowCard", player_name=p.name, team_name="Visitante"))
            if p.red_cards > 0:
                for _ in range(p.red_cards):
                    events.append(SpecialEvent(minute="--", type="RedCard", player_name=p.name, team_name="Visitante"))

        import html as _html
        import re
        title_match = re.search(r"<title>\s*([^<]+)\s*</title>", html, re.IGNORECASE)
        title_text = _html.unescape(title_match.group(1)) if title_match else "Kamp"
        parts = [p.strip() for p in title_text.split("-")]
        
        home_team = "Local"
        away_team = "Visitante"
        if len(parts) >= 2:
            home_team = parts[0]
            away_team = parts[1]
            
        score = None
        score_match = re.search(r'<h3 class="a_matchScore">[^<]*(\d+)\s*-\s*(\d+)[^<]*</h3>', html, re.IGNORECASE)
        if score_match:
            score = f"{score_match.group(1)}-{score_match.group(2)}"
        else:
            score_match = re.search(r'<span class="a_score">[^<]*(\d+)\s*-\s*(\d+)[^<]*</span>', html, re.IGNORECASE)
            if score_match:
                score = f"{score_match.group(1)}-{score_match.group(2)}"
            else:
                score_match = re.search(r'\b(\d+)\s*-\s*(\d+)\b', title_text)
                if score_match:
                    score = f"{score_match.group(1)}-{score_match.group(2)}"

        date_arg = "N/A"
        time_arg = "N/A"
        date_match = re.search(r'\b(\d{2}\.\d{2}\.\d{4})\b', title_text)
        if date_match:
            dparts = date_match.group(1).split(".")
            date_arg = f"{dparts[2]}-{dparts[1]}-{dparts[0]}"
            
        time_match = re.search(r'\b(\d{2}:\d{2})\b', html)
        if time_match:
            time_arg = time_match.group(1)

        # Resolve the league this match actually belongs to. today() carries the
        # real league per match; only Toppserien (NO1) exposes a standings table
        # and a full-season fixtures list, so the table/form context is only
        # meaningful there — for lower tiers we use today()'s matches as context.
        try:
            today_matches, _ = self.today()
        except Exception:
            today_matches = []
        today_target = next((m for m in today_matches if m.match_id == match_id), None)
        league_code = (today_target.league_code if today_target else None) or "NO1"
        league_name = (today_target.league_name if today_target else None) or "Toppserien"

        if league_code == "NO1":
            standings = self.standings("NO1")
            try:
                _, all_matches = self.fixtures("NO1")
            except Exception:
                all_matches = []
            if not all_matches:
                all_matches = today_matches
        else:
            standings = StandingsResult(title=league_name, found=True)
            all_matches = today_matches

        for m in all_matches:
            if m.match_id == match_id:
                if home_team in ("Local", "Visitante", "Kamp", ""):
                    home_team = m.home
                if away_team in ("Local", "Visitante", "Kamp", ""):
                    away_team = m.away
                break

        details = SpecialMatchDetail(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league_code=league_code,
            league_name=league_name,
            date_arg=date_arg,
            time_arg=time_arg,
            status="Played" if score else "Scheduled",
            score=score,
            venue=parser.venue,
            attendance=parser.attendance,
            home_lineup=home_lineup,
            away_lineup=away_lineup,
            events=events
        )

        analyzer = SpecialLeagueAnalyzer(home_team, away_team, all_matches, standings)
        stats = {
            "form": analyzer.get_form(),
            "h2h": analyzer.get_h2h(),
            "goals": analyzer.get_goals(),
            "table": analyzer.get_table_context(),
            "common_opponents": analyzer.get_common_opponents()
        }

        return render_special_match_report(details, stats)


