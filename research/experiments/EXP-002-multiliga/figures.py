"""Figuras del informe EXP-002 (PNG bajo fig/).

Paleta categórica validada (dataviz reference, modo claro), asignación FIJA por
entidad en todas las figuras:
  b0 base rate -> gris de referencia, G0 -> azul, DC -> verde,
  stack_cal -> magenta, stack_full -> amarillo.
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

from research.peak_models.evaluate import (  # noqa: E402
    ORDER, PCOLS, paired_bootstrap, rps_per_match)
from research.peak_models.zoo import STACK_FEATS  # noqa: E402

HERE = Path(__file__).parent
FIG = HERE / "fig"
FIG.mkdir(exist_ok=True)

COLORS = {
    "b0_base_rate": "#52514e",
    "g0_logistic_dppg": "#2a78d6",
    "dc_best": "#008300",
    "stack_cal": "#e87ba4",
    "stack_full": "#eda100",
}
LABELS = {
    "b0_base_rate": "B0 tasa base",
    "g0_logistic_dppg": "G0 logística Δppg",
    "dc_best": "Dixon-Coles",
    "stack_cal": "DC recalibrado",
    "stack_full": "DC + forma/momentum",
}
plt.rcParams.update({"figure.dpi": 150, "font.size": 9,
                     "axes.edgecolor": "#c9c8c2", "axes.linewidth": 0.8,
                     "axes.grid": True, "grid.color": "#e8e7e2",
                     "grid.linewidth": 0.6, "axes.axisbelow": True})


def load() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    from research.peak_models import loader as data_loader

    res = pd.read_csv(HERE / "walkforward_2026.csv", parse_dates=["date"])
    res["match_id"] = res["match_id"].astype(str)
    if "country" not in res.columns:
        meta = data_loader.load_all()[["match_id", "country"]].drop_duplicates("match_id")
        res = res.merge(meta, on="match_id", how="left")
    feats = pd.read_csv(HERE / "features.csv", parse_dates=["date"])
    feats["match_id"] = feats["match_id"].astype(str)
    results = json.loads((HERE / "results.json").read_text())
    # fila a fila (cada fila lleva sus propias probabilidades) — nunca via
    # groupby+concatenate, que desalinea el orden de filas
    res["rps"] = rps_per_match(res[PCOLS].to_numpy(), res["result"].to_numpy())
    return res, feats, results


def per_match(res: pd.DataFrame) -> dict[str, pd.Series]:
    return {m: g.set_index("match_id")["rps"] for m, g in res.groupby("model")}


def fig_model_comparison(res: pd.DataFrame) -> None:
    pm = per_match(res)
    common = None
    for s in pm.values():
        common = s.index if common is None else common.intersection(s.index)
    rng = np.random.default_rng(11)
    rows = []
    for m, s in pm.items():
        v = s.loc[common].to_numpy()
        idx = rng.integers(0, len(v), size=(3000, len(v)))
        boots = v[idx].mean(axis=1)
        rows.append((m, v.mean(), np.quantile(boots, 0.025), np.quantile(boots, 0.975)))
    rows.sort(key=lambda r: -r[1])
    fig, ax = plt.subplots(figsize=(7, 3.2))
    for i, (m, mean, lo, hi) in enumerate(rows):
        ax.plot([lo, hi], [i, i], color=COLORS[m], lw=2, solid_capstyle="round")
        ax.plot(mean, i, "o", color=COLORS[m], ms=7)
        ax.annotate(f"{mean:.4f}", (hi, i), xytext=(6, -3),
                    textcoords="offset points", fontsize=8, color="#52514e")
    ax.set_yticks(range(len(rows)), [LABELS[r[0]] for r in rows])
    ax.set_xlabel("RPS en 2026 (menor = mejor) · punto = media, barra = IC 95% bootstrap")
    ax.set_title("Comparación de modelos — walk-forward semanal 2026, 3 países")
    fig.tight_layout(); fig.savefig(FIG / "model_comparison.png"); plt.close(fig)


def fig_rps_by_league(res: pd.DataFrame) -> None:
    keep = ["g0_logistic_dppg", "dc_best", "stack_full"]
    t = (res[res.model.isin(keep)]
         .groupby(["model", "country", "league_code"])["rps"].mean().reset_index())
    order = (t[t.model == "dc_best"]
             .sort_values(["country", "rps"])["league_code"].tolist())
    fig, ax = plt.subplots(figsize=(7.5, 6))
    for m in keep:
        g = t[t.model == m].set_index("league_code").reindex(order)
        ax.plot(g["rps"], range(len(order)), "o", ms=6, color=COLORS[m],
                label=LABELS[m], alpha=0.9)
    for i, lg in enumerate(order):
        ax.axhline(i, color="#e8e7e2", lw=0.5, zorder=0)
    ax.set_yticks(range(len(order)), order)
    ax.invert_yaxis()
    ax.set_xlabel("RPS 2026 (menor = mejor)")
    ax.set_title("RPS por liga — ¿dónde aporta cada modelo?")
    ax.legend(loc="lower right", frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "rps_by_league.png"); plt.close(fig)


def fig_calibration(res: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(9.5, 3.3), sharey=True)
    for ax, outcome in zip(axes, ORDER):
        col = PCOLS[ORDER.index(outcome)]
        for m in ["dc_best", "stack_full"]:
            g = res[res.model == m]
            p = g[col].to_numpy()
            hit = (g["result"] == outcome).astype(float).to_numpy()
            qs = np.quantile(p, np.linspace(0, 1, 9))
            bins = np.clip(np.searchsorted(qs[1:-1], p), 0, 7)
            xs = [p[bins == b].mean() for b in range(8) if (bins == b).any()]
            ys = [hit[bins == b].mean() for b in range(8) if (bins == b).any()]
            ax.plot(xs, ys, "o-", ms=4, lw=1.5, color=COLORS[m], label=LABELS[m])
        lim = max(0.65, ax.get_xlim()[1])
        ax.plot([0, lim], [0, lim], "--", color="#c9c8c2", lw=1, zorder=0)
        ax.set_title({"H": "P(local)", "D": "P(empate)", "A": "P(visita)"}[outcome])
        ax.set_xlabel("predicho")
    axes[0].set_ylabel("frecuencia observada")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Calibración por resultado — 2026 walk-forward", y=1.0)
    fig.tight_layout(); fig.savefig(FIG / "calibration.png"); plt.close(fig)


def fig_momentum(res: pd.DataFrame, feats: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.4))
    # (a) EDA: tasa H empírica por quintil de adj_form5_diff
    df = res[res.model == "dc_best"].merge(
        feats[["match_id", "adj_form5_diff", "ppg_vs_stronger8_diff"]], on="match_id")
    ax = axes[0]
    for col, color, lbl in [("adj_form5_diff", "#2a78d6", "sobre-rendimiento últ. 5 (Δ)"),
                            ("ppg_vs_stronger8_diff", "#008300", "PPG vs rivales más fuertes (Δ)")]:
        d = df.dropna(subset=[col]).copy()
        d["bin"] = pd.qcut(d[col], 5, duplicates="drop")
        g = d.groupby("bin", observed=True).agg(x=(col, "mean"),
                                                h=("result", lambda s: (s == "H").mean()))
        ax.plot(g["x"], g["h"], "o-", lw=1.5, ms=5, color=color, label=lbl)
    ax.axhline(df["result"].eq("H").mean(), color="#c9c8c2", ls="--", lw=1)
    ax.set_xlabel("valor de la feature (local − visita), quintiles")
    ax.set_ylabel("frecuencia de victoria local")
    ax.set_title("¿La forma ajustada por rival predice? (EDA 2026)")
    ax.legend(frameon=False, fontsize=8)
    # (b) inferencia: delta RPS stack_full vs stack_cal por país
    pm = per_match(res)
    meta = res[res.model == "dc_best"].set_index("match_id")["country"]
    ax = axes[1]
    rows = []
    ids_all = pm["stack_cal"].index.intersection(pm["stack_full"].index)
    for scope, ids in [("Total", ids_all)] + [
            (c, ids_all[meta.reindex(ids_all) == c]) for c in ["FIN", "SWE", "NOR"]]:
        bs = paired_bootstrap(pm["stack_cal"].loc[ids].to_numpy(),
                              pm["stack_full"].loc[ids].to_numpy())
        rows.append((scope, bs["delta_mean"], bs["ci_lo"], bs["ci_hi"]))
    for i, (scope, d, lo, hi) in enumerate(rows):
        ax.plot([lo, hi], [i, i], color="#eda100", lw=2, solid_capstyle="round")
        ax.plot(d, i, "o", ms=7, color="#eda100")
    ax.axvline(0, color="#52514e", lw=1)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlabel("Δ RPS (features − solo recalibración) · IC 95%\nnegativo = las features ayudan")
    ax.set_title("¿Aportan las features sobre Dixon-Coles?")
    fig.tight_layout(); fig.savefig(FIG / "momentum_effect.png"); plt.close(fig)


def fig_coefficients(results: dict) -> None:
    coef = results.get("stack_full_coefficients")
    if not coef:
        return
    names = ["logit_H", "logit_D"] + STACK_FEATS
    classes = list(coef.keys())
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    width = 0.27
    cls_colors = {"H": "#2a78d6", "D": "#e87ba4", "A": "#008300"}
    for j, cls in enumerate(["H", "D", "A"]):
        if cls not in coef:
            continue
        vals = [coef[cls].get(n, 0.0) for n in names]
        ax.bar(np.arange(len(names)) + (j - 1) * width, vals, width,
               color=cls_colors[cls], label=f"clase {cls}", edgecolor="white", lw=0.5)
    ax.axhline(0, color="#52514e", lw=1)
    ax.set_xticks(range(len(names)), names, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("coeficiente (features estandarizadas no — escala propia)")
    ax.set_title("Meta-modelo stack_full: qué pesa cada señal (última semana)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "stack_coefficients.png"); plt.close(fig)


def fig_league_profiles() -> None:
    from research.peak_models import loader
    df = loader.load_all()
    g = df.groupby(["country", "league_code"]).agg(
        goles=("home_goals", lambda s: np.nan), n=("match_id", "size")).reset_index()
    agg = df.assign(total=df.home_goals + df.away_goals,
                    draw=(df.result == "D").astype(float),
                    home=(df.result == "H").astype(float))
    g = agg.groupby(["country", "league_code"]).agg(
        goles=("total", "mean"), empates=("draw", "mean"),
        local=("home", "mean"), n=("total", "size")).reset_index()
    colors = {"FIN": "#2a78d6", "SWE": "#008300", "NOR": "#eda100"}
    fig, ax = plt.subplots(figsize=(7, 4.6))
    for c, gg in g.groupby("country"):
        ax.scatter(gg["goles"], gg["empates"], s=gg["n"] / 6, color=colors[c],
                   label=c, alpha=0.85, edgecolor="white", lw=0.8)
        for r in gg.itertuples():
            ax.annotate(r.league_code, (r.goles, r.empates), fontsize=7,
                        xytext=(4, 3), textcoords="offset points", color="#52514e")
    ax.set_xlabel("goles por partido (media de la liga)")
    ax.set_ylabel("tasa de empates")
    ax.set_title("Perfil de ligas (2025-26) — insumo del clustering jerárquico\n"
                 "tamaño del punto = nº de partidos")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "league_profiles.png"); plt.close(fig)


def fig_cold_start(res: pd.DataFrame, feats: pd.DataFrame) -> None:
    gp = feats.set_index("match_id")[["home_gp", "away_gp"]].min(axis=1)
    d = res.merge(gp.rename("min_gp"), left_on="match_id", right_index=True)
    d["gpbin"] = pd.cut(d["min_gp"], [-1, 4, 9, 15, 25, 60],
                        labels=["0-4", "5-9", "10-15", "16-25", "26+"])
    keep = ["g0_logistic_dppg", "dc_best", "stack_full"]
    fig, ax = plt.subplots(figsize=(7, 3.4))
    for m in keep:
        g = d[d.model == m].groupby("gpbin", observed=True)["rps"].mean()
        ax.plot(g.index.astype(str), g.to_numpy(), "o-", lw=1.5, ms=5,
                color=COLORS[m], label=LABELS[m])
    ax.set_xlabel("partidos previos del equipo con menos historia (en su liga)")
    ax.set_ylabel("RPS medio")
    ax.set_title("Arranque en frío: error según historia disponible (2026)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "cold_start.png"); plt.close(fig)


def main() -> None:
    res, feats, results = load()
    fig_model_comparison(res)
    fig_rps_by_league(res)
    fig_calibration(res)
    fig_momentum(res, feats)
    fig_coefficients(results)
    fig_league_profiles()
    fig_cold_start(res, feats)
    print("figuras →", FIG)


if __name__ == "__main__":
    main()
