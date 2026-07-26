"""EXP-006.1 — Corrección suave de la media a baja λ (autorizada por el director).

Contracción continua hacia un umbral τ (NO piso duro, para no aplastar
diferencias informativas):

    log λ' = (1-a)·log λ + a·log τ      si λ < τ
    log λ' = log λ                       si λ ≥ τ

a=0 → modelo original; a=1 → todo lo bajo sube hasta τ; intermedio → suave y
monótono. Se ajusta (a, τ) SOLO con λ OOS de 2025 minimizando el log-loss de
MARCADOR (criterio primario del director). Evaluación descriptiva en 2026 (dev).

Comparadores: Poisson (a=0), Poisson ρ=0, NB drop-in (φ=0.074), corrección
global constante (λ'=c·λ, c ajustado en 2025). Rotación por países: ajustar en
dos, evaluar en el tercero. Bootstrap semanal para los contrastes.

Criterios de promoción del director (se reportan todos, no se decide acá):
- reduce log-loss de marcador;
- no empeora RPS 1X2 más de 0.0005;
- reduce el sesgo Y−λ del decil bajo;
- mejora P(0) sin crear déficit en intensidades medias;
- conserva el signo en los tres países;
- no requiere parámetros por temporada (se chequea comparando a,τ 2025 vs 2026).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import nbinom, poisson

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.peak_models.models import probs_1x2, score_matrix  # noqa: E402

REF = ROOT / "research/experiments/EXP-004-referee"
HERE = Path(__file__).parent
FIG = HERE / "fig"
FIG.mkdir(exist_ok=True)
plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True,
                     "grid.color": "#e8e7e2", "axes.axisbelow": True})

PHI = 0.074
FIN = {"VL", "M1L", "M1", "M2", "NL"}


def country_of(code: str) -> str:
    if code.startswith("SW-"):
        return "SWE"
    if code.startswith("NO-"):
        return "NOR"
    return "FIN" if code in FIN else "?"


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    d25 = pd.read_csv(REF / "lambdas_2025.csv", parse_dates=["date"])
    d26 = pd.read_csv(REF / "lambdas_2026.csv", parse_dates=["date"])
    for d in (d25, d26):
        d["week"] = d["date"].dt.to_period("W").astype(str)
        d["country"] = d["league_code"].map(country_of)
    return d25, d26


def contract(lam: np.ndarray, a: float, tau: float) -> np.ndarray:
    lam = np.maximum(np.asarray(lam, dtype=float), 1e-9)  # evita log(0)
    if a == 0 or tau <= 0:
        return lam.copy()
    low = lam < tau
    out = lam.copy()
    out[low] = np.exp((1 - a) * np.log(lam[low]) + a * np.log(tau))
    return out


def score_logloss_per_match(
    d: pd.DataFrame, a: float, tau: float, maxg: int = 12
) -> np.ndarray:
    ks = np.arange(maxg + 1)
    lh = contract(d["lam_h"].to_numpy(), a, tau)
    la = contract(d["lam_a"].to_numpy(), a, tau)
    ll = np.empty(len(d))
    for i in range(len(d)):
        ph = poisson.pmf(ks, lh[i]); ph /= ph.sum()
        pa = poisson.pmf(ks, la[i]); pa /= pa.sum()
        gh = min(int(d["hg"].iat[i]), maxg); ga = min(int(d["ag"].iat[i]), maxg)
        ll[i] = -np.log(max(ph[gh] * pa[ga], 1e-12))
    return ll


def score_logloss(d: pd.DataFrame, a: float, tau: float, maxg: int = 12) -> float:
    return float(score_logloss_per_match(d, a, tau, maxg).mean())


def fit_correction(d: pd.DataFrame) -> tuple[float, float]:
    def obj(theta):
        a = np.clip(theta[0], 0, 1); tau = np.clip(theta[1], 0.4, 2.5)
        return score_logloss(d, a, tau)
    best = None
    for tau0 in (0.9, 1.2, 1.5):
        r = minimize(obj, [0.5, tau0], method="Nelder-Mead",
                     options={"xatol": 1e-3, "fatol": 1e-5, "maxiter": 200})
        if best is None or r.fun < best.fun:
            best = r
    return float(np.clip(best.x[0], 0, 1)), float(np.clip(best.x[1], 0.4, 2.5))


def fit_global_c(d: pd.DataFrame) -> float:
    def obj(c):
        return score_logloss(d.assign(lam_h=d.lam_h * c[0], lam_a=d.lam_a * c[0]),
                             0.0, 0.0)
    r = minimize(obj, [1.05], method="Nelder-Mead",
                 options={"xatol": 1e-3, "maxiter": 100})
    return float(r.x[0])


def nb_logloss_per_match(
    d: pd.DataFrame, phi: float, maxg: int = 12
) -> np.ndarray:
    ks = np.arange(maxg + 1)
    r = 1.0 / phi
    ll = np.empty(len(d))
    for i, row in enumerate(d.itertuples()):
        ph = nbinom.pmf(ks, r, r / (r + row.lam_h)); ph /= ph.sum()
        pa = nbinom.pmf(ks, r, r / (r + row.lam_a)); pa /= pa.sum()
        gh = min(int(row.hg), maxg); ga = min(int(row.ag), maxg)
        ll[i] = -np.log(max(ph[gh] * pa[ga], 1e-12))
    return ll


def nb_score_logloss(d: pd.DataFrame, phi: float, maxg: int = 12) -> float:
    return float(nb_logloss_per_match(d, phi, maxg).mean())


def rps_1x2(d: pd.DataFrame, a: float, tau: float) -> np.ndarray:
    lh = contract(d["lam_h"].to_numpy(), a, tau)
    la = contract(d["lam_a"].to_numpy(), a, tau)
    order = {"H": 0, "D": 1, "A": 2}
    out = np.empty(len(d))
    for i in range(len(d)):
        p = np.array(probs_1x2(score_matrix(lh[i], la[i], 0.0)))
        res = "H" if d["hg"].iat[i] > d["ag"].iat[i] else ("A" if d["ag"].iat[i] > d["hg"].iat[i] else "D")
        y = np.zeros(3); y[order[res]] = 1
        out[i] = ((np.cumsum(p) - np.cumsum(y)) ** 2).sum() / 2
    return out


def wblock(delta: np.ndarray, weeks: np.ndarray, seed=7, n=4000):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"d": delta, "w": weeks})
    groups = [g["d"].to_numpy() for _, g in df.groupby("w", sort=True)]
    boot = np.array([np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))]).mean()
                     for _ in range(n)])
    return float(delta.mean()), float(np.quantile(boot, .025)), float(np.quantile(boot, .975))


def low_decile_bias(d: pd.DataFrame, a: float, tau: float) -> dict:
    """Sesgo Y−λ' en el decil bajo por lado (long), corregido vs original."""
    sides = pd.concat([
        pd.DataFrame({"y": d.hg, "lam": d.lam_h, "week": d.week}),
        pd.DataFrame({"y": d.ag, "lam": d.lam_a, "week": d.week})], ignore_index=True)
    thr = sides["lam"].quantile(0.1)
    low = sides[sides["lam"] <= thr].copy()
    low["lamc"] = contract(low["lam"].to_numpy(), a, tau)
    b0 = wblock((low["y"] - low["lam"]).to_numpy(), low["week"].to_numpy())
    bc = wblock((low["y"] - low["lamc"]).to_numpy(), low["week"].to_numpy(), seed=9)
    return {"lam_threshold": round(float(thr), 3),
            "bias_original": round(b0[0], 4), "bias_orig_ci": [round(b0[1], 4), round(b0[2], 4)],
            "bias_corregido": round(bc[0], 4), "bias_corr_ci": [round(bc[1], 4), round(bc[2], 4)]}


def p0_by_decile(d: pd.DataFrame, a: float, tau: float) -> list:
    sides = pd.concat([
        pd.DataFrame({"y": d.hg, "lam": d.lam_h, "week": d.week}),
        pd.DataFrame({"y": d.ag, "lam": d.lam_a, "week": d.week})], ignore_index=True)
    sides["dec"] = pd.qcut(sides["lam"], 10, duplicates="drop")
    rows = []
    for dec, g in sides.groupby("dec", observed=True):
        lamc = contract(g["lam"].to_numpy(), a, tau)
        obs = (g["y"] == 0).to_numpy(dtype=float)
        gap_pois = wblock(
            obs - np.exp(-g["lam"].to_numpy()), g["week"].to_numpy(),
            seed=41)
        gap_corr = wblock(obs - np.exp(-lamc), g["week"].to_numpy(), seed=43)
        rows.append({"lam": round(float(g["lam"].mean()), 3),
                     "obs_P0": round(float((g["y"] == 0).mean()), 4),
                     "pois_P0": round(float(np.exp(-g["lam"]).mean()), 4),
                     "corr_P0": round(float(np.exp(-lamc).mean()), 4),
                     "obs_minus_pois": round(gap_pois[0], 4),
                     "obs_minus_pois_ci": [round(gap_pois[1], 4),
                                           round(gap_pois[2], 4)],
                     "obs_minus_corr": round(gap_corr[0], 4),
                     "obs_minus_corr_ci": [round(gap_corr[1], 4),
                                           round(gap_corr[2], 4)]})
    return rows


def main() -> None:
    d25, d26 = load()
    out = {}

    a, tau = fit_correction(d25)
    a26, tau26 = fit_correction(d26)  # solo para chequear estabilidad de params
    c_glob = fit_global_c(d25)
    out["fit_2025"] = {"a": round(a, 3), "tau": round(tau, 3), "c_global": round(c_glob, 3)}
    out["fit_2026_check"] = {"a": round(a26, 3), "tau": round(tau26, 3)}
    print(f"ajuste 2025: a={a:.3f} tau={tau:.3f} | c_global={c_glob:.3f}")
    print(f"(chequeo 2026: a={a26:.3f} tau={tau26:.3f})")

    # ---- log-loss de marcador en 2026 (todos los modelos) ---------------
    d26c = d26.assign(lam_h=d26.lam_h * c_glob, lam_a=d26.lam_a * c_glob)
    scores = {
        "poisson": score_logloss(d26, 0.0, 0.0),
        "correccion_lambda": score_logloss(d26, a, tau),
        "global_c": score_logloss(d26c, 0.0, 0.0),
        "negbin": nb_score_logloss(d26, PHI),
    }
    out["logloss_marcador_2026"] = {k: round(v, 4) for k, v in scores.items()}
    print("log-loss marcador 2026:", out["logloss_marcador_2026"])
    ll = {
        "poisson": score_logloss_per_match(d26, 0.0, 0.0),
        "correccion_lambda": score_logloss_per_match(d26, a, tau),
        "global_c": score_logloss_per_match(d26c, 0.0, 0.0),
        "negbin": nb_logloss_per_match(d26, PHI),
    }
    ll_contrasts = {}
    for baseline in ("poisson", "global_c", "negbin"):
        mll, loll, hill = wblock(
            ll["correccion_lambda"] - ll[baseline],
            d26["week"].to_numpy(), seed=47)
        ll_contrasts[f"correccion_vs_{baseline}"] = {
            "delta": round(mll, 4), "ci_lo": round(loll, 4),
            "ci_hi": round(hill, 4)}
    out["logloss_block_contrasts_2026"] = ll_contrasts
    print("IC log-loss por bloques:", ll_contrasts)

    # ---- RPS 1X2 pareado (correccion vs poisson) ------------------------
    rps_c = rps_1x2(d26, a, tau)
    rps_p = rps_1x2(d26, 0.0, 0.0)
    m, lo, hi = wblock(rps_c - rps_p, d26["week"].to_numpy())
    out["rps_delta_vs_poisson"] = {"delta": round(m, 4), "ci_lo": round(lo, 4),
                                   "ci_hi": round(hi, 4),
                                   "rps_poisson": round(float(rps_p.mean()), 4),
                                   "rps_correccion": round(float(rps_c.mean()), 4)}
    print(f"RPS 1X2: poisson {rps_p.mean():.4f} → corrección {rps_c.mean():.4f} "
          f"(Δ={m:+.4f} IC=[{lo:+.4f},{hi:+.4f}])")

    # ---- sesgo del decil bajo y P(0) por decil --------------------------
    out["low_decile_bias_2026"] = low_decile_bias(d26, a, tau)
    print("sesgo decil bajo 2026:", out["low_decile_bias_2026"])
    out["p0_by_decile_2026"] = p0_by_decile(d26, a, tau)

    # ---- rotación por países (fit en 2, eval en el 3ro) -----------------
    rot = {}
    for held in ["FIN", "SWE", "NOR"]:
        tr = d25[d25.country != held]
        te = d26[d26.country == held]
        if len(te) < 30:
            continue
        ah, th = fit_correction(tr)
        ll_p = score_logloss(te, 0.0, 0.0)
        ll_c = score_logloss(te, ah, th)
        ll_delta = (
            score_logloss_per_match(te, ah, th)
            - score_logloss_per_match(te, 0.0, 0.0)
        )
        ll_bs = wblock(ll_delta, te["week"].to_numpy(), seed=53)
        rps_dc = rps_1x2(te, ah, th) - rps_1x2(te, 0.0, 0.0)
        rps_bs = wblock(rps_dc, te["week"].to_numpy(), seed=59)
        rot[held] = {"a": round(ah, 3), "tau": round(th, 3),
                     "logloss_poisson": round(ll_p, 4),
                     "logloss_correccion": round(ll_c, 4),
                     "delta_logloss": round(ll_c - ll_p, 4),
                     "delta_logloss_ci": [round(ll_bs[1], 4),
                                          round(ll_bs[2], 4)],
                     "delta_rps": round(float(rps_dc.mean()), 4),
                     "delta_rps_ci": [round(rps_bs[1], 4),
                                      round(rps_bs[2], 4)]}
        print(f"  sin {held}→eval {held}: a={ah:.2f} τ={th:.2f} "
              f"Δlogloss={ll_c-ll_p:+.4f} Δrps={rps_dc.mean():+.4f}")
    out["country_rotation"] = rot

    # ---- figuras --------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    xx = np.linspace(0.2, 2.5, 200)
    axes[0].plot(xx, contract(xx, a, tau), color="#008300", lw=2, label=f"a={a:.2f}, τ={tau:.2f}")
    axes[0].plot(xx, xx, "--", color="#c9c8c2", lw=1, label="identidad (a=0)")
    axes[0].axvline(tau, color="#e8e7e2")
    axes[0].set_xlabel("λ original"); axes[0].set_ylabel("λ' corregido")
    axes[0].set_title("Contracción suave hacia τ (ajuste 2025)")
    axes[0].legend(frameon=False, fontsize=8)
    dec = pd.DataFrame(out["p0_by_decile_2026"])
    axes[1].plot(dec["lam"], dec["obs_P0"], "o-", color="#52514e", ms=4, label="observado")
    axes[1].plot(dec["lam"], dec["pois_P0"], "o-", color="#e34948", ms=4, label="Poisson")
    axes[1].plot(dec["lam"], dec["corr_P0"], "o-", color="#008300", ms=4, label="corregido")
    axes[1].set_xlabel("λ (media del decil)"); axes[1].set_ylabel("P(Y=0)")
    axes[1].set_title("P(0) por intensidad: ¿la corrección cierra el déficit?")
    axes[1].legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "lambda_correction.png"); plt.close(fig)

    json.dump(out, open(HERE / "lambda_correction.json", "w"), indent=2)
    print("→ lambda_correction.json + fig/lambda_correction.png")


if __name__ == "__main__":
    main()
