"""Tests sintéticos del instrumento (NO es una corrida del experimento).

Verifica `lambda_redesign.py` contra las cláusulas del protocolo v3.1 usando
fixtures mínimos / datos sintéticos, según el orden autorizado por el director.
Cubre: leakage temporal, bins repetidos/vacíos, ramas τ=q0/q100/fallback, φ̂≤0,
goles Y≥12, reproducibilidad de semillas, conservación de partidos completos en
bloques, y una predicción de P por partido en el outer loop.

Correr:  research/.venv/bin/python research/experiments/EXP-006-development/test_lambda_redesign.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import lambda_redesign as L  # noqa: E402


def _synth(n_weeks=20, per_week=30, seed=0, bias=0.0, lam_range=(0.5, 2.5),
           dup_lam=False, underdisp=False):
    """DataFrame sintético con estructura date/week/hg/ag/lam_h/lam_a."""
    rng = np.random.default_rng(seed)
    rows = []
    start = pd.Timestamp("2025-04-07")  # un lunes
    for wk in range(n_weeks):
        d = start + pd.Timedelta(weeks=wk)
        for _ in range(per_week):
            if dup_lam:
                lh = la = 1.0
            else:
                lh = rng.uniform(*lam_range); la = rng.uniform(*lam_range)
            if underdisp:
                hg = int(round(lh)); ag = int(round(la))  # varianza ~0 < media
            else:
                hg = rng.poisson(lh + bias); ag = rng.poisson(la + bias)
            rows.append({"date": d, "hg": hg, "ag": ag, "lam_h": lh, "lam_a": la,
                         "league": "X", "country": "FIN"})
    df = pd.DataFrame(rows)
    df["week"] = L.week_label(df["date"])
    return df


CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn)); return fn
    return deco


@check("Y>=12 usa bin de cola: PMF suma 1 y log-loss finito")
def t_tail():
    p = L._side_pmf_full(1.3, None)
    assert abs(p.sum() - 1.0) < 1e-9, p.sum()
    df = pd.DataFrame({"hg": [15], "ag": [0], "lam_h": [1.3], "lam_a": [1.0],
                       "week": ["w"]})
    ll = L.score_logloss_vec(df, 0.0, 0.0)
    assert np.isfinite(ll[0]) and ll[0] > 0, ll
    # goles 12 y 15 puntúan igual (ambos caen en el bin de cola)
    df2 = df.copy(); df2["hg"] = 12
    assert np.isclose(L.score_logloss_vec(df, 0, 0)[0], L.score_logloss_vec(df2, 0, 0)[0])


@check("φ̂≤0 (subdispersión) -> estimate_phi=0 y NB==Poisson")
def t_phi_neg():
    df = _synth(underdisp=True, seed=1)
    phi = L.estimate_phi(df)
    assert phi == 0.0, phi
    a = L._side_logpmf_nb(np.array([0, 1, 2]), np.array([1.0, 1.5, 2.0]), 0.0)
    b = L._side_logpmf_poisson(np.array([0, 1, 2]), np.array([1.0, 1.5, 2.0]))
    assert np.allclose(a, b)


@check("τ: bias≈0 en todo -> τ=q0 (mínimo)")
def t_tau_q0():
    df = _synth(bias=0.0, seed=2, n_weeks=25, per_week=40)
    lam_min = L.to_sides(df)["lam"].min()
    tau, fb = L.tau_rule(df, seed=41000)
    assert not fb and np.isclose(tau, lam_min, atol=1e-6), (tau, lam_min, fb)


@check("τ: bias>0 en todo -> τ=q100 (máximo)")
def t_tau_q100():
    df = _synth(bias=0.8, seed=3, n_weeks=25, per_week=40)  # goles sistemáticamente > λ
    lam_max = L.to_sides(df)["lam"].max()
    tau, fb = L.tau_rule(df, seed=41000)
    assert not fb and np.isclose(tau, lam_max, atol=1e-6), (tau, lam_max, fb)


@check("τ decisión: todos incluyen 0 -> q0 (borde izquierdo del primer bin)")
def t_tau_decide_q0():
    borders = np.array([0.5, 1.0, 1.5, 2.0])
    flags = [(True, True, False), (True, True, True), (True, True, True)]
    tau, fb = L._tau_decide(borders, flags, median_lam=1.2)
    assert not fb and tau == 0.5, (tau, fb)


@check("τ decisión: ninguno incluye 0 y todos positivos -> q100")
def t_tau_decide_q100():
    borders = np.array([0.5, 1.0, 1.5, 2.0])
    flags = [(True, False, True), (True, False, True), (True, False, True)]
    tau, fb = L._tau_decide(borders, flags, median_lam=1.2)
    assert not fb and tau == 2.0, (tau, fb)


@check("τ decisión: signos mezclados sin IC que incluya 0 -> fallback=mediana")
def t_tau_decide_fallback():
    borders = np.array([0.5, 1.0, 1.5, 2.0])
    flags = [(True, False, False), (False, None, None), (True, False, True)]
    tau, fb = L._tau_decide(borders, flags, median_lam=1.23)
    assert fb and tau == 1.23, (tau, fb)


@check("bins repetidos/colapsados -> borders<2 -> fallback mediana")
def t_dup_bins():
    df = _synth(dup_lam=True, seed=4)  # todos lam=1.0
    tau, fb = L.tau_rule(df, seed=41000)
    assert fb and np.isclose(tau, 1.0), (tau, fb)


@check("reproducibilidad de semillas (τ y bootstrap)")
def t_seed_repro():
    df = _synth(seed=5)
    assert L.tau_rule(df, 41000) == L.tau_rule(df, 41000)
    v = np.random.default_rng(0).normal(size=500); w = np.repeat(np.arange(20), 25)
    assert L.week_block_mean_ci(v, w, 7) == L.week_block_mean_ci(v, w, 7)
    # semillas distintas -> IC distinto (con alta probabilidad)
    assert L.week_block_mean_ci(v, w, 7) != L.week_block_mean_ci(v, w, 8)


@check("bloque-semana conserva ambos lados del partido")
def t_block_sides():
    df = _synth(seed=6, n_weeks=3, per_week=5)
    sides = L.to_sides(df)
    # cada partido aporta 2 filas con la MISMA semana
    assert len(sides) == 2 * len(df)
    per_week = sides.groupby("week").size()
    assert (per_week == 2 * df.groupby("week").size()).all()


@check("outer loop: exactamente una predicción de P por partido")
def t_one_pred_per_match():
    df = _synth(seed=7, n_weeks=30, per_week=40, lam_range=(0.6, 2.4))
    oos_m, oos_s, choices = L.run_outer(df, test_start="2025-06-02", test_end="2025-12-01")
    test_mask = (df["date"] >= "2025-06-02") & (df["date"] < "2025-12-01")
    outer_weeks = [w for w in sorted(df.loc[test_mask, "week"].unique())
                   if len(df[df["week"] < w]) >= L.MIN_OUTER_TRAIN]
    n_expected = int(((df["week"].isin(outer_weeks)) & test_mask).sum())
    assert len(oos_m) == n_expected, (len(oos_m), n_expected)
    assert len(oos_s) == 2 * n_expected, (len(oos_s), 2 * n_expected)   # dos lados
    assert len(choices) == len(outer_weeks)


@check("sin leakage temporal: alterar la última semana no cambia folds previos")
def t_no_leakage():
    df = _synth(seed=8, n_weeks=32, per_week=40, lam_range=(0.6, 2.4))
    _, _, ch1 = L.run_outer(df, test_start="2025-06-02", test_end="2025-12-01")
    df2 = df.copy()
    last_week = sorted(df2["week"].unique())[-1]
    m = df2["week"] == last_week
    df2.loc[m, "hg"] = 9; df2.loc[m, "ag"] = 9   # outcomes futuros corruptos
    _, _, ch2 = L.run_outer(df2, test_start="2025-06-02", test_end="2025-12-01")
    # todas las decisiones de folds salvo (a lo sumo) la última deben coincidir
    assert ch1[:-1] == ch2[:len(ch1) - 1], (ch1, ch2)


@check("constantes congeladas coinciden con el protocolo v3.1")
def t_constants():
    assert L.MAXG == 12
    assert L.EPS0 == 0.02 and L.EPS_LAMBDA == 0.05
    assert L.MIN_INNER_TRAIN == 150 and L.MIN_INNER_WEEKS == 4
    assert L.MIN_OUTER_TRAIN == 300 and L.N_BOOT == 4000
    assert L.SELECTION_STABILITY == 0.60
    assert L.TAU0_GRID == (0.9, 1.2, 1.5) and L.A0 == 0.5
    # seed_tau determinista: 41000 + 1000·outer + inner
    assert L.seed_tau(0, 0) == 41000
    assert L.seed_tau(3, 7) == 44007
    assert L.seed_tau(999, 999) == 41000 + 1000 * 999 + 999


@check("week_label usa W-SUN (lunes-domingo): un lunes y su domingo caen en la misma semana")
def t_week_sun():
    s = pd.Series(pd.to_datetime(["2025-06-02", "2025-06-08", "2025-06-09"]))  # lun, dom, lun sig
    w = L.week_label(s).tolist()
    assert w[0] == w[1] and w[1] != w[2], w


def main():
    ok = 0
    for name, fn in CHECKS:
        try:
            fn(); print(f"PASS  {name}"); ok += 1
        except AssertionError as e:
            print(f"FAIL  {name}\n      {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {name}\n      {type(e).__name__}: {e}")
    print(f"\n{ok}/{len(CHECKS)} tests OK")
    sys.exit(0 if ok == len(CHECKS) else 1)


if __name__ == "__main__":
    main()
