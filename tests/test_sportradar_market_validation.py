from __future__ import annotations

import json
import unittest

from sandbox.sportradar_http.market_validation import (
    build_market_validation_report,
    build_sport_match_index,
    summarize_sport_markets,
)


class SportradarMarketValidationTests(unittest.TestCase):
    def test_build_match_index_and_summarize_priced_markets(self) -> None:
        index = build_sport_match_index(_overview_payload())
        summary = summarize_sport_markets(_markets_payload(), match_index=index)

        self.assertEqual(index[10]["home"], "Home FC")
        self.assertEqual(summary["counts"]["matches_with_market_payload"], 1)
        self.assertEqual(summary["counts"]["matches_with_active_priced_market"], 1)
        self.assertEqual(summary["counts"]["matches_with_1x2"], 1)
        self.assertEqual(summary["counts"]["matches_with_handicap"], 1)
        self.assertEqual(summary["counts"]["matches_with_totals"], 1)
        self.assertEqual(summary["sample_matches"][0]["home"], "Home FC")
        json.dumps(summary)

    def test_render_market_validation_report(self) -> None:
        summary = summarize_sport_markets(_markets_payload(), match_index=build_sport_match_index(_overview_payload()))
        report = build_market_validation_report([{"date": "2026-05-27", **summary}])

        self.assertIn("Sportradar Active Market Validation", report)
        self.assertIn("Home FC vs Away FC", report)


def _overview_payload() -> dict:
    return {
        "doc": [
            {
                "data": {
                    "sport": {
                        "realcategories": [
                            {
                                "name": "Australia",
                                "tournaments": [
                                    {
                                        "_utid": 1260,
                                        "seasonid": 140108,
                                        "name": "Capital NPL 1",
                                        "matches": [
                                            {
                                                "_id": 10,
                                                "inlivescore": True,
                                                "teams": {"home": {"name": "Home FC"}, "away": {"name": "Away FC"}},
                                                "time": {"uts": 1780120000},
                                                "result": {"period": "nt"},
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                }
            }
        ]
    }


def _markets_payload() -> dict:
    return {
        "queryUrl": "unified_sport_matches_markets/1/2026-05-27/0",
        "doc": [
            {
                "data": {
                    "matches": {
                        "10": {
                            "markets": [
                                {
                                    "name": "1x2",
                                    "active": True,
                                    "outcomes": [
                                        {"name": "{$competitor1}", "odds": 2.0, "active": True},
                                        {"name": "draw", "odds": 3.0, "active": True},
                                        {"name": "{$competitor2}", "odds": 4.0, "active": True},
                                    ],
                                },
                                {
                                    "name": "Handicap",
                                    "active": True,
                                    "specifiers": {"hcp": "-0.25"},
                                    "outcomes": [{"name": "{$competitor1}", "odds": 1.9, "active": True}],
                                },
                                {
                                    "name": "Total",
                                    "active": True,
                                    "specifiers": {"total": "2.5"},
                                    "outcomes": [{"name": "over", "odds": 1.8, "active": True}],
                                },
                            ]
                        }
                    }
                }
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
