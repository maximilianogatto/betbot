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


def fit_poisson(
    matches: pd.DataFrame,
    *,
    asof: pd.Timestamp,
    halflife_days: float | None = None,
    ridge_sigma: float = 1.0,
    fit_rho: bool = False,
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
    bounds = [(-3, 3), (-1.5, 1.5), ((-0.5, 0.5) if fit_rho else (0.0, 0.0))]
    bounds += [(-3, 3)] * (2 * n)
    res = minimize(nll, x0, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 500})

    mu, gamma, rho, atk, dfc = unpack(res.x)
    return PoissonFit(
        teams=teams, mu=float(mu), home_adv=float(gamma), rho=float(rho),
        attack={t: float(atk[t_idx[t]]) for t in teams},
        defence={t: float(dfc[t_idx[t]]) for t in teams},
        halflife_days=halflife_days, ridge_sigma=ridge_sigma,
        n_matches=len(g), converged=bool(res.success),
    )
