from __future__ import annotations

import unittest

from sandbox.sportradar_http.endpoints import discovery, live, matches, odds, standings, stats, tournaments
from sandbox.sportradar_http.endpoints.catalog import ENDPOINT_SPECS, extract_doc_data, render_endpoint_catalog_v2


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_gismo(self, endpoint_path: str, *, namespace: str = "bet365", timezone: str = "Etc:UTC", **kwargs: object):
        self.calls.append({"endpoint_path": endpoint_path, "namespace": namespace, "timezone": timezone, **kwargs})
        return {"queryUrl": endpoint_path, "doc": [{"event": endpoint_path.split("/", 1)[0], "data": {"ok": True}}]}


class SportradarHTTPEndpointsTests(unittest.TestCase):
    def test_discovery_wrappers_call_expected_paths(self) -> None:
        client = FakeClient()

        discovery.get_sport_overview(client, sport_id=1, date="2026-05-26")
        discovery.get_sport_matches_markets(client, sport_id=1, date="2026-05-26")
        discovery.get_config_tree_mini(client)

        self.assertEqual(client.calls[0]["endpoint_path"], "unified_sport_matches/1/2026-05-26/0")
        self.assertEqual(client.calls[0]["timezone"], "America:Montevideo")
        self.assertEqual(client.calls[1]["endpoint_path"], "unified_sport_matches_markets/1/2026-05-26/0")
        self.assertEqual(client.calls[2]["endpoint_path"], "config_tree_mini/67/0/1")

    def test_match_odds_standings_stats_live_wrappers(self) -> None:
        client = FakeClient()

        matches.get_match_info(client, match_id=61624678)
        odds.get_match_markets(client, match_id=61624678)
        standings.get_season_tables(client, season_id=130805)
        stats.get_team_lastx(client, team_id=2885, count=5)
        live.get_match_timeline(client, match_id=61624678)
        tournaments.get_tournament_fixtures(client, season_id=130805)

        paths = [call["endpoint_path"] for call in client.calls]
        self.assertIn("match_info_statshub/61624678", paths)
        self.assertIn("match_markets/61624678", paths)
        self.assertIn("stats_season_tables/130805//", paths)
        self.assertIn("stats_team_lastx/2885/5", paths)
        self.assertIn("match_timeline/61624678", paths)
        self.assertIn("stats_season_fixtures2/130805", paths)

    def test_catalog_documents_core_endpoints(self) -> None:
        self.assertIn("match_markets", ENDPOINT_SPECS)
        self.assertIn("stats_season_tables", ENDPOINT_SPECS)
        self.assertTrue(ENDPOINT_SPECS["match_timeline"].live)
        self.assertTrue(ENDPOINT_SPECS["unified_sport_matches"].prematch)

        rendered = render_endpoint_catalog_v2()
        self.assertIn("match_markets", rendered)
        self.assertIn("Replay Requirements", rendered)

    def test_extract_doc_data_is_defensive(self) -> None:
        self.assertEqual(extract_doc_data({"doc": [{"data": {"x": 1}}]}), {"x": 1})
        self.assertIsNone(extract_doc_data({}))


if __name__ == "__main__":
    unittest.main()

