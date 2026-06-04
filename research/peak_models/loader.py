"""Pandas helpers to load the Finland peak-modelling dataset.

    from research.peak_models import loader
    df = loader.load_matches()            # all played matches (both seasons)
    longf = loader.to_team_long(df)       # one row per team per match (venue split)

Requires pandas (``pip install pandas``). The CSVs are produced by
``build_dataset.py``.
"""

from __future__ import annotations

import os
from typing import Optional

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
_BY = os.path.join(_DATA, "by_league_year")

_INT_COLS = ["home_goals", "away_goals", "ht_home", "ht_away"]


def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    for c in _INT_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def load_matches() -> pd.DataFrame:
    """All *played* matches across both seasons (the modelling master)."""

    return _coerce(pd.read_csv(os.path.join(_DATA, "finland_matches_played.csv")))


def load_league(code: str, season: str | int) -> pd.DataFrame:
    """Every fixture (played + scheduled) for one league+season."""

    return _coerce(pd.read_csv(os.path.join(_BY, f"{code}_{season}.csv")))


def load_today() -> pd.DataFrame:
    """Today's senior fixtures to predict (may include in-play games)."""

    return _coerce(pd.read_csv(os.path.join(_DATA, "today_fixtures.csv")))


def to_team_long(df: pd.DataFrame) -> pd.DataFrame:
    """Reshape match rows to one row per team per match, with venue split.

    Columns: season, league_code, group_id, date, team_id, team, opponent_id,
    opponent, venue ('home'|'away'), gf, ga, points.
    """

    home = pd.DataFrame({
        "season": df["season"], "league_code": df["league_code"], "group_id": df["group_id"],
        "date": df["date"], "match_id": df["match_id"],
        "team_id": df["home_team_id"], "team": df["home_team"],
        "opponent_id": df["away_team_id"], "opponent": df["away_team"],
        "venue": "home", "gf": df["home_goals"], "ga": df["away_goals"],
    })
    away = pd.DataFrame({
        "season": df["season"], "league_code": df["league_code"], "group_id": df["group_id"],
        "date": df["date"], "match_id": df["match_id"],
        "team_id": df["away_team_id"], "team": df["away_team"],
        "opponent_id": df["home_team_id"], "opponent": df["home_team"],
        "venue": "away", "gf": df["away_goals"], "ga": df["home_goals"],
    })
    long_df = pd.concat([home, away], ignore_index=True)
    long_df["points"] = long_df.apply(
        lambda r: 3 if r["gf"] > r["ga"] else (1 if r["gf"] == r["ga"] else 0), axis=1
    )
    return long_df.sort_values(["date", "match_id"]).reset_index(drop=True)


def table_as_of(
    df: pd.DataFrame,
    cutoff: Optional[str] = None,
    *,
    league_code: Optional[str] = None,
    season: Optional[str | int] = None,
    group_id: Optional[int] = None,
) -> pd.DataFrame:
    """Point-in-time standings from matches strictly before ``cutoff`` (no leakage).

    Filter to a single league/season/group first for a meaningful table.
    """

    g = df.copy()
    if league_code is not None:
        g = g[g["league_code"] == league_code]
    if season is not None:
        g = g[g["season"].astype(str) == str(season)]
    if group_id is not None:
        g = g[g["group_id"] == group_id]
    if cutoff is not None:
        g = g[g["date"] < pd.to_datetime(cutoff)]

    longf = to_team_long(g)
    agg = longf.groupby(["team_id", "team"]).agg(
        played=("gf", "size"),
        gf=("gf", "sum"), ga=("ga", "sum"), points=("points", "sum"),
    ).reset_index()
    agg["gd"] = agg["gf"] - agg["ga"]
    agg = agg.sort_values(["points", "gd", "gf"], ascending=False).reset_index(drop=True)
    agg["position"] = agg.index + 1
    return agg
