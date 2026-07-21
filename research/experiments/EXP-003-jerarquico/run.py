"""EXP-003 — Jerárquico multi-liga (MAP empírico-Bayes) + diagnóstico M1.

Preguntas:
1. ¿El pooling jerárquico (grafo de equipos compartido dentro del país +
   intercepts por liga/cluster con shrinkage) mejora al Dixon-Coles por liga?
2. ¿El nivel de cluster (C1/C2 congelado con 2025) agrega sobre el nivel liga?
3. ¿El jerárquico arregla la anomalía M1 (ascendidos con historia en otra división)?

Protocolo: τs elegidos con walk-forward 2025 (jul→nov); 2026 solo para el final.
Correr:  research/.venv/bin/python research/experiments/EXP-003-jerarquico/run.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.peak_models import loader  # noqa: E402
from research.peak_models.evaluate import (  # noqa: E402
    PCOLS, compare, paired_bootstrap, rps_per_match, walk_forward)
from research.peak_models.zoo import make_hier  # noqa: E402

HERE = Path(__file__).parent


def main() -> None:
    t0 = time.time()
    df = loader.load_all()
    clusters = pd.read_csv(HERE / "league_clusters.csv")
    cmap = dict(zip(clusters.league_code, clusters.cluster))
    print(f"dataset {len(df)} | clusters: {sorted(set(cmap.values()))}", flush=True)

    # ---- 1. grid de taus en 2025 ----------------------------------------
    grid = {}
    for tl in (0.05, 0.15, 0.5):
        grid[f"jer_tl{tl}"] = make_hier({l: "c0" for l in cmap}, tau_league=tl)
    tune = walk_forward(df, grid, test_start="2025-07-01", test_end="2025-12-01")
    tt = compare(tune, baseline=list(grid)[0])
    print(tt[["n", "rps", "log_loss"]].round(4).to_string(), flush=True)
    best = tt["rps"].idxmin()
    tau_l = float(best.split("tl")[1])
    print(f"tau_league={tau_l}  [{time.time()-t0:.0f}s]", flush=True)

    # ---- 2. corrida final 2026 ------------------------------------------
    finals = {
        "jer_pais": make_hier({l: "c0" for l in cmap}, tau_league=tau_l),
        "jer_cluster": make_hier(cmap, tau_league=tau_l, tau_cluster=0.25),
    }
    res = walk_forward(df, finals, test_start="2026-01-01")
    prev = pd.read_csv(ROOT / "research/experiments/EXP-002-multiliga/walkforward_2026.csv",
                       parse_dates=["date"])
    prev["match_id"] = prev["match_id"].astype(str)
    keep_prev = prev[prev.model.isin(["dc_best", "stack_cal", "b0_base_rate"])]
    allres = pd.concat([keep_prev.drop(columns=[c for c in keep_prev.columns
                                                if c not in res.columns]), res],
                       ignore_index=True)
    allres.to_csv(HERE / "walkforward_2026.csv", index=False)
    table = compare(allres, baseline="dc_best")
    print(table.round(4).to_string(), flush=True)

    # ---- 3. desgloses y diagnóstico M1 ----------------------------------
    allres["rps"] = rps_per_match(allres[PCOLS].to_numpy(), allres["result"].to_numpy())
    meta = df[["match_id", "country", "league_code"]].drop_duplicates("match_id")
    allres = allres.merge(meta[["match_id", "country"]], on="match_id", how="left")
    by_country = allres.groupby(["model", "country"])["rps"].mean().unstack().round(4)
    by_league = allres.groupby(["model", "league_code"])["rps"].mean().unstack().round(4)
    print(by_country.to_string(), flush=True)
    print(by_league[["M1", "M2", "M1L"]].to_string(), flush=True)

    # movilidad entre divisiones: equipos con historia en otra liga del pais
    d25 = df[df.season.astype(str) == "2025"]
    d26 = df[df.season.astype(str) == "2026"]
    prev_league = {}
    for r in d25.itertuples():
        prev_league[f"{r.country}|{r.home_team_id}"] = r.league_code
        prev_league[f"{r.country}|{r.away_team_id}"] = r.league_code
    movers = set()
    for r in d26.itertuples():
        for tid in (f"{r.country}|{r.home_team_id}", f"{r.country}|{r.away_team_id}"):
            if tid in prev_league and prev_league[tid] != r.league_code:
                movers.add(tid)
    d26 = d26.copy()
    d26["has_mover"] = [
        (f"{r.country}|{r.home_team_id}" in movers) or (f"{r.country}|{r.away_team_id}" in movers)
        for r in d26.itertuples()]
    mv = d26[["match_id", "has_mover"]].copy()
    mv["match_id"] = mv["match_id"].astype(str)
    seg = allres.merge(mv, on="match_id", how="inner")
    seg_table = (seg.groupby(["model", "has_mover"])["rps"].agg(["mean", "size"])
                 .round(4).unstack())
    print("RPS según partidos con equipos que cambiaron de división:", flush=True)
    print(seg_table.to_string(), flush=True)

    # bootstrap jer_pais vs dc_best en el segmento con movers
    pm = {m: g.set_index("match_id")["rps"] for m, g in allres.groupby("model")}
    mover_ids = seg[(seg.model == "dc_best") & seg.has_mover]["match_id"]
    bs_mov = paired_bootstrap(pm["dc_best"].loc[mover_ids].to_numpy(),
                              pm["jer_pais"].loc[mover_ids].to_numpy())
    ids_m1 = allres[(allres.model == "dc_best")
                    & (allres.league_code == "M1")]["match_id"]
    bs_m1 = paired_bootstrap(pm["dc_best"].loc[ids_m1].to_numpy(),
                             pm["jer_pais"].loc[ids_m1].to_numpy())
    print(f"jer_pais vs dc en movers: Δ={bs_mov['delta_mean']:.4f} "
          f"IC=({bs_mov['ci_lo']:.4f},{bs_mov['ci_hi']:.4f})", flush=True)
    print(f"jer_pais vs dc en M1:     Δ={bs_m1['delta_mean']:.4f} "
          f"IC=({bs_m1['ci_lo']:.4f},{bs_m1['ci_hi']:.4f})", flush=True)

    json.dump({
        "tau_league_grid_2025": json.loads(tt.reset_index().to_json(orient="records")),
        "tau_league_best": tau_l,
        "final_2026": json.loads(table.reset_index().to_json(orient="records")),
        "rps_by_country": json.loads(by_country.reset_index().to_json(orient="records")),
        "rps_by_league": json.loads(by_league.reset_index().to_json(orient="records")),
        "n_movers_2026": len(movers),
        "movers_segment": json.loads(seg_table.to_json()),
        "bootstrap_movers_jer_vs_dc": bs_mov,
        "bootstrap_m1_jer_vs_dc": bs_m1,
    }, open(HERE / "results.json", "w"), indent=2)
    print(f"listo [{time.time()-t0:.0f}s]", flush=True)


if __name__ == "__main__":
    main()
