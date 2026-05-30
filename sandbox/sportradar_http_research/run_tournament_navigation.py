"""CLI for tournament -> fixtures navigation.

Use this script when validating the future BetBot flow:

    tournament_id -> resolved season_id -> fixtures[] -> selected match_id

It performs browser bootstrap only when the cached session state is missing or
expired, then uses HTTP replay for `config_tree_mini` and
`stats_season_fixtures2`. Outputs are compact JSON plus a Markdown report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stats_providers.sportradar_http.engine.endpoints.discovery import get_config_tree_mini
from stats_providers.sportradar_http.engine.endpoints.tournaments import get_tournament_fixtures
from stats_providers.sportradar_http.engine.http_client import SportradarHTTPClient
from stats_providers.sportradar_http.engine.runtime import add_bootstrap_mode_arg, load_or_refresh_session_state
from stats_providers.sportradar_http.engine.session_manager import save_session_state
from stats_providers.sportradar_http.engine.tournament_navigation import (
    build_tournament_navigation_snapshot,
    build_tournament_tree,
    render_tournament_navigation_report,
    resolve_tournament,
)


DEFAULT_SESSION_STATE = Path("stats_providers/sportradar_http/engine/reports/session_state_headed.json")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for one tournament navigation run."""

    parser = argparse.ArgumentParser(description="Resolve Sportradar tournament navigation and fixtures.")
    parser.add_argument("--sport-id", type=int, default=1)
    parser.add_argument("--tournament-id", type=int, required=True)
    parser.add_argument("--category-id", type=int, default=67)
    parser.add_argument("--depth", type=int, default=0)
    parser.add_argument("--session-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument("--out-dir", type=Path, default=Path("stats_providers/sportradar_http/engine/examples/tournament_navigation"))
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--max-fixtures", type=int, default=120)
    add_bootstrap_mode_arg(parser)
    return parser.parse_args()


def main() -> int:
    """Resolve tournament metadata, fetch fixtures and write artifacts."""

    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    state, manager = ensure_state(args.session_state, seconds=args.seconds, bootstrap_mode=args.bootstrap_mode)
    client = SportradarHTTPClient(
        session_state=state,
        session_manager=manager,
        auto_refresh=True,
        retries=1,
        timeout_seconds=args.timeout,
    )
    config_tree = get_config_tree_mini(
        client,
        sport_id=args.sport_id,
        category_id=args.category_id,
        depth=args.depth,
    )
    resolved = resolve_tournament(build_tournament_tree(config_tree), args.tournament_id)
    fixtures_payload = {}
    if resolved.get("season_id") is not None:
        fixtures_payload = get_tournament_fixtures(client, season_id=int(resolved["season_id"]))

    snapshot = build_tournament_navigation_snapshot(
        sport_id=args.sport_id,
        tournament_id=args.tournament_id,
        config_tree_payload=config_tree,
        fixtures_payload=fixtures_payload,
        max_fixtures=args.max_fixtures,
    )
    snapshot["client_metrics"] = client.metrics_json()
    report = render_tournament_navigation_report(snapshot)
    write_json(args.out_dir / "tournament_navigation.json", snapshot)
    write_json(args.out_dir / "tournament_fixtures.json", snapshot.get("fixtures") or [])
    (args.out_dir / "tournament_navigation_report.md").write_text(report, encoding="utf-8")
    if client.state is not None:
        save_session_state(client.state, args.session_state)
    print(f"Wrote {args.out_dir / 'tournament_navigation.json'}")
    print(f"Wrote {args.out_dir / 'tournament_fixtures.json'}")
    print(f"Wrote {args.out_dir / 'tournament_navigation_report.md'}")
    return 0


def ensure_state(path: Path, *, seconds: float, bootstrap_mode: str = "headless"):
    """Load cached session state or run configured bootstrap if needed."""

    return load_or_refresh_session_state(path, seconds=seconds, bootstrap_mode=bootstrap_mode)


def write_json(path: Path, payload: object) -> None:
    """Write pretty JSON using UTF-8."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
