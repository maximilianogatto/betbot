"""EXP-005 — Corrida confirmatoria ÚNICA (no ejecutar antes del cierre).

Guardas:
- se niega a correr antes del 2026-12-01 (salvo --dry-run, que solo valida el
  pipeline con datos ANTERIORES a la ventana);
- ventana confirmatoria: [2026-07-27, 2026-11-30) — AMENDMENT-001;
- hipótesis y análisis EXACTOS de REGISTERED.md; nada más se computa acá.

H1: RPS(dc_best) < RPS(g0)            → IC bloques semana excluye 0
H2: log-loss(stack_cal) < log-loss(dc) Y RPS(stack_cal) ≤ RPS(dc)+0.0005
H3: RPS(jer_pais) < RPS(dc) en ligas C1={M2, NL}
H4: RPS(dc_dyn_gamma) < RPS(dc), global  [si AMENDMENT-002 lo habilitó]
H5: var. residuos Pearson (H y A) > 1 con IC bloques semana

Una sola pasada; el resultado se escribe en confirmatory_results.json y NO se
re-ejecuta con variaciones.
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
from research.peak_models.evaluate import (  # noqa: E402
    PCOLS, logloss_per_match, rps_per_match, walk_forward)
from research.peak_models.models import fit_poisson  # noqa: E402
from research.peak_models.zoo import (  # noqa: E402
    base_rate, make_hier, make_logistic_dppg, make_poisson, make_stacked)

sys.path.insert(0, str(ROOT / "research/experiments/EXP-004-referee"))
from block_bootstrap import block_bootstrap  # noqa: E402

HERE = Path(__file__).parent
W_START, W_END = pd.Timestamp("2026-07-27"), pd.Timestamp("2026-11-30")
DC = dict(halflife_days=120.0, ridge_sigma=0.75, fit_rho=True)


def load_frozen_dyn_gamma() -> float | None:
    """H_gamma congelado por AMENDMENT-002; None si H4 no fue habilitada."""

    p = HERE / "AMENDMENT-002.md"
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        s = line.strip().strip("`").strip()
        if s.startswith("H_GAMMA_FROZEN:"):
            val = s.split(":", 1)[1].strip().lower()
            return None if val in ("none", "") else float(val)
    return None


def main(dry_run: bool = False) -> None:
    today = pd.Timestamp.now().normalize()
    if not dry_run and today < pd.Timestamp("2026-12-01"):
        raise SystemExit("VENTANA ABIERTA: no ejecutar antes del 2026-12-01 "
                         "(usar --dry-run para validar pipeline con datos previos).")
    out_path = HERE / ("dryrun_results.json" if dry_run else "confirmatory_results.json")
    if not dry_run and out_path.exists():
        raise SystemExit("confirmatory_results.json ya existe: la pasada única "
                         "ya se hizo. No re-ejecutar.")

    df = loader.load_all()
    if dry_run:
        start, end = pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-20")
    else:
        start, end = W_START, W_END
        n_after = (df["date"] >= W_END).sum()
        print(f"(partidos posteriores al cierre presentes: {n_after})")

    clusters = pd.read_csv(ROOT / "research/experiments/EXP-003-jerarquico/league_clusters.csv")
    cmap = dict(zip(clusters.league_code, clusters.cluster))
    hg = load_frozen_dyn_gamma()

    models = {
        "b0_base_rate": base_rate,
        "g0_logistic_dppg": make_logistic_dppg(df),
        "dc_best": make_poisson(**DC),
        "jer_pais": make_hier({l: "c0" for l in cmap}, tau_league=0.15),
    }
    if hg is not None:
        models["dc_dyn_gamma"] = make_poisson(**DC, gamma_halflife=hg)

    res = walk_forward(df, models, test_start=str(start.date()),
                       test_end=str(end.date()))
    # stack_cal: meta entrenada con OOS previas a cada cutoff (pase dc sobre
    # histórico + la propia ventana, siempre respetando date < cutoff)
    oos_hist = walk_forward(df, {"dc_best": make_poisson(**DC)},
                            test_start="2025-06-15", test_end=str(start.date()))
    oos_all = pd.concat([oos_hist, res[res.model == "dc_best"]], ignore_index=True)
    from research.peak_models.features import build_features
    feats = build_features(df)
    stack = walk_forward(df, {"stack_cal": make_stacked(oos_all, feats, use_features=False)},
                         test_start=str(start.date()), test_end=str(end.date()))
    res = pd.concat([res, stack], ignore_index=True)
    res.to_csv(HERE / ("dryrun_walkforward.csv" if dry_run else "confirmatory_walkforward.csv"),
               index=False)

    res["rps"] = rps_per_match(res[PCOLS].to_numpy(), res["result"].to_numpy())
    res["log_loss"] = logloss_per_match(res[PCOLS].to_numpy(), res["result"].to_numpy())
    pm = {m: g.set_index("match_id") for m, g in res.groupby("model")}

    def contrast(a: str, b: str, metric: str, leagues: list[str] | None = None) -> dict:
        ids = pm[a].index.intersection(pm[b].index)
        if leagues:
            ids = ids[pm[a].loc[ids, "league_code"].isin(leagues)]
        d = pm[a].loc[ids, metric] - pm[b].loc[ids, metric]
        return block_bootstrap(d, pm[a].loc[ids, "cutoff"].astype(str), scheme="week")

    out: dict = {"window": [str(start.date()), str(end.date())],
                 "dry_run": dry_run, "n": int(res.match_id.nunique()),
                 "rps": {m: round(float(g["rps"].mean()), 4) for m, g in res.groupby("model")}}
    out["H1"] = contrast("dc_best", "g0_logistic_dppg", "rps")
    out["H2_logloss"] = contrast("stack_cal", "dc_best", "log_loss")
    out["H2_rps"] = contrast("stack_cal", "dc_best", "rps")
    out["H3_C1"] = contrast("jer_pais", "dc_best", "rps", leagues=["M2", "NL"])
    if "dc_dyn_gamma" in pm:
        out["H4"] = contrast("dc_dyn_gamma", "dc_best", "rps")

    # H5: dispersión condicional en la ventana
    played = df.dropna(subset=["home_goals", "away_goals"]).sort_values("date")
    test = played[(played["date"] >= start) & (played["date"] < end)]
    rows = []
    for wk in sorted(test["date"].dt.to_period("W").unique()):
        cutoff = wk.start_time
        train = played[played["date"] < cutoff]
        fits = {}
        for r in test[test["date"].dt.to_period("W") == wk].itertuples():
            lg = r.league_code
            if lg not in fits:
                fits[lg] = fit_poisson(train[train["league_code"] == lg],
                                       asof=cutoff, **DC)
            if fits[lg] is None:
                continue
            lh, la, _ = fits[lg].rates(r.home_team_id, r.away_team_id)
            rows.append({"week": str(wk), "hg": r.home_goals, "ag": r.away_goals,
                         "lam_h": lh, "lam_a": la})
    lam = pd.DataFrame(rows)
    rng = np.random.default_rng(7)
    h5 = {}
    for side, y, l in [("H", "hg", "lam_h"), ("A", "ag", "lam_a")]:
        r2 = ((lam[y] - lam[l]) ** 2 / lam[l]).to_numpy()
        groups = [gr for _, g in lam.assign(r2=r2).groupby("week")
                  if len(gr := g["r2"].to_numpy())]
        boot = np.empty(4000)
        for i in range(4000):
            pick = rng.integers(0, len(groups), size=len(groups))
            boot[i] = np.concatenate([groups[j] for j in pick]).mean()
        h5[side] = {"estimate": round(float(r2.mean()), 4),
                    "ci_lo": round(float(np.quantile(boot, 0.025)), 4),
                    "ci_hi": round(float(np.quantile(boot, 0.975)), 4)}
    out["H5"] = h5

    json.dump(out, open(out_path, "w"), indent=2)
    print(json.dumps(out, indent=2)[:2000])
    print("→", out_path)


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
