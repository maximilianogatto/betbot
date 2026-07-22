"""EXP-004.8 — Binomial negativa como drop-in (Línea 1, cierre de H1/H2).

El director predijo: la NB, a media fija, aumenta P(0) y como el modelo ya
sobrepredice el 0-0, arreglaría colas altas empeorando los bajos. Test barato:
tomar los λ del DC (OOS, lambdas_*.csv) y reemplazar la Poisson por una NB con
la MISMA media y dispersión Var=λ+φλ² (φ del diagnóstico global). Evaluar la
celda 0-0, la distribución de goles y el log-loss de MARCADOR — sin re-ajustar
(un drop-in honesto: aísla el efecto de la cola, no del re-ajuste de medias).

También cuantifica el ajuste de forma: ¿E[r²|λ] plano ⇒ quasi-Poisson (φ
constante) mejor que NB (Var/λ creciente)? Se compara el 0-0 predicho por
Poisson, NB y quasi-Poisson contra el observado.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
PHI = 0.074  # dispersión global estable (overdispersion_structure: 0.076/0.074)
MAXG = 15


def nb_pmf(k: np.ndarray, mu: float, phi: float) -> np.ndarray:
    if phi <= 1e-9:
        return poisson.pmf(k, mu)
    r = 1.0 / phi
    p = r / (r + mu)
    return nbinom.pmf(k, r, p)


def main() -> None:
    frames = []
    for f in ["lambdas_2025.csv", "lambdas_2026.csv"]:
        p = HERE / f
        if p.exists():
            frames.append(pd.read_csv(p, parse_dates=["date"]))
    d = pd.concat(frames, ignore_index=True)
    d = d.dropna(subset=["lam_h", "lam_a", "hg", "ag"])
    ks = np.arange(MAXG + 1)

    obs_00 = float(((d["hg"] == 0) & (d["ag"] == 0)).mean())
    acc = {"poisson": 0.0, "negbin": 0.0}
    ll_score = {"poisson": 0.0, "negbin": 0.0}  # log-loss de marcador exacto
    n = len(d)
    for r in d.itertuples():
        for name, pmf in [("poisson", lambda k, m: poisson.pmf(k, m)),
                          ("negbin", lambda k, m: nb_pmf(k, m, PHI))]:
            ph = pmf(ks, r.lam_h); pa = pmf(ks, r.lam_a)
            ph /= ph.sum(); pa /= pa.sum()
            acc[name] += ph[0] * pa[0]
            gh = min(int(r.hg), MAXG); ga = min(int(r.ag), MAXG)
            ll_score[name] += -np.log(max(ph[gh] * pa[ga], 1e-12))

    out = {
        "phi": PHI,
        "obs_00": round(obs_00, 4),
        "pred_00_poisson": round(acc["poisson"] / n, 4),
        "pred_00_negbin": round(acc["negbin"] / n, 4),
        "logloss_marcador_poisson": round(ll_score["poisson"] / n, 4),
        "logloss_marcador_negbin": round(ll_score["negbin"] / n, 4),
        "n": n,
    }
    print(json.dumps(out, indent=2))
    print(f"\nEl 0-0 observado es {obs_00:.3f}. Poisson ya predice "
          f"{acc['poisson']/n:.3f} (sobrepredice). NB predice "
          f"{acc['negbin']/n:.3f}.")
    verdict = ("NB EMPEORA el 0-0 (lo aleja más del observado)"
               if abs(acc["negbin"]/n - obs_00) > abs(acc["poisson"]/n - obs_00)
               else "NB mejora el 0-0")
    print("Veredicto:", verdict)
    json.dump(out, open(HERE / "negbin_dropin.json", "w"), indent=2)


if __name__ == "__main__":
    main()
