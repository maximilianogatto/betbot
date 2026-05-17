from __future__ import annotations

import unittest

from sandbox.sportradar_stats.analysis import (
    build_endpoint_key,
    decode_maybe_base64_json,
    detect_capabilities,
    extract_sportradar_match_id,
    infer_polling_behavior,
    normalize_endpoint_path,
)


class SportradarStatsAnalysisTests(unittest.TestCase):
    def test_extract_sportradar_match_id(self) -> None:
        self.assertEqual(
            extract_sportradar_match_id("https://s5.sir.sportradar.com/bet365/en/match/61624664"),
            "61624664",
        )

    def test_decode_maybe_base64_json(self) -> None:
        decoded = decode_maybe_base64_json("eyJlbmRwb2ludCI6Im1hdGNoX3RpbWVsaW5lLzYxNjI0NjY0IiwidHlwZSI6InRpbWVsaW5lIn0")
        self.assertEqual(
            decoded,
            {"endpoint": "match_timeline/61624664", "type": "timeline"},
        )

    def test_normalize_endpoint_path_replaces_numeric_segments(self) -> None:
        self.assertEqual(
            normalize_endpoint_path("https://example.test/api/match_timeline/61624664"),
            "/api/match_timeline/:id",
        )

    def test_build_endpoint_key_prefers_decoded_request_data_hint(self) -> None:
        endpoint_key = build_endpoint_key(
            "https://example.test/61624664?data=abc",
            decoded_request_data={"endpoint": "match_timeline/61624664"},
        )
        self.assertEqual(endpoint_key, "/match_timeline/:id")

    def test_detect_capabilities_from_payload(self) -> None:
        capabilities = detect_capabilities(
            "/match_timeline/:id",
            {
                "match_id": 61624664,
                "status": "live",
                "score": {"home": 1, "away": 0},
                "timeline": [{"type": "yellow_card"}],
                "statistics": {"corners": {"home": 5, "away": 2}},
            },
        )
        self.assertTrue({"match_id", "live_state", "score", "timeline", "cards", "corners"} <= capabilities)

    def test_infer_polling_behavior_marks_fast_repeats(self) -> None:
        from datetime import datetime, timedelta, timezone

        base = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
        summary = infer_polling_behavior(
            [base, base + timedelta(seconds=1), base + timedelta(seconds=2)],
            3,
        )
        self.assertTrue(summary["polling_likely"])


if __name__ == "__main__":
    unittest.main()
