"""EXP-004.2 — ¿El Poisson describe los goles? (referee §6).

Replay walk-forward semanal del DC guardando (λH, λA) por partido de 2026
(out-of-sample) y diagnósticos:

1. Media vs varianza de goles por liga (índice de dispersión, global y por liga).
2. Distribución de nº de goles observada vs predicha (mezcla de Poissons con
   los λ de cada partido — la predicha correcta, no una Poisson única).
3. Celdas de marcadores bajos: obs vs pred con ρ y sin ρ.
4. Correlación residual (Pearson) entre goles local y visitante.
5. Calibración de λ por deciles (¿λ̂ predice la media real de goles?).
6. Masa perdida por truncar la matriz en 10 goles.
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

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.peak_models import loader  # noqa: E402
from research.peak_models.models import fit_poisson, score_matrix  # noqa: E402

HERE = Path(__file__).parent
FIG = HERE / "fig"
FIG.mkdir(exist_ok=True)
plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True,
                     "grid.color": "#e8e7e2", "axes.axisbelow": True})

BEST = {"halflife_days": 120.0, "ridge_sigma": 0.75, "fit_rho": True}


def replay_lambdas() -> pd.DataFrame:
    df = loader.load_all()
    played = df.dropna(subset=["home_goals", "away_goals"]).sort_values("date")
    test = played[played["date"] >= pd.Timestamp("2026-01-01")]
    rows = []
    for wk in sorted(test["date"].dt.to_period("W").unique()):
        cutoff = wk.start_time
        train = played[played["date"] < cutoff]
        rows_wk = test[test["date"].dt.to_period("W") == wk]
        fits = {}
        for r in rows_wk.itertuples():
            lg = r.league_code
            if lg not in fits:
                fits[lg] = fit_poisson(train[train["league_code"] == lg],
                                       asof=cutoff, **BEST)
            f = fits[lg]
            if f is None:
                continue
            lh, la, known = f.rates(r.home_team_id, r.away_team_id)
            rows.append({"match_id": str(r.match_id), "league_code": lg,
                         "country": r.country, "date": r.date,
                         "hg": int(r.home_goals), "ag": int(r.away_goals),
                         "lam_h": lh, "lam_a": la, "rho": f.rho, "known": known})
    return pd.DataFrame(rows)


def main() -> None:
    d = replay_lambdas()
    d.to_csv(HERE / "lambdas_2026.csv", index=False)
    print(f"{len(d)} partidos con λ OOS")

    out = {}
    # --- 1. media vs varianza (goles totales y por lado) ------------------
    disp = []
    for lg, g in d.groupby("league_code"):
        for side, col in [("H", "hg"), ("A", "ag")]:
            m, v = g[col].mean(), g[col].var(ddof=1)
            disp.append({"liga": lg, "lado": side, "media": round(m, 3),
                         "var": round(v, 3), "dispersion": round(v / m, 3),
                         "n": len(g)})
    disp = pd.DataFrame(disp)
    glob = {s: (d[c].mean(), d[c].var(ddof=1))
            for s, c in [("H", "hg"), ("A", "ag")]}
    print("dispersión global: H %.3f  A %.3f" %
          (glob["H"][1] / glob["H"][0], glob["A"][1] / glob["A"][0]))
    out["dispersion_global"] = {s: round(v / m, 4) for s, (m, v) in glob.items()}
    out["dispersion_por_liga"] = json.loads(disp.to_json(orient="records"))

    # --- 2. distribución de goles obs vs pred (mezcla) --------------------
    ks = np.arange(0, 9)
    pred_h = np.array([poisson.pmf(ks, l) for l in d["lam_h"]]).mean(axis=0)
    pred_a = np.array([poisson.pmf(ks, l) for l in d["lam_a"]]).mean(axis=0)
    obs_h = np.array([(d["hg"] == k).mean() for k in ks])
    obs_a = np.array([(d["ag"] == k).mean() for k in ks])
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.4))
    for ax, obs, pred, lbl in [(axes[0], obs_h, pred_h, "local"),
                               (axes[1], obs_a, pred_a, "visitante")]:
        ax.bar(ks - 0.18, obs, 0.36, color="#2a78d6", label="observado")
        ax.bar(ks + 0.18, pred, 0.36, color="#eda100",
               label="predicho (mezcla de Poissons)")
        ax.set_xlabel(f"goles {lbl}"); ax.set_ylabel("frecuencia")
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Distribución de goles 2026: observada vs predictiva OOS", y=1.0)
    fig.tight_layout(); fig.savefig(FIG / "goal_distribution.png"); plt.close(fig)
    out["goles_obs_vs_pred_H"] = [[int(k), round(float(o), 4), round(float(p), 4)]
                                  for k, o, p in zip(ks, obs_h, pred_h)]

    # --- 3. celdas bajas obs vs pred (con y sin rho) ----------------------
    cells = [(0, 0), (1, 0), (0, 1), (1, 1)]
    pred_rho = {c: 0.0 for c in cells}
    pred_norho = {c: 0.0 for c in cells}
    trunc_mass = 0.0
    for r in d.itertuples():
        m_rho = score_matrix(r.lam_h, r.lam_a, r.rho)
        m_no = score_matrix(r.lam_h, r.lam_a, 0.0)
        for c in cells:
            pred_rho[c] += m_rho[c]
            pred_norho[c] += m_no[c]
        trunc_mass += 1 - poisson.cdf(10, r.lam_h) + 1 - poisson.cdf(10, r.lam_a)
    n = len(d)
    rows = []
    for c in cells:
        obs = ((d["hg"] == c[0]) & (d["ag"] == c[1])).mean()
        rows.append({"celda": f"{c[0]}-{c[1]}", "obs": round(obs, 4),
                     "pred_rho": round(pred_rho[c] / n, 4),
                     "pred_sin_rho": round(pred_norho[c] / n, 4)})
    cells_df = pd.DataFrame(rows)
    print(cells_df.to_string(index=False))
    out["celdas_bajas"] = json.loads(cells_df.to_json(orient="records"))
    out["masa_truncada_media"] = float(trunc_mass / (2 * n))

    # --- 4. correlación residual Pearson ---------------------------------
    rh = (d["hg"] - d["lam_h"]) / np.sqrt(d["lam_h"])
    ra = (d["ag"] - d["lam_a"]) / np.sqrt(d["lam_a"])
    out["corr_residual_pearson"] = round(float(np.corrcoef(rh, ra)[0, 1]), 4)
    print("corr residual H-A:", out["corr_residual_pearson"])

    # --- 4b. dispersión condicional y CI por bloques semanales -----------
    # E[r^2] debe ser aproximadamente 1 bajo una Poisson bien especificada,
    # con r=(y-lambda)/sqrt(lambda). Remuestreamos semanas completas para no
    # tratar como independientes partidos generados bajo el mismo régimen.
    d["week"] = pd.to_datetime(d["date"]).dt.to_period("W").astype(str)
    rng = np.random.default_rng(17)
    weeks = sorted(d["week"].unique())
    conditional = {}
    for side, resid in [("H", rh), ("A", ra)]:
        tmp = pd.DataFrame({"r2": np.asarray(resid) ** 2, "week": d["week"]})
        groups = [g["r2"].to_numpy() for _, g in tmp.groupby("week", sort=True)]
        boot = np.empty(4000)
        for i in range(len(boot)):
            pick = rng.integers(0, len(groups), size=len(groups))
            boot[i] = np.concatenate([groups[j] for j in pick]).mean()
        conditional[side] = {
            "estimate": round(float(tmp["r2"].mean()), 4),
            "ci_week_lo": round(float(np.quantile(boot, 0.025)), 4),
            "ci_week_hi": round(float(np.quantile(boot, 0.975)), 4),
            "n_weeks": len(weeks),
        }
    out["dispersion_pearson_condicional"] = conditional
    print("dispersión Pearson condicional:", conditional)

    # --- 5. calibración de λ por deciles ---------------------------------
    fig, ax = plt.subplots(figsize=(6.5, 4))
    for lam, goals, c, lbl in [(d["lam_h"], d["hg"], "#2a78d6", "local"),
                               (d["lam_a"], d["ag"], "#008300", "visitante")]:
        q = pd.qcut(lam, 10, duplicates="drop")
        g = pd.DataFrame({"lam": lam, "gl": goals}).groupby(q, observed=True).mean()
        ax.plot(g["lam"], g["gl"], "o-", color=c, label=lbl, ms=5, lw=1.5)
    lim = [0.5, 3.2]
    ax.plot(lim, lim, "--", color="#c9c8c2", lw=1)
    ax.set_xlabel("λ̂ predicho (media del decil)")
    ax.set_ylabel("goles observados (media del decil)")
    ax.set_title("Calibración de intensidades: λ̂ vs goles reales por decil (2026 OOS)")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "lambda_calibration.png"); plt.close(fig)

    # --- figura media-varianza -------------------------------------------
    fig, ax = plt.subplots(figsize=(6.5, 4))
    for side, c in [("H", "#2a78d6"), ("A", "#008300")]:
        g = disp[disp["lado"] == side]
        ax.scatter(g["media"], g["var"], s=g["n"] / 3, color=c, alpha=0.85,
                   label=f"goles {side}", edgecolor="white", lw=0.6)
    lim = [0.6, 3.4]
    ax.plot(lim, lim, "--", color="#52514e", lw=1)
    ax.annotate("var = media (Poisson)", (2.0, 1.85), fontsize=8,
                color="#52514e", rotation=30)
    ax.set_xlabel("media de goles (liga, 2026)")
    ax.set_ylabel("varianza de goles (liga, 2026)")
    ax.set_title("Test de equidispersión por liga: puntos sobre la diagonal ⇒ Poisson OK")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "mean_variance.png"); plt.close(fig)

    json.dump(out, open(HERE / "poisson_diagnostics.json", "w"), indent=2)
    print("→ poisson_diagnostics.json + fig/")


if __name__ == "__main__":
    main()
