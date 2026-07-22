"""Tuning de dc_dyn_gamma (H4 de EXP-005) — SOLO datos 2025 (regla del director).

La localía gamma se re-estima con kernel propio 2^(-dt/H_gamma) (perfil con
solución cerrada, ver models.py). Acá se elige H_gamma con:
1. pseudo-walk-forward 2025 (test jul→nov) sobre los 3 países;
2. sensibilidad excluyendo un país por vez (¿el ranking es estable?);
3. contraste vs el DC congelado (gamma con el kernel general de 120d).

El H_gamma elegido queda CONGELADO en AMENDMENT-002 con el hash del commit.
Este script no toca ningún partido de 2026.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.peak_models import loader  # noqa: E402
from research.peak_models.evaluate import PCOLS, compare, logloss_per_match, rps_per_match, walk_forward  # noqa: E402
from research.peak_models.zoo import make_poisson  # noqa: E402

sys.path.insert(0, str(ROOT / "research/experiments/EXP-004-referee"))
from block_bootstrap import block_bootstrap  # noqa: E402

HERE = Path(__file__).parent
GRID = [30.0, 60.0, 120.0, 240.0, None]  # None = baseline (kernel general)


def run_window(df: pd.DataFrame) -> pd.DataFrame:
    models = {}
    for hg in GRID:
        name = f"dyn_g{int(hg)}" if hg else "dc_base"
        models[name] = make_poisson(halflife_days=120.0, ridge_sigma=0.75,
                                    fit_rho=True, gamma_halflife=hg)
    return walk_forward(df, models, test_start="2025-07-01",
                        test_end="2025-12-01")


def main() -> None:
    df = loader.load_all()
    df = df[df["date"] < pd.Timestamp("2026-01-01")]  # SOLO 2025

    out = {}
    res = run_window(df)
    res["rps"] = rps_per_match(res[PCOLS].to_numpy(), res["result"].to_numpy())
    res["log_loss"] = logloss_per_match(res[PCOLS].to_numpy(), res["result"].to_numpy())
    table = compare(res, baseline="dc_base")
    print("global 2025:")
    print(table[["n", "rps", "log_loss"]].round(4).to_string(), flush=True)
    out["global"] = json.loads(table.reset_index().to_json(orient="records"))

    # contraste con IC por bloques (semana) del mejor candidato vs base
    pm = {m: g.set_index("match_id") for m, g in res.groupby("model")}
    best = table.drop(index="dc_base")["rps"].idxmin()
    ids = pm[best].index.intersection(pm["dc_base"].index)
    for metric in ("rps", "log_loss"):
        d = pm[best].loc[ids, metric] - pm["dc_base"].loc[ids, metric]
        bs = block_bootstrap(d, pm[best].loc[ids, "cutoff"].astype(str), scheme="week")
        out[f"best_vs_base_{metric}"] = {"best": best, **bs}
        print(f"{best} − dc_base [{metric}]: Δ={bs['delta_mean']:+.4f} "
              f"IC=({bs['ci_lo']:+.4f},{bs['ci_hi']:+.4f})", flush=True)

    # Sensibilidad por subconjuntos: se excluye un país tanto del ajuste como
    # de la evaluación. No es validación de transferencia al país retenido.
    loco = {}
    for held_out in ["FIN", "SWE", "NOR"]:
        sub = df[df["country"] != held_out]
        r = run_window(sub)
        r["rps"] = rps_per_match(r[PCOLS].to_numpy(), r["result"].to_numpy())
        rank = r.groupby("model")["rps"].mean().sort_values()
        loco[held_out] = {m: round(v, 4) for m, v in rank.items()}
        print(f"sin {held_out}: {list(rank.index)}", flush=True)
    out["leave_one_country_excluded_sensitivity"] = loco

    json.dump(out, open(HERE / "dyn_gamma_tuning.json", "w"), indent=2)
    print("→ dyn_gamma_tuning.json", flush=True)


if __name__ == "__main__":
    main()
