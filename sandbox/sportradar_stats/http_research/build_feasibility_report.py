from __future__ import annotations

import argparse
import json
from pathlib import Path

from sandbox.sportradar_stats.http_research.reporting import render_api_feasibility


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build final Statshub HTTP API feasibility report.")
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--replay-results", type=Path)
    parser.add_argument("--token-results", type=Path)
    return parser.parse_args()


def load_json(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    args = parse_args()
    catalog = load_json(args.capture_dir / "endpoints_index.json")
    replay = load_json(args.replay_results or (args.capture_dir / "http_probe_results.json"))
    token = load_json(args.token_results or (args.capture_dir / "token_replay_results.json"))
    report = render_api_feasibility(catalog=catalog, replay_payload=replay, token_payload=token)
    output = args.capture_dir / "api_feasibility.md"
    output.write_text(report, encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
