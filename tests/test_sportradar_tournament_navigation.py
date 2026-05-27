from __future__ import annotations

import json
import unittest

from sandbox.sportradar_http.tournament_navigation import (
    build_tournament_navigation_snapshot,
    build_tournament_tree,
    render_tournament_navigation_report,
    resolve_tournament,
)


class SportradarTournamentNavigationTests(unittest.TestCase):
    def test_build_tree_and_resolve_unique_tournament_id(self) -> None:
        tree = build_tournament_tree(_config_tree_fixture())
        resolved = resolve_tournament(tree, 18340)

        self.assertTrue(resolved["found"])
        self.assertEqual(resolved["match_kind"], "unique_tournament_id")
        self.assertEqual(resolved["season_id"], 138964)
        self.assertEqual(resolved["concrete_tournament_id"], 46533)
        self.assertEqual(resolved["primary"]["country_name"], "Australia")
        self.assertEqual(len(resolved["stages"]), 2)

    def test_snapshot_normalizes_fixtures_and_report_dates(self) -> None:
        snapshot = build_tournament_navigation_snapshot(
            sport_id=1,
            tournament_id=18340,
            config_tree_payload=_config_tree_fixture(),
            fixtures_payload=_fixtures_fixture(),
            max_fixtures=10,
        )
        report = render_tournament_navigation_report(snapshot)

        self.assertEqual(snapshot["fixture_count"], 1)
        self.assertEqual(snapshot["fixtures"][0]["match_id"], 7001)
        self.assertIn("2026-06-13T", report)
        self.assertIn("South Australia NPL, Women", report)
        json.dumps(snapshot)


def _config_tree_fixture() -> dict:
    return {
        "doc": [
            {
                "data": [
                    {
                        "_id": 1,
                        "_sid": 1,
                        "name": "Soccer",
                        "realcategories": [
                            {
                                "_id": 34,
                                "_sid": 1,
                                "_rcid": 34,
                                "name": "Australia",
                                "cc": {"a2": "au", "name": "Australia"},
                                "tournaments": [
                                    {
                                        "_id": 46533,
                                        "_sid": 1,
                                        "_rcid": 34,
                                        "_tid": 46533,
                                        "_utid": 18340,
                                        "name": "South Australia NPL, Women",
                                        "seasonid": 138964,
                                        "currentseason": 138964,
                                        "roundbyround": True,
                                    },
                                    {
                                        "_id": 86724,
                                        "_sid": 1,
                                        "_rcid": 34,
                                        "_tid": 86724,
                                        "_utid": 18340,
                                        "name": "South Australia NPL, Women, Final round",
                                        "seasonid": 127725,
                                        "currentseason": 138964,
                                        "roundbyround": True,
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        ],
        "queryUrl": "/bet365/en/Etc:UTC/gismo/config_tree_mini/67/0/1",
    }


def _fixtures_fixture() -> dict:
    return {
        "doc": [
            {
                "data": {
                    "matches": [
                        {
                            "_id": 7001,
                            "_seasonid": 138964,
                            "_utid": 18340,
                            "round": 10,
                            "roundname": {"name": "Round 10"},
                            "time": {"uts": 1781338200, "date": "13/06/26", "time": "05:30", "tz": "UTC"},
                            "teams": {
                                "home": {"_id": 100, "uid": 100, "name": "Home FC"},
                                "away": {"_id": 200, "uid": 200, "name": "Away FC"},
                            },
                            "result": {"home": None, "away": None, "winner": None},
                            "inlivescore": True,
                        }
                    ]
                }
            }
        ],
        "queryUrl": "/bet365/en/Etc:UTC/gismo/stats_season_fixtures2/138964",
    }


if __name__ == "__main__":
    unittest.main()
