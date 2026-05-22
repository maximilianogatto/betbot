from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.analysis import render_filtered_capture_report
from sandbox.sportradar_stats.analyze_filtered_capture import (
    build_index_and_samples,
    mirror_report_if_possible,
)
from sandbox.sportradar_stats.build_match_features import load_or_build_snapshot
from sandbox.sportradar_stats.capture_everything import capture_everything
from sandbox.sportradar_stats.capture_runtime import resolve_capture_user_data_dir
from sandbox.sportradar_stats.features_builder import build_match_features_document
from sandbox.sportradar_stats.filtering import filter_capture_directory
from sandbox.sportradar_stats.snapshot_builder import build_match_snapshot_from_capture_dir


@dataclass(slots=True)
class PipelineOptions:
    stats_url: str
    out_dir: Path
    seconds: float = 30.0
    pretty: bool = False
    skip_capture: bool = False
    include_debug_raw: bool = False
    group_json: bool = False
    headed: bool = False
    user_data_dir: str | None = None
    bootstrap_url: str | None = None


class PipelineStageError(RuntimeError):
    def __init__(self, stage_name: str, message: str) -> None:
        super().__init__(f"Stage '{stage_name}' failed: {message}")
        self.stage_name = stage_name
        self.message = message


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full offline Sportradar stats pipeline for one Bet365Stats URL.",
    )
    parser.add_argument("stats_url", help="Sportradar / Bet365Stats URL.")
    parser.add_argument(
        "--seconds",
        type=float,
        default=30.0,
        help="How long to keep the page open during capture.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("sandbox/sportradar_stats/captures/test_full"),
        help="Directory where all capture and derived artifacts will be written.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Write human-readable JSON outputs for snapshot and features.",
    )
    parser.add_argument(
        "--skip-capture",
        action="store_true",
        help="Reuse an existing capture directory and skip Playwright capture.",
    )
    parser.add_argument(
        "--include-debug-raw",
        action="store_true",
        help="Include compact debug payload samples inside match_snapshot.json.",
    )
    parser.add_argument(
        "--json",
        "--group-json",
        dest="group_json",
        action="store_true",
        help="Also write filtered_fetch.json during the filter stage.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run the capture browser in headed mode.",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Optional persistent Chromium profile directory for the capture stage.",
    )
    parser.add_argument(
        "--bootstrap-url",
        default=None,
        help="Optional Bet365 page to open before the stats URL.",
    )
    return parser.parse_args(argv)


def render_json(payload: dict[str, Any], *, pretty: bool) -> str:
    if pretty:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


async def run_capture_stage(options: PipelineOptions) -> Path:
    await capture_everything(
        options.stats_url,
        out_dir=options.out_dir,
        seconds=options.seconds,
        headless=not options.headed,
        user_data_dir=options.user_data_dir,
        bootstrap_url=options.bootstrap_url,
    )
    responses_path = options.out_dir / "responses.ndjson"
    if not responses_path.exists():
        raise PipelineStageError("capture", f"Expected capture output {responses_path} was not created.")
    return responses_path


def run_filter_stage(options: PipelineOptions) -> dict[str, Any]:
    responses_path = options.out_dir / "responses.ndjson"
    if not responses_path.exists():
        raise PipelineStageError("filter", f"No existe {responses_path}")

    result = filter_capture_directory(options.out_dir, write_json=options.group_json)
    filtered_path = options.out_dir / "filtered_fetch.ndjson"
    if not filtered_path.exists():
        raise PipelineStageError(
            "filter",
            f"Filtering finished but {filtered_path} was not generated.",
        )
    return result


def run_analysis_stage(options: PipelineOptions) -> Path:
    filtered_path = options.out_dir / "filtered_fetch.ndjson"
    responses_path = options.out_dir / "responses.ndjson"
    if not filtered_path.exists() and not responses_path.exists():
        raise PipelineStageError(
            "analyze",
            f"No existe ni {filtered_path} ni {responses_path}",
        )

    index_payload, endpoint_samples, source_path = build_index_and_samples(options.out_dir)
    report_text = render_filtered_capture_report(
        index_payload,
        endpoint_samples,
        capture_dir=str(options.out_dir),
        source_name=source_path.name,
    )
    report_path = options.out_dir / "endpoint_report.md"
    report_path.write_text(report_text, encoding="utf-8")
    mirror_report_if_possible(options.out_dir, report_text)

    index_path = options.out_dir / "endpoints_index.json"
    if not index_path.exists():
        index_path.write_text(
            json.dumps(index_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return report_path


def run_snapshot_stage(options: PipelineOptions) -> Path:
    filtered_path = options.out_dir / "filtered_fetch.ndjson"
    if not filtered_path.exists():
        raise PipelineStageError(
            "snapshot",
            f"Falta {filtered_path}; no se puede construir match_snapshot.json",
        )

    snapshot = build_match_snapshot_from_capture_dir(
        options.out_dir,
        include_debug_raw=options.include_debug_raw,
    )
    out_path = options.out_dir / "match_snapshot.json"
    out_path.write_text(render_json(snapshot, pretty=options.pretty), encoding="utf-8")
    return out_path


def run_features_stage(options: PipelineOptions) -> Path:
    snapshot, snapshot_path = load_or_build_snapshot(
        options.out_dir,
        include_debug_raw=options.include_debug_raw,
    )
    feature_document = build_match_features_document(
        snapshot,
        source_snapshot_path=str(snapshot_path),
    )
    out_path = options.out_dir / "match_features.json"
    out_path.write_text(
        render_json(feature_document, pretty=options.pretty),
        encoding="utf-8",
    )
    return out_path


def print_generated_paths(paths: dict[str, Path | None]) -> None:
    print("Generated artifacts:")
    for label in (
        "responses.ndjson",
        "filtered_fetch.ndjson",
        "filtered_fetch.json",
        "endpoints_index.json",
        "endpoint_report.md",
        "match_snapshot.json",
        "match_features.json",
    ):
        path = paths.get(label)
        if path is None:
            continue
        print(f"- {label}: {path}")


def run_pipeline(options: PipelineOptions) -> dict[str, Path | None]:
    options.out_dir.mkdir(parents=True, exist_ok=True)
    options.user_data_dir = resolve_capture_user_data_dir(options.user_data_dir)

    generated_paths: dict[str, Path | None] = {
        "responses.ndjson": options.out_dir / "responses.ndjson",
        "filtered_fetch.ndjson": options.out_dir / "filtered_fetch.ndjson",
        "filtered_fetch.json": options.out_dir / "filtered_fetch.json" if options.group_json else None,
        "endpoints_index.json": options.out_dir / "endpoints_index.json",
        "endpoint_report.md": options.out_dir / "endpoint_report.md",
        "match_snapshot.json": options.out_dir / "match_snapshot.json",
        "match_features.json": options.out_dir / "match_features.json",
    }

    try:
        if not options.skip_capture:
            if options.user_data_dir:
                print(f"Using capture profile: {options.user_data_dir}")
            else:
                print("Using capture profile: none")
            asyncio.run(run_capture_stage(options))
        run_filter_stage(options)
        if not (options.out_dir / "filtered_fetch.ndjson").exists():
            raise PipelineStageError(
                "pipeline",
                f"Expected {(options.out_dir / 'filtered_fetch.ndjson')} after filter stage.",
            )
        run_analysis_stage(options)
        run_snapshot_stage(options)
        run_features_stage(options)
    except PipelineStageError:
        raise
    except Exception as exc:
        raise PipelineStageError("pipeline", str(exc)) from exc

    return generated_paths


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    options = PipelineOptions(
        stats_url=args.stats_url,
        out_dir=args.out_dir.resolve(),
        seconds=args.seconds,
        pretty=args.pretty,
        skip_capture=args.skip_capture,
        include_debug_raw=args.include_debug_raw,
        group_json=args.group_json,
        headed=args.headed,
        user_data_dir=args.user_data_dir,
        bootstrap_url=args.bootstrap_url,
    )

    try:
        generated_paths = run_pipeline(options)
    except PipelineStageError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print_generated_paths(generated_paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
