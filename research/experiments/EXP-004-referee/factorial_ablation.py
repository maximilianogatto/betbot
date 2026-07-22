"""EXP-004.4 — Matriz factorial G0 (referee §11) + ablaciones DC (referee §15.10).

Factorial 2×2 en 2026 (los cuatro comparten fallback a tasa base de liga y
regla de historia mínima): entrada {Δppg, Δposición} × forma {logística,
histograma}. Aísla si la diferencia G0 vs G0b venía de la variable o de la
forma funcional.

Ablaciones del DC en 2025 (ventana de desarrollo, para no gastar 2026):
completo vs sin-localía, sin-decay, sin-shrinkage (σ=10), sin-ρ; IC pareados
por bloques de semana.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.peak_models import loader  # noqa: E402
from research.peak_models.evaluate import PCOLS, ORDER, compare, rps_per_match, walk_forward  # noqa: E402
from research.peak_models.zoo import (  # noqa: E402
    league_rates, make_poisson, point_in_time_ppg, point_in_time_standing_diff)

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from block_bootstrap import block_bootstrap  # noqa: E402


def make_tabular(full_df: pd.DataFrame, *, feature: str, form: str):
    """Modelo de tabla unificado: feature ∈ {dppg, dpos}, form ∈ {logit, hist}."""

    from sklearn.linear_model import LogisticRegression

    if feature == "dppg":
        f = point_in_time_ppg(full_df).set_index("match_id")
        f["x"] = f["delta_ppg"]
        f.loc[(f["gp_home"] < 4) | (f["gp_away"] < 4), "x"] = np.nan
    else:
        f = point_in_time_standing_diff(full_df, min_pj=4).set_index("match_id")
        f["x"] = f["standing_diff"]
    xr = (-3.5, 3.5) if feature == "dppg" else (-1.0, 1.0)
    edges = np.linspace(*xr, 10)

    def model(train: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
        rates, glob = league_rates(train)
        tr = train.join(f[["x"]], on="match_id").dropna(subset=["x"])
        fitted = None
        if len(tr) >= 150 and tr["result"].nunique() == 3:
            if form == "logit":
                clf = LogisticRegression(max_iter=1000)
                clf.fit(tr[["x"]].to_numpy(), tr["result"].to_numpy())
                oi = [list(clf.classes_).index(c) for c in ORDER]
                fitted = ("logit", clf, oi)
            else:
                b = np.clip(np.digitize(tr["x"], edges[1:-1]), 0, 8)
                P = np.full((9, 3), np.nan)
                for k in range(9):
                    sel = tr.loc[b == k, "result"]
                    if len(sel) >= 15:
                        P[k] = [np.mean(sel == c) for c in ORDER]
                fitted = ("hist", P, None)
        out = []
        for r in rows.itertuples():
            x = f.at[r.match_id, "x"] if r.match_id in f.index else np.nan
            fallback = (rates.loc[r.league_code].to_numpy()
                        if r.league_code in rates.index else glob)
            if fitted is None or pd.isna(x):
                out.append(fallback); continue
            if fitted[0] == "logit":
                _, clf, oi = fitted
                out.append(clf.predict_proba([[x]])[0][oi])
            else:
                _, P, _ = fitted
                k = int(np.clip(np.digitize(x, edges[1:-1]), 0, 8))
                valid = ~np.isnan(P[:, 0])
                if not valid.any():
                    out.append(fallback); continue
                if not valid[k]:
                    ks = np.where(valid)[0]
                    k = int(ks[np.argmin(np.abs(ks - k))])
                p = P[k]
                out.append(p / p.sum())
        return pd.DataFrame(np.array(out), columns=PCOLS)

    return model


def main() -> None:
    df = loader.load_all()

    # ---- factorial 2x2 (2026) -------------------------------------------
    models = {f"{feat}_{form}": make_tabular(df, feature=feat, form=form)
              for feat in ("dppg", "dpos") for form in ("logit", "hist")}
    res = walk_forward(df, models, test_start="2026-01-01")
    res.to_csv(HERE / "factorial_2026.csv", index=False)
    res["rps"] = rps_per_match(res[PCOLS].to_numpy(), res["result"].to_numpy())
    tab = res.groupby("model")["rps"].mean().round(4)
    print("factorial 2x2 (RPS 2026):")
    print(tab.to_string())
    # contrastes pareados por bloques de semana
    pm = {m: g.set_index("match_id") for m, g in res.groupby("model")}
    contrasts = [("dppg_logit", "dpos_logit"), ("dppg_hist", "dpos_hist"),
                 ("dppg_logit", "dppg_hist"), ("dpos_logit", "dpos_hist")]
    fact = {"rps": json.loads(tab.to_json())}
    for a, b in contrasts:
        ids = pm[a].index.intersection(pm[b].index)
        d = pm[a].loc[ids, "rps"] - pm[b].loc[ids, "rps"]
        bs = block_bootstrap(d, pm[a].loc[ids, "cutoff"].astype(str), scheme="week")
        fact[f"{a}_menos_{b}"] = bs
        print(f"  {a} − {b}: Δ={bs['delta_mean']:+.4f} "
              f"IC=({bs['ci_lo']:+.4f},{bs['ci_hi']:+.4f})")
    json.dump(fact, open(HERE / "factorial.json", "w"), indent=2)

    # ---- ablaciones DC (2025) -------------------------------------------
    abl = {
        "dc_completo": make_poisson(halflife_days=120, ridge_sigma=0.75, fit_rho=True),
        "sin_decay": make_poisson(halflife_days=None, ridge_sigma=0.75, fit_rho=True),
        "sin_shrinkage": make_poisson(halflife_days=120, ridge_sigma=10.0, fit_rho=True),
        "sin_rho": make_poisson(halflife_days=120, ridge_sigma=0.75, fit_rho=False),
        "sin_localia": make_poisson(halflife_days=120, ridge_sigma=0.75, fit_rho=True,
                                    fit_home_adv=False),
    }
    res_a = walk_forward(df, abl, test_start="2025-07-01", test_end="2025-12-01")
    res_a["rps"] = rps_per_match(res_a[PCOLS].to_numpy(), res_a["result"].to_numpy())
    pm = {m: g.set_index("match_id") for m, g in res_a.groupby("model")}
    print("ablaciones (2025, walk-forward):")
    out_a = {}
    for m in abl:
        if m == "dc_completo":
            continue
        ids = pm[m].index.intersection(pm["dc_completo"].index)
        d = pm[m].loc[ids, "rps"] - pm["dc_completo"].loc[ids, "rps"]
        bs = block_bootstrap(d, pm[m].loc[ids, "cutoff"].astype(str), scheme="week")
        out_a[m] = bs
        print(f"  {m}: RPS={pm[m]['rps'].mean():.4f}  Δvs completo={bs['delta_mean']:+.4f} "
              f"IC=({bs['ci_lo']:+.4f},{bs['ci_hi']:+.4f})")
    out_a["dc_completo_rps"] = float(pm["dc_completo"]["rps"].mean())
    json.dump(out_a, open(HERE / "ablations.json", "w"), indent=2)


if __name__ == "__main__":
    main()
