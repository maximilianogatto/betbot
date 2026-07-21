"""Clustering de ligas por perfil estadístico (EXP-003, nivel intermedio del jerárquico).

Descriptores por liga (solo 2025 — la asignación de cluster se congela ANTES de
tocar 2026, coherente con el protocolo): media de goles, tasa de empates,
ventaja localía (P(H)−P(A)), tasa over 2.5, desvío del diferencial de goles.
Ward + silhouette para elegir k. Salidas: league_clusters.csv, fig/dendrogram.png,
fig/cluster_scatter.png.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from sklearn.metrics import silhouette_score

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.peak_models import loader  # noqa: E402

HERE = Path(__file__).parent
FIG = HERE / "fig"
FIG.mkdir(exist_ok=True)

plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True,
                     "grid.color": "#e8e7e2", "axes.axisbelow": True})


def league_descriptors(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["season"].astype(str) == "2025"].copy()  # solo 2025 (congelado)
    d["total"] = d.home_goals + d.away_goals
    agg = d.groupby(["country", "league_code"]).agg(
        goles=("total", "mean"),
        empates=("result", lambda s: (s == "D").mean()),
        localia=("result", lambda s: (s == "H").mean() - (s == "A").mean()),
        over25=("total", lambda s: (s > 2.5).mean()),
        sd_dg=("total", "std"),
        n=("total", "size"),
    ).reset_index()
    dg = d.assign(dg=d.home_goals - d.away_goals).groupby(["country", "league_code"])["dg"].std()
    agg["sd_dg"] = dg.to_numpy()
    return agg


def main() -> None:
    df = loader.load_all()
    desc = league_descriptors(df)
    feats = ["goles", "empates", "localia", "over25", "sd_dg"]
    X = desc[feats].astype(float).to_numpy()
    Xz = (X - X.mean(0)) / X.std(0)

    Z = linkage(Xz, method="ward")
    sil = {}
    for k in range(2, 7):
        lab = fcluster(Z, k, criterion="maxclust")
        sil[k] = float(silhouette_score(Xz, lab))
    k_best = max(sil, key=sil.get)
    labels = fcluster(Z, k_best, criterion="maxclust")
    desc["cluster"] = [f"C{c}" for c in labels]
    desc.to_csv(HERE / "league_clusters.csv", index=False)
    print("silhouette por k:", {k: round(v, 3) for k, v in sil.items()})
    print("k elegido:", k_best)
    print(desc[["league_code", "country", "goles", "empates", "localia", "cluster"]]
          .sort_values("cluster").round(3).to_string(index=False))

    # --- dendrograma ---
    fig, ax = plt.subplots(figsize=(8, 4))
    dendrogram(Z, labels=desc["league_code"].tolist(), ax=ax,
               color_threshold=Z[-(k_best - 1), 2])
    ax.set_ylabel("distancia de Ward (features z-score)")
    ax.set_title(f"Dendrograma de ligas (datos 2025) — corte en k={k_best} "
                 f"(silhouette {sil[k_best]:.2f})")
    fig.tight_layout(); fig.savefig(FIG / "dendrogram.png"); plt.close(fig)

    # --- scatter goles/empates coloreado por cluster ---
    colors = {"C1": "#2a78d6", "C2": "#008300", "C3": "#e87ba4", "C4": "#eda100",
              "C5": "#1baf7a", "C6": "#eb6834"}
    fig, ax = plt.subplots(figsize=(7, 4.6))
    for c, g in desc.groupby("cluster"):
        ax.scatter(g["goles"], g["empates"], s=60, color=colors[c], label=c,
                   edgecolor="white", lw=0.8)
        for r in g.itertuples():
            ax.annotate(r.league_code, (r.goles, r.empates), fontsize=7,
                        xytext=(4, 3), textcoords="offset points", color="#52514e")
    ax.set_xlabel("goles por partido (2025)")
    ax.set_ylabel("tasa de empates (2025)")
    ax.set_title("Clusters de ligas en el plano goles-empates")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "cluster_scatter.png"); plt.close(fig)
    print("figuras →", FIG)


if __name__ == "__main__":
    main()
