from __future__ import annotations

import json
import unittest

from sandbox.sportradar_stats.features_builder import (
    build_derived_features,
    build_match_features_document,
)


class SportradarFeaturesBuilderTests(unittest.TestCase):
    def test_build_derived_features_handles_empty_snapshot(self) -> None:
        features = build_derived_features({})

        self.assertIsNone(features["form_gap"])
        self.assertIsNone(features["points_per_match_home"])
        self.assertIsNone(features["h2h_home_edge"])
        self.assertIsNone(features["live_clock_state"])

    def test_build_derived_features_computes_simple_metrics(self) -> None:
        snapshot = {
            "snapshot_metadata": {
                "snapshot_version": 1,
                "capture_type": "prematch",
            },
            "team_standing": {
                "home": {
                    "position": 5,
                    "points": 54,
                    "matches": 30,
                    "goal_diff": 12,
                    "goals_for": 45,
                    "goals_against": 33,
                },
                "away": {
                    "position": 9,
                    "points": 42,
                    "matches": 30,
                    "goal_diff": 2,
                    "goals_for": 36,
                    "goals_against": 34,
                },
            },
            "team_score": {
                "home": {"form": {"recent_points": 10}},
                "away": {"form": {"recent_points": 7}},
            },
            "team_scoring": {
                "home": {
                    "derived_features": {
                        "goals_scored_avg_home": 1.8,
                        "goals_conceded_avg_home": 0.9,
                        "both_teams_scored_rate": 0.6,
                    }
                },
                "away": {
                    "derived_features": {
                        "goals_scored_avg_away": 0.8,
                        "goals_conceded_avg_away": 1.6,
                        "both_teams_scored_rate": 0.4,
                    }
                },
            },
            "h2h": {
                "summary": {
                    "total_matches": 10,
                    "home_team_wins": 6,
                    "away_team_wins": 2,
                }
            },
            "injuries": {
                "home": [{"player_id": "1"}, {"player_id": "2"}],
                "away": [{"player_id": "3"}],
            },
            "live_state": {
                "status": "Not started",
                "period": "NS",
                "score_home": None,
                "score_away": None,
                "clock": None,
            },
        }

        features = build_derived_features(snapshot)

        self.assertEqual(features["form_gap"], 3)
        self.assertEqual(features["table_position_gap"], 4)
        self.assertEqual(features["points_per_match_home"], 1.8)
        self.assertEqual(features["points_per_match_away"], 1.4)
        self.assertEqual(features["goals_for_avg_home"], 1.8)
        self.assertEqual(features["goals_for_avg_away"], 0.8)
        self.assertEqual(features["goals_against_avg_home"], 0.9)
        self.assertEqual(features["goals_against_avg_away"], 1.6)
        self.assertEqual(features["goal_difference_gap"], 10.0)
        self.assertEqual(features["home_attack_strength"], 1.7)
        self.assertEqual(features["away_attack_strength"], 0.85)
        self.assertEqual(features["home_defense_weakness"], 0.9)
        self.assertEqual(features["away_defense_weakness"], 1.6)
        self.assertEqual(features["over_tendency_index"], 2.55)
        self.assertEqual(features["btts_tendency_index"], 0.5)
        self.assertEqual(features["h2h_sample_size"], 10)
        self.assertEqual(features["h2h_home_edge"], 0.4)
        self.assertEqual(features["h2h_away_edge"], -0.4)
        self.assertEqual(features["injuries_count_home"], 2)
        self.assertEqual(features["injuries_count_away"], 1)
        self.assertEqual(features["live_score_state"], "not_started")
        self.assertEqual(features["live_clock_state"], "not_started")

    def test_build_derived_features_preserves_none_when_data_missing(self) -> None:
        snapshot = {
            "snapshot_metadata": {"snapshot_version": 1, "capture_type": "unknown"},
            "team_standing": {"home": {"points": 30, "matches": 20}, "away": {}},
            "team_score": {"home": {"form": {}}, "away": {"form": {}}},
            "team_scoring": {"home": {"derived_features": {}}, "away": {"derived_features": {}}},
            "injuries": {"home": [], "away": []},
        }

        features = build_derived_features(snapshot)

        self.assertEqual(features["points_per_match_home"], 1.5)
        self.assertIsNone(features["points_per_match_away"])
        self.assertIsNone(features["goals_for_avg_home"])
        self.assertIsNone(features["btts_tendency_index"])
        self.assertIsNone(features["live_score_state"])

    def test_feature_document_is_json_serializable(self) -> None:
        snapshot = {
            "snapshot_metadata": {"snapshot_version": 1, "capture_type": "live"},
            "source_capture_dir": "sandbox/sportradar_stats/captures/test",
            "match_id": "61624664",
            "home": "Elche",
            "away": "Getafe",
            "competition": "LaLiga",
            "season": "LaLiga 25/26",
            "round": 37,
            "kickoff_utc": "2026-05-17T17:00:00+00:00",
            "team_standing": {},
            "team_score": {},
            "team_scoring": {},
            "injuries": {},
            "live_state": {"score_home": 1, "score_away": 0, "clock": 67},
            "h2h": {},
        }

        document = build_match_features_document(snapshot, source_snapshot_path="/tmp/match_snapshot.json")
        rendered = json.dumps(document, ensure_ascii=False)

        self.assertIn('"match_id": "61624664"', rendered)
        self.assertIn('"capture_type": "live"', rendered)
        self.assertEqual(document["derived_features"]["live_score_state"], "home_leading")
        self.assertEqual(document["derived_features"]["live_clock_state"], "running:67")


if __name__ == "__main__":
    unittest.main()
