from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_http.endpoints.discovery import get_sport_matches_markets, get_sport_overview
from sandbox.sportradar_http.endpoints.odds import get_match_markets
from sandbox.sportradar_http.endpoints.standings import get_formtable, get_season_tables
from sandbox.sportradar_http.endpoints.stats import get_team_lastx, get_team_streaks
from sandbox.sportradar_http.http_client import SportradarHTTPClient, summarize_payload
from sandbox.sportradar_http.session_manager import (
    BootstrapConfig,
    SportradarSessionManager,
    load_session_state,
    save_session_state,
)


DEFAULT_SESSION_STATE = Path("sandbox/sportradar_http/reports/session_state_headed.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real Sportradar HTTP replay examples.")
    parser.add_argument("--session-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument("--out-dir", type=Path, default=Path("sandbox/sportradar_http/examples/http_client"))
    parser.add_argument("--report", type=Path, default=Path("sandbox/sportradar_http/reports/http_client_report.md"))
    parser.add_argument("--date", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--sport-id", type=int, default=1)
    parser.add_argument("--match-id", type=int, default=61624678)
    parser.add_argument("--season-id", type=int, default=130805)
    parser.add_argument("--team-id", type=int, default=2885)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--skip-refresh-example", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    state = ensure_state(args.session_state, seconds=args.seconds)
    client = SportradarHTTPClient(session_state=state, auto_refresh=False, retries=1, debug=True)

    success_examples = run_success_examples(client, args)
    blocked_example = run_blocked_example(client, state.sample_signed_url)
    refresh_example = None
    if not args.skip_refresh_example:
        refresh_example = run_refresh_example(args)

    write_json(args.out_dir / "success_examples.json", success_examples)
    write_json(args.out_dir / "blocked_example.json", blocked_example)
    if refresh_example is not None:
        write_json(args.out_dir / "refresh_example.json", refresh_example)
    snapshot = build_http_replay_snapshot(
        args=args,
        state=state,
        success_examples=success_examples,
        blocked_example=blocked_example,
        refresh_example=refresh_example,
        metrics=client.metrics_json(),
    )
    write_json(args.out_dir / "http_replay_snapshot.json", snapshot)

    report = render_http_client_report(
        snapshot=snapshot,
        success_examples=success_examples,
        blocked_example=blocked_example,
        refresh_example=refresh_example,
        metrics=client.metrics_json(),
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(f"Wrote {args.report}")
    print(f"Wrote examples in {args.out_dir}")
    return 0


def ensure_state(path: Path, *, seconds: float):
    if path.exists():
        state = load_session_state(path)
        if state.signed_token and not state.signed_token.is_expired():
            return state
    manager = SportradarSessionManager(BootstrapConfig(headed=True, seconds_per_url=seconds))
    state = manager.refresh_session()
    save_session_state(state, path)
    return state


def run_success_examples(client: SportradarHTTPClient, args: argparse.Namespace) -> list[dict[str, Any]]:
    calls = [
        ("fixtures", lambda: get_sport_overview(client, sport_id=args.sport_id, date=args.date)),
        ("fixture_markets", lambda: get_sport_matches_markets(client, sport_id=args.sport_id, date=args.date)),
        ("match_odds", lambda: get_match_markets(client, match_id=args.match_id)),
        ("standings", lambda: get_season_tables(client, season_id=args.season_id)),
        ("formtable", lambda: get_formtable(client, season_id=args.season_id)),
        ("team_lastx", lambda: get_team_lastx(client, team_id=args.team_id, count=5)),
        ("team_streaks", lambda: get_team_streaks(client, team_id=args.team_id)),
    ]
    results: list[dict[str, Any]] = []
    for label, fn in calls:
        payload = fn()
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        results.append(
            {
                "label": label,
                "body_size_bytes": len(encoded),
                "summary": summarize_payload(payload),
            }
        )
    return results


def run_blocked_example(client: SportradarHTTPClient, sample_signed_url: str | None) -> dict[str, Any]:
    if not sample_signed_url:
        return {"error": "no sample signed URL available"}
    with httpx.Client(timeout=20.0, follow_redirects=True) as raw_client:
        response = raw_client.get(sample_signed_url)
    validation = client.validate_response(response)
    body_json = response.json() if response.headers.get("content-type", "").startswith("application/json") else None
    return {
        "url": sample_signed_url,
        "status_code": response.status_code,
        "body_size_bytes": len(response.text.encode("utf-8")),
        "validation": asdict(validation),
        "summary": summarize_payload(body_json) if isinstance(body_json, dict) else None,
    }


def run_refresh_example(args: argparse.Namespace) -> dict[str, Any]:
    manager = SportradarSessionManager(BootstrapConfig(headed=True, seconds_per_url=args.seconds))
    client = SportradarHTTPClient.with_bootstrap(manager, retries=1, debug=True)
    payload = get_match_markets(client, match_id=args.match_id)
    return {
        "refreshed": True,
        "token_expiration": client.state.token_expiration() if client.state else None,
        "fetch_count": client.state.fetch_count if client.state else None,
        "metrics": client.metrics_json(),
        "summary": summarize_payload(payload),
    }


def build_http_replay_snapshot(
    *,
    args: argparse.Namespace,
    state: Any,
    success_examples: list[dict[str, Any]],
    blocked_example: dict[str, Any],
    refresh_example: dict[str, Any] | None,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    by_label = {str(item.get("label")): item for item in success_examples}
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "inputs": {
            "sport_id": args.sport_id,
            "date": args.date,
            "match_id": args.match_id,
            "season_id": args.season_id,
            "team_id": args.team_id,
        },
        "session": {
            "token_expiration": state.token_expiration(),
            "headed": state.headed,
            "headless": state.headless,
            "endpoints_seen_at_bootstrap": state.endpoints_seen,
            "bootstrap_fetch_count": state.fetch_count,
        },
        "http_replay": {
            "fixtures": by_label.get("fixtures"),
            "odds": {
                "sport_fixture_markets": by_label.get("fixture_markets"),
                "match_markets": by_label.get("match_odds"),
            },
            "standings": by_label.get("standings"),
            "stats": {
                "formtable": by_label.get("formtable"),
                "team_lastx": by_label.get("team_lastx"),
                "team_streaks": by_label.get("team_streaks"),
            },
        },
        "validation_examples": {
            "blocked_without_headers": blocked_example,
            "refresh_success": refresh_example,
        },
        "metrics": metrics,
        "raw_refs": {
            "session_state": str(args.session_state),
            "report": str(args.report),
        },
    }


def render_http_client_report(
    *,
    snapshot: dict[str, Any],
    success_examples: list[dict[str, Any]],
    blocked_example: dict[str, Any],
    refresh_example: dict[str, Any] | None,
    metrics: dict[str, Any],
) -> str:
    lines = [
        "# Sportradar HTTP Client Report",
        "",
        f"- Generated at: `{datetime.now(UTC).isoformat()}`",
        f"- Snapshot schema: `{snapshot.get('schema_version')}`",
        f"- Inputs: `{snapshot.get('inputs')}`",
        f"- Token expiration: `{(snapshot.get('session') or {}).get('token_expiration')}`",
        "",
        "## Successful HTTP Replay",
        "",
    ]
    for item in success_examples:
        summary = item.get("summary") or {}
        lines.append(
            "- `{label}` bytes={bytes} queryUrl=`{query}` event=`{event}` data_type=`{data_type}` counts=`{counts}`".format(
                label=item.get("label"),
                bytes=item.get("body_size_bytes"),
                query=summary.get("queryUrl"),
                event=summary.get("doc_event"),
                data_type=summary.get("data_type"),
                counts=summary.get("data_counts"),
            )
        )
    lines.extend(
        [
            "",
            "## Blocked Request Example",
            "",
            f"- Status: `{blocked_example.get('status_code')}`",
            f"- Body bytes: `{blocked_example.get('body_size_bytes')}`",
            f"- Validation: `{blocked_example.get('validation')}`",
            "",
            "## Refresh Example",
            "",
        ]
    )
    if refresh_example is None:
        lines.append("- Skipped.")
    else:
        lines.extend(
            [
                f"- Refreshed: `{refresh_example.get('refreshed')}`",
                f"- Token expiration: `{refresh_example.get('token_expiration')}`",
                f"- Bootstrap fetch count: `{refresh_example.get('fetch_count')}`",
                f"- Payload summary: `{refresh_example.get('summary')}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Client Metrics",
            "",
            f"```json\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n```",
            "",
            "## Notes",
            "",
            "- Browser is used only for bootstrap/refresh.",
            "- Successful examples use pure HTTP replay after bootstrap.",
            "- The blocked example intentionally omits replay headers to verify detection.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
