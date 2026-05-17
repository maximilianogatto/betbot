from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.analysis import render_endpoint_report, summarize_capture_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze one captured Sportradar / Bet365Stats feed directory."
    )
    parser.add_argument(
        "capture_dir",
        type=Path,
        help="Directory containing responses.ndjson.",
    )
    return parser.parse_args()


def load_ndjson(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            normalized = line.strip()
            if not normalized:
                continue
            payload = json.loads(normalized)
            if isinstance(payload, dict):
                records.append(payload)
    return records


def mirror_report_if_possible(capture_dir: Path, report_text: str) -> None:
    parent = capture_dir.parent
    if parent.name != "captures":
        return

    sandbox_dir = parent.parent
    if sandbox_dir.name != "sportradar_stats":
        return

    (sandbox_dir / "endpoint_report.md").write_text(report_text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    capture_dir = args.capture_dir.resolve()
    responses_path = capture_dir / "responses.ndjson"
    if not responses_path.exists():
        raise FileNotFoundError(f"No existe {responses_path}")

    records = load_ndjson(responses_path)
    summary = summarize_capture_records(records)

    summary_path = capture_dir / "endpoints_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report_text = render_endpoint_report(summary, capture_dir=str(capture_dir))
    report_path = capture_dir / "endpoint_report.md"
    report_path.write_text(report_text, encoding="utf-8")
    mirror_report_if_possible(capture_dir, report_text)
    print(f"Wrote {summary_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
