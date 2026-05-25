from __future__ import annotations

import unittest

from sandbox.solca.betby_http import (
    BetbyBrandConfig,
    build_live_url,
    build_league_odds_document,
    config_from_site_url,
    deep_merge,
    extract_handicap,
    extract_live_state,
    extract_tournament_id,
    extract_totals,
    snapshot_versions_from_manifest,
)


class SolcaBetbyHttpTests(unittest.TestCase):
    def test_extract_tournament_id_from_bt_path(self) -> None:
        url = "https://solcasino.io/sports?bt-path=%2Fsoccer%2Faustralia%2Fnpl-western-australia-women-1891453782668222464"

        self.assertEqual(extract_tournament_id(url), "1891453782668222464")

    def test_extract_tournament_id_from_plain_path(self) -> None:
        url = "https://demo.betby.com/sportsbook/sidebar/soccer/australia/queensland-premier-league-1-1899821103254212608"

        self.assertEqual(extract_tournament_id(url), "1899821103254212608")

    def test_config_from_supported_clone(self) -> None:
        config = config_from_site_url("https://rainbet.com/sports?bt-path=%2Fsoccer%2Fa-123456789012")

        self.assertEqual(config.platform, "rainbet")
        self.assertTrue(config.site_origin.startswith("https://rainbet.com"))

    def test_config_from_demo_betby(self) -> None:
        config = config_from_site_url("https://demo.betby.com/sportsbook/sidebar/soccer/australia/a-123456789012")

        self.assertEqual(config.platform, "betby_demo")
        self.assertEqual(config.api_host, "demoapi.betby.com")
        self.assertEqual(config.brand_id, "1653815133341880320")
        self.assertIn("/api/v4/live/brand/", build_live_url(config, 0))

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

    def test_extract_live_state_from_betby_event(self) -> None:
        event = {
            "state": {
                "provider": "35b93b7a",
                "status": 1,
                "match_status": 6,
                "clock": {"match_time": "02:50", "timestamp": 1779609912121},
            }
        }

        live_state = extract_live_state(event, feed="live")

        self.assertTrue(live_state["in_live_feed"])
        self.assertTrue(live_state["is_live"])
        self.assertEqual(live_state["status_code"], 1)
        self.assertEqual(live_state["match_status_code"], 6)
        self.assertEqual(live_state["clock"]["match_time"], "02:50")

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

    def test_build_live_league_document_keeps_live_state(self) -> None:
        snapshot = {
            "categories": {"1669818988831576064": {"name": "Australia"}},
            "tournaments": {
                "1899821103254212608": {
                    "category_id": "1669818988831576064",
                    "name": "Queensland Premier League 1",
                }
            },
            "events": {
                "2668418987494346793": {
                    "desc": {
                        "scheduled": 1779609600,
                        "type": "match",
                        "sport": "1",
                        "tournament": "1899821103254212608",
                        "competitors": [
                            {"id": "313095", "name": "St George Willawong FC"},
                            {"id": "1098127", "name": "Ipswich FC"},
                        ],
                    },
                    "state": {
                        "provider": "35b93b7a",
                        "status": 1,
                        "match_status": 6,
                        "clock": {"match_time": "02:50", "timestamp": 1779609912121},
                    },
                    "markets": {
                        "1": {"": {"1": {"k": "1.7"}, "2": {"k": "3.9"}, "3": {"k": "4.2"}}},
                        "18": {"total=2.5": {"12": {"k": "1.9"}, "13": {"k": "1.8"}}},
                    },
                }
            },
        }

        document = build_league_odds_document(
            snapshot,
            config=BetbyBrandConfig(
                platform="betby_demo",
                site_origin="https://demo.betby.com",
                api_host="demoapi.betby.com",
                brand_id="1653815133341880320",
            ),
            source_url="https://demo.betby.com/sportsbook/sidebar/soccer/australia/queensland-premier-league-1-1899821103254212608",
            tournament_id="1899821103254212608",
            feed="live",
        )

        self.assertEqual(document["source"]["feed"], "live")
        self.assertEqual(document["summary"]["matches_in_live_feed"], 1)
        self.assertEqual(document["summary"]["matches_currently_live"], 1)
        self.assertEqual(document["matches"][0]["live_state"]["clock"]["match_time"], "02:50")


if __name__ == "__main__":
    unittest.main()
