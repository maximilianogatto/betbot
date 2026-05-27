"""Validate active priced markets from existing Sportradar sport/date endpoints.

This is a hardening script for the future BetBot provider. It does not discover
new endpoints. It uses:

    unified_sport_matches
    unified_sport_matches_markets

The goal is to prove whether the HTTP replay provider can see real priced 1X2,
handicap and totals markets for prematch/live-like matches on specific dates.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_http.endpoints.discovery import get_sport_matches_markets, get_sport_overview
from sandbox.sportradar_http.http_client import SportradarHTTPClient
from sandbox.sportradar_http.market_validation import (
    build_market_validation_report,
    build_sport_match_index,
    summarize_sport_markets,
)
from sandbox.sportradar_http.runtime import add_bootstrap_mode_arg, load_or_refresh_session_state
from sandbox.sportradar_http.session_manager import save_session_state


DEFAULT_SESSION_STATE = Path("sandbox/sportradar_http/reports/session_state_headed.json")


def parse_args() -> argparse.Namespace:
    """Parse CLI args for active market validation."""

    parser = argparse.ArgumentParser(description="Validate active Sportradar sport/date market coverage.")
    parser.add_argument("--sport-id", type=int, default=1)
    parser.add_argument("--date", action="append", help="Date YYYY-MM-DD. Can repeat. Defaults to today + --days.")
    parser.add_argument("--days", type=int, default=4, help="Number of dates from today when --date is omitted.")
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--session-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument("--out-dir", type=Path, default=Path("sandbox/sportradar_http/examples/active_market_validation"))
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--timeout", type=float, default=25.0)
    add_bootstrap_mode_arg(parser)
    return parser.parse_args()


def main() -> int:
    """Run active market validation and write JSON/Markdown outputs."""

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
    results = []
    for day in _dates(args):
        overview = get_sport_overview(client, sport_id=args.sport_id, date=day)
        markets = get_sport_matches_markets(client, sport_id=args.sport_id, date=day)
        match_index = build_sport_match_index(overview)
        summary = summarize_sport_markets(markets, match_index=match_index, sample_limit=args.sample_limit)
        results.append({"date": day, **summary})

    output = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "sportradar_statshub",
        "inputs": {"sport_id": args.sport_id, "dates": _dates(args)},
        "results": results,
        "client_metrics": client.metrics_json(),
    }
    (args.out_dir / "active_market_validation.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out_dir / "active_market_validation_report.md").write_text(build_market_validation_report(results), encoding="utf-8")
    if client.state is not None:
        save_session_state(client.state, args.session_state)
    print(f"Wrote {args.out_dir / 'active_market_validation.json'}")
    print(f"Wrote {args.out_dir / 'active_market_validation_report.md'}")
    return 0


def _dates(args: argparse.Namespace) -> list[str]:
    if args.date:
        return args.date
    start = date.today()
    return [(start + timedelta(days=offset)).isoformat() for offset in range(max(args.days, 1))]


if __name__ == "__main__":
    raise SystemExit(main())
