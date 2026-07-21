"""Model zoo: callables with the walk_forward signature (train, rows) -> probs.

Every model slices its own training data; the harness guarantees ``train`` only
holds matches strictly before the week being predicted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.peak_models import loader
from research.peak_models.evaluate import ORDER, PCOLS
from research.peak_models.models import (fit_poisson, fit_poisson_hier,
                                         predict_probs, predict_probs_hier)

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


# ------------------------------------------------- jerárquico multi-liga

def make_hier(league_cluster: dict[str, str], **params):
    """Wrapper del MAP jerárquico (un solo fit conjunto por semana)."""

    def model(train: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
        rates, glob = league_rates(train)
        cutoff = rows["date"].min().normalize()
        fit = fit_poisson_hier(train, asof=cutoff, league_cluster=league_cluster,
                               **params)
        out = []
        for r in rows.itertuples():
            if fit is None:
                out.append(rates.loc[r.league_code].to_numpy()
                           if r.league_code in rates.index else glob)
                continue
            p = predict_probs_hier(fit, f"{r.country}|{r.home_team_id}",
                                   f"{r.country}|{r.away_team_id}", r.league_code)
            out.append([p["p_home"], p["p_draw"], p["p_away"]])
        return pd.DataFrame(np.array(out, dtype=float), columns=PCOLS)

    return model


# ------------------------------- G0b: histograma binneado sobre Δposición
# Port del LeaguePredictor del director (research.ipynb, worktree peak-research):
# P(resultado | Δposición normalizada) estimada por bins fijos en [-1, 1] con
# fallback nearest-bin. Correcciones respecto del original: las probabilidades
# se renormalizan a suma 1 y hay fallback a tasa base de liga cuando no hay
# tabla o el bin no tiene muestra.

def point_in_time_standing_diff(matches: pd.DataFrame, *, min_pj: int = 4) -> pd.DataFrame:
    """-(pos_home - pos_away)/N_teams antes de cada partido (replay cronológico).

    N_teams es el tamaño conocido de la serie (calendario), no un dato futuro.
    Filas sin tabla suficiente (algún equipo con < min_pj PJ) quedan NaN.
    """

    df = (matches.dropna(subset=["home_goals", "away_goals"])
          .sort_values(["date", "match_id"]))
    n_teams = (matches.groupby(["season", "league_code", "group_id"])
               .apply(lambda g: len(set(g.home_team_id) | set(g.away_team_id)),
                      include_groups=False))
    rows = []
    for key, g in df.groupby(["season", "league_code", "group_id"], sort=False):
        stats: dict = {}
        nt = float(n_teams.loc[key])
        for r in g.itertuples():
            h = stats.get(r.home_team_id)
            a = stats.get(r.away_team_id)
            diff = np.nan
            if h and a and min(h[3], a[3]) >= min_pj:
                table = sorted(stats.values(), key=lambda s: (-s[0], -s[1], -s[2]))
                pos = {id(s): i + 1 for i, s in enumerate(table)}
                diff = -(pos[id(h)] - pos[id(a)]) / nt
            rows.append({"match_id": r.match_id, "standing_diff": diff})
            for tid, gf, ga in [(r.home_team_id, r.home_goals, r.away_goals),
                                (r.away_team_id, r.away_goals, r.home_goals)]:
                s = stats.setdefault(tid, [0, 0, 0, 0])  # pts, dg, gf, pj
                s[0] += 3 if gf > ga else (1 if gf == ga else 0)
                s[1] += gf - ga
                s[2] += gf
                s[3] += 1
    return pd.DataFrame(rows)


def make_binned_standing(full_df: pd.DataFrame, *, n_bins: int = 9,
                         min_bin_count: int = 15):
    feats = point_in_time_standing_diff(full_df).set_index("match_id")
    edges = np.linspace(-1, 1, n_bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2

    def model(train: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
        rates, glob = league_rates(train)
        tr = train.join(feats, on="match_id").dropna(subset=["standing_diff"])
        P_bins = np.full((n_bins, 3), np.nan)
        if len(tr):
            b = np.clip(np.digitize(tr["standing_diff"], edges[1:-1]), 0, n_bins - 1)
            for k in range(n_bins):
                sel = tr.loc[b == k, "result"]
                if len(sel) >= min_bin_count:
                    P_bins[k] = [np.mean(sel == c) for c in ORDER]
        valid = ~np.isnan(P_bins[:, 0])
        out = []
        for r in rows.itertuples():
            d = feats.at[r.match_id, "standing_diff"] if r.match_id in feats.index else np.nan
            if pd.isna(d) or not valid.any():
                out.append(rates.loc[r.league_code].to_numpy()
                           if r.league_code in rates.index else glob)
                continue
            k = int(np.clip(np.digitize(d, edges[1:-1]), 0, n_bins - 1))
            if not valid[k]:  # nearest bin válido (interp 'nearest' del original)
                k = int(np.where(valid)[0][np.argmin(np.abs(centers[valid] - centers[k]))])
            p = P_bins[k]
            out.append(p / p.sum())
        return pd.DataFrame(np.array(out), columns=PCOLS)

    return model


# ------------------------------------------------- stacking DC + features

STACK_FEATS = ["elo_diff", "mom5_diff", "adj_form5_diff", "sos5_diff",
               "ppg_vs_stronger8_diff", "form5_pts_diff"]


def make_stacked(oos_dc: pd.DataFrame, feats: pd.DataFrame, *,
                 use_features: bool = True):
    """Meta-logistic over out-of-sample DC probs (+ form/momentum features).

    ``oos_dc``: walk-forward DC predictions for every match (match_id, date,
    result, p_home/p_draw/p_away) — all out-of-sample, so training the meta
    model on rows with date < cutoff introduces no leakage.
    ``use_features=False`` is the ablation: pure recalibration of DC.
    """

    from sklearn.linear_model import LogisticRegression

    base = oos_dc.set_index("match_id")
    F = feats.set_index("match_id")

    def design(ids: pd.Index) -> np.ndarray:
        P = base.loc[ids, PCOLS].to_numpy(dtype=float).clip(1e-6, 1 - 1e-6)
        X = np.log(P[:, [0, 1]] / P[:, [2]])  # logits vs away
        if use_features:
            xf = F.loc[ids, STACK_FEATS].to_numpy(dtype=float)
            xf = np.where(np.isnan(xf), 0.0, xf)  # sin historia = neutro
            X = np.hstack([X, xf])
        return X

    def model(train: pd.DataFrame, rows: pd.DataFrame) -> pd.DataFrame:
        cutoff = rows["date"].min()
        tr_ids = base.index.intersection(train.loc[train["date"] < cutoff, "match_id"])
        te_ids = pd.Index(rows["match_id"])
        fallback = base.reindex(te_ids)[PCOLS].to_numpy(dtype=float)
        tr = base.loc[tr_ids]
        if len(tr) < 150 or tr["result"].nunique() < 3:
            return pd.DataFrame(fallback, columns=PCOLS)
        clf = LogisticRegression(max_iter=2000, C=1.0)
        clf.fit(design(tr_ids), tr["result"].to_numpy())
        order_idx = [list(clf.classes_).index(c) for c in ORDER]
        P = clf.predict_proba(design(te_ids))[:, order_idx]
        model.last_coef = (list(clf.classes_), clf.coef_)  # inspección
        return pd.DataFrame(P, columns=PCOLS)

    return model


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
