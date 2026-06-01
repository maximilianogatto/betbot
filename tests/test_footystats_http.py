"""Unit tests for isolated FootyStats HTTP research helpers."""

from __future__ import annotations

import json
import unittest

import httpx

from sandbox.footystats_http.capture_traffic import build_endpoint_index, endpoint_key
from sandbox.footystats_http.client import FootyStatsHTTPClient
from sandbox.footystats_http.normalizers import (
    classify_url,
    discover_league_links,
    extract_embedded_match_data,
    extract_match_page_ids,
    extract_official_api_endpoints,
    extract_script_ajax_endpoints,
    parse_live_scores,
    parse_match_live_panel,
)
from sandbox.footystats_http.probe_http import classify_result


class FootyStatsNormalizerTests(unittest.TestCase):
    def test_discovers_and_deduplicates_public_league_links(self) -> None:
        html = """
        <a href='/australia/a-league'>A-League</a>
        <a href='/australia/a-league'>A-League</a>
        <a href='/clubs/example-1'>Club</a>
        <a href='/stats/xg'>Stats</a>
        """
        leagues = discover_league_links(html)
        self.assertEqual([item.path for item in leagues], ["/australia/a-league"])

    def test_parses_public_live_scores_defensively(self) -> None:
        scores = parse_live_scores(
            [
                {"match_id": 10, "team_a_score": "2", "team_b_score": 1, "minute": "64"},
                {"unexpected": True},
            ]
        )
        self.assertEqual(scores[0].to_dict(), {"match_id": "10", "home_score": 2, "away_score": 1, "minute": "64"})
        self.assertEqual(len(scores), 1)

    def test_extracts_match_ids_and_live_panel(self) -> None:
        html = """
        <script>var ziz=8535299; var zizz=15434;</script>
        <p class='ac fs2e bold'>2 <span class='normal dark-gray'>-</span> 0</p><p class='ac semi-bold mt05'>64<span>'</span></p>
        <tr class='row'><td class='item key' scope='row'>Corners</td><td class='item stat null'>4</td><td class='item stat null'>5</td></tr>
        """
        self.assertEqual(extract_match_page_ids(html), {"match_id": "8535299", "competition_id": "15434"})
        panel = parse_match_live_panel(html)
        self.assertEqual(panel["score_home"], 2)
        self.assertEqual(panel["score_away"], 0)
        self.assertEqual(panel["minute"], "64")
        self.assertEqual(panel["stats"]["Corners"], {"home": "4", "away": "5"})

    def test_extracts_embedded_league_match_data(self) -> None:
        html = '<script>var mh_matchData = [{"id":1,"status":"complete"},];</script>'
        self.assertEqual(extract_embedded_match_data(html), [{"id": 1, "status": "complete"}])

    def test_ignores_prematch_stat_rows_without_live_panel(self) -> None:
        html = """
        <tr class='row'><td class='item key' scope='row'>Corners</td><td class='item stat null'>4</td><td class='item stat null'>5</td></tr>
        """
        panel = parse_match_live_panel(html)
        self.assertFalse(panel["is_live_panel_present"])
        self.assertEqual(panel["stats"], {})

    def test_extracts_script_and_documented_api_endpoints(self) -> None:
        script = 'url:n+"ajax_livescore.php"; url:n+"ajax_matches.php";'
        docs = "GET https://api.football-data-api.com/match?key=YOURKEY&match_id=1"
        self.assertEqual(extract_script_ajax_endpoints(script), ["ajax_livescore.php", "ajax_matches.php"])
        self.assertEqual(extract_official_api_endpoints(docs), ["https://api.football-data-api.com/match"])

    def test_classifies_source_contracts(self) -> None:
        self.assertEqual(classify_url("https://footystats.org/ajax_livescore.php"), "public_ajax")
        self.assertEqual(classify_url("https://footystats.org/australia/a-league"), "public_html")
        self.assertEqual(classify_url("https://api.football-data-api.com/match?key=x"), "official_api")


class FootyStatsClientTests(unittest.TestCase):
    def test_fetches_live_scores_with_plain_http(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/ajax_livescore.php")
            return httpx.Response(200, json=[{"match_id": 7, "team_a_score": 1, "team_b_score": 0, "minute": "HT"}])

        with FootyStatsHTTPClient(transport=httpx.MockTransport(handler)) as client:
            scores = client.fetch_live_scores()
        self.assertEqual(scores[0].match_id, "7")
        self.assertEqual(scores[0].minute, "HT")

    def test_official_api_requires_explicit_key(self) -> None:
        with FootyStatsHTTPClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))) as client:
            with self.assertRaisesRegex(ValueError, "explicit API key"):
                client.official_api_request("match", params={"match_id": 1})


class FootyStatsCaptureTests(unittest.TestCase):
    def test_endpoint_index_groups_public_ajax(self) -> None:
        records = [
            {
                "endpoint_key": endpoint_key("https://footystats.org/ajax_livescore.php"),
                "url": "https://footystats.org/ajax_livescore.php",
                "status": 200,
                "resource_type": "xhr",
                "body_size_bytes": 10,
                "body_json": [],
            }
        ]
        index = build_endpoint_index(records)
        self.assertEqual(index["public_ajax:/ajax_livescore.php"]["count"], 1)
        self.assertTrue(index["public_ajax:/ajax_livescore.php"]["has_json"])

    def test_probe_classifies_empty_and_blocked_payloads(self) -> None:
        self.assertEqual(classify_result(200, b""), "empty")
        self.assertEqual(classify_result(403, b"blocked"), "blocked")
        self.assertEqual(classify_result(200, json.dumps({"ok": True}).encode()), "ok")


if __name__ == "__main__":
    unittest.main()
