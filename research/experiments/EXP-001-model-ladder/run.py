"""EXP-001 — Escalera de modelos 1X2 sobre Finlandia (protocolo §4/§6).

Pregunta: ¿los modelos de goles (Poisson / Dixon-Coles con decaimiento y
shrinkage) superan al baseline G0 (logística sobre delta_ppg) y a la tasa base,
bajo walk-forward semanal honesto?

Protocolo:
1. Selección de hiperparámetros (halflife, sigma, rho) SOLO con walk-forward
   dentro de 2025 (test 2025-07-01 → 2025-11-30). 2026 no se toca.
2. Corrida final: walk-forward semanal sobre TODA la temporada 2026 jugada.
3. Métricas: RPS (primaria), log-loss, Brier, ECE + bootstrap pareado vs G0.

Correr:  research/.venv/bin/python research/experiments/EXP-001-model-ladder/run.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.peak_models import loader  # noqa: E402
from research.peak_models.evaluate import compare, walk_forward  # noqa: E402
from research.peak_models.zoo import base_rate, make_logistic_dppg, make_poisson  # noqa: E402

HERE = Path(__file__).parent
GRID_HALFLIFE = [None, 120.0, 240.0]
GRID_SIGMA = [0.75, 1.5]


def main() -> None:
    df = loader.load_matches()
    print(f"dataset: {len(df)} partidos jugados "
          f"({df.date.min().date()} → {df.date.max().date()})", flush=True)

    # ---- 1. selección de hiperparámetros en 2025 ------------------------
    t0 = time.time()
    tuning_models = {}
    for hl in GRID_HALFLIFE:
        for sg in GRID_SIGMA:
            tuning_models[f"poisson_hl{hl or 0:.0f}_sg{sg}"] = make_poisson(
                halflife_days=hl, ridge_sigma=sg)
    print(f"tuning: {len(tuning_models)} configs, walk-forward 2025-07→2025-12",
          flush=True)
    tune_res = walk_forward(df, tuning_models,
                            test_start="2025-07-01", test_end="2025-12-01")
    tune_table = compare(tune_res, baseline=list(tuning_models)[0])
    print(tune_table[["n", "rps", "log_loss"]].round(4).to_string(), flush=True)
    best_name = tune_table["rps"].idxmin()
    best_hl = None if "_hl0_" in best_name else float(best_name.split("_hl")[1].split("_")[0])
    best_sg = float(best_name.split("_sg")[1])
    print(f"mejor config: {best_name} (hl={best_hl}, sigma={best_sg}) "
          f"[{time.time()-t0:.0f}s]", flush=True)

    # rho on/off con la mejor config, mismo split de tuning
    rho_res = walk_forward(
        df,
        {"dc_rho": make_poisson(halflife_days=best_hl, ridge_sigma=best_sg, fit_rho=True),
         "dc_norho": make_poisson(halflife_days=best_hl, ridge_sigma=best_sg)},
        test_start="2025-07-01", test_end="2025-12-01")
    rho_table = compare(rho_res, baseline="dc_norho")
    print(rho_table[["n", "rps", "log_loss"]].round(4).to_string(), flush=True)
    use_rho = bool(rho_table["rps"].idxmin() == "dc_rho")
    print(f"rho: {'sí' if use_rho else 'no'}", flush=True)

    # ---- 2. corrida final en 2026 ---------------------------------------
    final_models = {
        "b0_base_rate": base_rate,
        "g0_logistic_dppg": make_logistic_dppg(df),
        "poisson_plain": make_poisson(halflife_days=None, ridge_sigma=best_sg),
        "dc_best": make_poisson(halflife_days=best_hl, ridge_sigma=best_sg,
                                fit_rho=use_rho),
    }
    print("corrida final 2026…", flush=True)
    res = walk_forward(df, final_models, test_start="2026-01-01")
    res.to_csv(HERE / "walkforward_2026.csv", index=False)
    table = compare(res, baseline="g0_logistic_dppg")
    print(table.round(4).to_string(), flush=True)

    # segmentos: por liga y por historia disponible
    per_league = (res.assign(rps=lambda d: rps_rows(d))
                  .groupby(["model", "league_code"])["rps"].mean().unstack().round(4))
    print(per_league.to_string(), flush=True)

    config = {
        "experiment": "EXP-001-model-ladder",
        "date_run": pd.Timestamp.now().isoformat(),
        "dataset": {"n_matches": int(len(df)),
                    "range": [str(df.date.min().date()), str(df.date.max().date())]},
        "tuning": {"grid_halflife": GRID_HALFLIFE, "grid_sigma": GRID_SIGMA,
                   "window": ["2025-07-01", "2025-12-01"],
                   "best": {"halflife_days": best_hl, "ridge_sigma": best_sg,
                            "fit_rho": use_rho}},
        "final_window": ["2026-01-01", str(df.date.max().date())],
        "refit": "weekly (Monday cutoff)",
    }
    (HERE / "config.json").write_text(json.dumps(config, indent=2))
    results = {
        "tuning_2025": json.loads(tune_table.reset_index().to_json(orient="records")),
        "rho_check_2025": json.loads(rho_table.reset_index().to_json(orient="records")),
        "final_2026": json.loads(table.reset_index().to_json(orient="records")),
        "rps_by_league_2026": json.loads(per_league.reset_index().to_json(orient="records")),
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2))
    print(f"listo [{time.time()-t0:.0f}s] → results.json / walkforward_2026.csv",
          flush=True)


def rps_rows(d: pd.DataFrame):
    from research.peak_models.evaluate import PCOLS, rps_per_match
    return rps_per_match(d[PCOLS].to_numpy(), d["result"].to_numpy())


if __name__ == "__main__":
    main()
