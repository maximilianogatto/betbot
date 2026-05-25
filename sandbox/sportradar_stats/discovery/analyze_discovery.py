from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.discovery.discovery_core import (
    build_endpoints_index,
    write_endpoint_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze a Sportradar discovery capture and generate compact endpoint mapping.",
    )
    parser.add_argument("capture_dir", type=Path)
    return parser.parse_args()


def iter_records(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                yield record


def build_discovery_map(index: dict[str, object]) -> dict[str, object]:
    endpoints = index.get("endpoints") if isinstance(index.get("endpoints"), dict) else {}
    by_role: dict[str, list[str]] = {}
    for endpoint_key, endpoint in endpoints.items():  # type: ignore[union-attr]
        if not isinstance(endpoint, dict):
            continue
        roles = endpoint.get("roles")
        if not isinstance(roles, dict):
            continue
        for role in roles:
            by_role.setdefault(str(role), []).append(str(endpoint_key))
    return {
        "schema_version": 1,
        "records_count": index.get("records_count", 0),
        "endpoint_count": index.get("endpoint_count", 0),
        "by_role": {role: sorted(keys) for role, keys in sorted(by_role.items())},
        "endpoints": endpoints,
    }


def analyze_capture_dir(capture_dir: Path) -> dict[str, Path]:
    responses_path = capture_dir / "discovery_responses.ndjson"
    if not responses_path.exists():
        raise FileNotFoundError(f"Missing {responses_path}")

    records = list(iter_records(responses_path))
    index = build_endpoints_index(records)
    index_path = capture_dir / "endpoints_index.json"
    map_path = capture_dir / "discovery_map.json"
    report_path = capture_dir / "endpoint_report.md"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    map_path.write_text(json.dumps(build_discovery_map(index), ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(write_endpoint_report(index), encoding="utf-8")
    return {
        "endpoints_index": index_path,
        "discovery_map": map_path,
        "endpoint_report": report_path,
    }


def main() -> int:
    args = parse_args()
    outputs = analyze_capture_dir(args.capture_dir)
    for path in outputs.values():
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
