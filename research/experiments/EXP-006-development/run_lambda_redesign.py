"""Corrida ÚNICA del protocolo λ v3.1 sobre 2025 (paso 4 del orden autorizado).

1. Regenera (y cachea) los λ DC-OOS de todo 2025 por walk-forward semanal.
2. Corre el procedimiento adaptativo P (nested walk-forward) y promotion_pass.
3. Corre la selección interna final sobre todo-2025 (spec que se congelaría).
4. Publica TODO en lambda_redesign.json, aunque promotion_pass=False, sin
   modificar reglas ni parámetros.

Sólo 2025. No toca EXP-005 ni producción. No se re-ejecuta con variaciones.
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
sys.path.insert(0, str(Path(__file__).parent))

import lambda_redesign as L  # noqa: E402
from research.peak_models import loader  # noqa: E402
from research.peak_models.models import fit_poisson  # noqa: E402

HERE = Path(__file__).parent
LAM_CSV = HERE / "lambdas_2025_full.csv"
DC = {"halflife_days": 120.0, "ridge_sigma": 0.75, "fit_rho": True}
FIN = {"VL", "M1L", "M1", "M2", "NL"}


def country_of(code: str) -> str:
    if code.startswith("SW-"):
        return "SWE"
    if code.startswith("NO-"):
        return "NOR"
    return "FIN" if code in FIN else "?"


def regen_lambdas() -> pd.DataFrame:
    if LAM_CSV.exists():
        return pd.read_csv(LAM_CSV, parse_dates=["date"])
    df = loader.load_all()
    played = df.dropna(subset=["home_goals", "away_goals"]).sort_values("date")
    y2025 = played[(played["date"] >= "2025-01-01") & (played["date"] < "2026-01-01")]
    rows = []
    weeks = sorted(y2025["date"].dt.to_period("W-SUN").unique())
    for wk in weeks:
        cutoff = wk.start_time
        train = played[played["date"] < cutoff]
        test = y2025[y2025["date"].dt.to_period("W-SUN") == wk]
        fits = {}
        for r in test.itertuples():
            lg = r.league_code
            if lg not in fits:
                fits[lg] = fit_poisson(train[train["league_code"] == lg], asof=cutoff, **DC)
            f = fits[lg]
            if f is None:
                continue
            lh, la, _ = f.rates(r.home_team_id, r.away_team_id)
            rows.append({"date": r.date, "league": lg, "country": country_of(lg),
                         "hg": int(r.home_goals), "ag": int(r.away_goals),
                         "lam_h": lh, "lam_a": la})
    out = pd.DataFrame(rows)
    out["week"] = L.week_label(out["date"])
    out.to_csv(LAM_CSV, index=False)
    return out


def final_selection(df: pd.DataFrame) -> dict:
    """Selección interna sobre todo-2025: la spec que se congelaría (outer_ix=999)."""
    all_train = df[df["date"] < pd.Timestamp("2025-12-01")]
    pred = L.select_family(all_train, outer_ix=999)
    diag = {"family": pred.family, "a": pred.a, "tau": pred.tau}
    if pred.family == "S_full":
        a, tau, conv = L.fit_s_full(all_train)
        diag["identifiability_note"] = "descriptivo (no gate en Opción A)"
        diag["refit_a"], diag["refit_tau"], diag["converged"] = a, tau, conv
    return diag


def main() -> None:
    t0 = time.time()
    df = regen_lambdas()
    print(f"λ 2025: {len(df)} partidos con λ DC-OOS "
          f"({df.date.min().date()}→{df.date.max().date()}) [{time.time()-t0:.0f}s]",
          flush=True)

    oos_m, oos_s, choices = L.run_outer(df, test_start="2025-06-01", test_end="2025-12-01")
    print(f"outer: {len(oos_m)} partidos test, {len(choices)} folds "
          f"[{time.time()-t0:.0f}s]", flush=True)
    prom = L.promotion_pass(oos_m, oos_s, choices)
    final = final_selection(df)

    result = {
        "protocol": "LAMBDA-REDESIGN-PROTOCOL.md v3.1 (Opción A)",
        "date_run": pd.Timestamp.now().isoformat(),
        "n_lambda_matches": int(len(df)),
        "n_outer_test_matches": int(len(oos_m)),
        "n_outer_folds": int(len(choices)),
        "selection_frequency": pd.Series(choices).value_counts().to_dict(),
        "final_selection_all2025": final,
        "promotion_pass": prom,
        "means": {
            "ll_P": float(oos_m["ll_P"].mean()),
            "ll_poisson": float(oos_m["ll_pois"].mean()),
            "ll_negbin": float(oos_m["ll_nb"].mean()),
            "rps_P": float(oos_m["rps_P"].mean()),
            "rps_poisson": float(oos_m["rps_pois"].mean()),
        },
    }
    (HERE / "lambda_redesign.json").write_text(json.dumps(result, indent=2))
    oos_m.to_csv(HERE / "lambda_redesign_oos_match.csv", index=False)
    oos_s.to_csv(HERE / "lambda_redesign_oos_side.csv", index=False)

    print(json.dumps(result, indent=2)[:2500], flush=True)
    print(f"\nPROMOTION_PASS = {prom['promotion_pass']}  [{time.time()-t0:.0f}s]",
          flush=True)
    print("→ lambda_redesign.json (+ oos csvs)", flush=True)


if __name__ == "__main__":
    main()
