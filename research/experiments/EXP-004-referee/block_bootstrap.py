"""EXP-004.1 — Intervalos con dependencia: bootstrap por bloques (referee §3).

El bootstrap i.i.d. por partido ignora que: los partidos de una semana salen del
mismo ajuste, comparten equipos y régimen. Acá se rehacen las comparaciones
centrales bajo cuatro esquemas de remuestreo y se compara la sensibilidad:

  iid          — partido a partido (el original, cota inferior de varianza)
  week         — bloques = semana de predicción (cutoff)
  week_league  — bloques = semana × liga (unidad de ajuste real del DC)
  moving4      — bloques móviles circulares de 4 semanas consecutivas

En todos los casos el estadístico es la media de Δrps por partido (pareado);
remuestrear bloques preserva la correlación intra-bloque.
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
    PCOLS, logloss_per_match, rps_per_match)

HERE = Path(__file__).parent
HERE.mkdir(exist_ok=True)
N_BOOT = 4000


def load_results() -> pd.DataFrame:
    r3 = pd.read_csv(ROOT / "research/experiments/EXP-003-jerarquico/walkforward_2026.csv",
                     parse_dates=["date", "cutoff"])
    r2 = pd.read_csv(ROOT / "research/experiments/EXP-002-multiliga/walkforward_2026.csv",
                     parse_dates=["date", "cutoff"])
    r2 = r2[r2.model.isin(["g0_logistic_dppg", "g0b_binned_standing"])]
    res = pd.concat([r3, r2[r3.columns.intersection(r2.columns)]], ignore_index=True)
    res["match_id"] = res["match_id"].astype(str)
    res["rps"] = rps_per_match(res[PCOLS].to_numpy(), res["result"].to_numpy())
    res["log_loss"] = logloss_per_match(
        res[PCOLS].to_numpy(), res["result"].to_numpy())
    return res


def block_bootstrap(delta: pd.Series, blocks: pd.Series, *, scheme: str,
                    seed: int = 7) -> dict:
    """CI de mean(delta) remuestreando bloques enteros con reemplazo."""

    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"d": delta.to_numpy(), "b": blocks.to_numpy()})
    if scheme == "iid":
        v = df["d"].to_numpy()
        idx = rng.integers(0, len(v), size=(N_BOOT, len(v)))
        means = v[idx].mean(axis=1)
    elif scheme in ("block", "week", "week_league"):
        groups = [g["d"].to_numpy() for _, g in df.groupby("b", sort=True)]
        nb = len(groups)
        means = np.empty(N_BOOT)
        for i in range(N_BOOT):
            pick = rng.integers(0, nb, size=nb)
            sample = np.concatenate([groups[j] for j in pick])
            means[i] = sample.mean()
    elif scheme.startswith("moving"):
        L = int(scheme.replace("moving", ""))
        keys = sorted(df["b"].unique())
        groups = {k: g["d"].to_numpy() for k, g in df.groupby("b", sort=True)}
        nb = len(keys)
        n_starts = int(np.ceil(nb / L))
        means = np.empty(N_BOOT)
        for i in range(N_BOOT):
            starts = rng.integers(0, nb, size=n_starts)
            sample = np.concatenate([groups[keys[(s + o) % nb]]
                                     for s in starts for o in range(L)])
            means[i] = sample.mean()
    else:
        raise ValueError(scheme)
    return {"delta_mean": float(df["d"].mean()),
            "ci_lo": float(np.quantile(means, 0.025)),
            "ci_hi": float(np.quantile(means, 0.975)),
            "p_better": float((means < 0).mean()),
            "n_blocks": int(blocks.nunique()) if scheme != "iid" else int(len(df))}


def main() -> None:
    res = load_results()
    wide = {m: g.set_index("match_id") for m, g in res.groupby("model")}
    comparisons = [
        ("dc_best", "g0_logistic_dppg"),      # negativo = DC mejor
        ("stack_cal", "dc_best"),
        ("jer_pais", "dc_best"),
        ("dc_best", "b0_base_rate"),
    ]
    out = {}
    rows = []
    for target, base in comparisons:
        common = wide[target].index.intersection(wide[base].index)
        t = wide[target].loc[common]
        week = t["cutoff"].astype(str)
        wl = week + "|" + t["league_code"]
        for metric in ("rps", "log_loss"):
            d = t[metric] - wide[base].loc[common, metric]
            for scheme, blocks in [("iid", week), ("week", week),
                                   ("week_league", wl), ("moving4", week)]:
                bs = block_bootstrap(d, blocks, scheme=scheme)
                key = f"{target}_vs_{base}"
                out.setdefault(key, {}).setdefault(metric, {})[scheme] = bs
                rows.append({"comparacion": f"{target} − {base}",
                             "metrica": metric, "esquema": scheme,
                             "delta": round(bs["delta_mean"], 4),
                             "ci_lo": round(bs["ci_lo"], 4),
                             "ci_hi": round(bs["ci_hi"], 4),
                             "p_mejor": round(bs["p_better"], 3),
                             "n_bloques": bs["n_blocks"]})
    table = pd.DataFrame(rows)
    print(table.to_string(index=False))
    json.dump(out, open(HERE / "block_bootstrap.json", "w"), indent=2)
    table.to_csv(HERE / "block_bootstrap.csv", index=False)


if __name__ == "__main__":
    main()
