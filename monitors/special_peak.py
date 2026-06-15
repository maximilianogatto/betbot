"""Daily "peak" scoring for special-league matches (Finland / Sweden).

These federation feeds (`tulospalvelu.palloliitto.fi`, `svenskfotboll.se`) cover
promotion ligas and cups that mainstream stats sites ignore. Because the public
casinos price these games off thin data, they are fertile ground for value.

The 1-10 score blends two reads:

* **Value-opportunity** (structural, available all day): a cup round and/or a
  cross-division pairing means the favourite is likely to rotate its XI.
* **B-Team / substitute detector** (confirmed once lineups publish, ~1h before
  kickoff): the regularity of today's XI versus the team's recent *league* XI.
  A low regularity = the A-team is resting = the casino price still reflects the
  strong side = value before the odds collapse.

Every scored match also carries a *peak* flag plus a *window* telling the user
*when* to act (cup games must wait for the official lineup ~1h pre-kickoff).

The scoring functions accept already-fetched payloads / injected lookups so they
stay unit-testable without hitting the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from core.timezones import current_display_timezone, tz_offset_label
from monitors.peak_model import (
    LeagueModel,
    PastMatch,
    PeakParams,
    PrematchBreakdown,
    TeamStats,
    score_prematch,
)

_HELSINKI = ZoneInfo("Europe/Helsinki")
_STOCKHOLM = ZoneInfo("Europe/Stockholm")
_ARG = ZoneInfo("America/Argentina/Buenos_Aires")

# Finland senior-competition category_id codes. These are EXACT codes (the
# federation feed tags youth/hobby leagues with codes like P15LE / MH1 / P12HL
# whose *names* still contain "Liiga"/"Cup"/"Kakkonen", so name matching would
# leak youth games — we match the code only).
#   VL  Veikkausliiga (1) · M1L Ykkösliiga (2) · M1 Ykkönen (3) · M2 Kakkonen (4)
#   NL  Kansallinen Liiga (women 1)
#   MSC Suomen Cup · NSC Naisten Suomen Cup · LC Liigacup · M1LCUP Ykkösliigacup
#   MRC Regions Cup · MRRC Roots Cup (regional men's cups: big division gaps)
_FIN_CUP_CODES = {"MSC", "NSC", "LC", "M1LCUP", "MRC", "MRRC"}
_FIN_LEAGUE_CODES = {"VL", "M1L", "M1", "M2", "NL"}
_FIN_SENIOR_CODES = _FIN_LEAGUE_CODES | _FIN_CUP_CODES

# Sweden has no clean category codes in the "matches today" feed, only a
# competition name. Keep the pro/semi-pro senior tiers + the national cup and
# drop youth (P19/F18/U..), academy and friendly noise.
_SWE_LEAGUE_HINTS = ("allsvenskan", "superettan", "ettan", "damallsvenskan", "elitettan")
_SWE_CUP_HINTS = ("svenska cupen",)
_SWE_YOUTH_HINTS = (
    "p21", "p19", "p17", "p16", "p15", "p14", "p13",
    "f21", "f19", "f18", "f17", "f16", "f15",
    "u21", "u19", "u17", "u16", "ungdom", "pojkar", "flickor", "junior",
    "akademi", "3-nations", "landskamp", "träningsmatch", "futsal",
)

_FINISHED_STATUSES = {"finished", "played", "walkover"}

# Scoring weights (sum clamps to 1..10).
_W_BASE = 1.0
_W_SENIOR = 1.0
_W_CUP = 3.0
_W_MISMATCH = 2.5
_W_ROT_MASSIVE = 3.5
_W_ROT_PARTIAL = 1.0
_W_ROT_REGULAR = -1.5

# Rotation thresholds (regularity ratio of today's XI vs recent league XI).
_ROT_MASSIVE = 0.45
_ROT_PARTIAL = 0.70

# Peak gating.
_PEAK_SCORE_THRESHOLD = 6.5
LINEUP_WINDOW_MIN = 150  # only run the (costly) rotation detector this close.
LINEUP_LEAD_MIN = 60  # lineups publish ~1h before kickoff.

# Cup overlay: a cup round is inherently watch-worthy (rotation risk the
# pre-lineup mismatch model can't see), so floor its model score.
_CUP_FLOOR = 5.0
# Rotation overlay deltas applied on top of the model score (1-10).
_ROT_DELTA_MASSIVE = 3.0
_ROT_DELTA_PARTIAL = 1.0
_ROT_DELTA_REGULAR = -1.0


@dataclass
class PeakFactor:
    """One contribution to a match's 1-10 score."""

    label: str
    detail: str
    points: float


@dataclass
class RotationResult:
    """Outcome of the B-Team / substitute detector for one team."""

    ratio: Optional[float]
    new_starters: list[str] = field(default_factory=list)


@dataclass
class SpecialMatchScore:
    """A scored special-league match ready for the daily digest."""

    source: str  # e.g. "🇫🇮 Finlandia"
    provider_key: str  # "finland" | "sweden"
    match_id: str
    home: str
    away: str
    competition: str
    kickoff_arg: Optional[datetime]
    kickoff_label: str  # "HH:MM" in Argentina time
    score: float
    is_peak: bool
    peak_window: str
    rotation_ratio: Optional[float]
    factors: list[PeakFactor]
    detail_command: str  # e.g. "/fin_match 123"
    favorite: Optional[str] = None  # name of the favoured team, if any
    edge: float = 0.0  # signed mismatch edge toward home (>0 home favoured)

    @property
    def score_int(self) -> int:
        return int(round(self.score))

    @property
    def badge(self) -> str:
        s = self.score_int
        if s >= 8:
            return "🔥"
        if s >= 6:
            return "✅"
        if s >= 4:
            return "🟡"
        return "⚪️"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _parse_kickoff(date_str: Optional[str], time_str: Optional[str], tz: ZoneInfo) -> Optional[datetime]:
    """Build a tz-aware kickoff datetime from a federation date+time."""

    if not date_str or not time_str:
        return None
    raw = f"{str(date_str).strip()} {str(time_str).strip()}"
    raw = raw.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            naive = datetime.strptime(raw, fmt)
            return naive.replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def _arg_label(kickoff: Optional[datetime]) -> str:
    if kickoff is None:
        return "N/A"
    return kickoff.astimezone(_ARG).strftime("%H:%M")


def _within_lineup_window(kickoff: Optional[datetime], now: datetime) -> bool:
    """True when kickoff is close enough that lineups may be published."""

    if kickoff is None:
        return False
    delta = (kickoff - now).total_seconds() / 60.0
    # From LINEUP_WINDOW_MIN before kickoff up to kickoff itself.
    return -10.0 <= delta <= LINEUP_WINDOW_MIN


def _peak_decision(
    score: float,
    rotation_ratio: Optional[float],
    kickoff: Optional[datetime],
    now: datetime,
) -> tuple[bool, str]:
    """Decide the peak flag and the timing advice ('cuándo entrar')."""

    confirmed_b_team = rotation_ratio is not None and rotation_ratio < _ROT_MASSIVE
    if confirmed_b_team:
        return True, "🟢 AHORA — alineación B confirmada; entrá antes de que caigan las cuotas"

    is_peak = score >= _PEAK_SCORE_THRESHOLD
    if kickoff is None:
        return is_peak, "Horario sin confirmar"

    arg_now = now.astimezone(_ARG)
    k = kickoff.astimezone(_ARG)
    lead = k - timedelta(minutes=LINEUP_LEAD_MIN)
    if arg_now < lead:
        window = f"⏳ Esperá las alineaciones ~{lead:%H:%M} (1h antes del inicio {k:%H:%M})"
    elif arg_now < k:
        window = f"🟢 AHORA — las alineaciones deberían estar publicadas (inicio {k:%H:%M})"
    else:
        window = "⌛ Ya empezó / pasó la ventana"
    return is_peak, window


# --------------------------------------------------------------------------- #
# B-Team / substitute detector (numeric core; shared with /fin_match text view)
# --------------------------------------------------------------------------- #
def compute_rotation_ratio(
    api: Any,
    *,
    team_id: Any,
    primary_category: Any,
    competition_id: Any,
    starters: list[dict[str, Any]],
    target_match_id: Any,
) -> RotationResult:
    """Regularity of today's XI vs the team's last 3 *league* starting XIs.

    Returns ``RotationResult(ratio=None)`` when there is not enough data to
    compare (no starters, no recent league games, or fetch failure).
    """

    if not starters:
        return RotationResult(None)

    try:
        league_matches = api.get_matches_by_league(competition_id, primary_category)
    except Exception:
        return RotationResult(None)

    recent: list[dict[str, Any]] = []
    for m in league_matches or []:
        if str(m.get("match_id")) == str(target_match_id):
            continue
        if m.get("status") in ("Finished", "Played") and m.get("walkover") != 1:
            if str(m.get("team_A_id")) == str(team_id) or str(m.get("team_B_id")) == str(team_id):
                recent.append(m)

    recent.sort(key=lambda x: x.get("date", ""), reverse=True)
    recent = recent[:3]
    if not recent:
        return RotationResult(None)

    starter_counts: dict[Any, int] = {}
    for rm in recent:
        try:
            details = api.get_match_details(rm.get("match_id"))
        except Exception:
            continue
        if not details:
            continue
        for p in details.get("lineups", []):
            if str(p.get("team_id")) == str(team_id) and p.get("start") == "1":
                pid = p.get("player_id")
                starter_counts[pid] = starter_counts.get(pid, 0) + 1

    min_starts = max(1, len(recent) // 2 + (1 if len(recent) % 2 != 0 else 0))
    regular_ids = {pid for pid, count in starter_counts.items() if count >= min_starts}
    current_ids = {p.get("player_id") for p in starters}
    matching = current_ids & regular_ids

    denom = 11 if len(matching) <= 11 else len(starters)
    ratio = len(matching) / denom if denom else None
    new_starters = [
        f"{p.get('shirt_number')} {p.get('player_name')}".strip()
        for p in starters
        if p.get("player_id") not in regular_ids
    ]
    return RotationResult(ratio, new_starters)


def rotation_lookup_for_match(api: Any, details: dict[str, Any]) -> tuple[RotationResult, RotationResult]:
    """Run the rotation detector for both teams of a fetched match payload."""

    home_id = details.get("team_A_id")
    away_id = details.get("team_B_id")
    lineups = details.get("lineups", []) or []
    home_starters = [p for p in lineups if str(p.get("team_id")) == str(home_id) and p.get("start") == "1"]
    away_starters = [p for p in lineups if str(p.get("team_id")) == str(away_id) and p.get("start") == "1"]
    competition_id = details.get("competition_id")
    match_id = details.get("match_id")
    home = compute_rotation_ratio(
        api,
        team_id=home_id,
        primary_category=details.get("team_A_primary_category_id") or details.get("category_id"),
        competition_id=competition_id,
        starters=home_starters,
        target_match_id=match_id,
    )
    away = compute_rotation_ratio(
        api,
        team_id=away_id,
        primary_category=details.get("team_B_primary_category_id") or details.get("category_id"),
        competition_id=competition_id,
        starters=away_starters,
        target_match_id=match_id,
    )
    return home, away


# --------------------------------------------------------------------------- #
# Finland scoring
# --------------------------------------------------------------------------- #
def _is_fin_senior(match: dict[str, Any]) -> bool:
    return str(match.get("category_id") or "") in _FIN_SENIOR_CODES


def _is_fin_cup(match: dict[str, Any]) -> bool:
    return str(match.get("category_id") or "") in _FIN_CUP_CODES


def score_finland_match(
    match: dict[str, Any],
    *,
    now: datetime,
    model: Optional[LeagueModel] = None,
    rotation_lookup: Optional[Callable[[dict[str, Any]], tuple[RotationResult, RotationResult]]] = None,
    params: Optional[PeakParams] = None,
) -> Optional[SpecialMatchScore]:
    """Score one Finnish federation match.

    With a ``model`` the statistical mismatch model drives the score; without it
    (e.g. competition data unavailable) a lightweight structural fallback is used.
    Returns ``None`` to skip the match.
    """

    status = str(match.get("status") or "").lower()
    if status in _FINISHED_STATUSES or not _is_fin_senior(match):
        return None
    if model is not None:
        return _score_finland_model(match, now=now, model=model, rotation_lookup=rotation_lookup, params=params)
    return _score_finland_structural(match, now=now, rotation_lookup=rotation_lookup)


def _score_finland_structural(
    match: dict[str, Any],
    *,
    now: datetime,
    rotation_lookup: Optional[Callable[[dict[str, Any]], tuple[RotationResult, RotationResult]]] = None,
) -> Optional[SpecialMatchScore]:
    """Lightweight fallback score (cup + cross-division + rotation), no league model."""

    home = match.get("home_team_name") or match.get("club_A_name") or "Local"
    away = match.get("away_team_name") or match.get("club_B_name") or "Visitante"
    match_id = str(match.get("match_id"))
    competition = match.get("category_name") or "Liga"
    kickoff = _parse_kickoff(match.get("date"), match.get("time"), _HELSINKI)

    factors = [PeakFactor("Base", "Liga de federación (cobertura pública escasa)", _W_BASE)]
    points = _W_BASE

    if _is_fin_cup(match):
        points += _W_CUP
        factors.append(PeakFactor("Copa", "Ronda de copa: alta chance de rotación del favorito", _W_CUP))
    else:
        points += _W_SENIOR
        factors.append(PeakFactor("Liga senior", "Categoría adulta de primer/segundo nivel", _W_SENIOR))

    home_div = str(match.get("team_A_primary_category_id") or "")
    away_div = str(match.get("team_B_primary_category_id") or "")
    if home_div and away_div and home_div != away_div:
        points += _W_MISMATCH
        factors.append(PeakFactor("Desnivel", "Equipos de distinta división: el favorito puede reservar titulares", _W_MISMATCH))

    rotation_ratio: Optional[float] = None
    if rotation_lookup is not None and _within_lineup_window(kickoff, now):
        try:
            home_rot, away_rot = rotation_lookup(match)
        except Exception:
            home_rot = away_rot = RotationResult(None)
        ratios = [r.ratio for r in (home_rot, away_rot) if r and r.ratio is not None]
        if ratios:
            rotation_ratio = min(ratios)
            if rotation_ratio < _ROT_MASSIVE:
                points += _W_ROT_MASSIVE
                factors.append(PeakFactor("B-Team confirmado", f"Regularidad {rotation_ratio:.0%}: ROTACIÓN MASIVA", _W_ROT_MASSIVE))
            elif rotation_ratio < _ROT_PARTIAL:
                points += _W_ROT_PARTIAL
                factors.append(PeakFactor("Rotación parcial", f"Regularidad {rotation_ratio:.0%}: algunos suplentes", _W_ROT_PARTIAL))
            else:
                points += _W_ROT_REGULAR
                factors.append(PeakFactor("Titulares habituales", f"Regularidad {rotation_ratio:.0%}: juega el A-Team", _W_ROT_REGULAR))

    score = max(1.0, min(10.0, points))
    is_peak, window = _peak_decision(score, rotation_ratio, kickoff, now)
    return SpecialMatchScore(
        source="🇫🇮 Finlandia",
        provider_key="finland",
        match_id=match_id,
        home=home,
        away=away,
        competition=competition,
        kickoff_arg=kickoff.astimezone(_ARG) if kickoff else None,
        kickoff_label=_arg_label(kickoff),
        score=score,
        is_peak=is_peak,
        peak_window=window,
        rotation_ratio=rotation_ratio,
        factors=factors,
        detail_command=f"/fin_match {match_id}",
    )


def _model_factors(
    breakdown: PrematchBreakdown,
    favorite_name: Optional[str],
    params: PeakParams,
) -> list[PeakFactor]:
    """Translate a model breakdown into human-readable Spanish factor lines."""

    c = breakdown.components
    fav = favorite_name or "—"
    factors: list[PeakFactor] = []
    if abs(c["supremacy"]) > 0.05:
        factors.append(PeakFactor(
            "Superioridad de gol",
            f"z de ataque/defensa {c['supremacy_z']:+.2f} → favorito {fav}",
            round(params.w_supremacy * c["supremacy"], 2),
        ))
    if abs(c["position"]) > 0.02:
        factors.append(PeakFactor(
            "Tabla",
            f"diferencia de posiciones (gate de datos {c['data_gate']:.0%})",
            round(params.w_position * c["position"], 2),
        ))
    if c["h2h_n"]:
        factors.append(PeakFactor(
            f"H2H ({c['h2h_n']})",
            f"tendencia {c['h2h']:+.2f} hacia {fav}",
            round(params.w_h2h * c["h2h"], 2),
        ))
    if c["transitivity_n"]:
        factors.append(PeakFactor(
            f"Rivales en común ({c['transitivity_n']})",
            f"señal {c['transitivity']:+.2f} hacia {fav}",
            round(params.w_transitivity * c["transitivity"], 2),
        ))
    if c["data_gate"] < 0.5:
        factors.append(PeakFactor(
            "⚠️ Pocos datos",
            f"gate {c['data_gate']:.0%}: la tabla aún no es representativa",
            0.0,
        ))
    if not factors:
        factors.append(PeakFactor("Sin desnivel claro", "los equipos lucen parejos", 0.0))
    return factors


def _score_finland_model(
    match: dict[str, Any],
    *,
    now: datetime,
    model: LeagueModel,
    rotation_lookup: Optional[Callable[[dict[str, Any]], tuple[RotationResult, RotationResult]]] = None,
    params: Optional[PeakParams] = None,
) -> SpecialMatchScore:
    """Model-driven score for a Finnish match (mismatch model + cup/rotation overlay)."""

    params = params or PeakParams()
    home = match.get("home_team_name") or match.get("club_A_name") or "Local"
    away = match.get("away_team_name") or match.get("club_B_name") or "Visitante"
    match_id = str(match.get("match_id"))
    competition = match.get("category_name") or "Liga"
    kickoff = _parse_kickoff(match.get("date"), match.get("time"), _HELSINKI)
    home_id = str(match.get("team_A_id") or "")
    away_id = str(match.get("team_B_id") or "")

    breakdown = score_prematch(home_id, away_id, model, now=now, params=params)
    favorite_name = None
    if breakdown.favorite_id == home_id:
        favorite_name = home
    elif breakdown.favorite_id == away_id:
        favorite_name = away

    score = breakdown.score
    factors = _model_factors(breakdown, favorite_name, params)

    if _is_fin_cup(match):
        if score < _CUP_FLOOR:
            score = _CUP_FLOOR
        factors.append(PeakFactor("Copa", "ronda de copa: rotación posible (mirá las alineaciones)", 0.0))

    rotation_ratio = _apply_rotation(match, now, rotation_lookup, factors)
    if rotation_ratio is not None:
        score += _rotation_delta(rotation_ratio)

    score = max(1.0, min(10.0, score))
    is_peak, window = _peak_decision(score, rotation_ratio, kickoff, now)
    return SpecialMatchScore(
        source="🇫🇮 Finlandia",
        provider_key="finland",
        match_id=match_id,
        home=home,
        away=away,
        competition=competition,
        kickoff_arg=kickoff.astimezone(_ARG) if kickoff else None,
        kickoff_label=_arg_label(kickoff),
        score=score,
        is_peak=is_peak,
        peak_window=window,
        rotation_ratio=rotation_ratio,
        factors=factors,
        detail_command=f"/fin_match {match_id}",
        favorite=favorite_name,
        edge=breakdown.edge,
    )


def _apply_rotation(
    match: dict[str, Any],
    now: datetime,
    rotation_lookup: Optional[Callable[[dict[str, Any]], tuple[RotationResult, RotationResult]]],
    factors: list[PeakFactor],
) -> Optional[float]:
    """Run the B-Team detector when near kickoff; append a factor and return the min ratio."""

    kickoff = _parse_kickoff(match.get("date"), match.get("time"), _HELSINKI)
    if rotation_lookup is None or not _within_lineup_window(kickoff, now):
        return None
    try:
        home_rot, away_rot = rotation_lookup(match)
    except Exception:
        return None
    ratios = [r.ratio for r in (home_rot, away_rot) if r and r.ratio is not None]
    if not ratios:
        return None
    ratio = min(ratios)
    if ratio < _ROT_MASSIVE:
        factors.append(PeakFactor("B-Team confirmado", f"Regularidad {ratio:.0%}: ROTACIÓN MASIVA", _ROT_DELTA_MASSIVE))
    elif ratio < _ROT_PARTIAL:
        factors.append(PeakFactor("Rotación parcial", f"Regularidad {ratio:.0%}: algunos suplentes", _ROT_DELTA_PARTIAL))
    else:
        factors.append(PeakFactor("Titulares habituales", f"Regularidad {ratio:.0%}: juega el A-Team", _ROT_DELTA_REGULAR))
    return ratio


def _rotation_delta(ratio: float) -> float:
    if ratio < _ROT_MASSIVE:
        return _ROT_DELTA_MASSIVE
    if ratio < _ROT_PARTIAL:
        return _ROT_DELTA_PARTIAL
    return _ROT_DELTA_REGULAR


# --------------------------------------------------------------------------- #
# Sweden scoring (mismatch model from aggregated results; B-Team detector stays
# Finland-only for now).
# --------------------------------------------------------------------------- #
def _is_swe_senior(competition: str) -> bool:
    name = str(competition or "").lower()
    if any(hint in name for hint in _SWE_YOUTH_HINTS):
        return False
    return any(hint in name for hint in _SWE_LEAGUE_HINTS) or any(hint in name for hint in _SWE_CUP_HINTS)


def _is_swe_cup(competition: str) -> bool:
    name = str(competition or "").lower()
    if any(hint in name for hint in _SWE_YOUTH_HINTS):
        return False
    return any(hint in name for hint in _SWE_CUP_HINTS)


def score_sweden_match(
    match: dict[str, Any],
    *,
    now: datetime,
    model: Optional[LeagueModel] = None,
    params: Optional[PeakParams] = None,
    standings_gap: Optional[float] = None,
) -> Optional[SpecialMatchScore]:
    """Score one Swedish federation match.

    With a ``model`` the mismatch model drives the score; otherwise a structural
    fallback (cup/senior + optional ``standings_gap``) is used.
    """

    status = str(match.get("status") or "").lower()
    if status in _FINISHED_STATUSES:
        return None
    competition = match.get("competition_name") or match.get("title") or "Liga"
    if not _is_swe_senior(competition):
        return None
    if model is not None:
        return _score_sweden_model(match, now=now, model=model, competition=competition, params=params)
    return _score_sweden_structural(match, now=now, competition=competition, standings_gap=standings_gap)


def _score_sweden_structural(
    match: dict[str, Any],
    *,
    now: datetime,
    competition: str,
    standings_gap: Optional[float] = None,
) -> Optional[SpecialMatchScore]:
    """Lightweight fallback score for a Swedish match (no league model)."""

    home = match.get("home") or match.get("home_team") or "Local"
    away = match.get("away") or match.get("away_team") or "Visitante"
    match_id = str(match.get("match_id") or match.get("id") or "")
    kickoff = _parse_kickoff_from_local(match.get("start_time_local"), _STOCKHOLM)

    factors = [PeakFactor("Base", "Liga de federación sueca (cobertura pública escasa)", _W_BASE)]
    points = _W_BASE
    if _is_swe_cup(competition):
        points += _W_CUP
        factors.append(PeakFactor("Copa", "Svenska Cupen: posible rotación / cruce de divisiones", _W_CUP))
    else:
        points += _W_SENIOR
        factors.append(PeakFactor("Liga senior", "Categoría adulta de la federación sueca", _W_SENIOR))

    if standings_gap is not None and standings_gap >= 0.5:
        bonus = round(_W_MISMATCH * min(1.0, standings_gap), 1)
        points += bonus
        factors.append(PeakFactor("Desnivel de tabla", f"Brecha de posiciones {standings_gap:.0%}: posible mismatch", bonus))

    score = max(1.0, min(10.0, points))
    is_peak, window = _peak_decision(score, None, kickoff, now)
    return SpecialMatchScore(
        source="🇸🇪 Suecia",
        provider_key="sweden",
        match_id=match_id,
        home=home,
        away=away,
        competition=competition,
        kickoff_arg=kickoff.astimezone(_ARG) if kickoff else None,
        kickoff_label=_arg_label(kickoff),
        score=score,
        is_peak=is_peak,
        peak_window=window,
        rotation_ratio=None,
        factors=factors,
        detail_command=f"/swe_match {match_id}" if match_id else "/swe_today",
    )


def _norm_team(name: str) -> str:
    """Normalised team key for Sweden (results feed has names, not ids)."""

    return " ".join(str(name or "").strip().lower().split())


def _score_sweden_model(
    match: dict[str, Any],
    *,
    now: datetime,
    model: LeagueModel,
    competition: str,
    params: Optional[PeakParams] = None,
) -> SpecialMatchScore:
    """Model-driven score for a Swedish match (mismatch model + cup overlay)."""

    params = params or PeakParams()
    home = match.get("home") or match.get("home_team") or "Local"
    away = match.get("away") or match.get("away_team") or "Visitante"
    match_id = str(match.get("match_id") or match.get("id") or "")
    kickoff = _parse_kickoff_from_local(match.get("start_time_local"), _STOCKHOLM)
    home_id = _norm_team(home)
    away_id = _norm_team(away)

    breakdown = score_prematch(home_id, away_id, model, now=now, params=params)
    favorite_name = None
    if breakdown.favorite_id == home_id:
        favorite_name = home
    elif breakdown.favorite_id == away_id:
        favorite_name = away

    score = breakdown.score
    factors = _model_factors(breakdown, favorite_name, params)
    if _is_swe_cup(competition):
        if score < _CUP_FLOOR:
            score = _CUP_FLOOR
        factors.append(PeakFactor("Copa", "Svenska Cupen: rotación / cruce de divisiones posible", 0.0))

    score = max(1.0, min(10.0, score))
    is_peak, window = _peak_decision(score, None, kickoff, now)
    return SpecialMatchScore(
        source="🇸🇪 Suecia",
        provider_key="sweden",
        match_id=match_id,
        home=home,
        away=away,
        competition=competition,
        kickoff_arg=kickoff.astimezone(_ARG) if kickoff else None,
        kickoff_label=_arg_label(kickoff),
        score=score,
        is_peak=is_peak,
        peak_window=window,
        rotation_ratio=None,
        factors=factors,
        detail_command=f"/swe_match {match_id}" if match_id else "/swe_today",
        favorite=favorite_name,
        edge=breakdown.edge,
    )


def _parse_kickoff_from_local(value: Optional[str], tz: ZoneInfo) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
# League-model adapters (build a peak_model.LeagueModel from the live feeds)
# --------------------------------------------------------------------------- #
def _to_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _fin_standings_to_teams(standings: list[dict[str, Any]]) -> dict[str, TeamStats]:
    teams: dict[str, TeamStats] = {}
    for row in standings or []:
        tid = str(row.get("team_id") or "")
        if not tid:
            continue
        teams[tid] = TeamStats(
            team_id=tid,
            name=str(row.get("team_name") or ""),
            position=_to_int(row.get("current_standing")),
            played=_to_int(row.get("matches_played")) or 0,
            played_home=_to_int(row.get("matches_played_home")) or 0,
            played_away=_to_int(row.get("matches_played_away")) or 0,
            gf_home=_to_int(row.get("goals_for_home")) or 0,
            ga_home=_to_int(row.get("goals_against_home")) or 0,
            gf_away=_to_int(row.get("goals_for_away")) or 0,
            ga_away=_to_int(row.get("goals_against_away")) or 0,
        )
    return teams


def _fin_matches_to_past(raw: list[dict[str, Any]]) -> list[PastMatch]:
    out: list[PastMatch] = []
    for m in raw or []:
        if m.get("status") not in ("Finished", "Played") or m.get("walkover") == 1:
            continue
        gh = _to_int(m.get("fs_A"))
        ga = _to_int(m.get("fs_B"))
        if gh is None or ga is None:
            continue
        out.append(PastMatch(
            date=str(m.get("date") or ""),
            home_id=str(m.get("team_A_id") or ""),
            away_id=str(m.get("team_B_id") or ""),
            gh=gh, ga=ga,
            match_id=str(m.get("match_id") or ""),
        ))
    return out


def _resolve_fin_previous_competition(api: Any, competition_id: str, category_id: str, now: datetime) -> Optional[str]:
    """Resolve the previous season's competition_id for the same category."""

    import re

    season_year = now.astimezone(_HELSINKI).year
    digits = re.search(r"(\d{2})$", str(competition_id))
    if digits:
        season_year = 2000 + int(digits.group(1))
    prev_season = str(season_year - 1)
    try:
        cats = api.get_categories(prev_season)
    except Exception:
        return None
    for c in cats or []:
        if str(c.get("category_id")) == str(category_id):
            cid = c.get("competition_id")
            return str(cid) if cid else None
    return None


def build_finland_model(
    api: Any,
    competition_id: str,
    category_id: str,
    *,
    now: datetime,
    include_previous: bool = True,
    group_id: str = "1",
) -> LeagueModel:
    """Build a LeagueModel for one Finnish competition (standings + matches)."""

    try:
        standings = api.get_standings(competition_id, category_id, group_id)
    except Exception:
        standings = []
    teams = _fin_standings_to_teams(standings)

    try:
        matches = _fin_matches_to_past(api.get_matches_by_league(competition_id, category_id))
    except Exception:
        matches = []

    if include_previous:
        prev_id = _resolve_fin_previous_competition(api, competition_id, category_id, now)
        if prev_id and prev_id != competition_id:
            try:
                matches += _fin_matches_to_past(api.get_matches_by_league(prev_id, category_id))
            except Exception:
                pass

    return LeagueModel(name=str(category_id), teams=teams, matches=matches)


def _enrich_fin_red_cards(api: Any, matches: list[PastMatch], home_id: str, away_id: str, cache: dict[str, dict]) -> None:
    """Set red-card flags on the H2H matches of a given pair (lazy + cached)."""

    pair = {home_id, away_id}
    for m in matches:
        if m.has_red_info or not m.match_id or {m.home_id, m.away_id} != pair:
            continue
        details = cache.get(m.match_id)
        if details is None:
            try:
                details = api.get_match_details(m.match_id) or {}
            except Exception:
                details = {}
            cache[m.match_id] = details
        team_a_id = str(details.get("team_A_id") or m.home_id)
        for b in details.get("bookings", []) or []:
            if "red" in str(b.get("card_type") or "").lower():
                if str(b.get("team_id")) == team_a_id:
                    m.home_red = True
                else:
                    m.away_red = True
        m.has_red_info = True


# Swedish senior competition_id map (2026), to resolve the model from the
# "matches today" competition name (which carries no id).
_SWE_COMP_IDS = {
    "allsvenskan": "133348",
    "superettan": "133340",
    "ettan norra": "133338",
    "ettan södra": "133339",
    "ettan sodra": "133339",
    "damallsvenskan": "133440",
    "elitettan": "133439",
}


def _resolve_swe_competition_id(competition_name: str) -> Optional[str]:
    low = str(competition_name or "").lower()
    for key, cid in _SWE_COMP_IDS.items():
        if key in low:
            return cid
    return None


def _parse_swe_score(value: Any) -> tuple[Optional[int], Optional[int]]:
    try:
        parts = str(value).replace("–", "-").split("-")
        return int(parts[0].strip()), int(parts[1].strip())
    except (TypeError, ValueError, IndexError):
        return None, None


def build_sweden_model(client: Any, competition_id: str, *, name: str = "") -> LeagueModel:
    """Build a LeagueModel for one Swedish competition.

    Standings give position/played; per-team home/away goals are aggregated from
    the season's results (the standings feed lacks goals-for/against splits).
    Teams are keyed by normalised name (the results feed has names, not ids).
    """

    teams: dict[str, TeamStats] = {}
    try:
        st = client.get_standings(competition_id)
        rows = st.get("teams") if isinstance(st, dict) else st
    except Exception:
        rows = []
    for row in rows or []:
        key = _norm_team(row.get("team"))
        if not key:
            continue
        teams[key] = TeamStats(
            team_id=key,
            name=str(row.get("team") or ""),
            position=_to_int(row.get("position")),
            played=_to_int(row.get("played")) or 0,
        )

    try:
        res = client.get_latest_results(competition_id, limit=300)
        results = res.get("matches") if isinstance(res, dict) else res
    except Exception:
        results = []

    matches: list[PastMatch] = []
    for r in results or []:
        gh, ga = _parse_swe_score(r.get("score"))
        if gh is None or ga is None:
            continue
        hk = _norm_team(r.get("home"))
        ak = _norm_team(r.get("away"))
        if not hk or not ak:
            continue
        th = teams.setdefault(hk, TeamStats(team_id=hk, name=str(r.get("home") or "")))
        ta = teams.setdefault(ak, TeamStats(team_id=ak, name=str(r.get("away") or "")))
        th.played_home += 1
        th.gf_home += gh
        th.ga_home += ga
        ta.played_away += 1
        ta.gf_away += ga
        ta.ga_away += gh
        matches.append(PastMatch(
            date=str(r.get("start_time_local") or "")[:10],
            home_id=hk, away_id=ak, gh=gh, ga=ga,
            match_id=str(r.get("match_id") or ""),
        ))

    return LeagueModel(name=name or str(competition_id), teams=teams, matches=matches)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def build_peak_scores(
    *,
    finland_api: Any = None,
    sweden_client: Any = None,
    now: Optional[datetime] = None,
    fin_date: Optional[str] = None,
    params: Optional[PeakParams] = None,
    include_previous: bool = True,
) -> list[SpecialMatchScore]:
    """Fetch today's special-league matches and return them scored & ranked.

    Matches are grouped by competition so each league model (standings + match
    history, current + previous season) is built once. Network access happens
    only through the injected ``finland_api`` / ``sweden_client`` objects.
    """

    now = now or datetime.now(tz=_ARG)
    params = params or PeakParams()
    scores: list[SpecialMatchScore] = []

    if finland_api is not None:
        fin_date = fin_date or now.astimezone(_HELSINKI).date().isoformat()
        try:
            matches = finland_api.get_matches_by_date(fin_date) or []
        except Exception:
            matches = []
        senior = [
            m for m in matches
            if str(m.get("status") or "").lower() not in _FINISHED_STATUSES and _is_fin_senior(m)
        ]

        fin_models: dict[tuple[str, str], LeagueModel] = {}
        red_cache: dict[str, dict] = {}

        def _lookup(match: dict[str, Any]) -> tuple[RotationResult, RotationResult]:
            details = finland_api.get_match_details(match.get("match_id"))
            if not details:
                return RotationResult(None), RotationResult(None)
            return rotation_lookup_for_match(finland_api, details)

        for match in senior:
            key = (str(match.get("competition_id") or ""), str(match.get("category_id") or ""))
            model = fin_models.get(key)
            if model is None:
                model = build_finland_model(finland_api, key[0], key[1], now=now, include_previous=include_previous)
                fin_models[key] = model
            try:
                _enrich_fin_red_cards(
                    finland_api, model.matches,
                    str(match.get("team_A_id") or ""), str(match.get("team_B_id") or ""),
                    red_cache,
                )
            except Exception:
                pass
            scored = score_finland_match(match, now=now, model=model, rotation_lookup=_lookup, params=params)
            if scored is not None:
                scores.append(scored)

    if sweden_client is not None:
        try:
            swe_matches = sweden_client.get_matches_today() or []
        except Exception:
            swe_matches = []
        senior = [
            m for m in swe_matches
            if str(m.get("status") or "").lower() not in _FINISHED_STATUSES
            and _is_swe_senior(m.get("competition_name") or m.get("title") or "")
        ]
        swe_models: dict[str, LeagueModel] = {}
        for match in senior:
            comp = match.get("competition_name") or match.get("title") or ""
            cid = _resolve_swe_competition_id(comp)
            model = None
            if cid:
                model = swe_models.get(cid)
                if model is None:
                    try:
                        model = build_sweden_model(sweden_client, cid, name=comp)
                    except Exception:
                        model = None
                    swe_models[cid] = model
            scored = score_sweden_match(match, now=now, model=model, params=params)
            if scored is not None:
                scores.append(scored)

    scores.sort(key=_rank_key)
    return scores


def _rank_key(score: SpecialMatchScore) -> tuple[float, datetime]:
    far_future = datetime.max.replace(tzinfo=_ARG)
    return (-score.score, score.kickoff_arg or far_future)


# --------------------------------------------------------------------------- #
# Rendering (Sportradar-style markdown digest)
# --------------------------------------------------------------------------- #
def _kickoff_label_for_display(score: "SpecialMatchScore", tz: ZoneInfo) -> str:
    """Re-render a score's kickoff in ``tz`` (kickoff_arg is an absolute instant)."""

    if score.kickoff_arg is not None:
        return score.kickoff_arg.astimezone(tz).strftime("%H:%M")
    return score.kickoff_label


def render_peak_digest(scores: list[SpecialMatchScore], *, now: Optional[datetime] = None) -> str:
    """Render the daily ranked digest as Telegram Markdown (active display tz)."""

    tz = current_display_timezone()
    now = now or datetime.now(tz=tz)
    date_label = now.astimezone(tz).strftime("%d/%m/%Y")
    header = [
        f"🎯 *Peak del día — Ligas Especiales* ({date_label})",
        "_Detección + análisis + puntaje 1–10 de Finlandia 🇫🇮 y Suecia 🇸🇪._",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if not scores:
        header.append("\n📭 No hay partidos de ligas especiales para analizar hoy.")
        return "\n".join(header)

    peaks = [s for s in scores if s.is_peak]
    rest = [s for s in scores if not s.is_peak]

    lines = list(header)
    lines.append(f"\n🔝 *{len(peaks)} oportunidad(es) destacada(s)* de {len(scores)} partido(s) analizado(s).\n")

    if peaks:
        lines.append("⭐ *PEAKS (listos para apostar / vigilar):*")
        for score in peaks:
            lines.extend(_render_entry(score, tz))
        lines.append("")

    if rest:
        lines.append("📋 *Resto del radar:*")
        for score in rest:
            lines.append(
                f"  {score.badge} *{score.score_int}/10* · `{_kickoff_label_for_display(score, tz)}` "
                f"{score.home} vs {score.away} — {score.detail_command}"
            )

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 Para el reporte completo de un partido usá su comando (ej `/fin_match <ID>`).")
    return "\n".join(lines)


def _render_entry(score: SpecialMatchScore, tz: ZoneInfo) -> list[str]:
    out = [
        f"\n{score.badge} *{score.score_int}/10* — {score.source}",
        f"🏆 {score.competition}",
        f"⚽ *{score.home} vs {score.away}* · 🕒 `{_kickoff_label_for_display(score, tz)}` ({tz_offset_label(tz)})",
    ]
    if score.favorite:
        out.append(f"⭐ Favorito: *{score.favorite}*")
    out.append(f"🎯 Peak: {score.peak_window}")
    if score.rotation_ratio is not None:
        out.append(f"🔍 Regularidad XI más baja: *{score.rotation_ratio:.0%}*")
    out.append("📊 Factores:")
    for factor in score.factors:
        sign = "+" if factor.points >= 0 else ""
        out.append(f"   • {factor.label} ({sign}{factor.points:g}): {factor.detail}")
    out.append(f"👉 Reporte: {score.detail_command}")
    return out


def render_match_report(score: SpecialMatchScore) -> str:
    """Render a single match's scored report (Sportradar-style)."""

    tz = current_display_timezone()
    lines = [
        f"{score.badge} *Reporte de Peak — {score.score_int}/10*",
        f"{score.source} · 🏆 {score.competition}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"⚽ *{score.home} vs {score.away}*",
        f"🕒 Inicio: `{_kickoff_label_for_display(score, tz)}` ({tz_offset_label(tz)})",
        f"⭐ Favorito: *{score.favorite}*" if score.favorite else "⭐ Favorito: sin desnivel claro",
        f"🎯 Peak: {'SÍ ✅' if score.is_peak else 'No ⚪️'} — {score.peak_window}",
    ]
    if score.rotation_ratio is not None:
        lines.append(f"🔍 Regularidad del XI (mín. entre equipos): *{score.rotation_ratio:.0%}*")
    lines.append("\n📊 *Desglose del puntaje:*")
    for factor in score.factors:
        sign = "+" if factor.points >= 0 else ""
        lines.append(f"   • *{factor.label}* ({sign}{factor.points:g}) — {factor.detail}")
    lines.append(f"\n👉 Detalle de alineaciones/goles: {score.detail_command}")
    return "\n".join(lines)
