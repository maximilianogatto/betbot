"""Controlled live polling probe for match timeline endpoints.

Purpose:
    Investigate live-state behavior without integrating live betting logic into
    BetBot. The probe polls match metadata, timeline, timelinedelta and situation
    endpoints, then writes NDJSON records plus a compact summary/report.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stats_providers.sportradar_http.engine.bot_ready.provider import build_live_state_document
from stats_providers.sportradar_http.engine.endpoints.live import (
    get_match_situation,
    get_match_timeline,
    get_match_timelinedelta,
)
from stats_providers.sportradar_http.engine.endpoints.matches import get_match_info, get_match_snapshot
from stats_providers.sportradar_http.engine.http_client import SportradarHTTPClient
from stats_providers.sportradar_http.engine.runtime import add_bootstrap_mode_arg, load_or_refresh_session_state
from stats_providers.sportradar_http.engine.session_manager import save_session_state


DEFAULT_SESSION_STATE = Path("stats_providers/sportradar_http/engine/reports/session_state_headed.json")


def parse_args() -> argparse.Namespace:
    """Parse CLI args for match id, poll count and output directory."""

    parser = argparse.ArgumentParser(description="Run a compact Sportradar live polling probe.")
    parser.add_argument("--match-id", type=int, default=61624678)
    parser.add_argument("--polls", type=int, default=3)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--session-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument("--out-dir", type=Path, default=Path("stats_providers/sportradar_http/engine/examples/live_probe_61624678"))
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    add_bootstrap_mode_arg(parser)
    return parser.parse_args()


def main() -> int:
    """Run repeated live polling and write NDJSON/summary/report artifacts."""

    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    state, manager = load_or_refresh_session_state(
        args.session_state,
        seconds=args.seconds,
        bootstrap_mode=args.bootstrap_mode,
    )
    client = SportradarHTTPClient(
        session_state=state,
        session_manager=manager,
        auto_refresh=True,
        retries=1,
        timeout_seconds=args.timeout,
    )
    records: list[dict[str, Any]] = []
    ndjson_path = args.out_dir / "live_probe.ndjson"
    with ndjson_path.open("w", encoding="utf-8") as handle:
        for poll_index in range(max(args.polls, 1)):
            record = poll_live_once(client, match_id=args.match_id, poll_index=poll_index)
            records.append(record)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            if poll_index < args.polls - 1:
                time.sleep(max(args.interval, 0))
    summary = build_live_probe_summary(records, metrics=client.metrics_json())
    write_json(args.out_dir / "live_probe_summary.json", summary)
    (args.out_dir / "live_probe_report.md").write_text(render_live_probe_report(summary), encoding="utf-8")
    if client.state is not None:
        save_session_state(client.state, args.session_state)
    print(f"Wrote {ndjson_path}")
    print(f"Wrote {args.out_dir / 'live_probe_summary.json'}")
    print(f"Wrote {args.out_dir / 'live_probe_report.md'}")
    return 0


def poll_live_once(client: SportradarHTTPClient, *, match_id: int, poll_index: int) -> dict[str, Any]:
    """Poll live-related endpoints once and return a compact document."""

    payloads: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    calls = {
        "match_info": lambda: get_match_info(client, match_id=match_id),
        "match_snapshot": lambda: get_match_snapshot(client, match_id=match_id),
        "match_timeline": lambda: get_match_timeline(client, match_id=match_id),
        "match_timelinedelta": lambda: get_match_timelinedelta(client, match_id=match_id),
        "match_situation": lambda: get_match_situation(client, match_id=match_id),
    }
    for name, call in calls.items():
        try:
            payloads[name] = call()
        except Exception as exc:
            errors[name] = repr(exc)
    document = build_live_state_document(match_id=match_id, payloads=payloads, errors=errors)
    return {
        "poll_index": poll_index,
        "captured_at": datetime.now(UTC).isoformat(),
        "document": document,
    }


def build_live_probe_summary(records: list[dict[str, Any]], *, metrics: dict[str, Any]) -> dict[str, Any]:
    """Summarize live probe records across polls."""

    compact_records = []
    for record in records:
        document = record.get("document") if isinstance(record.get("document"), dict) else {}
        live_state = document.get("live_state") if isinstance(document.get("live_state"), dict) else {}
        live_delta = document.get("live_delta") if isinstance(document.get("live_delta"), dict) else {}
        situation = document.get("live_situation") if isinstance(document.get("live_situation"), dict) else {}
        compact_records.append(
            {
                "poll_index": record.get("poll_index"),
                "captured_at": record.get("captured_at"),
                "status": live_state.get("status"),
                "score_home": live_state.get("score_home"),
                "score_away": live_state.get("score_away"),
                "timeline_events": live_state.get("raw_event_count"),
                "delta_events": live_delta.get("raw_event_count"),
                "situation_samples": situation.get("raw_sample_count"),
                "quality": document.get("feature_quality"),
            }
        )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "poll_count": len(records),
        "records": compact_records,
        "client_metrics": metrics,
    }


def render_live_probe_report(summary: dict[str, Any]) -> str:
    """Render live probe observations as Markdown."""

    lines = [
        "# Sportradar Live Probe Report",
        "",
        f"- Generated at: `{summary.get('generated_at')}`",
        f"- Poll count: `{summary.get('poll_count')}`",
        "",
        "## Polls",
        "",
    ]
    for record in summary.get("records") or []:
        lines.append(
            "- poll={poll} at=`{at}` status=`{status}` score=`{home}-{away}` timeline_events=`{events}` delta_events=`{delta}` situation_samples=`{samples}`".format(
                poll=record.get("poll_index"),
                at=record.get("captured_at"),
                status=record.get("status"),
                home=record.get("score_home"),
                away=record.get("score_away"),
                events=record.get("timeline_events"),
                delta=record.get("delta_events"),
                samples=record.get("situation_samples"),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `match_timeline` is the full event stream snapshot.",
            "- `match_timelinedelta` is the delta feed candidate for lightweight live polling.",
            "- `stats_match_situation` exposes pressure-like samples: attack/dangerous/safe buckets.",
            "- Ended matches normally show zero delta events; live matches are expected to change over polls.",
            "",
            "## Client Metrics",
            "",
            f"```json\n{json.dumps(summary.get('client_metrics'), ensure_ascii=False, indent=2)}\n```",
        ]
    )
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
