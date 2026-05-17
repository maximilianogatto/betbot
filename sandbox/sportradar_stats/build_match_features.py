from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.features_builder import build_match_features_document
from sandbox.sportradar_stats.snapshot_builder import build_match_snapshot_from_capture_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build compact derived features from one Sportradar capture snapshot.",
    )
    parser.add_argument(
        "capture_dir",
        type=Path,
        help="Directory containing match_snapshot.json or filtered_fetch.ndjson.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write human-readable indented JSON.",
    )
    parser.add_argument(
        "--include-debug-raw",
        action="store_true",
        help="If the snapshot must be rebuilt, include compact debug payload samples.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Optional output path. Defaults to <capture_dir>/match_features.json",
    )
    return parser.parse_args()


def load_or_build_snapshot(
    capture_dir: Path,
    *,
    include_debug_raw: bool,
) -> tuple[dict[str, object], Path]:
    snapshot_path = capture_dir / "match_snapshot.json"
    if snapshot_path.exists():
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            if isinstance(snapshot, dict):
                return snapshot, snapshot_path
        except json.JSONDecodeError:
            pass

    snapshot = build_match_snapshot_from_capture_dir(
        capture_dir,
        include_debug_raw=include_debug_raw,
    )
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return snapshot, snapshot_path


def count_populated_features(features: dict[str, object]) -> tuple[int, int]:
    total = len(features)
    populated = sum(1 for value in features.values() if value is not None)
    return populated, total


def main() -> int:
    args = parse_args()
    capture_dir = args.capture_dir.resolve()
    snapshot, snapshot_path = load_or_build_snapshot(
        capture_dir,
        include_debug_raw=args.include_debug_raw,
    )
    feature_document = build_match_features_document(
        snapshot,
        source_snapshot_path=str(snapshot_path),
    )

    out_path = args.out.resolve() if args.out else capture_dir / "match_features.json"
    rendered = (
        json.dumps(feature_document, ensure_ascii=False, indent=2)
        if args.pretty
        else json.dumps(feature_document, ensure_ascii=False, separators=(",", ":"))
    )
    out_path.write_text(rendered, encoding="utf-8")

    derived_features = feature_document.get("derived_features")
    populated, total = count_populated_features(derived_features if isinstance(derived_features, dict) else {})
    print(f"Wrote {out_path}")
    print(
        "Summary: "
        f"{feature_document.get('home')} vs {feature_document.get('away')} "
        f"(match_id={feature_document.get('match_id')}, capture_type={feature_document.get('capture_type')}, "
        f"features={populated}/{total})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
