"""EXP-004.7 — Recalibrador específico de empate (Línea 2 del programa).

Hipótesis del director: logit P(D) = α + β1·logit(p_D^DC) + β2·s + β3·d + β4·s·d
con s = log(λH+λA) (intensidad total) y d = |log(λH/λA)| (desigualdad).
Se entrena SOLO con predicciones DC out-of-sample previas al cutoff
(lambdas 2025 jul-nov + 2026 hasta la semana anterior); 1−P(D) se reparte
entre H y A preservando su razón original del DC.

Evaluación dev (2026 ≤ 20-jul): vs dc_best y stack_cal en RPS, log-loss y
pendiente/ECE del empate, IC por bloques semanales.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.peak_models.evaluate import (  # noqa: E402
    ORDER, PCOLS, ece, logloss_per_match, rps_per_match)
from research.peak_models.models import probs_1x2, score_matrix  # noqa: E402

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from block_bootstrap import block_bootstrap  # noqa: E402
from calibration_deep import calib_slope  # noqa: E402


def load_oos() -> pd.DataFrame:
    frames = []
    for f in ["lambdas_2025.csv", "lambdas_2026.csv"]:
        d = pd.read_csv(HERE / f, parse_dates=["date"])
        frames.append(d)
    d = pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True)
    # lambdas_2025.csv no guardó rho (columna solo en el replay 2026); ρ es
    # minúsculo y estas probabilidades son features de entrenamiento del meta —
    # usar ρ=0 para la historia 2025 es despreciable.
    if "rho" not in d.columns:
        d["rho"] = 0.0
    d["rho"] = d["rho"].fillna(0.0)
    probs = np.array([probs_1x2(score_matrix(r.lam_h, r.lam_a, r.rho))
                      for r in d.itertuples()])
    d[["p_home", "p_draw", "p_away"]] = probs
    d["s"] = np.log(d["lam_h"] + d["lam_a"])
    d["dneq"] = np.abs(np.log(d["lam_h"] / d["lam_a"]))
    d["logit_pd"] = np.log(d["p_draw"] / (1 - d["p_draw"]))
    d["is_draw"] = (d["hg"] == d["ag"]).astype(int)
    d["result"] = np.select([d.hg > d.ag, d.hg == d.ag], ["H", "D"], "A")
    d["week"] = d["date"].dt.to_period("W").astype(str)
    if "match_id" not in d.columns:
        d["match_id"] = d.index.astype(str)
    return d


FEATS = ["logit_pd", "s", "dneq", "sd"]


def main() -> None:
    from sklearn.linear_model import LogisticRegression

    d = load_oos()
    d["sd"] = d["s"] * d["dneq"]
    test = d[d["date"] >= pd.Timestamp("2026-01-01")].copy()

    out_rows = []
    for wk in sorted(test["week"].unique()):
        cutoff = test.loc[test["week"] == wk, "date"].min()
        tr = d[d["date"] < cutoff.normalize() - pd.Timedelta(days=cutoff.weekday())]
        te = test[test["week"] == wk].copy()
        if len(tr) < 300:
            te["p_draw_new"] = te["p_draw"]
        else:
            clf = LogisticRegression(max_iter=2000)
            clf.fit(tr[FEATS].to_numpy(), tr["is_draw"].to_numpy())
            te["p_draw_new"] = clf.predict_proba(te[FEATS].to_numpy())[:, 1]
        ratio = te["p_home"] / (te["p_home"] + te["p_away"])
        te["p_home_new"] = (1 - te["p_draw_new"]) * ratio
        te["p_away_new"] = (1 - te["p_draw_new"]) * (1 - ratio)
        out_rows.append(te)
    res = pd.concat(out_rows, ignore_index=True)

    P_dc = res[["p_home", "p_draw", "p_away"]].to_numpy()
    P_new = res[["p_home_new", "p_draw_new", "p_away_new"]].to_numpy()
    y = res["result"].to_numpy()

    metrics = {}
    for name, P in [("dc", P_dc), ("draw_recal", P_new)]:
        slope, inter = calib_slope(P[:, 1], (y == "D").astype(int))
        metrics[name] = {
            "rps": round(float(rps_per_match(P, y).mean()), 4),
            "log_loss": round(float(logloss_per_match(P, y).mean()), 4),
            "ece_D": round(ece(P, y, "D"), 4),
            "slope_D": round(slope, 3),
        }
    print(pd.DataFrame(metrics).T.to_string())

    contrasts = {}
    for metric, fn in [("rps", rps_per_match), ("log_loss", logloss_per_match)]:
        delta = pd.Series(fn(P_new, y) - fn(P_dc, y))
        bs = block_bootstrap(delta, res["week"], scheme="week")
        contrasts[metric] = bs
        print(f"draw_recal − dc [{metric}]: Δ={bs['delta_mean']:+.4f} "
              f"IC=({bs['ci_lo']:+.4f},{bs['ci_hi']:+.4f}) p={bs['p_better']:.3f}")

    # comparación con stack_cal (mismos partidos, del walkforward EXP-003)
    wf = pd.read_csv(ROOT / "research/experiments/EXP-003-jerarquico/walkforward_2026.csv",
                     parse_dates=["date"])
    wf["match_id"] = wf["match_id"].astype(str)
    sc = wf[wf.model == "stack_cal"].set_index("match_id")
    res["match_id"] = res["match_id"].astype(str)
    ids = res.set_index("match_id").index.intersection(sc.index)
    r2 = res.set_index("match_id").loc[ids]
    P_sc = sc.loc[ids, PCOLS].to_numpy()
    y2 = r2["result"].to_numpy()
    P_new2 = r2[["p_home_new", "p_draw_new", "p_away_new"]].to_numpy()
    delta = pd.Series(logloss_per_match(P_new2, y2) - logloss_per_match(P_sc, y2))
    bs = block_bootstrap(delta, r2["week"], scheme="week")
    contrasts["vs_stack_cal_logloss"] = bs
    print(f"draw_recal − stack_cal [log_loss]: Δ={bs['delta_mean']:+.4f} "
          f"IC=({bs['ci_lo']:+.4f},{bs['ci_hi']:+.4f})")

    json.dump({"metrics": metrics, "contrasts": contrasts,
               "n_test": int(len(res))},
              open(HERE / "draw_recalibrator.json", "w"), indent=2)
    print("→ draw_recalibrator.json")


if __name__ == "__main__":
    main()
