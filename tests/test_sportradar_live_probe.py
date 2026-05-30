from __future__ import annotations

import unittest

from sandbox.sportradar_http_research.run_live_probe import build_live_probe_summary, render_live_probe_report


class SportradarLiveProbeTests(unittest.TestCase):
    def test_live_probe_summary_and_report_are_compact(self) -> None:
        records = [
            {
                "poll_index": 0,
                "captured_at": "2026-05-26T00:00:00+00:00",
                "document": {
                    "live_state": {"status": "Live", "score_home": 1, "score_away": 0, "raw_event_count": 12},
                    "live_delta": {"raw_event_count": 2},
                    "live_situation": {"raw_sample_count": 30},
                    "feature_quality": {"has_timeline": True},
                },
            }
        ]

        summary = build_live_probe_summary(records, metrics={"total_requests": 1})
        report = render_live_probe_report(summary)

        self.assertEqual(summary["poll_count"], 1)
        self.assertEqual(summary["records"][0]["delta_events"], 2)
        self.assertIn("match_timelinedelta", report)
        self.assertNotIn("\"document\"", report)


if __name__ == "__main__":
    unittest.main()
