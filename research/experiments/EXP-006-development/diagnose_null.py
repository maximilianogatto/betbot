"""Diagnóstico del resultado null (por qué P eligió Poisson en los 27 folds).

NO cambia reglas ni parámetros; sólo explica por qué ni S_full ni S_tau_fixed
son inner_eligible. Reproducible: usa lambdas_2025_full.csv (producido por la
corrida única) y las funciones congeladas de lambda_redesign.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import lambda_redesign as L  # noqa: E402

HERE = Path(__file__).parent


def main() -> None:
    df = pd.read_csv(HERE / "lambdas_2025_full.csv", parse_dates=["date"])
    train = df[df["date"] < "2025-09-01"]
    test = df[(df["date"] >= "2025-09-01") & (df["date"] < "2025-10-01")]
    pois_ll = float(L.score_logloss_vec(train, 0, 0).mean())
    print(f"train={len(train)} test={len(test)} | poisson ll_train={pois_ll:.4f}\n")
    for fam in ("S_full", "S_tau_fixed"):
        pred = L.fit_family(fam, train, seed=41000)
        b1, b2 = L.region_borders(train)
        lh, la = pred.lam_corr_sides(test)
        y = np.concatenate([test["hg"].to_numpy(), test["ag"].to_numpy()])
        lamc = np.concatenate([lh, la])
        reg = L.region_label(lamc, b1, b2)
        ll = float(pred.score_logloss(train).mean())
        resid = {r: round(float((y[reg == r] == 0).mean() - np.exp(-lamc[reg == r]).mean()), 3)
                 for r in ("baja", "media", "alta")}
        bias_low = float((y[reg == "baja"] - lamc[reg == "baja"]).mean())
        print(f"{fam}: a={pred.a:.3f} tau={pred.tau:.3f}")
        print(f"  (a) mejora log-loss marginal: {ll:.4f} < {pois_ll:.4f} = {ll < pois_ll}")
        print(f"  (b) residuo P0 por region {resid} -> sobrecorrige baja (>{L.EPS0}) = "
              f"{any(v > L.EPS0 for v in resid.values())}")
        print(f"  (c) sesgo region baja {bias_low:+.3f} -> |.|<= {L.EPS_LAMBDA} = "
              f"{abs(bias_low) <= L.EPS_LAMBDA}")
        print(f"  => inner_eligible = {ll < pois_ll and not any(v > L.EPS0 for v in resid.values()) and abs(bias_low) <= L.EPS_LAMBDA}\n")
    print("Conclusión: ambas mejoran el promedio pero violan las cotas de la región\n"
          "baja (sobrecorrigen y voltean el sesgo). Ninguna es elegible -> P = Poisson.")


if __name__ == "__main__":
    main()
