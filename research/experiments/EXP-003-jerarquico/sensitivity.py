"""Análisis de sensibilidad y dinámica (EXP-003, sección §sensibilidad del paper).

Figuras deterministas (exactas, sin ajuste):
1. rho_draw_curve.png — P(empate) exacta vs ρ para pares (λH, λA) típicos.
2. shrinkage_curve.png — factor de encogimiento normal-normal exacto vs nº de
   partidos, para varios σ (la mecánica James-Stein del ridge).
3. elo_dynamics.png — mapa dinámico de Elo: trayectorias del sistema
   determinista bajo distintos K (estable / sobreamortiguado / oscilante).

Figura computada (walk-forward 2025, nunca 2026):
4. contour_hl_sigma.png — curvas de nivel de RPS(half-life, σ) del DC por liga.
   (La corre `--contour`; tarda ~10-15 min.)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.peak_models.models import score_matrix, probs_1x2  # noqa: E402

HERE = Path(__file__).parent
FIG = HERE / "fig"
FIG.mkdir(exist_ok=True)
plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True,
                     "grid.color": "#e8e7e2", "axes.axisbelow": True})


def fig_rho_draw() -> None:
    rhos = np.linspace(-0.25, 0.25, 61)
    pairs = [(1.1, 0.9, "parejo, pocos goles"), (1.6, 1.3, "parejo, muchos goles"),
             (2.2, 0.8, "favorito claro")]
    colors = ["#2a78d6", "#008300", "#eda100"]
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    for (lh, la, lbl), c in zip(pairs, colors):
        pd_ = [probs_1x2(score_matrix(lh, la, r))[1] for r in rhos]
        ax.plot(rhos, pd_, lw=1.8, color=c, label=f"λH={lh}, λA={la} ({lbl})")
    ax.axvline(0, color="#52514e", lw=1)
    ax.axvspan(-0.07, -0.01, color="#e8e7e2", alpha=0.6)
    ax.annotate("rango ajustado\nen EXP-001/002", (-0.065, ax.get_ylim()[0] + 0.01),
                fontsize=7, color="#52514e")
    ax.set_xlabel("ρ (corrección Dixon-Coles de marcadores bajos)")
    ax.set_ylabel("P(empate) exacta")
    ax.set_title("Sensibilidad de la probabilidad de empate a ρ (cálculo exacto)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "rho_draw_curve.png"); plt.close(fig)


def fig_shrinkage() -> None:
    n = np.arange(0, 35)
    s2_obs = 0.65  # var de la evidencia por partido en escala log-ataque (ilustrativo)
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    for sigma, c in [(0.25, "#2a78d6"), (0.75, "#008300"), (1.5, "#eda100"),
                     (10.0, "#52514e")]:
        k = n * sigma**2 / (n * sigma**2 + s2_obs)
        ax.plot(n, k, lw=1.8, color=c,
                label=f"σ={sigma}" + ("  (≈ MLE puro)" if sigma == 10 else ""))
    ax.axvline(5, color="#c9c8c2", ls="--", lw=1)
    ax.annotate("5 PJ", (5.3, 0.05), fontsize=7, color="#52514e")
    ax.set_xlabel("partidos jugados del equipo (n)")
    ax.set_ylabel("peso de los datos vs prior  κ(n)")
    ax.set_title("Encogimiento normal-normal exacto: κ = nσ²/(nσ²+s²)\n"
                 "σ→0: todos los equipos iguales · σ→∞: sin regularización")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "shrinkage_curve.png"); plt.close(fig)


def fig_elo_dynamics() -> None:
    # sistema determinista de 2 equipos: x = diferencia de rating
    # x_{t+1} = x_t + 2K (p* − E(x_t)),  E(x) = 1/(1+10^{−x/400})
    def E(x):
        return 1.0 / (1.0 + 10 ** (-x / 400.0))

    p_true = 0.75
    x_star = 400 * np.log10(p_true / (1 - p_true))
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for K, c in [(8, "#2a78d6"), (32, "#008300"), (256, "#eda100"),
                 (1600, "#e34948")]:
        x = 0.0
        xs = [x]
        for _ in range(60):
            x = x + 2 * K * (p_true - E(x))
            xs.append(x)
        ax.plot(xs, lw=1.5, color=c, label=f"K={K}")
    ax.axhline(x_star, color="#52514e", ls="--", lw=1)
    ax.annotate(f"punto fijo x* = {x_star:.0f}", (38, x_star + 25), fontsize=8,
                color="#52514e")
    ax.set_xlabel("partidos (iteración del mapa)")
    ax.set_ylabel("diferencia de rating x_t")
    ax.set_title("Mapa dinámico de Elo (determinista, p*=0.75): convergencia para K chico;\n"
                 "el mapa discreto bifurca a oscilaciones/aperiodicidad para K≫ (la EDO límite es\n"
                 "monótona 1D, sin caos) — los K prácticos (8-32) están en zona estable")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "elo_dynamics.png"); plt.close(fig)


def contour() -> None:
    import pandas as pd

    from research.peak_models import loader
    from research.peak_models.evaluate import compare, walk_forward
    from research.peak_models.zoo import make_poisson

    df = loader.load_all()
    hls = [30.0, 60.0, 120.0, 240.0, 480.0]
    sgs = [0.3, 0.5, 0.75, 1.25, 2.0]
    models = {f"hl{h:.0f}_sg{s}": make_poisson(halflife_days=h, ridge_sigma=s,
                                               fit_rho=True)
              for h in hls for s in sgs}
    res = walk_forward(df, models, test_start="2025-07-01", test_end="2025-12-01")
    tab = compare(res, baseline=list(models)[0])
    Z = np.full((len(sgs), len(hls)), np.nan)
    for name, row in tab.iterrows():
        h = float(name.split("hl")[1].split("_")[0])
        s = float(name.split("sg")[1])
        Z[sgs.index(s), hls.index(h)] = row["rps"]
    json.dump({"hls": hls, "sgs": sgs, "rps": Z.tolist()},
              open(HERE / "contour_grid.json", "w"), indent=2)

    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    cs = ax.contourf(hls, sgs, Z, levels=14, cmap="Greens_r")
    fig.colorbar(cs, label="RPS walk-forward 2025 (menor = mejor)")
    ax.plot(120, 0.75, "o", color="#e34948", ms=8)
    ax.annotate("config elegida\n(EXP-001, solo FIN)", (120, 0.75),
                xytext=(10, 10), textcoords="offset points", fontsize=8,
                color="#e34948")
    i, j = np.unravel_index(np.nanargmin(Z), Z.shape)
    ax.plot(hls[j], sgs[i], "*", color="#2a78d6", ms=12)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks(hls, [str(int(h)) for h in hls])
    ax.set_yticks(sgs, [str(s) for s in sgs])
    ax.set_xlabel("half-life del decaimiento temporal (días, escala log)")
    ax.set_ylabel("σ del shrinkage de equipos (escala log)")
    ax.set_title("Curvas de nivel del RPS sobre (half-life, σ) — DC por liga,\n"
                 "walk-forward 2025 (17 ligas, 2.351 partidos). ★ = mínimo del grid")
    fig.tight_layout(); fig.savefig(FIG / "contour_hl_sigma.png"); plt.close(fig)
    print(tab[["rps"]].round(4).sort_values("rps").head(8).to_string())


if __name__ == "__main__":
    fig_rho_draw()
    fig_shrinkage()
    fig_elo_dynamics()
    print("figuras deterministas listas")
    if "--contour" in sys.argv:
        contour()
        print("contour listo")
