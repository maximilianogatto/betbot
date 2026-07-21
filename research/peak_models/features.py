"""Point-in-time form/momentum/schedule features (protocolo §3.3).

Everything is computed by a single chronological sweep per league: when a match
is processed, its features only see matches that FINISHED earlier (anti-leakage
by construction). Elo runs across seasons within a league; newly promoted teams
start at the league mean (1500) — a known limitation until the multi-league
hierarchical model links divisions.

Feature families (per team, mirrored home/away + diffs):
- ``elo``: pre-match Elo (K=24, home advantage 60 pts inside the expectation).
- ``form5_pts``: points in the last 5 games.
- ``mom5``: Elo now minus Elo 5 games ago (rating slope — regime shifts).
- ``adj_form5``: sum of (actual score − Elo-expected score) over last 5 games.
  Positive = over-performing expectations lately ("viene ganando partidos que
  no debía ganar"), the quantitative version of beating good teams.
- ``sos5``: mean pre-match Elo of the last 5 opponents (schedule strength).
- ``ppg_vs_stronger8``: PPG over the last 8 games against opponents that had a
  HIGHER pre-match Elo ("cómo le fue contra equipos mejores"); NaN if none.
"""

from __future__ import annotations

from collections import defaultdict, deque

import numpy as np
import pandas as pd

ELO_START = 1500.0
ELO_K = 24.0
ELO_HOME = 60.0

_TEAM_COLS = ["elo", "form5_pts", "mom5", "adj_form5", "sos5", "ppg_vs_stronger8", "gp"]


def build_features(matches: pd.DataFrame) -> pd.DataFrame:
    """One row per match_id with home_*/away_* features and *_diff columns."""

    df = (matches.dropna(subset=["home_goals", "away_goals"])
          .sort_values(["date", "match_id"]).copy())
    elo: dict = defaultdict(lambda: ELO_START)
    hist: dict = defaultdict(lambda: deque(maxlen=8))  # (pts, s_act-s_exp, opp_elo, stronger)
    elo_track: dict = defaultdict(lambda: deque(maxlen=6))  # elo before each game
    games: dict = defaultdict(int)  # total played (hist is capped at 8)

    rows = []
    for lg, g in df.groupby("league_code", sort=False):
        elo.clear(); hist.clear(); elo_track.clear(); games.clear()
        for r in g.sort_values(["date", "match_id"]).itertuples():
            h, a = r.home_team_id, r.away_team_id
            eh, ea = elo[h], elo[a]

            def team_feats(team, own_elo, opp_elo):
                hh = list(hist[team])
                track = list(elo_track[team])
                last5 = hh[-5:]
                feats = {
                    "elo": own_elo,
                    "form5_pts": sum(x[0] for x in last5) if last5 else np.nan,
                    "adj_form5": sum(x[1] for x in last5) if last5 else np.nan,
                    "sos5": np.mean([x[2] for x in last5]) if last5 else np.nan,
                    "mom5": own_elo - track[0] if len(track) >= 5 else np.nan,
                    "gp": games[team],
                }
                strong = [x for x in hh if x[3]]
                feats["ppg_vs_stronger8"] = (np.mean([x[0] for x in strong])
                                             if strong else np.nan)
                return feats

            fh = team_feats(h, eh, ea)
            fa = team_feats(a, ea, eh)
            row = {"match_id": r.match_id, "league_code": lg, "date": r.date}
            for k in _TEAM_COLS:
                row[f"home_{k}"] = fh[k]
                row[f"away_{k}"] = fa[k]
                row[f"{k}_diff"] = (fh[k] - fa[k]
                                    if pd.notna(fh[k]) and pd.notna(fa[k]) else np.nan)
            rows.append(row)

            # ---- update state AFTER computing features (no leakage) ----
            exp_h = 1.0 / (1.0 + 10 ** (-((eh + ELO_HOME) - ea) / 400.0))
            s_h = 1.0 if r.home_goals > r.away_goals else (0.5 if r.home_goals == r.away_goals else 0.0)
            pts_h = 3 if s_h == 1.0 else (1 if s_h == 0.5 else 0)
            pts_a = 3 if s_h == 0.0 else (1 if s_h == 0.5 else 0)
            games[h] += 1; games[a] += 1
            elo_track[h].append(eh); elo_track[a].append(ea)
            hist[h].append((pts_h, s_h - exp_h, ea, ea > eh))
            hist[a].append((pts_a, (1 - s_h) - (1 - exp_h), eh, eh > ea))
            elo[h] = eh + ELO_K * (s_h - exp_h)
            elo[a] = ea + ELO_K * ((1 - s_h) - (1 - exp_h))

    return pd.DataFrame(rows)
