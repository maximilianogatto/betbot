"""Run real provider validation across multiple Statshub tournaments.

This is a hardening tool, not a discovery crawler. It uses only the existing
stable pipeline:

    config_tree_mini -> stats_season_fixtures2 -> match pipeline -> intelligence

It validates whether each tournament can produce fixtures, match intelligence,
dated H2H/traceability evidence, live endpoint responses, and priced markets.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stats_providers.sportradar_http.engine.endpoints.discovery import get_config_tree_mini, get_sport_matches_markets
from stats_providers.sportradar_http.engine.endpoints.tournaments import get_tournament_fixtures
from stats_providers.sportradar_http.engine.features_engine import build_match_features
from stats_providers.sportradar_http.engine.http_client import SportradarHTTPClient
from stats_providers.sportradar_http.engine.match_intelligence import build_match_intelligence
from stats_providers.sportradar_http.engine.normalizers import normalize_sport_match_markets
from sandbox.sportradar_http_research.provider_validation import (
    ValidationTarget,
    build_validation_result,
    build_validation_summary,
    parse_validation_target,
    render_validation_report,
)
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
DEFAULT_TARGETS = (
    "8:LaLiga:top",
    "136:A-League:top",
    "1894:A-League Women:women",
    "1260:Capital NPL 1:minor",
    "18340:South Australia NPL Women:women",
)


def parse_args() -> argparse.Namespace:
    """Parse CLI args for a bounded validation matrix run."""

    parser = argparse.ArgumentParser(description="Validate Sportradar provider stability across tournaments.")
    parser.add_argument("--target", action="append", help="Tournament target as id[:label[:category]]. Can repeat.")
    parser.add_argument("--sport-id", type=int, default=1)
    parser.add_argument("--category-id", type=int, default=67)
    parser.add_argument("--depth", type=int, default=0)
    parser.add_argument("--fixture-index", type=int)
    parser.add_argument("--session-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument("--out-dir", type=Path, default=Path("stats_providers/sportradar_http/engine/examples/provider_validation"))
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--lastx", type=int, default=6)
    parser.add_argument("--nextx", type=int, default=2)
    parser.add_argument("--top-players", type=int, default=6)
    parser.add_argument(
        "--max-fixtures",
        type=int,
        help="Compatibility flag. Validation selects from the full fixture list to avoid stale truncated samples.",
    )
    parser.add_argument("--max-timeline-events", type=int, default=80)
    parser.add_argument("--max-targets", type=int, help="Optional cap for faster local hardening runs.")
    add_bootstrap_mode_arg(parser)
    return parser.parse_args()


def main() -> int:
    """Run provider validation and write matrix/report artifacts."""

    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    packages_dir = args.out_dir / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    targets = [parse_validation_target(raw) for raw in (args.target or DEFAULT_TARGETS)]
    if args.max_targets:
        targets = targets[: args.max_targets]

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
    tree = build_tournament_tree(config_tree)

    results = []
    for target in targets:
        result = validate_target(
            client=client,
            args=args,
            target=target,
            config_tree=config_tree,
            tree=tree,
            packages_dir=packages_dir,
        )
        results.append(result)

    output = {
        "schema_version": 1,
        "summary": build_validation_summary(results),
        "results": results,
        "client_metrics": client.metrics_json(),
    }
    write_json(args.out_dir / "provider_validation_results.json", output)
    (args.out_dir / "provider_validation_report.md").write_text(render_validation_report(results), encoding="utf-8")
    if client.state is not None:
        save_session_state(client.state, args.session_state)
    print(f"Wrote {args.out_dir / 'provider_validation_results.json'}")
    print(f"Wrote {args.out_dir / 'provider_validation_report.md'}")
    return 0


def validate_target(
    *,
    client: SportradarHTTPClient,
    args: argparse.Namespace,
    target: ValidationTarget,
    config_tree: dict[str, Any],
    tree: dict[str, Any],
    packages_dir: Path,
) -> dict[str, Any]:
    """Validate one tournament target and keep going on failure."""

    navigation: dict[str, Any] = {}
    selected_fixture: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None
    intelligence: dict[str, Any] | None = None
    fixture_market_odds: dict[str, Any] | None = None
    package_path: str | None = None
    try:
        resolved = resolve_tournament(tree, target.tournament_id)
        fixtures_payload: dict[str, Any] = {}
        if resolved.get("season_id") is not None:
            fixtures_payload = get_tournament_fixtures(client, season_id=int(resolved["season_id"]))
        navigation = build_tournament_navigation_snapshot(
            sport_id=args.sport_id,
            tournament_id=target.tournament_id,
            config_tree_payload=config_tree,
            fixtures_payload=fixtures_payload,
            max_fixtures=None,
        )
        selected_fixture = select_fixture(navigation.get("fixtures") or [], fixture_index=args.fixture_index)
        fixture_market_odds = fetch_fixture_market_odds(
            client=client,
            sport_id=args.sport_id,
            selected_fixture=selected_fixture,
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
        slug = _slug(f"{target.tournament_id}_{target.label}")
        package_json = packages_dir / f"{slug}.json"
        package_md = packages_dir / f"{slug}.md"
        write_json(package_json, package)
        package_md.write_text(package["report_summary"], encoding="utf-8")
        package_path = str(package_json)
        return build_validation_result(
            target=target,
            navigation=navigation,
            selected_fixture=selected_fixture,
            snapshot=snapshot,
            intelligence=intelligence,
            fixture_market_odds=fixture_market_odds,
            package_path=package_path,
        )
    except Exception as exc:
        return build_validation_result(
            target=target,
            navigation=navigation,
            selected_fixture=selected_fixture,
            snapshot=snapshot,
            intelligence=intelligence,
            fixture_market_odds=fixture_market_odds,
            package_path=package_path,
            error=repr(exc),
        )


def fetch_fixture_market_odds(
    *,
    client: SportradarHTTPClient,
    sport_id: int,
    selected_fixture: dict[str, Any],
) -> dict[str, Any]:
    """Fetch priced markets for a selected fixture from the sport/date endpoint."""

    match_id = selected_fixture.get("match_id")
    time_data = selected_fixture.get("time") if isinstance(selected_fixture.get("time"), dict) else {}
    kickoff = str(time_data.get("iso_utc") or "")
    date = kickoff.split("T", 1)[0] if "T" in kickoff else None
    if not match_id or not date:
        return {}
    home = selected_fixture.get("home") if isinstance(selected_fixture.get("home"), dict) else {}
    away = selected_fixture.get("away") if isinstance(selected_fixture.get("away"), dict) else {}
    try:
        payload = get_sport_matches_markets(client, sport_id=sport_id, date=date)
        return normalize_sport_match_markets(
            payload,
            match_id=int(match_id),
            home_name=home.get("name"),
            away_name=away.get("name"),
        )
    except Exception as exc:
        return {
            "source": "unified_sport_matches_markets",
            "error": repr(exc),
            "markets": {
                "1x2": {},
                "handicap": [],
                "totals": [],
                "other_market_names": [],
                "raw_market_count": 0,
            },
        }


def write_json(path: Path, payload: object) -> None:
    """Write pretty JSON using UTF-8."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


if __name__ == "__main__":
    raise SystemExit(main())
