"""Walk-forward evaluation harness (protocolo Fase 4, §6).

Weekly refit: for every ISO week with matches in the test window, each model is
(re)fitted on ALL matches strictly before the Monday of that week and predicts
that week's matches. Temporal split by construction — never random.

Models are callables ``(train_df, test_rows) -> DataFrame[p_home,p_draw,p_away]``
where ``train_df`` holds every played match before the cutoff (all leagues; the
model decides how to slice) and ``test_rows`` the matches to predict.

Metrics: RPS (primary for ordinal 1X2), log-loss, Brier, ECE. Paired block
bootstrap for the RPS/log-loss delta between two models.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

ORDER = ["H", "D", "A"]
PCOLS = ["p_home", "p_draw", "p_away"]


# ---------------------------------------------------------------- metrics

def _onehot(y: np.ndarray) -> np.ndarray:
    idx = {c: i for i, c in enumerate(ORDER)}
    out = np.zeros((len(y), 3))
    for r, v in enumerate(y):
        out[r, idx[v]] = 1.0
    return out


def rps_per_match(P: np.ndarray, y: np.ndarray) -> np.ndarray:
    Pc = np.cumsum(P, axis=1)
    Yc = np.cumsum(_onehot(y), axis=1)
    return ((Pc - Yc) ** 2).sum(axis=1) / (len(ORDER) - 1)


def logloss_per_match(P: np.ndarray, y: np.ndarray) -> np.ndarray:
    Y = _onehot(y)
    return -np.log(np.clip((P * Y).sum(axis=1), 1e-12, 1.0))


def brier_per_match(P: np.ndarray, y: np.ndarray) -> np.ndarray:
    return ((P - _onehot(y)) ** 2).sum(axis=1)


def ece(P: np.ndarray, y: np.ndarray, outcome: str = "H", bins: int = 8) -> float:
    """Expected calibration error for one outcome, quantile bins."""

    p = P[:, ORDER.index(outcome)]
    hit = (y == outcome).astype(float)
    df = pd.DataFrame({"p": p, "hit": hit})
    df["bin"] = pd.qcut(df["p"], bins, duplicates="drop")
    g = df.groupby("bin", observed=True).agg(p=("p", "mean"), obs=("hit", "mean"), n=("hit", "size"))
    return float((g["n"] / len(df) * (g["p"] - g["obs"]).abs()).sum())


def summarize(P: np.ndarray, y: np.ndarray) -> dict:
    return {
        "n": int(len(y)),
        "rps": float(rps_per_match(P, y).mean()),
        "log_loss": float(logloss_per_match(P, y).mean()),
        "brier": float(brier_per_match(P, y).mean()),
        "ece_home": ece(P, y, "H"),
        "accuracy": float((np.array(ORDER)[P.argmax(axis=1)] == y).mean()),
    }


def paired_bootstrap(
    per_match_a: np.ndarray, per_match_b: np.ndarray, n_boot: int = 4000, seed: int = 7
) -> dict:
    """CI for mean(b - a) per-match metric delta. Negative = b better (lower)."""

    rng = np.random.default_rng(seed)
    d = per_match_b - per_match_a
    idx = rng.integers(0, len(d), size=(n_boot, len(d)))
    means = d[idx].mean(axis=1)
    return {
        "delta_mean": float(d.mean()),
        "ci_lo": float(np.quantile(means, 0.025)),
        "ci_hi": float(np.quantile(means, 0.975)),
        "p_better": float((means < 0).mean()),
    }


# ---------------------------------------------------------------- harness

def walk_forward(
    df: pd.DataFrame,
    models: dict[str, Callable[[pd.DataFrame, pd.DataFrame], pd.DataFrame]],
    *,
    test_start: str,
    test_end: str | None = None,
) -> pd.DataFrame:
    """Run every model week by week. Returns long DF: one row per match×model."""

    played = df.dropna(subset=["home_goals", "away_goals"]).sort_values("date")
    test = played[played["date"] >= pd.Timestamp(test_start)]
    if test_end:
        test = test[test["date"] < pd.Timestamp(test_end)]

    out = []
    weeks = test["date"].dt.to_period("W").unique()
    for wk in sorted(weeks):
        cutoff = wk.start_time  # Monday 00:00 of the test week
        train = played[played["date"] < cutoff]
        rows = test[test["date"].dt.to_period("W") == wk]
        for name, model in models.items():
            probs = model(train, rows).reset_index(drop=True)
            block = rows.reset_index(drop=True)[
                ["match_id", "date", "league_code", "season", "group_id",
                 "home_team", "away_team", "home_team_id", "away_team_id",
                 "home_goals", "away_goals", "result"]
            ].copy()
            block["model"] = name
            block["cutoff"] = cutoff
            block[PCOLS] = probs[PCOLS].to_numpy(dtype=float)
            out.append(block)
    res = pd.concat(out, ignore_index=True)
    s = res[PCOLS].sum(axis=1)
    res[PCOLS] = res[PCOLS].div(s, axis=0)  # guard renormalization
    return res


def compare(results: pd.DataFrame, *, baseline: str) -> pd.DataFrame:
    """Metric table per model + paired bootstrap of RPS/log-loss vs baseline."""

    # common match set across models, aligned by match_id
    wide = {m: g.set_index("match_id").sort_index() for m, g in results.groupby("model")}
    common = None
    for g in wide.values():
        common = g.index if common is None else common.intersection(g.index)
    rows = []
    yb = wide[baseline].loc[common, "result"].to_numpy()
    Pb = wide[baseline].loc[common, PCOLS].to_numpy()
    base_rps = rps_per_match(Pb, yb)
    base_ll = logloss_per_match(Pb, yb)
    for name, g in wide.items():
        P = g.loc[common, PCOLS].to_numpy()
        y = g.loc[common, "result"].to_numpy()
        row = {"model": name, **summarize(P, y)}
        if name != baseline:
            bs = paired_bootstrap(base_rps, rps_per_match(P, y))
            row.update({"d_rps_vs_base": bs["delta_mean"],
                        "d_rps_ci": (round(bs["ci_lo"], 4), round(bs["ci_hi"], 4)),
                        "p_better_rps": bs["p_better"]})
            bs2 = paired_bootstrap(base_ll, logloss_per_match(P, y))
            row["d_logloss_vs_base"] = bs2["delta_mean"]
            row["p_better_logloss"] = bs2["p_better"]
        rows.append(row)
    return pd.DataFrame(rows).set_index("model").sort_values("rps")
