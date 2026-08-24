"""Unit tests for UnifiedMatchReportBuilder service."""

import unittest

from services.unified_match_report import (
    compute_team_stability,
    find_common_opponents,
    render_unified_match_report,
)


class UnifiedMatchReportTests(unittest.TestCase):
    def test_compute_team_stability_with_events(self) -> None:
        events = [
            {
                "homeTeam": {"name": "Team A"},
                "awayTeam": {"name": "Team B"},
                "homeScore": {"current": 3},
                "awayScore": {"current": 1},
            },
            {
                "homeTeam": {"name": "Team C"},
                "awayTeam": {"name": "Team A"},
                "homeScore": {"current": 0},
                "awayScore": {"current": 2},
            },
            {
                "homeTeam": {"name": "Team A"},
                "awayTeam": {"name": "Team D"},
                "homeScore": {"current": 2},
                "awayScore": {"current": 2},
            },
        ]

        stability = compute_team_stability("Team A", events)
        self.assertEqual(stability["games_count"], 3)
        self.assertGreater(stability["score"], 0)
        self.assertEqual(stability["gf_avg"], 2.33)
        self.assertEqual(stability["ga_avg"], 1.0)
        self.assertIn("Team B", stability["opponents"])

    def test_conditioned_team_stability_home_only(self) -> None:
        events = [
            {
                "homeTeam": {"name": "Team A"},
                "awayTeam": {"name": "Team B"},
                "homeScore": {"current": 3},
                "awayScore": {"current": 1},
            },
            {
                "homeTeam": {"name": "Team C"},
                "awayTeam": {"name": "Team A"},
                "homeScore": {"current": 0},
                "awayScore": {"current": 2},
            },
        ]

        home_stability = compute_team_stability("Team A", events, side="home")
        self.assertEqual(home_stability["games_count"], 1)
        self.assertEqual(home_stability["gf_avg"], 3.0)

        away_stability = compute_team_stability("Team A", events, side="away")
        self.assertEqual(away_stability["games_count"], 1)
        self.assertEqual(away_stability["gf_avg"], 2.0)

    def test_find_common_opponents(self) -> None:
        home_opps = {"Rival X": "Team A 2-1 Rival X", "Rival Y": "Team A 3-0 Rival Y"}
        away_opps = {"Rival X": "Team B 1-1 Rival X", "Rival Z": "Team B 0-2 Rival Z"}

        common = find_common_opponents(home_opps, away_opps)
        self.assertIn("Rival X", common)
        self.assertNotIn("Rival Y", common)
        self.assertEqual(common["Rival X"]["home"], "Team A 2-1 Rival X")

    def test_render_unified_match_report_runs_without_error(self) -> None:
        snapshot = {
            "match": {"home": "Team A", "away": "Team B", "status_description": "Ended", "score_home": 2, "score_away": 1},
            "standings": {
                "tables": [
                    {
                        "name": "General",
                        "rows": [
                            {"team": {"name": "Team A"}, "position": 1, "played": 10, "points": 25, "goals_for": 20, "goals_against": 5},
                            {"team": {"name": "Team B"}, "position": 2, "played": 10, "points": 20, "goals_for": 15, "goals_against": 10},
                        ],
                    }
                ]
            },
            "home_last_events": [
                {"homeTeam": {"name": "Team A"}, "awayTeam": {"name": "Rival X"}, "homeScore": {"current": 2}, "awayScore": {"current": 1}},
            ],
            "away_last_events": [
                {"homeTeam": {"name": "Rival X"}, "awayTeam": {"name": "Team B"}, "homeScore": {"current": 1}, "awayScore": {"current": 1}},
            ],
        }

        report_md = render_unified_match_report(snapshot)
        self.assertIn("Team A vs Team B", report_md)
        self.assertIn("PROMEDIOS DE LA LIGA", report_md)
        self.assertIn("ESTABILIDAD Y CONSISTENCIA", report_md)
        self.assertIn("RIVALES EN COMÚN RECIENTES", report_md)
