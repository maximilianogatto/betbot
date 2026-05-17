from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.snapshot_builder import build_match_snapshot_from_capture_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a compact per-match snapshot from one filtered Sportradar capture.",
    )
    parser.add_argument(
        "capture_dir",
        type=Path,
        help="Directory containing filtered_fetch.ndjson.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write human-readable indented JSON.",
    )
    parser.add_argument(
        "--include-debug-raw",
        action="store_true",
        help="Include compact debug payload samples for used endpoints.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional output path. Defaults to <capture_dir>/match_snapshot.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    capture_dir = args.capture_dir.resolve()
    snapshot = build_match_snapshot_from_capture_dir(
        capture_dir,
        include_debug_raw=args.include_debug_raw,
    )

    out_path = args.out.resolve() if args.out else capture_dir / "match_snapshot.json"
    if args.pretty:
        rendered = json.dumps(snapshot, ensure_ascii=False, indent=2)
    else:
        rendered = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    out_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
