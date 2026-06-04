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

_HELSINKI = ZoneInfo("Europe/Helsinki")
_STOCKHOLM = ZoneInfo("Europe/Stockholm")
_ARG = ZoneInfo("America/Argentina/Buenos_Aires")

# Finland standardized category codes (mirrors bot.handlers /fin_today).
_FIN_SENIOR_CODES = {"VL", "M1L", "M1", "M2", "NL", "MSC", "NSC", "LC", "M1LCUP"}
_FIN_CUP_CODES = {"MSC", "NSC", "LC", "M1LCUP"}
_FIN_SENIOR_NAME_HINTS = (
    "veikkausliiga", "ykkösliiga", "ykkönen", "ykkös", "kakkonen",
    "kansallinen", "naisten", "suomen cup", "liigacup",
)
_CUP_NAME_HINTS = ("cup", "copa", "cupen", "liigacup")
_NOISE_HINTS = ("futsal", "beach", "ranta", "hiekka")

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
def _is_fin_noise(match: dict[str, Any]) -> bool:
    blob = " ".join(
        str(match.get(k) or "").lower()
        for k in ("category_name", "competition_name", "sport_name")
    )
    return any(term in blob for term in _NOISE_HINTS)


def _is_fin_senior(match: dict[str, Any]) -> bool:
    if _is_fin_noise(match):
        return False
    code = str(match.get("category_id") or "")
    if code in _FIN_SENIOR_CODES:
        return True
    name = str(match.get("category_name") or "").lower()
    return any(hint in name for hint in _FIN_SENIOR_NAME_HINTS)


def _is_fin_cup(match: dict[str, Any]) -> bool:
    code = str(match.get("category_id") or "")
    if code in _FIN_CUP_CODES:
        return True
    name = str(match.get("category_name") or "").lower()
    return any(hint in name for hint in _CUP_NAME_HINTS)


def score_finland_match(
    match: dict[str, Any],
    *,
    now: datetime,
    rotation_lookup: Optional[Callable[[dict[str, Any]], tuple[RotationResult, RotationResult]]] = None,
) -> Optional[SpecialMatchScore]:
    """Score one Finnish federation match. Returns ``None`` to skip it."""

    status = str(match.get("status") or "").lower()
    if status in _FINISHED_STATUSES:
        return None
    if not _is_fin_senior(match):
        return None

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


# --------------------------------------------------------------------------- #
# Sweden scoring (no cup rounds in the tracked set => lighter, league-mismatch
# driven; the B-Team detector stays Finland-only for now).
# --------------------------------------------------------------------------- #
def score_sweden_match(
    match: dict[str, Any],
    *,
    now: datetime,
    standings_gap: Optional[float] = None,
) -> Optional[SpecialMatchScore]:
    """Score one Swedish federation match.

    ``standings_gap`` (0..1) is the relative table distance between the two
    sides when known; a wide gap flags a mismatch worth watching.
    """

    status = str(match.get("status") or "").lower()
    if status in _FINISHED_STATUSES:
        return None

    home = match.get("home") or match.get("home_team") or "Local"
    away = match.get("away") or match.get("away_team") or "Visitante"
    match_id = str(match.get("match_id") or match.get("id") or "")
    competition = match.get("competition_name") or match.get("title") or "Liga"
    kickoff = _parse_kickoff_from_local(match.get("start_time_local"), _STOCKHOLM)

    factors = [PeakFactor("Base", "Liga de federación sueca (cobertura pública escasa)", _W_BASE)]
    points = _W_BASE + _W_SENIOR
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
# Orchestration
# --------------------------------------------------------------------------- #
def build_peak_scores(
    *,
    finland_api: Any = None,
    sweden_client: Any = None,
    now: Optional[datetime] = None,
    fin_date: Optional[str] = None,
) -> list[SpecialMatchScore]:
    """Fetch today's special-league matches and return them scored & ranked.

    Network access happens only through the injected ``finland_api`` /
    ``sweden_client`` objects, so this stays unit-testable with fakes.
    """

    now = now or datetime.now(tz=_ARG)
    scores: list[SpecialMatchScore] = []

    if finland_api is not None:
        fin_date = fin_date or now.astimezone(_HELSINKI).date().isoformat()
        try:
            matches = finland_api.get_matches_by_date(fin_date) or []
        except Exception:
            matches = []

        def _lookup(match: dict[str, Any]) -> tuple[RotationResult, RotationResult]:
            details = finland_api.get_match_details(match.get("match_id"))
            if not details:
                return RotationResult(None), RotationResult(None)
            return rotation_lookup_for_match(finland_api, details)

        for match in matches:
            scored = score_finland_match(match, now=now, rotation_lookup=_lookup)
            if scored is not None:
                scores.append(scored)

    if sweden_client is not None:
        try:
            swe_matches = sweden_client.get_matches_today() or []
        except Exception:
            swe_matches = []
        for match in swe_matches:
            scored = score_sweden_match(match, now=now)
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
def render_peak_digest(scores: list[SpecialMatchScore], *, now: Optional[datetime] = None) -> str:
    """Render the daily ranked digest as Telegram Markdown."""

    now = now or datetime.now(tz=_ARG)
    date_label = now.astimezone(_ARG).strftime("%d/%m/%Y")
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
            lines.extend(_render_entry(score))
        lines.append("")

    if rest:
        lines.append("📋 *Resto del radar:*")
        for score in rest:
            lines.append(
                f"  {score.badge} *{score.score_int}/10* · `{score.kickoff_label}` "
                f"{score.home} vs {score.away} — {score.detail_command}"
            )

    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 Para el reporte completo de un partido usá su comando (ej `/fin_match <ID>`).")
    return "\n".join(lines)


def _render_entry(score: SpecialMatchScore) -> list[str]:
    out = [
        f"\n{score.badge} *{score.score_int}/10* — {score.source}",
        f"🏆 {score.competition}",
        f"⚽ *{score.home} vs {score.away}* · 🕒 `{score.kickoff_label}` (ARG)",
        f"🎯 Peak: {score.peak_window}",
    ]
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

    lines = [
        f"{score.badge} *Reporte de Peak — {score.score_int}/10*",
        f"{score.source} · 🏆 {score.competition}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"⚽ *{score.home} vs {score.away}*",
        f"🕒 Inicio: `{score.kickoff_label}` (ARG)",
        f"🎯 Peak: {'SÍ ✅' if score.is_peak else 'no ⚪️'} — {score.peak_window}",
    ]
    if score.rotation_ratio is not None:
        lines.append(f"🔍 Regularidad del XI (mín. entre equipos): *{score.rotation_ratio:.0%}*")
    lines.append("\n📊 *Desglose del puntaje:*")
    for factor in score.factors:
        sign = "+" if factor.points >= 0 else ""
        lines.append(f"   • *{factor.label}* ({sign}{factor.points:g}) — {factor.detail}")
    lines.append(f"\n👉 Detalle de alineaciones/goles: {score.detail_command}")
    return "\n".join(lines)
