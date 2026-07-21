"""Figuras principales de EXP-003: comparación con jerárquicos + segmento movers."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.peak_models.evaluate import PCOLS, rps_per_match  # noqa: E402

HERE = Path(__file__).parent
FIG = HERE / "fig"
plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True,
                     "grid.color": "#e8e7e2", "axes.axisbelow": True})

COLORS = {"b0_base_rate": "#52514e", "dc_best": "#008300",
          "stack_cal": "#e87ba4", "jer_pais": "#2a78d6", "jer_cluster": "#eda100"}
LABELS = {"b0_base_rate": "B0 tasa base", "dc_best": "DC por liga",
          "stack_cal": "DC recalibrado", "jer_pais": "Jerárquico (país)",
          "jer_cluster": "Jerárquico (cluster)"}


def main() -> None:
    res = pd.read_csv(HERE / "walkforward_2026.csv", parse_dates=["date"])
    res["match_id"] = res["match_id"].astype(str)
    res["rps"] = rps_per_match(res[PCOLS].to_numpy(), res["result"].to_numpy())
    pm = {m: g.set_index("match_id")["rps"] for m, g in res.groupby("model")}
    common = None
    for s in pm.values():
        common = s.index if common is None else common.intersection(s.index)

    rng = np.random.default_rng(23)
    fig, ax = plt.subplots(figsize=(7, 3.4))
    rows = []
    for m, s in pm.items():
        v = s.loc[common].to_numpy()
        idx = rng.integers(0, len(v), size=(3000, len(v)))
        boots = v[idx].mean(axis=1)
        rows.append((m, v.mean(), np.quantile(boots, 0.025), np.quantile(boots, 0.975)))
    rows.sort(key=lambda r: -r[1])
    for i, (m, mean, lo, hi) in enumerate(rows):
        ax.plot([lo, hi], [i, i], color=COLORS[m], lw=2, solid_capstyle="round")
        ax.plot(mean, i, "o", ms=7, color=COLORS[m])
        ax.annotate(f"{mean:.4f}", (hi, i), xytext=(6, -3),
                    textcoords="offset points", fontsize=8, color="#52514e")
    ax.set_yticks(range(len(rows)), [LABELS[r[0]] for r in rows])
    ax.set_xlabel("RPS 2026 (menor = mejor) · IC 95% bootstrap")
    ax.set_title("EXP-003: los jerárquicos NO mejoran al DC por liga (1.619 partidos)")
    fig.tight_layout(); fig.savefig(FIG / "hier_comparison.png"); plt.close(fig)

    # segmento movers
    import json
    seg = json.loads((HERE / "results.json").read_text())["movers_segment"]
    models = ["dc_best", "stack_cal", "jer_pais", "jer_cluster"]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    x = np.arange(len(models))
    w = 0.35
    no_mv = [seg["('mean', False)"][m] for m in models]
    mv = [seg["('mean', True)"][m] for m in models]
    ax.bar(x - w / 2, no_mv, w, color="#c9c8c2", label="sin equipos que cambiaron de división")
    ax.bar(x + w / 2, mv, w, color="#eb6834", label="con al menos un 'mover' (n=763)")
    for xi, v in zip(x + w / 2, mv):
        ax.annotate(f"{v:.3f}", (xi, v), ha="center", va="bottom", fontsize=7)
    ax.set_xticks(x, [LABELS[m] for m in models], fontsize=8)
    ax.set_ylim(0.19, 0.235)
    ax.set_ylabel("RPS medio 2026")
    ax.set_title("El pooling entre divisiones EMPEORA los partidos con ascendidos/descendidos:\n"
                 "la historia de otra división transfiere sesgada (escala de habilidad no comparable)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "movers_segment.png"); plt.close(fig)
    print("→ fig/hier_comparison.png, fig/movers_segment.png")


if __name__ == "__main__":
    main()
