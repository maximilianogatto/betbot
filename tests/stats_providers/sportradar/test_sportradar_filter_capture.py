from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from sandbox.sportradar_stats.filtering import (
    filter_capture_directory,
    normalize_filtered_record,
    should_keep_capture_record,
)


def make_record(
    *,
    url: str,
    resource_type: str,
    body_json: object | None = None,
    body_preview: str | None = None,
    status: int = 200,
    body_size: int = 123,
    elapsed_ms: float = 1234.5,
) -> dict[str, object]:
    return {
        "captured_at": "2026-05-15T12:00:00+00:00",
        "elapsed_ms": elapsed_ms,
        "url": url,
        "status": status,
        "resource_type": resource_type,
        "response_headers": {"content-type": "application/json"},
        "body_size": body_size,
        "body_json": body_json,
        "body_preview": body_preview,
    }


class SportradarFilterCaptureTests(unittest.TestCase):
    def test_assets_are_discarded_even_if_they_are_fetches(self) -> None:
        record = make_record(
            url="https://statshub.sportradar.com/assets/widget.css",
            resource_type="fetch",
            body_preview="body {}",
        )
        self.assertFalse(should_keep_capture_record(record))

    def test_gismo_match_timeline_is_kept(self) -> None:
        record = make_record(
            url="https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_timeline/61624664",
            resource_type="fetch",
            body_json={
                "queryUrl": "match_timeline/61624664",
                "doc": [
                    {
                        "event": "match_timeline",
                        "_maxage": 60,
                        "data": {
                            "match": {"_id": 61624664, "_doc": "match"},
                            "events": [],
                        },
                    }
                ],
            },
        )
        filtered = normalize_filtered_record(record)
        assert filtered is not None
        self.assertEqual(filtered["endpoint_key"], "match_timeline")
        self.assertIn("match_timeline", str(filtered["normalized_path"]))
        self.assertEqual(filtered["match_ids"], ["61624664"])

    def test_filter_capture_directory_groups_by_clean_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            capture_dir = Path(tmp_dir_name)
            responses_path = capture_dir / "responses.ndjson"
            raw_records = [
                make_record(
                    url="https://statshub.sportradar.com/assets/logo.svg",
                    resource_type="other",
                    body_preview="<svg></svg>",
                ),
                make_record(
                    url="https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_timeline/61624664",
                    resource_type="fetch",
                    body_json={
                        "queryUrl": "match_timeline/61624664",
                        "doc": [
                            {
                                "event": "match_timeline",
                                "_maxage": 60,
                                "data": {
                                    "match": {"_id": 61624664, "_doc": "match"},
                                    "events": [],
                                },
                            }
                        ],
                    },
                    body_size=400,
                    elapsed_ms=100.0,
                ),
                make_record(
                    url="https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_match_get/61624664",
                    resource_type="fetch",
                    body_json={
                        "queryUrl": "stats_match_get/61624664",
                        "doc": [
                            {
                                "event": "stats_match_get",
                                "_maxage": 3600,
                                "data": {
                                    "_id": 61624664,
                                    "_doc": "match",
                                    "teams": {"home": {"name": "Elche"}, "away": {"name": "Getafe"}},
                                },
                            }
                        ],
                    },
                    body_size=600,
                    elapsed_ms=250.0,
                ),
            ]
            with responses_path.open("w", encoding="utf-8") as handle:
                for record in raw_records:
                    handle.write(json.dumps(record, ensure_ascii=False))
                    handle.write("\n")

            result = filter_capture_directory(capture_dir)

            self.assertEqual(result["filtered_records_count"], 2)
            filtered_lines = [
                json.loads(line)
                for line in (capture_dir / "filtered_fetch.ndjson").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(filtered_lines), 2)

            endpoints_index = json.loads(
                (capture_dir / "endpoints_index.json").read_text(encoding="utf-8"),
            )
            self.assertIn("match_timeline", endpoints_index["endpoints"])
            self.assertIn("stats_match_get", endpoints_index["endpoints"])
            self.assertEqual(
                endpoints_index["endpoints"]["match_timeline"]["count"],
                1,
            )
            self.assertTrue(
                endpoints_index["endpoints"]["match_timeline"]["example_url"].endswith(
                    "/gismo/match_timeline/61624664",
                )
            )
            self.assertIn(
                "match",
                endpoints_index["endpoints"]["match_timeline"]["top_level_keys"],
            )


if __name__ == "__main__":
    unittest.main()
