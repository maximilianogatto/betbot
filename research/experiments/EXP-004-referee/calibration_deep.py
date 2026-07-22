"""EXP-004.3 — Calibración en profundidad (referee §12).

Para dc_best y stack_cal sobre 2026: ECE de las TRES clases, curvas de
confiabilidad con IC bootstrap por bin, pendiente e intercepto de calibración
(regresión logística sobre el logit de p), y descomposición de Murphy del Brier
(reliability − resolution + uncertainty) por clase.
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
from research.peak_models.evaluate import ORDER, PCOLS, ece  # noqa: E402

HERE = Path(__file__).parent
FIG = HERE / "fig"
FIG.mkdir(exist_ok=True)
plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True,
                     "grid.color": "#e8e7e2", "axes.axisbelow": True})

COLORS = {"dc_best": "#008300", "stack_cal": "#e87ba4"}


def murphy(p: np.ndarray, y: np.ndarray, bins: int = 10) -> dict:
    """Descomposición de Murphy del Brier binario con bins por cuantiles."""

    df = pd.DataFrame({"p": p, "y": y})
    df["bin"] = pd.qcut(df["p"], bins, duplicates="drop")
    g = df.groupby("bin", observed=True).agg(pk=("p", "mean"), ok=("y", "mean"),
                                             nk=("y", "size"))
    ybar = df["y"].mean()
    n = len(df)
    rel = float((g["nk"] / n * (g["pk"] - g["ok"]) ** 2).sum())
    res = float((g["nk"] / n * (g["ok"] - ybar) ** 2).sum())
    unc = float(ybar * (1 - ybar))
    return {"reliability": round(rel, 5), "resolution": round(res, 5),
            "uncertainty": round(unc, 5), "brier": round(rel - res + unc, 5)}


def calib_slope(p: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    from sklearn.linear_model import LogisticRegression

    z = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1 - 1e-6))
    clf = LogisticRegression(C=1e6, max_iter=1000).fit(z.reshape(-1, 1), y)
    return float(clf.coef_[0][0]), float(clf.intercept_[0])


def main() -> None:
    res = pd.read_csv(ROOT / "research/experiments/EXP-003-jerarquico/walkforward_2026.csv",
                      parse_dates=["date"])
    res["match_id"] = res["match_id"].astype(str)
    out = {}
    rng = np.random.default_rng(5)

    fig, axes = plt.subplots(2, 3, figsize=(10.5, 6.4), sharey=True)
    for row, model in enumerate(["dc_best", "stack_cal"]):
        g = res[res.model == model]
        for col, outcome in enumerate(ORDER):
            p = g[PCOLS[ORDER.index(outcome)]].to_numpy()
            y = (g["result"] == outcome).astype(int).to_numpy()
            e = ece(g[PCOLS].to_numpy(), g["result"].to_numpy(), outcome)
            slope, inter = calib_slope(p, y)
            dec = murphy(p, y)
            out[f"{model}_{outcome}"] = {"ece": round(e, 4), "slope": round(slope, 3),
                                         "intercept": round(inter, 3),
                                         "cal_in_large": round(float(p.mean() - y.mean()), 4),
                                         **dec}
            # reliability curve con IC bootstrap por bin
            qs = pd.qcut(p, 8, duplicates="drop")
            dfb = pd.DataFrame({"p": p, "y": y, "b": qs})
            xs, ys, lo, hi = [], [], [], []
            for _, gb in dfb.groupby("b", observed=True):
                xs.append(gb["p"].mean())
                obs = gb["y"].to_numpy()
                boots = obs[rng.integers(0, len(obs), size=(1500, len(obs)))].mean(axis=1)
                ys.append(obs.mean())
                lo.append(np.quantile(boots, 0.025)); hi.append(np.quantile(boots, 0.975))
            ax = axes[row, col]
            ax.errorbar(xs, ys, yerr=[np.array(ys) - lo, np.array(hi) - ys],
                        fmt="o-", color=COLORS[model], ms=4, lw=1.4, capsize=2)
            mx = max(max(xs) * 1.1, 0.4)
            ax.plot([0, mx], [0, mx], "--", color="#c9c8c2", lw=1)
            ax.set_title(f"{model} · P({outcome})  ECE={e:.3f}  slope={slope:.2f}",
                         fontsize=8)
            if col == 0:
                ax.set_ylabel("frecuencia observada")
            if row == 1:
                ax.set_xlabel("probabilidad predicha")
    fig.suptitle("Confiabilidad por clase con IC 95% por bin — 2026 walk-forward", y=1.0)
    fig.tight_layout(); fig.savefig(FIG / "reliability_3class.png"); plt.close(fig)

    tab = pd.DataFrame(out).T
    print(tab.to_string())
    json.dump(out, open(HERE / "calibration_deep.json", "w"), indent=2)


if __name__ == "__main__":
    main()
