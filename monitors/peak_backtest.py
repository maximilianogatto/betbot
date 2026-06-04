"""Retrospective, point-in-time backtest of the pre-match peak model.

Walks each competition's finished matches chronologically and, for every match,
rebuilds a :class:`~monitors.peak_model.LeagueModel` using ONLY the matches
played *before* that match's date (no leakage — even the table position is
recomputed from prior points). It then scores the fixture and compares the
predicted favourite / mismatch magnitude against what actually happened.

Outputs a calibration table (favourite-win rate by score bucket), proper scores
(Brier vs a base-rate baseline) and a per-factor signal diagnostic (which
component actually correlates with the realised result). This is the evidence
needed before investing in a heavier Bayesian / Kalman model.

The pure core (``build_model_at`` / ``run_backtest_on_matches`` / ``summarize``)
takes ``PastMatch`` lists, so it is unit-testable without network. ``main`` adds
a thin fetch layer over the Finland / Sweden feeds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from monitors.peak_model import (
    LeagueModel,
    PastMatch,
    PeakParams,
    TeamStats,
    score_prematch,
)

_FACTOR_KEYS = ("supremacy", "position", "h2h", "transitivity")


# --------------------------------------------------------------------------- #
# Point-in-time model reconstruction
# --------------------------------------------------------------------------- #
def _assign_positions(teams: dict[str, TeamStats], prior: list[PastMatch]) -> None:
    """Derive a table position per team from points (3/1/0) of prior matches."""

    pts = {tid: 0 for tid in teams}
    gd = {tid: 0 for tid in teams}
    for m in prior:
        gd[m.home_id] += m.gh - m.ga
        gd[m.away_id] += m.ga - m.gh
        if m.gh > m.ga:
            pts[m.home_id] += 3
        elif m.gh < m.ga:
            pts[m.away_id] += 3
        else:
            pts[m.home_id] += 1
            pts[m.away_id] += 1
    order = sorted(teams, key=lambda t: (-pts[t], -gd[t]))
    for i, tid in enumerate(order, start=1):
        teams[tid].position = i


def build_model_at(matches: list[PastMatch], cutoff_date: str, *, name: str = "") -> LeagueModel:
    """Build a LeagueModel from only the matches strictly *before* ``cutoff_date``."""

    prior = [m for m in matches if m.date and str(m.date) < str(cutoff_date)]
    teams: dict[str, TeamStats] = {}
    for m in prior:
        th = teams.setdefault(m.home_id, TeamStats(team_id=m.home_id))
        ta = teams.setdefault(m.away_id, TeamStats(team_id=m.away_id))
        th.played_home += 1
        th.gf_home += m.gh
        th.ga_home += m.ga
        ta.played_away += 1
        ta.gf_away += m.ga
        ta.ga_away += m.gh
    for t in teams.values():
        t.played = t.played_home + t.played_away
    _assign_positions(teams, prior)
    return LeagueModel(name=name, teams=teams, matches=prior)


# --------------------------------------------------------------------------- #
# Backtest rows
# --------------------------------------------------------------------------- #
@dataclass
class BacktestRow:
    date: str
    home_id: str
    away_id: str
    score: int
    magnitude: float
    edge: float
    favorite_id: Optional[str]
    home_margin: int  # gh - ga (actual)
    fav_result: Optional[str]  # "win" | "draw" | "loss" | None (no favourite)
    components: dict


def _parse_date(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def run_backtest_on_matches(
    matches: list[PastMatch],
    *,
    params: Optional[PeakParams] = None,
    min_history: int = 3,
) -> list[BacktestRow]:
    """Score every match point-in-time and pair it with its actual outcome."""

    params = params or PeakParams()
    rows: list[BacktestRow] = []
    ordered = sorted([m for m in matches if m.date], key=lambda m: str(m.date))
    for m in ordered:
        model = build_model_at(matches, m.date)
        th = model.teams.get(m.home_id)
        ta = model.teams.get(m.away_id)
        if th is None or ta is None or min(th.played, ta.played) < min_history:
            continue
        now = _parse_date(m.date) or datetime.now(tz=timezone.utc)
        bd = score_prematch(m.home_id, m.away_id, model, now=now, params=params)

        margin = m.gh - m.ga
        fav_result: Optional[str]
        if bd.favorite_id is None:
            fav_result = None
        else:
            fav_margin = margin if bd.favorite_id == m.home_id else -margin
            fav_result = "win" if fav_margin > 0 else "draw" if fav_margin == 0 else "loss"

        rows.append(BacktestRow(
            date=str(m.date), home_id=m.home_id, away_id=m.away_id,
            score=bd.score_int, magnitude=bd.magnitude, edge=bd.edge,
            favorite_id=bd.favorite_id, home_margin=margin,
            fav_result=fav_result, components=bd.components,
        ))
    return rows


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


@dataclass
class BacktestSummary:
    n_total: int
    n_with_favorite: int
    favorite_win_rate: Optional[float]
    favorite_draw_rate: Optional[float]
    calibration: dict[int, tuple[int, float]]  # score -> (n, win_rate)
    brier: Optional[float]
    brier_baseline: Optional[float]
    factor_corr: dict[str, Optional[float]]  # component -> pearson with home_margin
    magnitude_corr_absmargin: Optional[float]
    notes: list[str] = field(default_factory=list)


def summarize(rows: list[BacktestRow]) -> BacktestSummary:
    n_total = len(rows)
    with_fav = [r for r in rows if r.favorite_id is not None and r.fav_result is not None]
    n_fav = len(with_fav)

    win_rate = sum(1 for r in with_fav if r.fav_result == "win") / n_fav if n_fav else None
    draw_rate = sum(1 for r in with_fav if r.fav_result == "draw") / n_fav if n_fav else None

    # Calibration by score bucket.
    calibration: dict[int, tuple[int, float]] = {}
    by_bucket: dict[int, list[BacktestRow]] = {}
    for r in with_fav:
        by_bucket.setdefault(r.score, []).append(r)
    for bucket, items in sorted(by_bucket.items()):
        wins = sum(1 for r in items if r.fav_result == "win")
        calibration[bucket] = (len(items), wins / len(items))

    # Brier: model prob(favourite wins) ~ 0.5 + 0.5*magnitude vs outcome.
    brier = None
    brier_baseline = None
    if n_fav:
        outcomes = [1.0 if r.fav_result == "win" else 0.0 for r in with_fav]
        probs = [0.5 + 0.5 * r.magnitude for r in with_fav]
        brier = sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / n_fav
        base = sum(outcomes) / n_fav
        brier_baseline = sum((base - o) ** 2 for o in outcomes) / n_fav

    # Per-factor signal: correlation of each (home-oriented) component with the
    # realised home goal margin. Higher |r| => that factor carries signal.
    factor_corr: dict[str, Optional[float]] = {}
    margins = [float(r.home_margin) for r in rows]
    for key in _FACTOR_KEYS:
        xs = [float(r.components.get(key, 0.0)) for r in rows]
        factor_corr[key] = _pearson(xs, margins)
    mag_corr = _pearson([r.magnitude for r in rows], [abs(float(r.home_margin)) for r in rows])

    notes = []
    if n_fav < 50:
        notes.append("Muestra chica (<50): leé los números como indicativos, no concluyentes.")
    return BacktestSummary(
        n_total=n_total, n_with_favorite=n_fav,
        favorite_win_rate=win_rate, favorite_draw_rate=draw_rate,
        calibration=calibration, brier=brier, brier_baseline=brier_baseline,
        factor_corr=factor_corr, magnitude_corr_absmargin=mag_corr, notes=notes,
    )


def render_report(summary: BacktestSummary, *, title: str = "Backtest del peak detector") -> str:
    def pct(x: Optional[float]) -> str:
        return f"{x:.0%}" if x is not None else "n/a"

    def num(x: Optional[float]) -> str:
        return f"{x:+.3f}" if x is not None else "n/a"

    lines = [
        f"📐 {title}",
        "=" * 48,
        f"Partidos evaluados: {summary.n_total} (con favorito: {summary.n_with_favorite})",
        f"Tasa de acierto del favorito: {pct(summary.favorite_win_rate)} "
        f"(empates: {pct(summary.favorite_draw_rate)})",
    ]
    if summary.brier is not None:
        better = "MEJOR" if (summary.brier_baseline or 1) > summary.brier else "PEOR/IGUAL"
        lines.append(
            f"Brier: {summary.brier:.3f} vs baseline tasa-base {summary.brier_baseline:.3f} → modelo {better}"
        )
    lines.append("")
    lines.append("Calibración (acierto del favorito por bucket de score):")
    lines.append("  score │   n  │ acierto")
    lines.append("  ──────┼──────┼────────")
    for bucket in sorted(summary.calibration):
        n, wr = summary.calibration[bucket]
        bar = "█" * int(round(wr * 10))
        lines.append(f"   {bucket:>2}/10│ {n:>4} │ {wr:5.0%} {bar}")
    lines.append("")
    lines.append("Señal por factor (correlación con el margen real del local):")
    for key in _FACTOR_KEYS:
        lines.append(f"  • {key:<13} r = {num(summary.factor_corr.get(key))}")
    lines.append(f"  • magnitud↔|margen|  r = {num(summary.magnitude_corr_absmargin)}")
    for note in summary.notes:
        lines.append(f"\n⚠️ {note}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Fetch layer + CLI
# --------------------------------------------------------------------------- #
def finland_matches(api, competition_id: str, category_id: str, *, now: datetime, include_previous: bool = True) -> list[PastMatch]:
    from monitors.special_peak import _fin_matches_to_past, _resolve_fin_previous_competition

    out = _fin_matches_to_past(api.get_matches_by_league(competition_id, category_id))
    if include_previous:
        prev = _resolve_fin_previous_competition(api, competition_id, category_id, now)
        if prev and prev != competition_id:
            try:
                out += _fin_matches_to_past(api.get_matches_by_league(prev, category_id))
            except Exception:
                pass
    return out


def sweden_matches(client, competition_id: str) -> list[PastMatch]:
    from monitors.special_peak import _norm_team, _parse_swe_score

    res = client.get_latest_results(competition_id, limit=300)
    results = res.get("matches") if isinstance(res, dict) else res
    out: list[PastMatch] = []
    for r in results or []:
        gh, ga = _parse_swe_score(r.get("score"))
        if gh is None or ga is None:
            continue
        out.append(PastMatch(
            date=str(r.get("start_time_local") or "")[:10],
            home_id=_norm_team(r.get("home")), away_id=_norm_team(r.get("away")),
            gh=gh, ga=ga, match_id=str(r.get("match_id") or ""),
        ))
    return out


def main() -> None:  # pragma: no cover - thin network driver
    from zoneinfo import ZoneInfo

    from monitors.special_peak import _FIN_LEAGUE_CODES, _SWE_COMP_IDS
    from stats_providers.palloliitto.api_client import PalloliittoAPI
    from stats_providers.svenskfotboll_http.client import SvenskfotbollHTTPClient

    now = datetime.now(tz=ZoneInfo("America/Argentina/Buenos_Aires"))
    pooled: list[PastMatch] = []
    per_comp: list[tuple[str, int]] = []

    fa = PalloliittoAPI()
    try:
        cats = {str(c.get("category_id")): str(c.get("competition_id")) for c in (fa.get_categories("2026") or [])}
        for code in sorted(_FIN_LEAGUE_CODES):
            comp = cats.get(code)
            if not comp:
                continue
            ms = finland_matches(fa, comp, code, now=now)
            if ms:
                pooled += ms
                per_comp.append((f"FIN {code}", len(ms)))
    finally:
        fa.close()

    sc = SvenskfotbollHTTPClient()
    try:
        seen_cids: set[str] = set()
        for name, cid in _SWE_COMP_IDS.items():
            if cid in seen_cids:  # several name aliases map to one id
                continue
            seen_cids.add(cid)
            try:
                ms = sweden_matches(sc, cid)
            except Exception:
                ms = []
            if ms:
                pooled += ms
                per_comp.append((f"SWE {name}", len(ms)))
    finally:
        sc.close()

    rows = run_backtest_on_matches(pooled)
    summary = summarize(rows)
    print(render_report(summary, title="Backtest peak detector — Fin+Suecia (actual+previa)"))
    print("\nPartidos por competición (finished, pre-dedupe):")
    for label, n in per_comp:
        print(f"  {label}: {n}")


if __name__ == "__main__":  # pragma: no cover
    main()
