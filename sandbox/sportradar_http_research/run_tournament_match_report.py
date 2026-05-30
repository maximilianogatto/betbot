"""CLI for the full bot-ready tournament -> fixture -> match report flow.

Example:
    ./betbot/bin/python stats_providers/sportradar_http/engine/run_tournament_match_report.py \
      --sport-id 1 \
      --tournament-id 18340 \
      --bootstrap-mode headless

The script produces compact artifacts that a future Telegram command can render
without knowing about Sportradar endpoints.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stats_providers.sportradar_http.engine.endpoints.discovery import get_config_tree_mini
from stats_providers.sportradar_http.engine.endpoints.tournaments import get_tournament_fixtures
from stats_providers.sportradar_http.engine.features_engine import build_match_features
from stats_providers.sportradar_http.engine.http_client import SportradarHTTPClient
from stats_providers.sportradar_http.engine.match_intelligence import build_match_intelligence
from stats_providers.sportradar_http.engine.run_match_pipeline import build_match_snapshot, fetch_match_payloads
from stats_providers.sportradar_http.engine.runtime import add_bootstrap_mode_arg, load_or_refresh_session_state
from stats_providers.sportradar_http.engine.session_manager import save_session_state
from sandbox.sportradar_http_research.tournament_match_report import build_tournament_match_package, select_fixture
from stats_providers.sportradar_http.engine.tournament_navigation import (
    build_tournament_navigation_snapshot,
    build_tournament_tree,
    resolve_tournament,
)


DEFAULT_SESSION_STATE = Path("stats_providers/sportradar_http/engine/reports/session_state_headed.json")


def parse_args() -> argparse.Namespace:
    """Parse CLI args for selecting a fixture and building its report."""

    parser = argparse.ArgumentParser(description="Build a tournament-selected match intelligence report.")
    parser.add_argument("--sport-id", type=int, default=1)
    parser.add_argument("--tournament-id", type=int, required=True)
    parser.add_argument("--category-id", type=int, default=67)
    parser.add_argument("--depth", type=int, default=0)
    parser.add_argument("--match-id", type=int)
    parser.add_argument("--fixture-index", type=int)
    parser.add_argument("--session-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument("--out-dir", type=Path, default=Path("stats_providers/sportradar_http/engine/examples/tournament_match_report"))
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--lastx", type=int, default=8)
    parser.add_argument("--nextx", type=int, default=2)
    parser.add_argument("--top-players", type=int, default=8)
    parser.add_argument("--max-fixtures", type=int, default=500)
    parser.add_argument("--max-timeline-events", type=int, default=120)
    add_bootstrap_mode_arg(parser)
    return parser.parse_args()


def main() -> int:
    """Run navigation, select one fixture, build match intelligence and write artifacts."""

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

    config_tree = get_config_tree_mini(client, sport_id=args.sport_id, category_id=args.category_id, depth=args.depth)
    resolved = resolve_tournament(build_tournament_tree(config_tree), args.tournament_id)
    fixtures_payload = {}
    if resolved.get("season_id") is not None:
        fixtures_payload = get_tournament_fixtures(client, season_id=int(resolved["season_id"]))
    navigation = build_tournament_navigation_snapshot(
        sport_id=args.sport_id,
        tournament_id=args.tournament_id,
        config_tree_payload=config_tree,
        fixtures_payload=fixtures_payload,
        max_fixtures=args.max_fixtures,
    )
    selected_fixture = select_fixture(
        navigation.get("fixtures") or [],
        match_id=args.match_id,
        fixture_index=args.fixture_index,
    )
    match_args = SimpleNamespace(
        match_id=int(selected_fixture["match_id"]),
        lastx=args.lastx,
        nextx=args.nextx,
        top_players=args.top_players,
        max_timeline_events=args.max_timeline_events,
    )
    payloads, errors = fetch_match_payloads(client, match_args)
    snapshot = build_match_snapshot(args=match_args, payloads=payloads, errors=errors, client=client)
    features = build_match_features(snapshot)
    intelligence = build_match_intelligence(snapshot, features)
    package = build_tournament_match_package(
        navigation=navigation,
        selected_fixture=selected_fixture,
        match_intelligence=intelligence,
        client_metrics=client.metrics_json(),
    )

    write_json(args.out_dir / "tournament_navigation.json", navigation)
    write_json(args.out_dir / "selected_fixture.json", selected_fixture)
    write_json(args.out_dir / "match_snapshot.json", snapshot)
    write_json(args.out_dir / "match_features.json", features)
    write_json(args.out_dir / "match_intelligence.json", intelligence)
    write_json(args.out_dir / "tournament_match_report.json", package)
    (args.out_dir / "tournament_match_report.md").write_text(package["report_summary"], encoding="utf-8")
    if client.state is not None:
        save_session_state(client.state, args.session_state)
    print(f"Wrote {args.out_dir / 'tournament_match_report.json'}")
    print(f"Wrote {args.out_dir / 'tournament_match_report.md'}")
    print(f"Selected match_id={selected_fixture.get('match_id')}")
    return 0


def write_json(path: Path, payload: object) -> None:
    """Write pretty JSON using UTF-8."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
