"""Goal-based rating models for the peak research (protocolo Fase 3).

Implements the statistical ladder over the Finland dataset:

- ``fit_poisson``: independent-Poisson attack/defence model (Maher 1982) with
  optional exponential time decay (Dixon-Coles 1997) and optional low-score
  dependence correction (rho). A ridge penalty on attack/defence acts as a
  Normal(0, sigma) prior => shrinkage of small-sample teams toward the league
  average (poor-man's partial pooling).
- ``predict_probs``: score matrix -> P(H/D/A) (and totals, for later O/U work).

All fits are frozen "as of" a cutoff date by the caller: pass only matches
strictly before kickoff (anti-leakage rule of the protocol, §3.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 10  # score-matrix truncation; Finland league means are ~1.2-1.9/side


@dataclass
class PoissonFit:
    teams: list[int]
    mu: float
    home_adv: float
    rho: float
    attack: dict[int, float]
    defence: dict[int, float]
    halflife_days: float | None
    ridge_sigma: float
    n_matches: int
    converged: bool
    meta: dict = field(default_factory=dict)

    def rates(self, home_id: int, away_id: int) -> tuple[float, float, bool]:
        """(lambda_home, lambda_away, known) — unseen teams get atk=def=0."""

        known = home_id in self.attack and away_id in self.attack
        ah, dh = self.attack.get(home_id, 0.0), self.defence.get(home_id, 0.0)
        aa, da = self.attack.get(away_id, 0.0), self.defence.get(away_id, 0.0)
        lam_h = float(np.exp(self.mu + self.home_adv + ah - da))
        lam_a = float(np.exp(self.mu + aa - dh))
        return lam_h, lam_a, known


def _dc_tau(matrix: np.ndarray, lam_h: float, lam_a: float, rho: float) -> np.ndarray:
    """Dixon-Coles low-score dependence adjustment on the score matrix."""

    if rho == 0.0:
        return matrix
    m = matrix.copy()
    m[0, 0] *= max(1.0 - lam_h * lam_a * rho, 1e-10)
    m[1, 0] *= max(1.0 + lam_a * rho, 1e-10)
    m[0, 1] *= max(1.0 + lam_h * rho, 1e-10)
    m[1, 1] *= max(1.0 - rho, 1e-10)
    return m / m.sum()


def score_matrix(lam_h: float, lam_a: float, rho: float = 0.0) -> np.ndarray:
    """Truncated independent-Poisson score matrix with optional DC correction."""

    goals = np.arange(MAX_GOALS + 1)
    ph = poisson.pmf(goals, lam_h)
    pa = poisson.pmf(goals, lam_a)
    m = np.outer(ph, pa)
    m /= m.sum()
    return _dc_tau(m, lam_h, lam_a, rho)


def probs_1x2(matrix: np.ndarray) -> tuple[float, float, float]:
    ph = float(np.tril(matrix, -1).sum())  # home rows > away cols
    pd_ = float(np.trace(matrix))
    pa = float(np.triu(matrix, 1).sum())
    return ph, pd_, pa


def predict_probs(fit: PoissonFit, home_id: int, away_id: int) -> dict:
    lam_h, lam_a, known = fit.rates(home_id, away_id)
    m = score_matrix(lam_h, lam_a, fit.rho)
    ph, pd_, pa = probs_1x2(m)
    goals = np.arange(MAX_GOALS + 1)
    totals = np.add.outer(goals, goals)
    return {
        "p_home": ph, "p_draw": pd_, "p_away": pa,
        "lam_home": lam_h, "lam_away": lam_a, "teams_known": known,
        "p_over25": float(m[totals > 2.5].sum()),
        "p_btts": float(m[1:, 1:].sum()),
    }


@dataclass
class HierPoissonFit:
    """MAP del modelo jerárquico multi-liga (ver paper EXP-003, §modelos).

    log lam_H = mu0 + m_c(l) + d_l + (g0 + gc_c(l) + gl_l) + atk_h - def_a
    log lam_A = mu0 + m_c(l) + d_l + atk_a - def_h

    con priors normales (penalizaciones L2): m_c ~ N(0, tau_c), d_l ~ N(0, tau_l),
    idem localia, y atk/def ~ N(0, sigma_team) compartidos DENTRO del pais
    (mismo team_id en divisiones distintas = mismo equipo → los ascendidos
    conservan su historia de la division anterior).
    """

    teams: list
    leagues: list
    clusters: list
    mu0: float
    g0: float
    rho: float
    m_c: dict
    d_l: dict
    gc_c: dict
    gl_l: dict
    attack: dict
    defence: dict
    league_cluster: dict
    halflife_days: float | None
    n_matches: int
    converged: bool

    def rates(self, home_id, away_id, league: str) -> tuple[float, float, bool]:
        c = self.league_cluster.get(league)
        mu = self.mu0 + self.m_c.get(c, 0.0) + self.d_l.get(league, 0.0)
        ga = self.g0 + self.gc_c.get(c, 0.0) + self.gl_l.get(league, 0.0)
        known = home_id in self.attack and away_id in self.attack
        lam_h = float(np.exp(mu + ga + self.attack.get(home_id, 0.0) - self.defence.get(away_id, 0.0)))
        lam_a = float(np.exp(mu + self.attack.get(away_id, 0.0) - self.defence.get(home_id, 0.0)))
        return lam_h, lam_a, known


def predict_probs_hier(fit: HierPoissonFit, home_id, away_id, league: str) -> dict:
    lam_h, lam_a, known = fit.rates(home_id, away_id, league)
    m = score_matrix(lam_h, lam_a, fit.rho)
    ph, pd_, pa = probs_1x2(m)
    return {"p_home": ph, "p_draw": pd_, "p_away": pa,
            "lam_home": lam_h, "lam_away": lam_a, "teams_known": known}


def fit_poisson_hier(
    matches: pd.DataFrame,
    *,
    asof: pd.Timestamp,
    league_cluster: dict[str, str],
    halflife_days: float | None = 120.0,
    sigma_team: float = 0.75,
    tau_cluster: float = 0.25,
    tau_league: float = 0.15,
) -> HierPoissonFit | None:
    """MAP conjunto de TODAS las ligas (grafo por pais, intercepts por cluster/liga).

    ``matches`` puede mezclar paises: los grafos quedan bloque-diagonales solos
    (equipos de paises distintos nunca se cruzan) y los hiperparametros de
    cluster comparten informacion entre paises. team ids se namespacean por
    country para evitar colisiones entre federaciones.
    """

    g = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    g = g[g["date"] < asof]
    if len(g) < 50:
        return None
    g["h_key"] = g["country"].astype(str) + "|" + g["home_team_id"].astype(str)
    g["a_key"] = g["country"].astype(str) + "|" + g["away_team_id"].astype(str)

    teams = sorted(set(g["h_key"]).union(g["a_key"]))
    leagues = sorted(g["league_code"].unique())
    clusters = sorted({league_cluster.get(l, "c0") for l in leagues})
    t_idx = {t: i for i, t in enumerate(teams)}
    l_idx = {l: i for i, l in enumerate(leagues)}
    c_idx = {c: i for i, c in enumerate(clusters)}
    lc = np.array([c_idx[league_cluster.get(l, "c0")] for l in leagues])

    hi = g["h_key"].map(t_idx).to_numpy()
    ai = g["a_key"].map(t_idx).to_numpy()
    li = g["league_code"].map(l_idx).to_numpy()
    ci = lc[li]
    hg = g["home_goals"].to_numpy(dtype=float)
    ag = g["away_goals"].to_numpy(dtype=float)
    w = (0.5 ** (((asof - g["date"]).dt.days.to_numpy(dtype=float)) / halflife_days)
         if halflife_days else np.ones(len(g)))

    nT, nL, nC = len(teams), len(leagues), len(clusters)
    # theta = [mu0, g0, rho, m_c(nC), d_l(nL), gc_c(nC), gl_l(nL), atk(nT), def(nT)]
    off_mc, off_dl = 3, 3 + nC
    off_gc, off_gl = 3 + nC + nL, 3 + 2 * nC + nL
    off_atk = 3 + 2 * nC + 2 * nL
    off_def = off_atk + nT

    n_par = off_def + nT

    # NLL + gradiente analítico (rho=0 en el jerárquico: su aporte era marginal
    # en EXP-001/002 y el gradiente numérico sobre ~500 params no converge).
    def nll(th):
        mu0, g0 = th[0], th[1]
        m_c, d_l = th[off_mc:off_dl], th[off_dl:off_gc]
        gc_c, gl_l = th[off_gc:off_gl], th[off_gl:off_atk]
        atk, dfc = th[off_atk:off_def], th[off_def:]
        mu = mu0 + m_c[ci] + d_l[li]
        ga = g0 + gc_c[ci] + gl_l[li]
        log_lh = mu + ga + atk[hi] - dfc[ai]
        log_la = mu + atk[ai] - dfc[hi]
        lam_h, lam_a = np.exp(log_lh), np.exp(log_la)
        f = -np.sum(w * (hg * log_lh - lam_h + ag * log_la - lam_a))
        f += ((m_c**2).sum() + (gc_c**2).sum()) / (2 * tau_cluster**2)
        f += ((d_l**2).sum() + (gl_l**2).sum()) / (2 * tau_league**2)
        f += ((atk**2).sum() + (dfc**2).sum()) / (2 * sigma_team**2)

        gh = w * (hg - lam_h)   # dll/d(log lam_H) por partido
        gaw = w * (ag - lam_a)  # dll/d(log lam_A) por partido
        grad = np.zeros(n_par)
        grad[0] = -np.sum(gh + gaw)
        grad[1] = -np.sum(gh)
        both = gh + gaw
        grad[off_mc:off_dl] = -np.bincount(ci, weights=both, minlength=nC)
        grad[off_dl:off_gc] = -np.bincount(li, weights=both, minlength=nL)
        grad[off_gc:off_gl] = -np.bincount(ci, weights=gh, minlength=nC)
        grad[off_gl:off_atk] = -np.bincount(li, weights=gh, minlength=nL)
        grad[off_atk:off_def] = -(np.bincount(hi, weights=gh, minlength=nT)
                                  + np.bincount(ai, weights=gaw, minlength=nT))
        grad[off_def:] = (np.bincount(ai, weights=gh, minlength=nT)
                          + np.bincount(hi, weights=gaw, minlength=nT))
        grad[off_mc:off_dl] += th[off_mc:off_dl] / tau_cluster**2
        grad[off_gc:off_gl] += th[off_gc:off_gl] / tau_cluster**2
        grad[off_dl:off_gc] += th[off_dl:off_gc] / tau_league**2
        grad[off_gl:off_atk] += th[off_gl:off_atk] / tau_league**2
        grad[off_atk:] += th[off_atk:] / sigma_team**2
        return f, grad

    x0 = np.zeros(n_par)
    x0[0] = np.log(max(np.average((hg + ag) / 2, weights=w), 0.2))
    res = minimize(nll, x0, method="L-BFGS-B", jac=True,
                   options={"maxiter": 2000})
    th = res.x
    inv_c = {i: c for c, i in c_idx.items()}
    return HierPoissonFit(
        teams=teams, leagues=leagues, clusters=clusters,
        mu0=float(th[0]), g0=float(th[1]), rho=0.0,
        m_c={inv_c[i]: float(v) for i, v in enumerate(th[off_mc:off_dl])},
        d_l={l: float(th[off_dl + l_idx[l]]) for l in leagues},
        gc_c={inv_c[i]: float(v) for i, v in enumerate(th[off_gc:off_gl])},
        gl_l={l: float(th[off_gl + l_idx[l]]) for l in leagues},
        attack={t: float(th[off_atk + t_idx[t]]) for t in teams},
        defence={t: float(th[off_def + t_idx[t]]) for t in teams},
        league_cluster={l: league_cluster.get(l, "c0") for l in leagues},
        halflife_days=halflife_days, n_matches=len(g), converged=bool(res.success),
    )


def fit_poisson(
    matches: pd.DataFrame,
    *,
    asof: pd.Timestamp,
    halflife_days: float | None = None,
    ridge_sigma: float = 1.0,
    fit_rho: bool = False,
    fit_home_adv: bool = True,
    gamma_halflife: float | None = None,
) -> PoissonFit | None:
    """MLE of the attack/defence Poisson model on matches strictly before ``asof``.

    ``matches`` needs: date, home_team_id, away_team_id, home_goals, away_goals.
    Weights: w = 0.5 ** (days_before_asof / halflife_days) (Dixon-Coles decay).
    Ridge: -(atk^2+def^2)/(2 sigma^2), the Normal-prior shrinkage.
    """

    g = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    g = g[g["date"] < asof]
    if len(g) < 20:
        return None

    teams = sorted(set(g["home_team_id"]).union(g["away_team_id"]))
    t_idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = g["home_team_id"].map(t_idx).to_numpy()
    ai = g["away_team_id"].map(t_idx).to_numpy()
    hg = g["home_goals"].to_numpy(dtype=float)
    ag = g["away_goals"].to_numpy(dtype=float)

    if halflife_days:
        days = (asof - g["date"]).dt.days.to_numpy(dtype=float)
        w = 0.5 ** (days / halflife_days)
    else:
        w = np.ones(len(g))

    def unpack(theta):
        mu, gamma, rho = theta[0], theta[1], theta[2]
        atk = theta[3 : 3 + n]
        dfc = theta[3 + n : 3 + 2 * n]
        return mu, gamma, rho, atk, dfc

    low_h = hg <= 1
    low_a = ag <= 1
    low = low_h & low_a  # only 0/1-0/1 scores get the tau correction

    def nll(theta):
        mu, gamma, rho, atk, dfc = unpack(theta)
        log_lh = mu + gamma + atk[hi] - dfc[ai]
        log_la = mu + atk[ai] - dfc[hi]
        lam_h, lam_a = np.exp(log_lh), np.exp(log_la)
        ll = hg * log_lh - lam_h + ag * log_la - lam_a
        if fit_rho:
            tau = np.ones(len(hg))
            m00 = low & (hg == 0) & (ag == 0)
            m10 = low & (hg == 1) & (ag == 0)
            m01 = low & (hg == 0) & (ag == 1)
            m11 = low & (hg == 1) & (ag == 1)
            tau[m00] = np.maximum(1 - lam_h[m00] * lam_a[m00] * rho, 1e-10)
            tau[m10] = np.maximum(1 + lam_a[m10] * rho, 1e-10)
            tau[m01] = np.maximum(1 + lam_h[m01] * rho, 1e-10)
            tau[m11] = max(1 - rho, 1e-10)
            ll = ll + np.log(tau)
        penalty = (np.sum(atk**2) + np.sum(dfc**2)) / (2 * ridge_sigma**2)
        return -(np.sum(w * ll)) + penalty

    x0 = np.zeros(3 + 2 * n)
    x0[0] = np.log(max(np.average((hg + ag) / 2, weights=w), 0.2))
    bounds = [(-3, 3), ((-1.5, 1.5) if fit_home_adv else (0.0, 0.0)),
              ((-0.5, 0.5) if fit_rho else (0.0, 0.0))]
    bounds += [(-3, 3)] * (2 * n)
    res = minimize(nll, x0, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 500})

    mu, gamma, rho, atk, dfc = unpack(res.x)

    # dc_dyn_gamma (H6/H4-EXP005): la localía puede cambiar más rápido que las
    # fuerzas. Re-estimamos SOLO gamma con su propio kernel 2^(-dt/H_gamma)
    # perfilando la verosimilitud Poisson (los demás parámetros quedan fijos).
    # El perfil es concavo con solución CERRADA:
    #   e^gamma = sum(w' * goles_local) / sum(w' * lambda0),
    #   lambda0 = exp(mu + atk_h - def_a)  (intensidad local sin localía).
    # (Se ignoran los términos rho en el perfil: corrección de segundo orden.)
    if gamma_halflife is not None:
        wg = 0.5 ** (((asof - g["date"]).dt.days.to_numpy(dtype=float))
                     / gamma_halflife)
        lam0 = np.exp(mu + atk[hi] - dfc[ai])
        num, den = float(np.sum(wg * hg)), float(np.sum(wg * lam0))
        if num > 0 and den > 0:
            gamma = float(np.log(num / den))

    return PoissonFit(
        teams=teams, mu=float(mu), home_adv=float(gamma), rho=float(rho),
        attack={t: float(atk[t_idx[t]]) for t in teams},
        defence={t: float(dfc[t_idx[t]]) for t in teams},
        halflife_days=halflife_days, ridge_sigma=ridge_sigma,
        n_matches=len(g), converged=bool(res.success),
    )
