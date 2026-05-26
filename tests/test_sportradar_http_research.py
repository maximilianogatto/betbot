from __future__ import annotations

import unittest

from sandbox.sportradar_stats.http_research.core import (
    build_endpoint_catalog,
    build_endpoint_record,
    classify_endpoint,
    extract_gismo_endpoint_key,
    normalize_endpoint_path,
    parse_signed_t,
    replace_endpoint_path_in_signed_url,
)


class SportradarHttpResearchTests(unittest.TestCase):
    def test_extract_gismo_endpoint_key_from_url_and_query_url(self) -> None:
        url = "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_timeline/61624678?T=exp=123"
        self.assertEqual(extract_gismo_endpoint_key(url), "match_timeline")
        self.assertEqual(
            extract_gismo_endpoint_key("https://x/gismo/20", {"queryUrl": "stats_season_tables/1/2"}),
            "stats_season_tables",
        )

    def test_normalize_endpoint_path(self) -> None:
        self.assertEqual(
            normalize_endpoint_path("https://sh.fn.sportradar.com/bet365/en/gismo/match_timeline/61624678"),
            "/bet365/en/gismo/match_timeline/:id",
        )
        self.assertEqual(
            normalize_endpoint_path("unused", {"queryUrl": "unified_sport_matches/1/2026-05-25/0"}),
            "/unified_sport_matches/:id/:date/:id",
        )

    def test_decode_signed_t_data(self) -> None:
        raw_t = (
            "exp=1779767584~acl=/*~"
            "data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUifQ~"
            "hmac=abc"
        )
        parsed = parse_signed_t(raw_t)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["exp"], 1779767584)
        self.assertEqual(parsed["acl"], "/*")
        self.assertEqual(parsed["data_json"]["a"], "bet365")
        self.assertEqual(parsed["data_json"]["o"], "https://statshub.sportradar.com")

    def test_classify_endpoint(self) -> None:
        self.assertIn("live_state", classify_endpoint("match_timeline"))
        self.assertIn("odds", classify_endpoint("match_markets"))
        self.assertIn("standings", classify_endpoint("stats_season_tables"))
        self.assertIn("fixtures", classify_endpoint("unified_sport_matches"))

    def test_build_endpoint_record_and_catalog(self) -> None:
        raw = {
            "captured_at": "2026-05-25T10:00:00+00:00",
            "elapsed_ms": 100,
            "method": "GET",
            "url": "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_markets/61624678?T=exp=1779767584~acl=/*~data=eyJhIjoiYmV0MzY1In0~hmac=abc",
            "resource_type": "fetch",
            "request_headers": {"Accept": "application/json", "Cookie": "secret=hidden"},
            "status": 200,
            "content_type": "application/json",
            "response_headers": {"content-type": "application/json"},
            "body_size_bytes": 200,
            "body_json": {"queryUrl": "match_markets/61624678", "doc": [{"event": "match_markets", "data": {"markets": []}}]},
        }
        record = build_endpoint_record(raw)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["endpoint_key"], "match_markets")
        self.assertTrue(record["has_signed_token"])
        self.assertNotIn("cookie", record["request_headers"])

        catalog = build_endpoint_catalog([record])
        self.assertEqual(catalog["endpoint_count"], 1)
        self.assertEqual(catalog["endpoints"]["match_markets"]["count"], 1)
        self.assertTrue(catalog["endpoints"]["match_markets"]["has_signed_token"])

    def test_replace_endpoint_path_preserves_signed_query(self) -> None:
        url = "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_markets/61624678?T=exp=1~hmac=abc"
        replaced = replace_endpoint_path_in_signed_url(url, "match_timeline/61624678")
        self.assertIn("/gismo/match_timeline/61624678", replaced)
        self.assertIn("T=exp=1~hmac=abc", replaced)


if __name__ == "__main__":
    unittest.main()
