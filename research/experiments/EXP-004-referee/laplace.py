"""EXP-004.5 — Incertidumbre paramétrica vía Laplace (referee §7 y §8).

Sobre el ajuste DC de una liga (VL, cutoff = hoy):
1. Hessiano numérico de la NLL penalizada en el MAP → Σ = H⁻¹ (aprox. Laplace).
2. sd posterior del ataque de cada equipo vs su nº efectivo de partidos
   (Σ de pesos w): muestra que dos equipos con el mismo n NO tienen la misma
   información (depende de rivales, condición y antigüedad — referee §8).
3. Distribución predictiva integrada: θ ~ N(MAP, Σ), promedio de matrices de
   marcadores vs plug-in. Cuantifica cuánta sobreconfianza introduce ignorar
   la incertidumbre paramétrica (referee §7), sobre un partido "establecido"
   y uno con el equipo de menos historia.
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
from research.peak_models.models import (  # noqa: E402
    fit_poisson, probs_1x2, score_matrix)

HERE = Path(__file__).parent
FIG = HERE / "fig"
plt.rcParams.update({"figure.dpi": 150, "font.size": 9, "axes.grid": True,
                     "grid.color": "#e8e7e2", "axes.axisbelow": True})

LEAGUE = "VL"
BEST = dict(halflife_days=120.0, ridge_sigma=0.75, fit_rho=True)


def build_nll(g: pd.DataFrame, asof: pd.Timestamp, teams: list, *, sigma: float,
              halflife: float):
    t_idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = g["home_team_id"].map(t_idx).to_numpy()
    ai = g["away_team_id"].map(t_idx).to_numpy()
    hg = g["home_goals"].to_numpy(float)
    ag = g["away_goals"].to_numpy(float)
    days = (asof - g["date"]).dt.days.to_numpy(float)
    w = 0.5 ** (days / halflife)
    low = (hg <= 1) & (ag <= 1)

    def nll(th):
        mu, gamma, rho = th[0], th[1], th[2]
        atk, dfc = th[3:3 + n], th[3 + n:]
        log_lh = mu + gamma + atk[hi] - dfc[ai]
        log_la = mu + atk[ai] - dfc[hi]
        lam_h, lam_a = np.exp(log_lh), np.exp(log_la)
        ll = hg * log_lh - lam_h + ag * log_la - lam_a
        tau = np.ones(len(hg))
        m00 = low & (hg == 0) & (ag == 0); m10 = low & (hg == 1) & (ag == 0)
        m01 = low & (hg == 0) & (ag == 1); m11 = low & (hg == 1) & (ag == 1)
        tau[m00] = np.maximum(1 - lam_h[m00] * lam_a[m00] * rho, 1e-10)
        tau[m10] = np.maximum(1 + lam_a[m10] * rho, 1e-10)
        tau[m01] = np.maximum(1 + lam_h[m01] * rho, 1e-10)
        tau[m11] = max(1 - rho, 1e-10)
        ll = ll + np.log(tau)
        pen = (np.sum(atk**2) + np.sum(dfc**2)) / (2 * sigma**2)
        return -np.sum(w * ll) + pen

    return nll, w, hi, ai


def num_hessian(f, x0, eps=1e-4):
    p = len(x0)
    H = np.zeros((p, p))
    f0 = f(x0)
    for i in range(p):
        for j in range(i, p):
            ei = np.zeros(p); ei[i] = eps
            ej = np.zeros(p); ej[j] = eps
            H[i, j] = H[j, i] = (f(x0 + ei + ej) - f(x0 + ei) - f(x0 + ej) + f0) / eps**2
    return H


def main() -> None:
    df = loader.load_all()
    g = df[(df.league_code == LEAGUE)].dropna(subset=["home_goals", "away_goals"])
    asof = g["date"].max() + pd.Timedelta(days=1)
    fit = fit_poisson(g, asof=asof, **BEST)
    teams = fit.teams
    n = len(teams)
    theta = np.concatenate([[fit.mu, fit.home_adv, fit.rho],
                            [fit.attack[t] for t in teams],
                            [fit.defence[t] for t in teams]])
    nll, w, hi, ai = build_nll(g, asof, teams, sigma=BEST["ridge_sigma"],
                               halflife=BEST["halflife_days"])
    H = num_hessian(nll, theta)
    Sigma = np.linalg.inv(H + 1e-8 * np.eye(len(theta)))
    sd = np.sqrt(np.clip(np.diag(Sigma), 0, None))

    # nº efectivo de partidos por equipo (suma de pesos temporales)
    eff = np.zeros(n)
    for k in range(len(hi)):
        eff[hi[k]] += w[k]
        eff[ai[k]] += w[k]

    fig, ax = plt.subplots(figsize=(6.8, 4))
    ax.scatter(eff, sd[3:3 + n], color="#2a78d6", label="sd(ataque)", s=30,
               edgecolor="white", lw=0.6)
    ax.scatter(eff, sd[3 + n:], color="#008300", label="sd(defensa)", s=30,
               edgecolor="white", lw=0.6)
    ax.set_xlabel("partidos efectivos del equipo (Σ pesos temporales)")
    ax.set_ylabel("sd posterior (Laplace) del parámetro")
    ax.set_title(f"Incertidumbre paramétrica por equipo — {LEAGUE}, cutoff {asof.date()}\n"
                 "misma cantidad de partidos ≠ misma información (dispersión vertical)")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "laplace_sd_vs_n.png"); plt.close(fig)

    # predictiva integrada vs plug-in: partido establecido vs equipo nuevo
    eff_by_team = dict(zip(teams, eff))
    played26 = g[g["date"] >= pd.Timestamp("2026-01-01")]
    rows = []
    rng = np.random.default_rng(11)
    draws = rng.multivariate_normal(theta, Sigma, size=400)
    for label, pick in [("establecido", played26.iloc[-1]),
                        ("con equipo nuevo",
                         played26.loc[played26.apply(
                             lambda r: min(eff_by_team.get(r.home_team_id, 0),
                                           eff_by_team.get(r.away_team_id, 0)), axis=1).idxmin()])]:
        t_idx = {t: i for i, t in enumerate(teams)}
        ih, ia = t_idx[pick.home_team_id], t_idx[pick.away_team_id]
        lam_h = np.exp(theta[0] + theta[1] + theta[3 + ih] - theta[3 + n + ia])
        lam_a = np.exp(theta[0] + theta[3 + ia] - theta[3 + n + ih])
        plug = probs_1x2(score_matrix(lam_h, lam_a, fit.rho))
        acc = np.zeros(3)
        for th in draws:
            lh = np.exp(th[0] + th[1] + th[3 + ih] - th[3 + n + ia])
            la = np.exp(th[0] + th[3 + ia] - th[3 + n + ih])
            acc += np.array(probs_1x2(score_matrix(lh, la, fit.rho)))
        integ = acc / len(draws)
        rows.append({"partido": f"{pick.home_team} vs {pick.away_team}",
                     "tipo": label,
                     "plugin_H": round(plug[0], 3), "plugin_D": round(plug[1], 3),
                     "plugin_A": round(plug[2], 3),
                     "integrada_H": round(float(integ[0]), 3),
                     "integrada_D": round(float(integ[1]), 3),
                     "integrada_A": round(float(integ[2]), 3),
                     "max_p_plugin": round(max(plug), 3),
                     "max_p_integrada": round(float(integ.max()), 3)})
    tab = pd.DataFrame(rows)
    print(tab.to_string(index=False))
    json.dump({"liga": LEAGUE, "sd_media_atk": round(float(sd[3:3 + n].mean()), 3),
               "ejemplos": json.loads(tab.to_json(orient="records"))},
              open(HERE / "laplace.json", "w"), indent=2)
    print("→ laplace.json, fig/laplace_sd_vs_n.png")


if __name__ == "__main__":
    main()
