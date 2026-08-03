"""EXP-006.2 — Rediseño de la corrección de λ, implementación del protocolo v3.1.

Implementa EXACTAMENTE `LAMBDA-REDESIGN-PROTOCOL.md` (v3.1, Opción A: el candidato
es el procedimiento adaptativo P). NO se ejecuta la corrida real hasta que los
tests sintéticos (`test_lambda_redesign.py`) pasen. Ninguna regla depende de
mirar los resultados; las funciones son puras y deterministas dadas las semillas.

Columnas de trabajo (una fila = un partido): date, week, league, country, hg, ag,
lam_h, lam_a  (lam = intensidad DC-OOS; el partido es la unidad estadística).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import nbinom, poisson

MAXG = 12
EPS0 = 0.02          # margen equivalencia P(0)
EPS_LAMBDA = 0.05    # margen equivalencia sesgo Y-λ' (goles)
MIN_INNER_TRAIN = 150
MIN_INNER_WEEKS = 4
MIN_OUTER_TRAIN = 300
N_BOOT = 4000
SELECTION_STABILITY = 0.60
TAU0_GRID = (0.9, 1.2, 1.5)
A0 = 0.5
FAMILIES = ("S_full", "S_tau_fixed", "S_poisson")


# ----------------------------------------------------------------- básicos

def week_label(dates: pd.Series) -> pd.Series:
    return pd.to_datetime(dates).dt.to_period("W-SUN").astype(str)


def contract(lam: np.ndarray, a: float, tau: float) -> np.ndarray:
    lam = np.maximum(np.asarray(lam, dtype=float), 1e-9)
    if a <= 0 or tau <= 0:
        return lam.copy()
    low = lam < tau
    out = lam.copy()
    out[low] = np.exp((1 - a) * np.log(lam[low]) + a * np.log(tau))
    return out


def _side_logpmf_poisson(y: np.ndarray, lam: np.ndarray) -> np.ndarray:
    """log P(Y=y | λ) con bin de cola en 12: p_12 = P(Y>=12)."""
    y = np.asarray(y); lam = np.asarray(lam, dtype=float)
    yc = np.minimum(y, MAXG)
    tail = np.log(np.clip(poisson.sf(MAXG - 1, lam), 1e-300, 1.0))  # P(Y>=12)
    body = poisson.logpmf(yc, lam)
    return np.where(yc >= MAXG, tail, body)


def _side_logpmf_nb(y: np.ndarray, lam: np.ndarray, phi: float) -> np.ndarray:
    if phi <= 0:
        return _side_logpmf_poisson(y, lam)
    y = np.asarray(y); lam = np.asarray(lam, dtype=float)
    yc = np.minimum(y, MAXG)
    r = 1.0 / phi
    p = r / (r + lam)
    tail = np.log(np.clip(nbinom.sf(MAXG - 1, r, p), 1e-300, 1.0))
    body = nbinom.logpmf(yc, r, p)
    return np.where(yc >= MAXG, tail, body)


def score_logloss_vec(df: pd.DataFrame, a: float, tau: float,
                      phi: float | None = None) -> np.ndarray:
    """log-loss de marcador por partido (vectorizado; usa cola en 12)."""
    lh = contract(df["lam_h"].to_numpy(), a, tau)
    la = contract(df["lam_a"].to_numpy(), a, tau)
    if phi is None:
        lp = (_side_logpmf_poisson(df["hg"].to_numpy(), lh)
              + _side_logpmf_poisson(df["ag"].to_numpy(), la))
    else:
        lp = (_side_logpmf_nb(df["hg"].to_numpy(), lh, phi)
              + _side_logpmf_nb(df["ag"].to_numpy(), la, phi))
    return -np.clip(lp, np.log(1e-12), 0.0)


def _side_pmf_full(lam: float, phi: float | None) -> np.ndarray:
    ks = np.arange(MAXG + 1)
    if phi is None or phi <= 0:
        p = poisson.pmf(ks, lam)
        p[MAXG] = poisson.sf(MAXG - 1, lam)
    else:
        r = 1.0 / phi
        pp = r / (r + lam)
        p = nbinom.pmf(ks, r, pp)
        p[MAXG] = nbinom.sf(MAXG - 1, r, pp)
    return p


def rps_1x2_vec(df: pd.DataFrame, a: float, tau: float,
                phi: float | None = None) -> np.ndarray:
    lh = contract(df["lam_h"].to_numpy(), a, tau)
    la = contract(df["lam_a"].to_numpy(), a, tau)
    hg = df["hg"].to_numpy(); ag = df["ag"].to_numpy()
    out = np.empty(len(df))
    for i in range(len(df)):
        ph = _side_pmf_full(lh[i], phi); pa = _side_pmf_full(la[i], phi)
        m = np.outer(ph, pa)
        p_home = np.tril(m, -1).sum(); p_draw = np.trace(m); p_away = np.triu(m, 1).sum()
        p = np.array([p_home, p_draw, p_away]); p = p / p.sum()
        res = 0 if hg[i] > ag[i] else (2 if ag[i] > hg[i] else 1)
        y = np.zeros(3); y[res] = 1
        out[i] = ((np.cumsum(p) - np.cumsum(y)) ** 2).sum() / 2
    return out


def to_sides(df: pd.DataFrame) -> pd.DataFrame:
    """Long por lado: y, lam, week (ambos lados del partido en el mismo week)."""
    h = pd.DataFrame({"y": df["hg"], "lam": df["lam_h"], "week": df["week"]})
    a = pd.DataFrame({"y": df["ag"], "lam": df["lam_a"], "week": df["week"]})
    return pd.concat([h, a], ignore_index=True)


# ------------------------------------------------- bootstrap por bloque-semana

def week_block_mean_ci(values: np.ndarray, weeks: np.ndarray, seed: int,
                       n_boot: int = N_BOOT) -> tuple[float, float, float]:
    """IC de la media remuestreando semanas ENTERAS (bloque). Vectorizado:
    la media bootstrap = Σ suma_semana[elegidas] / Σ tamaño_semana[elegidas]."""
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return float("nan"), float("nan"), float("nan")
    # sumas y tamaños por semana (orden estable)
    order = np.argsort(weeks, kind="stable")
    w_sorted = np.asarray(weeks)[order]
    v_sorted = values[order]
    _, starts = np.unique(w_sorted, return_index=True)
    sums = np.add.reduceat(v_sorted, starts)
    sizes = np.diff(np.append(starts, len(v_sorted)))
    nb = len(sums)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, nb, size=(n_boot, nb))
    boot = sums[idx].sum(axis=1) / sizes[idx].sum(axis=1)
    return float(values.mean()), float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))


# ----------------------------------------------------------------- regla de τ

def _tau_decide(borders: np.ndarray, flags: list, median_lam: float) -> tuple[float, bool]:
    """Lógica pura de τ dada, por bin, (nonempty, includes_zero, sign_pos).

    Separada del bootstrap para poder testear las tres ramas de forma
    determinista (q0 / q100 / fallback). Protocolo §2.3.
    """
    n_bins = len(borders) - 1
    for k in range(n_bins):
        ne, inc0, _ = flags[k]
        if ne and inc0:
            return float(borders[k]), False        # primer bin con IC que incluye 0
    pos = [sp for (ne, _, sp) in flags if ne]
    if pos and all(pos):
        return float(borders[-1]), False           # sesgo>0 en todo → τ=q100
    return float(median_lam), True                 # degenerado → fallback mediana


def _tau_bins(train: pd.DataFrame, seed: int):
    """Devuelve (borders, flags, median_lam). flags[k]=(nonempty,includes_zero,sign_pos)."""
    sides = to_sides(train)
    lam = sides["lam"].to_numpy(dtype=float)
    y = sides["y"].to_numpy(dtype=float)
    weeks = sides["week"].to_numpy()
    median_lam = float(np.median(lam))
    borders = np.unique(np.quantile(lam, np.linspace(0, 1, 11)))  # q0=min…q100=max, sin dups
    if len(borders) < 2:
        return borders, None, median_lam
    n_bins = len(borders) - 1
    flags = []
    for k in range(n_bins):
        lo, hi = borders[k], borders[k + 1]
        mask = (lam >= lo) & (lam <= hi) if k == n_bins - 1 else (lam >= lo) & (lam < hi)
        if mask.sum() == 0:
            flags.append((False, None, None)); continue
        m, clo, chi = week_block_mean_ci(y[mask] - lam[mask], weeks[mask], seed)
        flags.append((True, bool(clo <= 0 <= chi), bool(m > 0)))
    return borders, flags, median_lam


def tau_rule(train: pd.DataFrame, seed: int) -> tuple[float, bool]:
    """τ por bins disjuntos de λ del CONJUNTO RECIBIDO por el fit (protocolo §2.3)."""
    borders, flags, median_lam = _tau_bins(train, seed)
    if flags is None:                               # <2 bordes: colapso
        return median_lam, True
    return _tau_decide(borders, flags, median_lam)


# ----------------------------------------------------------------- fits

def fit_s_full(train: pd.DataFrame) -> tuple[float, float, bool]:
    """(a, τ) por MLE de log-loss de marcador; multi-start a0=0.5×τ0. bool=converged."""
    def obj(theta):
        a = min(max(theta[0], 0.0), 1.0); tau = min(max(theta[1], 0.4), 2.5)
        return float(score_logloss_vec(train, a, tau).mean())
    best = None
    for tau0 in TAU0_GRID:
        r = minimize(obj, [A0, tau0], method="Nelder-Mead",
                     options={"xatol": 1e-3, "fatol": 1e-5, "maxiter": 200})
        if best is None or (r.fun < best.fun) or (
                np.isclose(r.fun, best.fun) and (r.x[0], r.x[1]) < (best.x[0], best.x[1])):
            best = r
    if best is None or not best.success:
        # se marca no-convergido; el caller decide (protocolo: spec no disponible)
        conv = bool(best.success) if best is not None else False
    else:
        conv = True
    a = float(min(max(best.x[0], 0.0), 1.0)); tau = float(min(max(best.x[1], 0.4), 2.5))
    return a, tau, conv


def fit_s_tau_fixed(train: pd.DataFrame, seed: int) -> tuple[float, float, bool]:
    tau, fallback = tau_rule(train, seed)
    res = minimize_scalar(lambda a: float(score_logloss_vec(train, a, tau).mean()),
                          bounds=(0.0, 1.0), method="bounded")
    return float(res.x), float(tau), fallback


def estimate_phi(train: pd.DataFrame) -> float:
    sides = to_sides(train)
    lam = sides["lam"].to_numpy(dtype=float); y = sides["y"].to_numpy(dtype=float)
    num = np.sum(((y - lam) ** 2 - lam) * lam ** 2)
    den = np.sum(lam ** 4)
    phi = num / den if den > 0 else 0.0
    return float(max(0.0, phi))


def region_borders(train: pd.DataFrame) -> tuple[float, float]:
    lam = to_sides(train)["lam"].to_numpy(dtype=float)
    return float(np.quantile(lam, 1 / 3)), float(np.quantile(lam, 2 / 3))


def region_label(lam: np.ndarray, b1: float, b2: float) -> np.ndarray:
    return np.where(lam < b1, "baja", np.where(lam < b2, "media", "alta"))


# ----------------------------------------------------------------- predictor

@dataclass
class Predictor:
    family: str
    a: float = 0.0
    tau: float = 0.0

    def score_logloss(self, df):
        return score_logloss_vec(df, self.a, self.tau)

    def rps(self, df):
        return rps_1x2_vec(df, self.a, self.tau)

    def lam_corr_sides(self, df):
        lh = contract(df["lam_h"].to_numpy(), self.a, self.tau)
        la = contract(df["lam_a"].to_numpy(), self.a, self.tau)
        return lh, la


def fit_family(family: str, train: pd.DataFrame, seed: int) -> Predictor | None:
    if family == "S_poisson":
        return Predictor("S_poisson", 0.0, 0.0)
    if family == "S_full":
        a, tau, conv = fit_s_full(train)
        return Predictor("S_full", a, tau) if conv else None
    if family == "S_tau_fixed":
        a, tau, _ = fit_s_tau_fixed(train, seed)
        return Predictor("S_tau_fixed", a, tau)
    raise ValueError(family)


# ----------------------------------------------------------------- inner loop

def seed_tau(outer_ix: int, inner_ix: int) -> int:
    return 41000 + 1000 * outer_ix + inner_ix


def _accumulate_family(family, inner_weeks, outer_train, outer_ix):
    """Devuelve (ll_mean, resid_por_region, bias_baja, disponible_en_todas)."""
    ll_all, side_y, side_lamc, side_reg = [], [], [], []
    available = True
    for inner_ix, w_i in enumerate(inner_weeks):
        inner_train = outer_train[outer_train["week"] < w_i]
        test = outer_train[outer_train["week"] == w_i]
        pred = fit_family(family, inner_train, seed_tau(outer_ix, inner_ix))
        if pred is None:                     # S_full no convergió
            available = False
            continue
        ll_all.append(pred.score_logloss(test))
        b1, b2 = region_borders(inner_train)
        lh, la = pred.lam_corr_sides(test)
        y = np.concatenate([test["hg"].to_numpy(), test["ag"].to_numpy()])
        lamc = np.concatenate([lh, la])
        side_y.append(y); side_lamc.append(lamc)
        side_reg.append(region_label(lamc, b1, b2))
    if not ll_all:
        return None
    ll_mean = float(np.concatenate(ll_all).mean())
    y = np.concatenate(side_y); lamc = np.concatenate(side_lamc)
    reg = np.concatenate(side_reg)
    resid = {}
    for r in ("baja", "media", "alta"):
        mk = reg == r
        if mk.sum() == 0:
            resid[r] = 0.0
        else:
            p0_obs = float((y[mk] == 0).mean())
            p0_pred = float(np.exp(-lamc[mk]).mean())
            resid[r] = p0_obs - p0_pred            # >0 = sobrecorrección
    lowmk = reg == "baja"
    bias_baja = float((y[lowmk] - lamc[lowmk]).mean()) if lowmk.sum() else 0.0
    return {"ll_mean": ll_mean, "resid": resid, "bias_baja": bias_baja,
            "available": available}


def select_family(outer_train: pd.DataFrame, outer_ix: int) -> Predictor:
    weeks = sorted(outer_train["week"].unique())
    inner_weeks = [w for w in weeks
                   if len(outer_train[outer_train["week"] < w]) >= MIN_INNER_TRAIN]
    if len(inner_weeks) < MIN_INNER_WEEKS:
        return Predictor("S_poisson", 0.0, 0.0)   # default seguro
    acc = {f: _accumulate_family(f, inner_weeks, outer_train, outer_ix)
           for f in FAMILIES}
    if acc["S_poisson"] is None:
        return Predictor("S_poisson", 0.0, 0.0)
    pois_ll = acc["S_poisson"]["ll_mean"]
    eligible = {}
    for f in ("S_full", "S_tau_fixed"):
        a = acc[f]
        if a is None:
            continue
        cond_a = a["ll_mean"] < pois_ll
        cond_b = all(a["resid"][r] <= EPS0 for r in ("baja", "media", "alta"))
        cond_c = abs(a["bias_baja"]) <= EPS_LAMBDA
        if cond_a and cond_b and cond_c:
            eligible[f] = a["ll_mean"]
    if not eligible:
        chosen = "S_poisson"
    else:
        best_ll = min(eligible.values())
        winners = [f for f, v in eligible.items() if np.isclose(v, best_ll)]
        chosen = "S_tau_fixed" if "S_tau_fixed" in winners else winners[0]
    pred = fit_family(chosen, outer_train, seed_tau(outer_ix, 999))
    return pred if pred is not None else Predictor("S_poisson", 0.0, 0.0)


# ----------------------------------------------------------------- outer loop

def run_outer(df: pd.DataFrame, test_start="2025-06-01", test_end="2025-12-01"):
    df = df.sort_values("date").reset_index(drop=True)
    test_mask = (df["date"] >= pd.Timestamp(test_start)) & (df["date"] < pd.Timestamp(test_end))
    outer_weeks = [w for w in sorted(df.loc[test_mask, "week"].unique())
                   if len(df[df["week"] < w]) >= MIN_OUTER_TRAIN]
    rows_match, rows_side, fold_choice = [], [], []
    for outer_ix, w_o in enumerate(outer_weeks):
        outer_train = df[df["week"] < w_o]
        test = df[(df["week"] == w_o) & test_mask]
        if len(test) == 0:
            continue
        pred_P = select_family(outer_train, outer_ix)
        fold_choice.append(pred_P.family)
        # comparadores (descriptivo + NB gate)
        phi = estimate_phi(outer_train)
        b1, b2 = region_borders(outer_train)
        ll_P = pred_P.score_logloss(test)
        ll_pois = score_logloss_vec(test, 0.0, 0.0)
        ll_nb = score_logloss_vec(test, 0.0, 0.0, phi=phi)
        rps_P = pred_P.rps(test)
        rps_pois = rps_1x2_vec(test, 0.0, 0.0)
        for i, (_, r) in enumerate(test.iterrows()):
            rows_match.append({"week": w_o, "selected": pred_P.family,
                               "ll_P": ll_P[i], "ll_pois": ll_pois[i],
                               "ll_nb": ll_nb[i], "rps_P": rps_P[i],
                               "rps_pois": rps_pois[i]})
        lh, la = pred_P.lam_corr_sides(test)
        for side_lam, goals in [(lh, test["hg"].to_numpy()), (la, test["ag"].to_numpy())]:
            reg = region_label(side_lam, b1, b2)
            for j in range(len(test)):
                rows_side.append({"week": w_o, "y": int(goals[j]),
                                  "lam_corr": float(side_lam[j]),
                                  "region": reg[j],
                                  "is_zero": int(goals[j] == 0)})
    return (pd.DataFrame(rows_match), pd.DataFrame(rows_side), fold_choice)


def promotion_pass(oos_match: pd.DataFrame, oos_side: pd.DataFrame,
                   fold_choice: list) -> dict:
    w = oos_match["week"].to_numpy()
    g1 = week_block_mean_ci((oos_match["ll_P"] - oos_match["ll_pois"]).to_numpy(), w, 47)
    g2 = week_block_mean_ci((oos_match["ll_P"] - oos_match["ll_nb"]).to_numpy(), w, 47)
    g3 = week_block_mean_ci((oos_match["rps_P"] - oos_match["rps_pois"]).to_numpy(), w, 7)
    gate1 = g1[2] < 0
    gate2 = g2[2] < 0
    gate3 = g3[2] < 0.0005
    gate4 = True; region_ci = {}
    for r in ("baja", "media", "alta"):
        s = oos_side[oos_side["region"] == r]
        if len(s) == 0:
            continue
        resid = s["is_zero"].to_numpy() - np.exp(-s["lam_corr"].to_numpy())
        m, lo, hi = week_block_mean_ci(resid, s["week"].to_numpy(), 41)
        region_ci[r] = (m, lo, hi)
        if not (lo >= -EPS0 and hi <= EPS0):
            gate4 = False
    s = oos_side[oos_side["region"] == "baja"]
    bias = (s["y"].to_numpy() - s["lam_corr"].to_numpy())
    b = week_block_mean_ci(bias, s["week"].to_numpy(), 43)
    gate5 = (b[1] >= -EPS_LAMBDA and b[2] <= EPS_LAMBDA)
    fc = pd.Series(fold_choice)
    modal_freq = float(fc.value_counts(normalize=True).iloc[0]) if len(fc) else 0.0
    gate6 = modal_freq >= SELECTION_STABILITY
    passed = gate1 and gate2 and gate3 and gate4 and gate5 and gate6
    return {"promotion_pass": bool(passed),
            "gate1_vs_poisson": {"delta": g1[0], "ci": [g1[1], g1[2]], "pass": bool(gate1)},
            "gate2_vs_negbin": {"delta": g2[0], "ci": [g2[1], g2[2]], "pass": bool(gate2)},
            "gate3_rps": {"delta": g3[0], "ci": [g3[1], g3[2]], "pass": bool(gate3)},
            "gate4_p0_regions": {"ci": {k: list(v) for k, v in region_ci.items()},
                                 "pass": bool(gate4)},
            "gate5_bias_low": {"delta": b[0], "ci": [b[1], b[2]], "pass": bool(gate5)},
            "gate6_stability": {"modal_freq": modal_freq,
                                "counts": fc.value_counts().to_dict(),
                                "pass": bool(gate6)}}
