from __future__ import annotations

import unittest

from sandbox.sportradar_http.features_engine import build_league_features
from sandbox.sportradar_http.normalizers import (
    normalize_fixtures,
    normalize_formtable,
    normalize_league_summary,
    normalize_standings,
)


class SportradarHTTPLeaguePipelineTests(unittest.TestCase):
    def test_normalize_league_summary_and_features(self) -> None:
        payload = {
            "queryUrl": "stats_season_leaguesummary/1",
            "doc": [
                {
                    "event": "stats_season_leaguesummary",
                    "data": {
                        "matches": {"played": 10, "home_wins": 5, "away_wins": 2, "draws": 3},
                        "goals": {"total": 28, "pr_match": 2.8},
                        "clean_sheet": {"total": 4},
                        "both_teams_to_score": {"total": 6},
                    },
                }
            ],
        }
        summary = normalize_league_summary(payload)
        snapshot = {
            "league_summary": summary,
            "standings": {
                "tables": [
                    {
                        "current_round": 10,
                        "max_rounds": 20,
                        "rows": [
                            {"points_per_match": 2.0},
                            {"points_per_match": 1.8},
                            {"points_per_match": 1.6},
                            {"points_per_match": 1.4},
                            {"points_per_match": 1.2},
                        ],
                    }
                ]
            },
        }
        features = build_league_features(snapshot)["values"]

        self.assertEqual(summary["matches_played"], 10)
        self.assertEqual(features["league_home_win_rate"], 0.5)
        self.assertEqual(features["league_btts_rate"], 0.6)
        self.assertEqual(features["season_progress"], 0.5)
        self.assertEqual(features["table_compactness_top5_ppm_gap"], 0.8)

    def test_normalize_standings_extracts_rows(self) -> None:
        payload = {
            "doc": [
                {
                    "data": {
                        "_id": "99",
                        "_utid": 8,
                        "name": "League",
                        "tables": [
                            {
                                "_id": "1",
                                "name": "League",
                                "currentround": 5,
                                "maxrounds": 10,
                                "tablerows": [
                                    {
                                        "pos": 1,
                                        "team": {"uid": 10, "name": "A"},
                                        "total": 5,
                                        "pointsTotal": 12,
                                        "winTotal": 4,
                                        "drawTotal": 0,
                                        "lossTotal": 1,
                                        "goalsForTotal": 10,
                                        "goalsAgainstTotal": 4,
                                        "goalDiffTotal": 6,
                                    }
                                ],
                            }
                        ],
                    }
                }
            ]
        }

        normalized = normalize_standings(payload)

        row = normalized["tables"][0]["rows"][0]
        self.assertEqual(row["team"]["name"], "A")
        self.assertEqual(row["points_per_match"], 2.4)

    def test_normalize_fixtures_is_compact(self) -> None:
        payload = {
            "doc": [
                {
                    "data": {
                        "matches": [
                            {
                                "_id": 1,
                                "round": 2,
                                "teams": {"home": {"uid": 10, "name": "A"}, "away": {"uid": 20, "name": "B"}},
                                "result": {"home": 2, "away": 1, "winner": "home"},
                                "time": {"date": "01/01/26", "time": "20:00", "tz": "UTC", "uts": 1767297600},
                            }
                        ]
                    }
                }
            ]
        }

        fixtures = normalize_fixtures(payload)

        self.assertEqual(fixtures[0]["match_id"], 1)
        self.assertEqual(fixtures[0]["home"]["name"], "A")
        self.assertEqual(fixtures[0]["result"]["winner"], "home")
        self.assertNotIn("comment", fixtures[0])

    def test_normalize_formtable_preserves_form_sequence(self) -> None:
        payload = {
            "doc": [
                {
                    "data": {
                        "currentround": 3,
                        "teams": [
                            {
                                "team": {"uid": 1, "name": "A"},
                                "points": {"total": 7},
                                "form": {"total": [{"value": "W"}, {"value": "D"}, {"value": "L"}]},
                            }
                        ],
                    }
                }
            ]
        }

        normalized = normalize_formtable(payload)

        self.assertEqual(normalized["current_round"], 3)
        self.assertEqual(normalized["teams"][0]["form_total"], ["W", "D", "L"])


if __name__ == "__main__":
    unittest.main()

