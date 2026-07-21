"""Model zoo: callables with the walk_forward signature (train, rows) -> probs.

Every model slices its own training data; the harness guarantees ``train`` only
holds matches strictly before the week being predicted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.peak_models import loader
from research.peak_models.evaluate import ORDER, PCOLS
from research.peak_models.models import fit_poisson, predict_probs

_GLOBAL_FALLBACK = np.array([0.42, 0.26, 0.32])  # sane Finland-ish prior


# ---------------------------------------------------------------- B0: base rate

def league_rates(train: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    rates = (train.groupby("league_code")["result"].value_counts(normalize=True)
             .unstack().reindex(columns=ORDER).fillna(0.0))
    glob = train["result"].value_counts(normalize=True).reindex(ORDER).fillna(0.0).to_numpy()
    if glob.sum() == 0:
        glob = _GLOBAL_FALLBACK
    return rates, glob


def base_rate(train: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
    rates, glob = league_rates(train)
    P = np.array([
        rates.loc[r.league_code].to_numpy() if r.league_code in rates.index else glob
        for r in rows.itertuples()
    ])
    return pd.DataFrame(P, columns=PCOLS)


# ------------------------------------------------- G0: logistic on delta_ppg

def make_logistic_dppg(full_df: pd.DataFrame):
    """Precompute point-in-time delta_ppg once (each row only uses prior games)."""

    from sklearn.linear_model import LogisticRegression

    feats = point_in_time_ppg(full_df).set_index("match_id")

    def model(train: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
        rates, glob = league_rates(train)
        tr = feats.loc[feats.index.intersection(train["match_id"])].dropna(subset=["delta_ppg"])
        clf = None
        if len(tr) >= 50 and tr["result"].nunique() == 3:
            clf = LogisticRegression(max_iter=1000)
            clf.fit(tr[["delta_ppg"]].to_numpy(), tr["result"].to_numpy())
            cls = list(clf.classes_)
            order_idx = [cls.index(c) for c in ORDER]
        out = []
        for r in rows.itertuples():
            d = feats.at[r.match_id, "delta_ppg"] if r.match_id in feats.index else np.nan
            if clf is None or pd.isna(d):
                out.append(rates.loc[r.league_code].to_numpy()
                           if r.league_code in rates.index else glob)
            else:
                out.append(clf.predict_proba([[d]])[0][order_idx])
        return pd.DataFrame(np.array(out), columns=PCOLS)

    return model


def point_in_time_ppg(matches: pd.DataFrame) -> pd.DataFrame:
    """delta_ppg feature, computed only from each team's PREVIOUS games
    (same season/league/group). Same construction as g0_baseline.ipynb."""

    long = loader.to_team_long(matches).dropna(subset=["gf", "ga"]).sort_values("date").copy()
    g = long.groupby(["season", "league_code", "group_id", "team_id"], sort=False)
    long["pts_before"] = g["points"].cumsum() - long["points"]
    long["games_before"] = g.cumcount()
    long["ppg_before"] = long["pts_before"] / long["games_before"].replace(0, np.nan)
    home = (long[long.venue == "home"][["match_id", "ppg_before", "games_before"]]
            .rename(columns={"ppg_before": "ppg_home", "games_before": "gp_home"}))
    away = (long[long.venue == "away"][["match_id", "ppg_before", "games_before"]]
            .rename(columns={"ppg_before": "ppg_away", "games_before": "gp_away"}))
    feat = matches.merge(home, on="match_id").merge(away, on="match_id")
    feat["delta_ppg"] = feat["ppg_home"] - feat["ppg_away"]
    return feat


# ------------------------------------------------- Poisson / Dixon-Coles

def make_poisson(*, halflife_days: float | None, ridge_sigma: float = 1.0,
                 fit_rho: bool = False):
    """Per-league attack/defence Poisson, fitted fresh at every cutoff."""

    def model(train: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
        rates, glob = league_rates(train)
        cutoff = rows["date"].min().normalize()
        fits = {}
        out = []
        for r in rows.itertuples():
            lg = r.league_code
            if lg not in fits:
                fits[lg] = fit_poisson(
                    train[train["league_code"] == lg], asof=cutoff,
                    halflife_days=halflife_days, ridge_sigma=ridge_sigma,
                    fit_rho=fit_rho,
                )
            fit = fits[lg]
            if fit is None:
                out.append(rates.loc[lg].to_numpy() if lg in rates.index else glob)
                continue
            p = predict_probs(fit, r.home_team_id, r.away_team_id)
            out.append([p["p_home"], p["p_draw"], p["p_away"]])
        return pd.DataFrame(np.array(out, dtype=float), columns=PCOLS)

    return model
