"""EXP-004.6 — Estructura de la sobredispersión (Línea 1 del programa, H1-H2).

Antes de cambiar de distribución: ¿la sobredispersión es global, por liga, o
función de la intensidad?

H1: concentrada en ciertas ligas → r̄² por liga con IC por bloques semanales,
    p-valores bootstrap para H0: r̄²=1, corrección Benjamini-Hochberg,
    y estabilidad 2025→2026.
H2: dependiente de λ → E[r²|λ] por deciles de λ con IC por bloques; ajuste de
    Var(G|λ)=λ+φλ² (φ global por regresión por el origen de (y−λ)²−λ sobre λ²).

Usa λ OOS de 2026 (lambdas_2026.csv) y regenera el replay equivalente para 2025.
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

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.peak_models import loader  # noqa: E402
from research.peak_models.models import fit_poisson  # noqa: E402

HERE = Path(__file__).parent
FIG = HERE / "fig"
plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True,
                     "grid.color": "#e8e7e2", "axes.axisbelow": True})

BEST = {"halflife_days": 120.0, "ridge_sigma": 0.75, "fit_rho": True}
WOMEN = {"NL", "SW-DA", "SW-EE", "NO-TS", "NO-1DK"}


def replay(start: str, end: str) -> pd.DataFrame:
    df = loader.load_all()
    played = df.dropna(subset=["home_goals", "away_goals"]).sort_values("date")
    test = played[(played["date"] >= pd.Timestamp(start))
                  & (played["date"] < pd.Timestamp(end))]
    rows = []
    for wk in sorted(test["date"].dt.to_period("W").unique()):
        cutoff = wk.start_time
        train = played[played["date"] < cutoff]
        fits = {}
        for r in test[test["date"].dt.to_period("W") == wk].itertuples():
            lg = r.league_code
            if lg not in fits:
                fits[lg] = fit_poisson(train[train["league_code"] == lg],
                                       asof=cutoff, **BEST)
            f = fits[lg]
            if f is None:
                continue
            lh, la, _ = f.rates(r.home_team_id, r.away_team_id)
            rows.append({"league_code": lg, "date": r.date,
                         "week": str(wk), "hg": int(r.home_goals),
                         "ag": int(r.away_goals), "lam_h": lh, "lam_a": la})
    return pd.DataFrame(rows)


def long_residuals(d: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (partido, lado): y, lambda, r2, semana, liga."""

    h = pd.DataFrame({"league": d["league_code"], "week": d["week"],
                      "y": d["hg"], "lam": d["lam_h"]})
    a = pd.DataFrame({"league": d["league_code"], "week": d["week"],
                      "y": d["ag"], "lam": d["lam_a"]})
    x = pd.concat([h, a], ignore_index=True)
    x["r2"] = (x["y"] - x["lam"]) ** 2 / x["lam"]
    return x


def week_block_ci(values: np.ndarray, weeks: np.ndarray, n_boot: int = 4000,
                  seed: int = 19) -> tuple[float, float, float, float]:
    """(media, lo, hi, p_dos_colas para H0: media=1)."""

    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"v": values, "w": weeks})
    groups = [g["v"].to_numpy() for _, g in df.groupby("w", sort=True)]
    nb = len(groups)
    boot = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, nb, size=nb)
        boot[i] = np.concatenate([groups[j] for j in pick]).mean()
    p = 2 * min((boot < 1).mean(), (boot > 1).mean())
    return (float(values.mean()), float(np.quantile(boot, 0.025)),
            float(np.quantile(boot, 0.975)), float(min(p, 1.0)))


def main() -> None:
    d26 = pd.read_csv(HERE / "lambdas_2026.csv", parse_dates=["date"])
    d26["week"] = d26["date"].dt.to_period("W").astype(str)
    print("replay 2025…", flush=True)
    d25 = replay("2025-07-01", "2025-12-01")
    d25.to_csv(HERE / "lambdas_2025.csv", index=False)

    x26, x25 = long_residuals(d26), long_residuals(d25)

    # ---- H1: por liga, con B-H y estabilidad ----------------------------
    rows = []
    for lg, g in x26.groupby("league"):
        m, lo, hi, p = week_block_ci(g["r2"].to_numpy(), g["week"].to_numpy())
        m25 = x25.loc[x25["league"] == lg, "r2"].mean()
        rows.append({"liga": lg, "genero": "F" if lg in WOMEN else "M",
                     "r2_2026": round(m, 3), "ci_lo": round(lo, 3),
                     "ci_hi": round(hi, 3), "p": round(p, 4),
                     "r2_2025": round(float(m25), 3),
                     "n": len(g)})
    t = pd.DataFrame(rows).sort_values("r2_2026", ascending=False)
    # Benjamini-Hochberg
    t = t.reset_index(drop=True)
    ps = t["p"].to_numpy()
    order = np.argsort(ps)
    m = len(ps)
    sig = np.zeros(m, dtype=bool)
    thresh = 0.10  # FDR 10%
    for rank, idx in enumerate(order, start=1):
        if ps[idx] <= rank / m * thresh:
            sig[order[:rank]] = True
    t["bh_sig_10"] = sig
    print(t.to_string(index=False))
    corr = float(np.corrcoef(t["r2_2025"], t["r2_2026"])[0, 1])
    print(f"estabilidad 2025→2026: corr = {corr:.3f}")

    fig, ax = plt.subplots(figsize=(6.5, 4.2))
    colors = t["genero"].map({"M": "#2a78d6", "F": "#e87ba4"})
    ax.scatter(t["r2_2025"], t["r2_2026"], c=colors, s=45, edgecolor="white", lw=0.6)
    for r in t.itertuples():
        ax.annotate(r.liga, (r.r2_2025, r.r2_2026), fontsize=7,
                    xytext=(4, 3), textcoords="offset points", color="#52514e")
    lims = [0.7, 1.9]
    ax.plot(lims, lims, "--", color="#c9c8c2", lw=1)
    ax.axhline(1, color="#e8e7e2"); ax.axvline(1, color="#e8e7e2")
    ax.set_xlabel("dispersión de Pearson r̄² — 2025 (dev)")
    ax.set_ylabel("dispersión de Pearson r̄² — 2026 (dev)")
    ax.set_title(f"H1: ¿la sobredispersión por liga es estable entre temporadas?\n"
                 f"correlación = {corr:.2f} · azul=masculina, rosa=femenina")
    fig.tight_layout(); fig.savefig(FIG / "overdispersion_by_league.png"); plt.close(fig)

    # ---- H2: E[r²|λ] por deciles ----------------------------------------
    fig, ax = plt.subplots(figsize=(6.8, 4))
    h2 = {}
    for name, x, c in [("2026", x26, "#008300"), ("2025", x25, "#eda100")]:
        x = x.copy()
        x["dec"] = pd.qcut(x["lam"], 10, duplicates="drop")
        xs, ys, los, his = [], [], [], []
        for _, g in x.groupby("dec", observed=True):
            m, lo, hi, _ = week_block_ci(g["r2"].to_numpy(), g["week"].to_numpy())
            xs.append(g["lam"].mean()); ys.append(m); los.append(lo); his.append(hi)
        ax.errorbar(xs, ys, yerr=[np.array(ys) - los, np.array(his) - ys],
                    fmt="o-", ms=4, lw=1.4, capsize=2, color=c, label=name)
        h2[name] = {"lam": [round(v, 3) for v in xs], "r2": [round(v, 3) for v in ys]}
        # phi de Var=lam+phi*lam^2:  E[(y-lam)^2 - lam] = phi*lam^2
        z = (x["y"] - x["lam"]) ** 2 - x["lam"]
        phi = float((z * x["lam"] ** 2).sum() / (x["lam"] ** 4).sum())
        h2[name]["phi_negbin"] = round(phi, 4)
        print(f"{name}: phi (Var=λ+φλ²) = {phi:.4f}")
    ax.axhline(1, color="#52514e", lw=1)
    ax.set_xlabel("λ̂ predicho (media del decil)")
    ax.set_ylabel("E[r² | λ]  (1 = Poisson)")
    ax.set_title("H2: ¿la sobredispersión depende de la intensidad prevista?\n"
                 "IC 95% por bloques semanales")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "overdispersion_by_lambda.png"); plt.close(fig)

    json.dump({"por_liga_2026": json.loads(t.to_json(orient="records")),
               "estabilidad_corr": corr, "por_lambda": h2},
              open(HERE / "overdispersion_structure.json", "w"), indent=2)
    print("→ overdispersion_structure.json + fig/")


if __name__ == "__main__":
    main()
