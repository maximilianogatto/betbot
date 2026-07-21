"""EXP-002 — Escalera multi-país (FIN+SWE+NOR) + capa de forma/momentum.

Preguntas:
1. ¿El resultado de EXP-001 (DC > G0 > base) generaliza a Suecia y Noruega?
2. ¿Las features de forma/momentum ajustadas por calidad del rival (Elo,
   pendiente de rating, adj_form, SoS, PPG-vs-más-fuertes) agregan señal
   POR ENCIMA del Dixon-Coles? (stack_full vs stack_cal = ablación)

Protocolo: idéntico a EXP-001 (walk-forward semanal, hiperparámetros de DC
congelados de EXP-001 con un chequeo de transferencia en 2025, 2026 intocado
para la comparación final).

Correr:  research/.venv/bin/python research/experiments/EXP-002-multiliga/run.py
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
    PCOLS, compare, rps_per_match, walk_forward)
from research.peak_models.features import build_features  # noqa: E402
from research.peak_models.zoo import (  # noqa: E402
    STACK_FEATS, base_rate, make_logistic_dppg, make_poisson, make_stacked)

HERE = Path(__file__).parent
BEST = {"halflife_days": 120.0, "ridge_sigma": 0.75, "fit_rho": True}


def main() -> None:
    t0 = time.time()
    df = loader.load_all()
    print(f"dataset: {len(df)} partidos, {df.league_code.nunique()} ligas, "
          f"paises: {sorted(df.country.unique())}", flush=True)

    feats = build_features(df)
    feats.to_csv(HERE / "features.csv", index=False)
    print(f"features: {len(feats)} filas [{time.time()-t0:.0f}s]", flush=True)

    # ---- 1. chequeo de transferencia de hiperparámetros (solo 2025 SWE+NOR)
    nord = df[df.country.isin(["SWE", "NOR"])]
    chk = walk_forward(
        nord,
        {"dc_hl120": make_poisson(**BEST),
         "dc_nodecay": make_poisson(halflife_days=None, ridge_sigma=0.75, fit_rho=True)},
        test_start="2025-07-01", test_end="2025-12-01")
    chk_table = compare(chk, baseline="dc_nodecay")
    print("transferencia hl120 (SWE+NOR 2025):", flush=True)
    print(chk_table[["n", "rps", "log_loss"]].round(4).to_string(), flush=True)

    # ---- 2. pase OOS de DC para entrenar el meta-modelo -----------------
    print("pase OOS dc_best 2025-06→hoy…", flush=True)
    oos = walk_forward(df, {"dc_best": make_poisson(**BEST)},
                       test_start="2025-06-15")
    oos.to_csv(HERE / "oos_dc.csv", index=False)
    print(f"OOS: {len(oos)} predicciones [{time.time()-t0:.0f}s]", flush=True)

    # ---- 3. comparación final 2026 --------------------------------------
    stack_cal = make_stacked(oos, feats, use_features=False)
    stack_full = make_stacked(oos, feats, use_features=True)
    res = walk_forward(
        df,
        {"b0_base_rate": base_rate,
         "g0_logistic_dppg": make_logistic_dppg(df),
         "stack_cal": stack_cal,
         "stack_full": stack_full},
        test_start="2026-01-01")
    dc26 = oos[oos["date"] >= pd.Timestamp("2026-01-01")].copy()
    res = pd.concat([res, dc26], ignore_index=True)
    res.to_csv(HERE / "walkforward_2026.csv", index=False)

    table = compare(res, baseline="dc_best")
    print(table.round(4).to_string(), flush=True)

    res["rps"] = rps_per_match(res[PCOLS].to_numpy(), res["result"].to_numpy())
    meta = df[["match_id", "country"]].drop_duplicates("match_id")
    res = res.merge(meta, on="match_id", how="left")
    by_country = res.groupby(["model", "country"])["rps"].mean().unstack().round(4)
    by_league = res.groupby(["model", "league_code"])["rps"].mean().unstack().round(4)
    print(by_country.to_string(), flush=True)

    coef = getattr(stack_full, "last_coef", None)
    coef_out = None
    if coef:
        classes, W = coef
        names = ["logit_H", "logit_D"] + STACK_FEATS
        coef_out = {c: dict(zip(names, np.round(w, 4).tolist()))
                    for c, w in zip(classes, W)}
        print("coeficientes stack_full (última semana):", flush=True)
        print(json.dumps(coef_out, indent=1)[:800], flush=True)

    (HERE / "config.json").write_text(json.dumps({
        "experiment": "EXP-002-multiliga",
        "date_run": pd.Timestamp.now().isoformat(),
        "dataset": {"n": int(len(df)),
                    "countries": {c: int(n) for c, n in df.country.value_counts().items()},
                    "leagues": int(df.league_code.nunique()),
                    "range": [str(df.date.min().date()), str(df.date.max().date())]},
        "dc_params": BEST, "stack_features": STACK_FEATS,
        "refit": "weekly", "final_window": ["2026-01-01", str(df.date.max().date())],
    }, indent=2))
    (HERE / "results.json").write_text(json.dumps({
        "hl_transfer_check_2025": json.loads(chk_table.reset_index().to_json(orient="records")),
        "final_2026": json.loads(table.reset_index().to_json(orient="records")),
        "rps_by_country": json.loads(by_country.reset_index().to_json(orient="records")),
        "rps_by_league": json.loads(by_league.reset_index().to_json(orient="records")),
        "stack_full_coefficients": coef_out,
    }, indent=2))
    print(f"listo [{time.time()-t0:.0f}s]", flush=True)


if __name__ == "__main__":
    main()
