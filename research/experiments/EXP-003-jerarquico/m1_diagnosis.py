"""EXP-003a — Diagnóstico de la anomalía M1 (Ykkönen).

Hipótesis en juego:
H1: la desventaja de DC vs G0 en M1 es señal real (estructura de la liga).
H2: es fluctuación de muestra chica (n≈90) no corregida por comparaciones múltiples.
H3: la causa son ascendidos sin historia (la resuelve el jerárquico).

Tests: bootstrap pareado DC vs G0 restringido a M1; recuento de recambio de
plantel de la liga; tasas de empate/sorpresa 2025 vs 2026; y el resultado del
jerárquico en M1 (de results.json). Figura resumen con los cuatro paneles.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.peak_models import loader  # noqa: E402
from research.peak_models.evaluate import PCOLS, paired_bootstrap, rps_per_match  # noqa: E402

HERE = Path(__file__).parent
FIG = HERE / "fig"
plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True,
                     "grid.color": "#e8e7e2", "axes.axisbelow": True})


def main() -> None:
    df = loader.load_all()
    res2 = pd.read_csv(ROOT / "research/experiments/EXP-002-multiliga/walkforward_2026.csv",
                       parse_dates=["date"])
    res2["match_id"] = res2["match_id"].astype(str)
    res2["rps"] = rps_per_match(res2[PCOLS].to_numpy(), res2["result"].to_numpy())
    m1_ids = df[(df.league_code == "M1") & (df.season.astype(str) == "2026")]["match_id"].astype(str)
    pm = {m: g.set_index("match_id")["rps"] for m, g in res2.groupby("model")}
    ids = pm["dc_best"].index.intersection(m1_ids)

    out = {}
    for rival in ["g0_logistic_dppg", "stack_cal", "b0_base_rate"]:
        bs = paired_bootstrap(pm[rival].loc[ids].to_numpy(),
                              pm["dc_best"].loc[ids].to_numpy())
        out[f"dc_vs_{rival}_en_M1"] = bs
        print(f"DC − {rival} en M1 (n={len(ids)}): Δ={bs['delta_mean']:+.4f} "
              f"IC=({bs['ci_lo']:+.4f},{bs['ci_hi']:+.4f}) P(DC mejor)={bs['p_better']:.2f}")

    # recambio y tasas por temporada, todas las ligas FIN (contexto)
    rows = []
    for lg in ["VL", "M1L", "M1", "M2", "NL"]:
        d25 = df[(df.league_code == lg) & (df.season.astype(str) == "2025")]
        d26 = df[(df.league_code == lg) & (df.season.astype(str) == "2026")]
        t25 = set(d25.home_team_id) | set(d25.away_team_id)
        t26 = set(d26.home_team_id) | set(d26.away_team_id)
        rows.append({
            "liga": lg,
            "equipos_2026": len(t26),
            "nuevos_2026": len(t26 - t25),
            "pct_nuevos": round(len(t26 - t25) / len(t26), 2) if t26 else np.nan,
            "empates_2025": round((d25.result == "D").mean(), 3),
            "empates_2026": round((d26.result == "D").mean(), 3),
            "local_2025": round((d25.result == "H").mean(), 3),
            "local_2026": round((d26.result == "H").mean(), 3),
        })
    ctx = pd.DataFrame(rows)
    print(ctx.to_string(index=False))
    out["contexto_ligas_fin"] = json.loads(ctx.to_json(orient="records"))

    # figura: IC de las tres comparaciones + tasas M1
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.4))
    ax = axes[0]
    labels = {"g0_logistic_dppg": "DC − G0", "stack_cal": "DC − stack_cal",
              "b0_base_rate": "DC − tasa base"}
    for i, (k, lbl) in enumerate(labels.items()):
        bs = out[f"dc_vs_{k}_en_M1"]
        # signo: paired_bootstrap(a=rival, b=dc) → delta = dc − rival; negativo = DC mejor
        ax.plot([bs["ci_lo"], bs["ci_hi"]], [i, i], color="#2a78d6", lw=2,
                solid_capstyle="round")
        ax.plot(bs["delta_mean"], i, "o", ms=7, color="#2a78d6")
    ax.axvline(0, color="#52514e", lw=1)
    ax.set_yticks(range(len(labels)), list(labels.values()))
    ax.invert_yaxis()
    ax.set_xlabel("Δ RPS en M1 2026 (negativo = DC mejor) · IC 95%")
    ax.set_title(f"La 'anomalía M1' bajo bootstrap pareado (n={len(ids)})")

    ax = axes[1]
    x = np.arange(len(ctx))
    w = 0.35
    ax.bar(x - w / 2, ctx["empates_2025"], w, color="#2a78d6", label="empates 2025")
    ax.bar(x + w / 2, ctx["empates_2026"], w, color="#eda100", label="empates 2026")
    ax.set_xticks(x, ctx["liga"])
    ax.set_ylabel("tasa de empates")
    ax.set_title("Corrimiento de la tasa de empates por liga (FIN)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "m1_diagnosis.png"); plt.close(fig)

    json.dump(out, open(HERE / "m1_diagnosis.json", "w"), indent=2)
    print("→ m1_diagnosis.json / fig/m1_diagnosis.png")


if __name__ == "__main__":
    main()
