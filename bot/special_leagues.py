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
    note: Optional[str] = None  # custom message shown when there is no table (e.g. cups)


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


# Norway adapter (NFF Scraper)
# --------------------------------------------------------------------------- #
_NO_OSLO = ZoneInfo("Europe/Oslo")


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
        for cell in row:
            for href in cell.get("hrefs", []):
                if "fiksId=" in href:
                    try:
                        parsed = urllib.parse.urlparse(href)
                        qs = urllib.parse.parse_qs(parsed.query)
                        if "fiksId" in qs:
                            return qs["fiksId"][0]
                    except Exception:
                        pass
        if len(row) > 8:
            txt = row[8].get("text", "").strip()
            if txt.isdigit():
                return txt
        import uuid
        return str(uuid.uuid4())

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

