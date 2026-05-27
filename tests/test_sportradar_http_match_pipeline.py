from __future__ import annotations

import json
import unittest

from sandbox.sportradar_http.features_engine import build_match_features
from sandbox.sportradar_http.normalizers import (
    normalize_match_details,
    normalize_match_markets,
    normalize_match_metadata,
    normalize_match_situation,
    normalize_match_table_slice,
    normalize_match_timeline,
    normalize_sport_match_markets,
    normalize_team_recent_payload,
    normalize_team_scoring,
)
from sandbox.sportradar_http.run_match_pipeline import build_feature_quality


class SportradarHTTPMatchPipelineTests(unittest.TestCase):
    def test_normalize_match_metadata_keeps_core_ids(self) -> None:
        payload = {
            "doc": [
                {
                    "data": {
                        "match": {
                            "_id": 10,
                            "_sid": 1,
                            "_seasonid": 99,
                            "_tid": 36,
                            "_utid": 8,
                            "round": 2,
                            "_dt": {"uts": 1779562800, "date": "23/05/26", "time": "19:00", "tz": "UTC"},
                            "teams": {"home": {"uid": 1, "name": "Home"}, "away": {"uid": 2, "name": "Away"}},
                            "result": {"home": 1, "away": 0, "winner": "home"},
                            "status": {"_id": 100, "name": "Ended"},
                        },
                        "tournament": {"name": "League"},
                        "season": {"_id": "99", "name": "League 25/26"},
                        "realcategory": {"name": "Spain"},
                    }
                }
            ]
        }

        metadata = normalize_match_metadata(payload)

        self.assertEqual(metadata["match_id"], 10)
        self.assertEqual(metadata["season_id"], 99)
        self.assertEqual(metadata["home"]["uid"], 1)
        self.assertEqual(metadata["competition"]["name"], "League")
        self.assertEqual(metadata["score"]["home"], 1)

    def test_normalize_match_markets_extracts_1x2_handicap_totals(self) -> None:
        payload = {
            "doc": [
                {
                    "data": {
                        "markets": [
                            {
                                "name": "1x2",
                                "outcomes": [
                                    {"name": "{$competitor1}", "odds": "2.10", "active": True},
                                    {"name": "draw", "odds": 3.2, "active": True},
                                    {"name": "{$competitor2}", "odds": 3.5, "active": True},
                                ],
                            },
                            {
                                "name": "Handicap",
                                "specifiers": {"hcp": "-0.25"},
                                "outcomes": [{"name": "{$competitor1} ({hcp})", "odds": 1.9, "active": True}],
                            },
                            {
                                "name": "Total",
                                "specifiers": {"total": "2.5"},
                                "outcomes": [{"name": "over {total}", "odds": 1.8, "active": True}],
                            },
                        ]
                    }
                }
            ]
        }

        normalized = normalize_match_markets(payload, home_name="Home", away_name="Away")

        markets = normalized["markets"]
        self.assertEqual(markets["1x2"], {"home": 2.1, "draw": 3.2, "away": 3.5})
        self.assertEqual(markets["handicap"][0]["line"], "-0.25")
        self.assertEqual(markets["totals"][0]["line"], "2.5")

    def test_normalize_sport_match_markets_extracts_one_match(self) -> None:
        payload = {
            "queryUrl": "unified_sport_matches_markets/1/2026-05-27/0",
            "doc": [
                {
                    "data": {
                        "matches": {
                            "10": {
                                "markets": [
                                    {
                                        "name": "1x2",
                                        "outcomes": [
                                            {"name": "{$competitor1}", "odds": 2.15, "active": True},
                                            {"name": "draw", "odds": 3.1, "active": True},
                                            {"name": "{$competitor2}", "odds": 3.8, "active": True},
                                        ],
                                    },
                                    {
                                        "name": "Handicap",
                                        "specifiers": {"hcp": "-0.25"},
                                        "outcomes": [{"name": "{$competitor1} ({+hcp})", "odds": 1.8, "active": True}],
                                    },
                                ]
                            }
                        }
                    }
                }
            ],
        }

        normalized = normalize_sport_match_markets(payload, match_id=10, home_name="Home", away_name="Away")

        self.assertEqual(normalized["source"], "unified_sport_matches_markets")
        self.assertEqual(normalized["markets"]["1x2"], {"home": 2.15, "draw": 3.1, "away": 3.8})
        self.assertEqual(normalized["markets"]["handicap"][0]["line"], "-0.25")

    def test_normalize_match_details_and_live_payloads_are_compact(self) -> None:
        details_payload = {
            "doc": [
                {
                    "data": {
                        "values": {
                            "110": {"name": "Ball possession", "value": {"home": 55, "away": 45}},
                            "125": {"name": "Shots on target", "value": {"home": 4, "away": 2}},
                        }
                    }
                }
            ]
        }
        timeline_payload = {
            "doc": [
                {
                    "data": {
                        "match": {
                            "result": {"home": 1, "away": 1},
                            "status": {"name": "Live"},
                            "timeinfo": {"played": "3600", "running": True},
                        },
                        "events": [
                            {"_id": "a", "type": "corner_kick", "team": "home", "time": 10, "name": "Corner"},
                            {
                                "_id": "b",
                                "type": "score_change",
                                "team": "away",
                                "time": 20,
                                "name": "Goal",
                                "result": {"home": 1, "away": 1},
                            },
                        ],
                    }
                }
            ]
        }
        situation_payload = {
            "doc": [
                {
                    "data": {
                        "data": [
                            {
                                "time": 1,
                                "home": {"dangerous": 2, "dangerouscount": 1, "attack": 3, "attackcount": 2},
                                "away": {"dangerous": 4, "dangerouscount": 3, "attack": 5, "attackcount": 4},
                            }
                        ]
                    }
                }
            ]
        }

        details = normalize_match_details(details_payload)
        timeline = normalize_match_timeline(timeline_payload)
        situation = normalize_match_situation(situation_payload)

        self.assertEqual(details["key_stats"]["possession"]["home"], 55.0)
        self.assertEqual(timeline["score_home"], 1)
        self.assertEqual(timeline["raw_event_count"], 2)
        self.assertEqual(situation["totals"]["away"]["dangerouscount"], 3)

    def test_match_features_are_json_serializable_and_defensive(self) -> None:
        snapshot = {
            "metadata": {"home": {"uid": 1}, "away": {"uid": 2}},
            "table_context": {
                "rows": [
                    {"team": {"uid": 1}, "position": 4, "points_per_match": 1.8},
                    {"team": {"uid": 2}, "position": 10, "points_per_match": 1.2},
                ]
            },
            "team_form": {"home": {"recent_points": 10}, "away": {"recent_points": 5}},
            "team_scoring": {
                "home": {
                    "scoring": {"goals_scored_avg": {"home": 1.7}, "btts_rate": {"home": 0.6}},
                    "conceding": {"goals_conceded_avg": {"home": 0.9}},
                },
                "away": {
                    "scoring": {"goals_scored_avg": {"away": 1.1}, "btts_rate": {"away": 0.5}},
                    "conceding": {"goals_conceded_avg": {"away": 1.4}},
                },
            },
            "h2h": {"summary": {"total_matches": 5, "home_team_wins": 3, "away_team_wins": 1}},
            "injuries": {"home": [1], "away": []},
            "live_state": {"score_home": 2, "score_away": 1},
            "live_situation": {
                "totals": {
                    "home": {"dangerouscount": 7},
                    "away": {"dangerouscount": 3},
                }
            },
        }

        features = build_match_features(snapshot)

        self.assertEqual(features["values"]["form_gap"], 5.0)
        self.assertEqual(features["values"]["table_position_gap"], 6.0)
        self.assertEqual(features["values"]["attack_strength_home"], 1.55)
        self.assertEqual(features["values"]["h2h_home_edge"], 0.4)
        self.assertEqual(features["values"]["live_pressure_home"], 0.7)
        json.dumps(features)

    def test_feature_quality_distinguishes_empty_odds_endpoint_from_priced_odds(self) -> None:
        quality = build_feature_quality(
            {"match_info": {}, "match_snapshot": {}, "match_markets": {}},
            {},
            odds={"markets": {"1x2": {}, "handicap": [], "totals": []}},
        )

        self.assertTrue(quality["has_odds_endpoint"])
        self.assertFalse(quality["has_priced_odds"])

    def test_recent_and_scoring_normalizers_keep_minimal_shape(self) -> None:
        recent_payload = {
            "doc": [
                {
                    "data": {
                        "team": {"_id": 1, "name": "Home"},
                        "matches": [
                            {
                                "_id": 1,
                                "teams": {"home": {"uid": 1, "name": "Home"}, "away": {"uid": 2, "name": "Away"}},
                                "result": {"home": 2, "away": 0},
                            }
                        ],
                    }
                }
            ]
        }
        scoring_payload = {
            "doc": [
                {
                    "data": {
                        "team": {"_id": 1, "name": "Home"},
                        "stats": {
                            "totalmatches": {"total": 10, "home": 5, "away": 5},
                            "scoring": {"goalsscoredaverage": {"total": 1.4, "home": 1.8, "away": 1.0}},
                            "conceding": {"goalsconcededaverage": {"total": 1.1, "home": 0.8, "away": 1.4}},
                        },
                    }
                }
            ]
        }

        recent = normalize_team_recent_payload(recent_payload, team_uid=1)
        scoring = normalize_team_scoring(scoring_payload)

        self.assertEqual(recent["form"], ["W"])
        self.assertEqual(recent["recent_points"], 3)
        self.assertEqual(scoring["scoring"]["goals_scored_avg"]["home"], 1.8)

    def test_table_slice_reuses_standing_shape(self) -> None:
        payload = {
            "doc": [
                {
                    "data": {
                        "_id": "1",
                        "currentround": 3,
                        "maxrounds": 6,
                        "tablerows": [
                            {
                                "pos": 2,
                                "team": {"uid": 1, "name": "Home"},
                                "total": 3,
                                "pointsTotal": 6,
                                "goalsForTotal": 5,
                                "goalsAgainstTotal": 2,
                                "goalDiffTotal": 3,
                            }
                        ],
                    }
                }
            ]
        }

        table = normalize_match_table_slice(payload)

        self.assertEqual(table["rows"][0]["points_per_match"], 2.0)


if __name__ == "__main__":
    unittest.main()
