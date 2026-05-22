from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from sandbox.sportradar_stats.probe_useful_http import (
    classify_probe_attempt,
    extract_json_exception_info,
    load_useful_records,
    render_probe_report,
    select_probe_targets,
    summarize_probe_results,
)


class SportradarProbeUsefulHttpTests(unittest.TestCase):
    def test_select_probe_targets_keeps_signed_useful_urls(self) -> None:
        records = [
            {
                "url": "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_markets/61624664?T=exp=123",
                "endpoint_name": "match_markets",
                "method": "GET",
                "signed_url": True,
            },
            {
                "url": "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_markets/61624664",
                "endpoint_name": "match_markets",
                "method": "GET",
                "signed_url": False,
            },
        ]
        targets = select_probe_targets(records)
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["endpoint_name"], "match_markets")

    def test_load_useful_records_falls_back_to_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            capture_dir = Path(tmp_dir_name)
            payload = [
                {
                    "url": "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_markets/61624664?T=exp=123",
                    "endpoint_name": "match_markets",
                }
            ]
            (capture_dir / "useful_fetch.json").write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            records, source_path = load_useful_records(capture_dir)
            self.assertEqual(len(records), 1)
            self.assertEqual(source_path.name, "useful_fetch.json")

    def test_probe_report_renders_mocked_summary(self) -> None:
        target_results = [
            {
                "url": "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_markets/61624664?T=exp=123",
                "endpoint_name": "match_markets",
                "conclusion": "HTTP reusable",
                "attempts": [
                    {
                        "attempt_label": "httpx_anonymous",
                        "status": 200,
                        "is_json": True,
                        "same_endpoint": True,
                        "body_size_bytes": 640,
                        "outcome": "reusable",
                    }
                ],
            },
            {
                "url": "https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_timeline/61624664?T=exp=expired",
                "endpoint_name": "match_timeline",
                "conclusion": "signature expired",
                "attempts": [
                    {
                        "attempt_label": "httpx_anonymous",
                        "status": 403,
                        "is_json": False,
                        "same_endpoint": False,
                        "body_size_bytes": 120,
                        "outcome": "signature_expired",
                    }
                ],
            },
        ]

        summary = summarize_probe_results(target_results)
        rendered = render_probe_report(
            {
                "generated_at": "2026-05-18T10:00:00+00:00",
                "source_file": "useful_fetch.ndjson",
                "cookie_source": None,
                **summary,
            }
        )

        self.assertIn("`match_markets`", rendered)
        self.assertIn("HTTP reusable", rendered)
        self.assertIn("signature expired", rendered)
        self.assertEqual(summary["endpoint_summaries"]["match_markets"]["count"], 1)

    def test_unauthorized_exception_payload_is_classified_as_blocked(self) -> None:
        payload = {
            "doc": [
                {
                    "event": "exception",
                    "data": {
                        "_doc": "exception",
                        "name": "Unauthorized",
                        "code": 403,
                        "message": "Unauthorized feed ",
                    },
                }
            ]
        }
        exception_info = extract_json_exception_info(payload)
        self.assertIsNotNone(exception_info)
        outcome = classify_probe_attempt(
            {
                "status": 200,
                "is_json": True,
                "same_endpoint": True,
                "json_exception": exception_info,
                "body_size_bytes": 149,
                "preview": None,
            },
            expected_endpoint_name="match_markets",
        )
        self.assertEqual(outcome, "blocked")


if __name__ == "__main__":
    unittest.main()
