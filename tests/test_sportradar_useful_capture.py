from __future__ import annotations

import unittest

from sandbox.sportradar_stats.capture_useful import (
    build_useful_endpoints_index,
    detect_useful_endpoint_name,
    should_capture_useful_response,
)


class SportradarUsefulCaptureTests(unittest.TestCase):
    def test_detect_useful_endpoint_name_from_gismo_url(self) -> None:
        endpoint_name = detect_useful_endpoint_name(
            "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_timeline/61624664?T=exp=123",
        )
        self.assertEqual(endpoint_name, "match_timeline")

    def test_allowlist_keeps_match_timeline_and_discards_assets(self) -> None:
        self.assertTrue(
            should_capture_useful_response(
                url="https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_timeline/61624664?T=exp=123",
                resource_type="fetch",
            )
        )
        self.assertFalse(
            should_capture_useful_response(
                url="https://statshub.sportradar.com/assets/widget.css",
                resource_type="fetch",
            )
        )

    def test_build_useful_endpoints_index_groups_by_clean_endpoint(self) -> None:
        records = [
            {
                "captured_at": "2026-05-18T10:00:00+00:00",
                "elapsed_ms": 100.0,
                "status": 200,
                "url": "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_timeline/61624664?T=exp=123",
                "host": "sh.fn.sportradar.com",
                "resource_type": "fetch",
                "content_type": "application/json",
                "normalized_path": "/match_timeline/:id",
                "endpoint_name": "match_timeline",
                "endpoint_key": "match_timeline",
                "endpoint_path": "match_timeline/61624664",
                "query_url": "match_timeline/61624664",
                "doc_event": "match_timeline",
                "maxage_seconds": 60,
                "body_json": {"queryUrl": "match_timeline/61624664", "doc": [{"data": {"match": {"_id": 61624664}}}]},
                "preview": None,
                "body_size_bytes": 512,
                "top_level_keys": ["match"],
                "match_id": "61624664",
                "match_ids": ["61624664"],
                "signed_url": True,
            }
        ]

        index = build_useful_endpoints_index(records, source_file="useful_fetch.ndjson")
        self.assertEqual(index["endpoint_count"], 1)
        self.assertEqual(index["endpoints"]["match_timeline"]["count"], 1)
        self.assertEqual(
            index["endpoints"]["match_timeline"]["example_url"],
            "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_timeline/61624664?T=exp=123",
        )


if __name__ == "__main__":
    unittest.main()
