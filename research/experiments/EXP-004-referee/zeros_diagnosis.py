"""EXP-004.9 — El déficit de ceros y la baja intensidad (pre-check de H_regímenes).

Motivación: r̄²≈1.2 (sobredispersión) PERO el 0-0 observado (0.040) < Poisson
(0.051) es un DÉFICIT de ceros. Una mezcla que preserve la media aumenta P(0)
por Jensen (e^{-λ} convexa) → NO puede arreglar el déficit; fallaría el criterio
de rechazo del director. Antes de construir la mezcla, caracterizamos el déficit:

1. Por lado: P(Y=0) observada vs Poisson E[e^{-λ}], global y por decil de λ, con
   IC por bloques semanales sobre la diferencia. ¿Uniforme o a baja intensidad?
2. Demostración numérica: cualquier mezcla mean-preserving sube P(0) (cota Jensen).
3. Efecto de ρ en el 0-0 (ρ ajustado vs ρ=0) — cuantifica cuánto del exceso de
   0-0 del DC viene de ρ<0.
4. ¿El déficit es de media (λ subestimada en contextos bajos) o de forma? Se
   contrasta P(Y=1)/P(Y=0) observado vs Poisson: en Poisson ese ratio = λ.
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
from scipy.stats import poisson

HERE = Path(__file__).parent
FIG = HERE / "fig"
plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True,
                     "grid.color": "#e8e7e2", "axes.axisbelow": True})


def load() -> pd.DataFrame:
    frames = []
    for f, yr in [("lambdas_2025.csv", "2025"), ("lambdas_2026.csv", "2026")]:
        p = HERE / f
        if p.exists():
            d = pd.read_csv(p, parse_dates=["date"])
            d["season"] = yr
            d["week"] = d["date"].dt.to_period("W").astype(str)
            frames.append(d)
    return pd.concat(frames, ignore_index=True)


def long_sides(d: pd.DataFrame) -> pd.DataFrame:
    h = d[["season", "week", "hg", "lam_h"]].rename(columns={"hg": "y", "lam_h": "lam"})
    a = d[["season", "week", "ag", "lam_a"]].rename(columns={"ag": "y", "lam_a": "lam"})
    return pd.concat([h, a], ignore_index=True)


def wblock_ci(v: np.ndarray, weeks: np.ndarray, seed=31, n=4000):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"v": v, "w": weeks})
    groups = [g["v"].to_numpy() for _, g in df.groupby("w", sort=True)]
    boot = np.array([np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))]).mean()
                     for _ in range(n)])
    return float(v.mean()), float(np.quantile(boot, .025)), float(np.quantile(boot, .975))


def main() -> None:
    d = load()
    x = long_sides(d)
    x["p0_pois"] = np.exp(-x["lam"])          # P(Y=0) que asigna Poisson por partido
    x["is0"] = (x["y"] == 0).astype(float)
    x["defbit"] = x["is0"] - x["p0_pois"]      # observado − esperado (por partido)

    out = {}
    # ---- 1. déficit global y por decil de lambda ------------------------
    for season, g in x.groupby("season"):
        m, lo, hi = wblock_ci(g["defbit"].to_numpy(), g["week"].to_numpy())
        out[f"deficit_global_{season}"] = {
            "obs_P0": round(float(g["is0"].mean()), 4),
            "pois_P0": round(float(g["p0_pois"].mean()), 4),
            "diff": round(m, 4), "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)}
        print(f"{season}: P(0) obs {g['is0'].mean():.4f} vs Poisson "
              f"{g['p0_pois'].mean():.4f}  Δ={m:+.4f} IC=({lo:+.4f},{hi:+.4f})")

    fig, ax = plt.subplots(figsize=(6.8, 4))
    for season, c in [("2026", "#008300"), ("2025", "#eda100")]:
        g = x[x.season == season].copy()
        g["dec"] = pd.qcut(g["lam"], 10, duplicates="drop")
        xs, ys, los, his = [], [], [], []
        for _, gg in g.groupby("dec", observed=True):
            m, lo, hi = wblock_ci(gg["defbit"].to_numpy(), gg["week"].to_numpy())
            xs.append(gg["lam"].mean()); ys.append(m); los.append(lo); his.append(hi)
        ax.errorbar(xs, ys, yerr=[np.array(ys) - los, np.array(his) - ys],
                    fmt="o-", ms=4, lw=1.4, capsize=2, color=c, label=season)
    ax.axhline(0, color="#52514e", lw=1)
    ax.set_xlabel("λ̂ predicho (media del decil)")
    ax.set_ylabel("P(Y=0) observada − Poisson  (negativo = déficit de ceros)")
    ax.set_title("¿Dónde falta el cero? Déficit de P(Y=0) por intensidad\n"
                 "IC 95% por bloques semanales")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "zeros_deficit_by_lambda.png"); plt.close(fig)

    # ---- 2. Jensen: la mezcla mean-preserving SUBE P(0) -----------------
    # dos escalas c1<1<c2 con pi tal que pi*c1+(1-pi)*c2=1; P0_mix=pi*e^{-c1 λ}+
    # (1-pi)*e^{-c2 λ} vs e^{-λ}. Ejemplo a λ=1.3 (media típica).
    lam = 1.3
    jensen = []
    for spread in [0.2, 0.4, 0.6]:
        c1, c2 = 1 - spread, 1 + spread
        pi = 0.5  # mean-preserving con c simétricos
        p0_mix = pi * np.exp(-c1 * lam) + (1 - pi) * np.exp(-c2 * lam)
        jensen.append({"spread": spread, "P0_poisson": round(float(np.exp(-lam)), 4),
                       "P0_mezcla_mean_preserving": round(float(p0_mix), 4)})
    out["jensen_demo_lambda1.3"] = jensen
    print("Jensen (λ=1.3): mezcla mean-preserving vs Poisson:")
    for j in jensen:
        print(f"  spread={j['spread']}: Poisson {j['P0_poisson']} → mezcla "
              f"{j['P0_mezcla_mean_preserving']} (sube)")

    # ---- 3. efecto de rho en el 0-0 (solo 2026, que trae rho) -----------
    d26 = d[d.season == "2026"].copy()
    if "rho" in d26.columns:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from research.peak_models.models import score_matrix  # noqa
        p00_rho = p00_norho = 0.0
        for r in d26.itertuples():
            p00_rho += score_matrix(r.lam_h, r.lam_a, r.rho)[0, 0]
            p00_norho += score_matrix(r.lam_h, r.lam_a, 0.0)[0, 0]
        n = len(d26)
        obs00 = float(((d26.hg == 0) & (d26.ag == 0)).mean())
        out["cell00_2026"] = {"obs": round(obs00, 4),
                              "pred_rho": round(p00_rho / n, 4),
                              "pred_rho0": round(p00_norho / n, 4)}
        print(f"0-0 2026: obs {obs00:.4f} | DC(ρ) {p00_rho/n:.4f} | "
              f"DC(ρ=0) {p00_norho/n:.4f}")

    # ---- 4. ¿media o forma? ratio P1/P0 observado vs Poisson (=λ) --------
    # Por decil: si obs P1/P0 ≈ λ, la forma es Poisson y el problema es la media.
    ratios = {}
    for season, g in x.groupby("season"):
        g = g.copy(); g["dec"] = pd.qcut(g["lam"], 6, duplicates="drop")
        rr = []
        for _, gg in g.groupby("dec", observed=True):
            p0 = (gg["y"] == 0).mean(); p1 = (gg["y"] == 1).mean()
            rr.append({"lam": round(float(gg["lam"].mean()), 3),
                       "obs_P1_P0": round(float(p1 / p0), 3) if p0 > 0 else None,
                       "poisson_ratio_lambda": round(float(gg["lam"].mean()), 3)})
        ratios[season] = rr
    out["shape_ratio_P1_P0"] = ratios
    print("ratio P1/P0 (Poisson predice = λ):")
    for s, rr in ratios.items():
        print(f"  {s}:", [(r["lam"], r["obs_P1_P0"]) for r in rr])

    json.dump(out, open(HERE / "zeros_diagnosis.json", "w"), indent=2)
    print("→ zeros_diagnosis.json + fig/zeros_deficit_by_lambda.png")


if __name__ == "__main__":
    main()
