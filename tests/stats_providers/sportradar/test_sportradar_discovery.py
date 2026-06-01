from __future__ import annotations

import unittest

from sandbox.sportradar_stats.discovery.discovery_core import (
    build_discovery_record,
    build_endpoints_index,
    extract_endpoint_name,
    infer_roles,
    should_capture_response,
)


class SportradarDiscoveryTests(unittest.TestCase):
    def test_filters_keep_gismo_fetch_and_drop_assets(self) -> None:
        self.assertTrue(
            should_capture_response(
                "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/sport_matches/1",
                "fetch",
                {"queryUrl": "sport_matches/1", "doc": [{"data": {}}]},
            )
        )
        self.assertFalse(
            should_capture_response(
                "https://statshub.sportradar.com/assets/app.css",
                "fetch",
                None,
            )
        )

    def test_extract_endpoint_name_prefers_query_url(self) -> None:
        endpoint = extract_endpoint_name(
            "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/20?T=exp=123",
            {"queryUrl": "stats_season_tables/1234"},
        )

        self.assertEqual(endpoint, "stats_season_tables")

    def test_infer_roles_for_discovery_names(self) -> None:
        self.assertIn("sport", infer_roles("sport_get", "/sport_get/:id"))
        self.assertIn("league", infer_roles("stats_season_tables", "/stats_season_tables/:id"))
        self.assertIn("fixture", infer_roles("sport_schedule", "/sport_schedule/:id"))
        self.assertIn("standings", infer_roles("stats_season_tables", "/stats_season_tables/:id"))
        self.assertIn("navigation", infer_roles("config_tree_mini", "/config_tree_mini/:id/:id/:id"))

    def test_build_record_and_index(self) -> None:
        record = build_discovery_record(
            {
                "captured_at": "2026-05-25T10:00:00+00:00",
                "elapsed_ms": 123,
                "method": "GET",
                "status": 200,
                "resource_type": "fetch",
                "url": "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/sport_matches/1?T=exp=123",
                "body_size_bytes": 250,
                "content_type": "application/json",
                "body_json": {
                    "queryUrl": "sport_matches/1",
                    "doc": [
                        {
                            "event": "sport_matches",
                            "data": {
                                "sport": {"_id": 1, "name": "Soccer"},
                                "tournaments": [{"_id": 99, "name": "League"}],
                            },
                        }
                    ],
                },
            }
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["endpoint_key"], "sport_matches")
        self.assertIn("sport", record["roles"])
        self.assertIn("1", record["id_patterns"]["path_ids"])
        self.assertIn("99", record["id_patterns"]["payload_ids"])

        index = build_endpoints_index([record])
        self.assertEqual(index["endpoint_count"], 1)
        self.assertEqual(index["endpoints"]["sport_matches"]["count"], 1)
        self.assertEqual(index["endpoints"]["sport_matches"]["example_url"], record["url"])


if __name__ == "__main__":
    unittest.main()
