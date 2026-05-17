from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.filtering import filter_capture_directory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter one raw Sportradar capture down to useful fetch/xhr / gismo responses.",
    )
    parser.add_argument(
        "capture_dir",
        type=Path,
        help="Directory containing responses.ndjson.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Also emit filtered_fetch.json. Disabled by default because it can be large.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    capture_dir = args.capture_dir.resolve()
    responses_path = capture_dir / "responses.ndjson"
    if not responses_path.exists():
        raise FileNotFoundError(f"No existe {responses_path}")

    result = filter_capture_directory(capture_dir, write_json=args.json)
    print(f"Wrote {result['filtered_ndjson_path']}")
    print(f"Wrote {result['endpoints_index_path']}")
    if result["filtered_json_path"] is not None:
        print(f"Wrote {result['filtered_json_path']}")
    print(
        "Filtered useful responses:",
        result["filtered_records_count"],
        "| endpoints:",
        result["endpoint_count"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
