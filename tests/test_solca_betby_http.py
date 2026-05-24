from __future__ import annotations

import unittest

from sandbox.solca.betby_http import (
    BetbyBrandConfig,
    build_league_odds_document,
    config_from_site_url,
    deep_merge,
    extract_handicap,
    extract_tournament_id,
    extract_totals,
    snapshot_versions_from_manifest,
)


class SolcaBetbyHttpTests(unittest.TestCase):
    def test_extract_tournament_id_from_bt_path(self) -> None:
        url = "https://solcasino.io/sports?bt-path=%2Fsoccer%2Faustralia%2Fnpl-western-australia-women-1891453782668222464"

        self.assertEqual(extract_tournament_id(url), "1891453782668222464")

    def test_config_from_supported_clone(self) -> None:
        config = config_from_site_url("https://rainbet.com/sports?bt-path=%2Fsoccer%2Fa-123456789012")

        self.assertEqual(config.platform, "rainbet")
        self.assertTrue(config.site_origin.startswith("https://rainbet.com"))

    def test_snapshot_versions_from_manifest_deduplicates(self) -> None:
        manifest = {
            "top_events_versions": [100, "101"],
            "rest_events_versions": [101, "bad", 102],
        }

        self.assertEqual(snapshot_versions_from_manifest(manifest), [100, 101, 102])

    def test_deep_merge_merges_snapshot_chunks(self) -> None:
        target = {"events": {"1": {"desc": {"a": 1}}}, "tournaments": {}}
        source = {"events": {"2": {"desc": {"b": 2}}}, "tournaments": {"9": {"name": "League"}}}

        self.assertEqual(
            deep_merge(target, source),
            {
                "events": {"1": {"desc": {"a": 1}}, "2": {"desc": {"b": 2}}},
                "tournaments": {"9": {"name": "League"}},
            },
        )

    def test_market_parsers_extract_totals_and_handicap(self) -> None:
        markets = {
            "18": {
                "total=2.5": {
                    "12": {"k": "1.91"},
                    "13": {"k": "1.89"},
                }
            },
            "16": {
                "hcp=-1.5": {
                    "1714": {"k": "2.21"},
                    "1715": {"k": "1.62"},
                }
            },
        }

        self.assertEqual(extract_totals(markets)[0]["over"], 1.91)
        self.assertEqual(extract_totals(markets)[0]["under"], 1.89)
        self.assertEqual(extract_handicap(markets)[0]["line"], -1.5)
        self.assertEqual(extract_handicap(markets)[0]["home"], 2.21)
        self.assertEqual(extract_handicap(markets)[0]["away"], 1.62)

    def test_build_league_odds_document_is_tracking_ready(self) -> None:
        snapshot = {
            "categories": {"4": {"name": "Australia"}},
            "tournaments": {
                "1891453782668222464": {
                    "category_id": "4",
                    "name": "NPL Western Australia, Women",
                    "slug": "npl-western-australia-women",
                }
            },
            "events": {
                "2669776007317295108": {
                    "desc": {
                        "scheduled": 1779608700,
                        "type": "match",
                        "sport": "1",
                        "tournament": "1891453782668222464",
                        "competitors": [
                            {"id": "371230", "name": "Subiaco AFC"},
                            {"id": "684595", "name": "Perth SC"},
                        ],
                    },
                    "markets": {
                        "1": {"": {"1": {"k": "8.8"}, "2": {"k": "5.4"}, "3": {"k": "1.25"}}},
                        "18": {"total=2.5": {"12": {"k": "1.35"}, "13": {"k": "2.82"}}},
                    },
                }
            },
        }

        document = build_league_odds_document(
            snapshot,
            config=BetbyBrandConfig(platform="solcasino", site_origin="https://solcasino.io"),
            source_url="https://solcasino.io/sports?bt-path=%2Fsoccer%2Faustralia%2Fnpl-western-australia-women-1891453782668222464",
            tournament_id="1891453782668222464",
            manifest={"version": 123},
            chunks=[{"version": 123}],
        )

        self.assertEqual(document["league"]["league"], "NPL Western Australia, Women")
        self.assertEqual(document["summary"]["matches_count"], 1)
        self.assertEqual(document["summary"]["matches_with_1x2"], 1)
        self.assertEqual(document["summary"]["matches_with_totals"], 1)
        self.assertEqual(document["matches"][0]["odds_1x2"]["1"], 8.8)
        self.assertEqual(document["matches"][0]["kickoff"]["date_utc"], "2026-05-24")


if __name__ == "__main__":
    unittest.main()
