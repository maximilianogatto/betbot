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
from typing import Optional
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
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
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

    def __init__(self, client, league_table: dict[str, tuple[str, str, str]]):
        self.client = client
        self.table = league_table
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

    def leagues(self) -> list[LeagueInfo]:
        return [
            LeagueInfo(code=code, name=name, tier=self._tier_num(tier),
                       gender="F" if "dam" in tier.lower() else "M")
            for code, (_cid, name, tier) in self.table.items()
        ]

    def _code_for(self, competition_name: str) -> Optional[str]:
        low = str(competition_name or "").lower()
        if any(h in low for h in _SWE_NOISE):
            return None
        for keyword, code in self._keywords:
            if keyword and keyword in low:
                return code
        return None

    def today(self) -> tuple[list[MatchRow], int]:
        try:
            matches = self.client.get_matches_today() or []
        except Exception:
            matches = []
        rows: list[MatchRow] = []
        omitted = 0
        for m in matches:
            code = self._code_for(m.get("competition_name") or "")
            if not code:
                omitted += 1
                continue
            _d, t_arg = _arg_time(m.get("start_time_local"), _STOCKHOLM)
            hs, as_ = m.get("home_score"), m.get("away_score")
            score = f"{hs}-{as_}" if hs is not None and as_ is not None else None
            rows.append(MatchRow(
                match_id=str(m.get("match_id") or ""), time_arg=t_arg,
                home=m.get("home") or "Local", away=m.get("away") or "Visitante",
                score=score, league_code=code, league_name=self.table[code][1],
                league_tier=self._tier_num(self.table[code][2]),
            ))
        rows.sort(key=lambda r: r.time_arg)
        return rows, omitted

    def standings(self, code: str) -> StandingsResult:
        code = code.upper()
        entry = self.table.get(code)
        if not entry:
            return StandingsResult(title=code, found=False)
        comp_id, name, _tier = entry
        try:
            data = self.client.get_standings(comp_id)
            teams = data.get("teams") if isinstance(data, dict) else data
        except Exception:
            teams = []
        rows = [
            StandRow(
                position=_to_int(t.get("position")) or i,
                team=str(t.get("team") or "?"),
                played=_to_int(t.get("played")) or 0,
                points=_to_int(t.get("points")) or 0,
                goal_diff=_to_int(t.get("goal_difference")) or 0,
            )
            for i, t in enumerate(teams or [], start=1)
        ]
        return StandingsResult(title=f"{name} (2026)", rows=rows)

    def fixtures(self, code: str) -> tuple[Optional[str], list[MatchRow]]:
        code = code.upper()
        entry = self.table.get(code)
        if not entry:
            return None, []
        comp_id, name, _tier = entry
        return name, self._match_rows(self.client.get_upcoming_matches, comp_id, code)

    def results(self, code: str) -> tuple[Optional[str], list[MatchRow]]:
        code = code.upper()
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
