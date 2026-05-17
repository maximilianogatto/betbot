from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.analysis import render_filtered_capture_report
from sandbox.sportradar_stats.filtering import (
    finalize_endpoint_index,
    iter_ndjson_records,
    normalize_filtered_record,
    update_endpoint_index,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze filtered Sportradar capture files and render a Markdown report.",
    )
    parser.add_argument(
        "capture_dir",
        type=Path,
        help="Directory containing filtered_fetch.ndjson or raw responses.ndjson.",
    )
    return parser.parse_args()


def mirror_report_if_possible(capture_dir: Path, report_text: str) -> None:
    parent = capture_dir.parent
    if parent.name != "captures":
        return

    sandbox_dir = parent.parent
    if sandbox_dir.name != "sportradar_stats":
        return

    (sandbox_dir / "endpoint_report.md").write_text(report_text, encoding="utf-8")


def build_index_and_samples(
    capture_dir: Path,
) -> tuple[dict[str, object], dict[str, dict[str, object]], Path]:
    filtered_path = capture_dir / "filtered_fetch.ndjson"
    responses_path = capture_dir / "responses.ndjson"
    source_path = filtered_path if filtered_path.exists() else responses_path
    if not source_path.exists():
        raise FileNotFoundError(
            f"No existe ni {filtered_path} ni {responses_path}",
        )

    buckets: dict[str, dict[str, object]] = {}
    endpoint_samples: dict[str, dict[str, object]] = {}
    filtered_records_count = 0

    if source_path == filtered_path:
        iterator = iter_ndjson_records(filtered_path)
    else:
        iterator = (
            filtered
            for raw in iter_ndjson_records(responses_path)
            for filtered in [normalize_filtered_record(raw)]
            if filtered is not None
        )

    for filtered_record in iterator:
        endpoint_key = str(filtered_record.get("endpoint_key") or "").strip()
        if not endpoint_key:
            continue

        filtered_records_count += 1
        update_endpoint_index(buckets, filtered_record)
        endpoint_samples.setdefault(endpoint_key, filtered_record)

    index_payload = finalize_endpoint_index(
        buckets,
        source_file=str(source_path),
        filtered_records_count=filtered_records_count,
    )
    return index_payload, endpoint_samples, source_path


def main() -> int:
    args = parse_args()
    capture_dir = args.capture_dir.resolve()

    index_payload, endpoint_samples, source_path = build_index_and_samples(capture_dir)
    report_text = render_filtered_capture_report(
        index_payload,
        endpoint_samples,
        capture_dir=str(capture_dir),
        source_name=source_path.name,
    )

    report_path = capture_dir / "endpoint_report.md"
    report_path.write_text(report_text, encoding="utf-8")
    mirror_report_if_possible(capture_dir, report_text)

    index_path = capture_dir / "endpoints_index.json"
    if not index_path.exists():
        index_path.write_text(
            json.dumps(index_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
