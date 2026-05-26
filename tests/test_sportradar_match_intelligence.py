from __future__ import annotations

import json
import unittest

from sandbox.sportradar_http.match_intelligence import build_match_intelligence


class SportradarMatchIntelligenceTests(unittest.TestCase):
    def test_builds_compact_bot_ready_intelligence(self) -> None:
        intelligence = build_match_intelligence(_snapshot_fixture(), _features_fixture())

        self.assertEqual(intelligence["schema_version"], 1)
        self.assertEqual(intelligence["match_id"], 61624678)
        self.assertEqual(intelligence["teams"]["home"]["name"], "Team A")
        self.assertEqual(intelligence["form"]["home"]["rating_10"], 6.67)
        self.assertEqual(intelligence["h2h"]["edge_label"], "Team A")
        self.assertEqual(intelligence["goal_context"]["btts_rate"], 0.72)
        self.assertEqual(intelligence["table_context"]["home"]["position_display"], "2nd (18 pts, 6P)")
        self.assertIsNotNone(intelligence["strength_indexes"]["home_strength_10"])

    def test_report_keeps_dates_for_h2h_and_traceability(self) -> None:
        intelligence = build_match_intelligence(_snapshot_fixture(), _features_fixture())
        report = intelligence["report_summary"]

        self.assertIn("22/06/24", report)
        self.assertIn("06/03/25", report)
        self.assertIn("12/04/26", report)
        self.assertIn("Common opponent Team B", report)

    def test_output_is_json_serializable(self) -> None:
        intelligence = build_match_intelligence(_snapshot_fixture(), _features_fixture())

        json.dumps(intelligence)


def _snapshot_fixture() -> dict:
    return {
        "metadata": {
            "match_id": 61624678,
            "home": {"uid": 10, "name": "Team A"},
            "away": {"uid": 20, "name": "Team C"},
            "competition": {"name": "Example League"},
            "kickoff": {"iso_utc": "2026-06-01T20:00:00+00:00"},
            "status": {"name": "Not started"},
            "score": {"home": None, "away": None},
            "season_id": 130805,
        },
        "team_form": {
            "home": {
                "form": ["W", "W", "D", "L", "L"],
                "recent_points": 10,
                "matches": [
                    _match(
                        match_id=1,
                        date="2026-04-12T00:00:00+00:00",
                        home_uid=10,
                        home_name="Team A",
                        away_uid=30,
                        away_name="Team B",
                        home_score=5,
                        away_score=0,
                        opponent_uid=30,
                        opponent_name="Team B",
                        result="W",
                    )
                ],
            },
            "away": {
                "form": ["L", "W", "D", "L", "W"],
                "recent_points": 7,
                "matches": [
                    _match(
                        match_id=2,
                        date="2025-03-06T00:00:00+00:00",
                        home_uid=30,
                        home_name="Team B",
                        away_uid=20,
                        away_name="Team C",
                        home_score=3,
                        away_score=1,
                        opponent_uid=30,
                        opponent_name="Team B",
                        result="L",
                    )
                ],
            },
        },
        "h2h": {
            "summary": {
                "total_matches": 3,
                "home_team_wins": 2,
                "away_team_wins": 1,
                "draws": 0,
            },
            "matches": [
                _match(
                    match_id=100,
                    date="2024-06-22T00:00:00+00:00",
                    home_uid=10,
                    home_name="Team A",
                    away_uid=20,
                    away_name="Team C",
                    home_score=5,
                    away_score=0,
                    opponent_uid=20,
                    opponent_name="Team C",
                    result="W",
                )
            ],
        },
        "table_context": {
            "rows": [
                {
                    "team": {"uid": 10, "name": "Team A"},
                    "position": 2,
                    "played": 6,
                    "points": 18,
                    "points_per_match": 3.0,
                    "goals_for": 20,
                    "goals_against": 6,
                    "goal_difference": 14,
                },
                {
                    "team": {"uid": 20, "name": "Team C"},
                    "position": 11,
                    "played": 5,
                    "points": 5,
                    "points_per_match": 1.0,
                    "goals_for": 7,
                    "goals_against": 15,
                    "goal_difference": -8,
                },
            ]
        },
        "team_scoring": {
            "home": {
                "scoring": {
                    "goals_scored_avg": {"total": 5.0, "home": 6.0, "away": 4.0},
                    "minutes_per_goal_scored": {"home": 20.0},
                },
                "conceding": {
                    "goals_conceded_avg": {"total": 1.0, "home": 0.0, "away": 2.0},
                    "minutes_per_goal_conceded": {"home": 90.0},
                },
            },
            "away": {
                "scoring": {
                    "goals_scored_avg": {"total": 3.0, "home": 4.0, "away": 2.0},
                    "minutes_per_goal_scored": {"away": 45.0},
                },
                "conceding": {
                    "goals_conceded_avg": {"total": 3.0, "home": 2.0, "away": 4.0},
                    "minutes_per_goal_conceded": {"away": 30.0},
                },
            },
        },
        "injuries": {
            "home": [{"player_name": "Player X", "status": "Injured", "missing": True}],
            "away": [],
        },
        "players": {
            "home": {"top_goals": [{"player_name": "Scorer A", "total": 12}]},
            "away": {"top_goals": [{"player_name": "Scorer C", "total": 8}]},
        },
        "live_state": {"raw_event_count": 0, "status": None},
        "feature_quality": {"data_completeness": 0.8},
    }


def _features_fixture() -> dict:
    return {
        "values": {
            "form_gap": 3,
            "table_position_gap": 9,
            "attack_strength_home": 1.7,
            "attack_strength_away": 1.1,
            "defense_weakness_home": 0.7,
            "defense_weakness_away": 1.5,
            "btts_tendency_index": 0.72,
            "over_tendency_index": 2.7,
            "live_score_state": None,
        }
    }


def _match(
    *,
    match_id: int,
    date: str,
    home_uid: int,
    home_name: str,
    away_uid: int,
    away_name: str,
    home_score: int,
    away_score: int,
    opponent_uid: int,
    opponent_name: str,
    result: str,
) -> dict:
    return {
        "match_id": match_id,
        "time": {"iso_utc": date},
        "home": {"uid": home_uid, "name": home_name},
        "away": {"uid": away_uid, "name": away_name},
        "score": {"home": home_score, "away": away_score},
        "opponent": {"uid": opponent_uid, "name": opponent_name},
        "result": result,
    }


if __name__ == "__main__":
    unittest.main()
