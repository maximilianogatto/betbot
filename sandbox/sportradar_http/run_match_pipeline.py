"""CLI and builder for match snapshots, features and intelligence.

Flow:
    1. Ensure an HTTP replay session.
    2. Fetch raw match/team/season endpoints through endpoint wrappers.
    3. Normalize raw payloads into `match_snapshot.json`.
    4. Build numeric/categorical `match_features.json`.
    5. Build compact bot-ready `match_intelligence.json`.
    6. Write technical and compact Markdown reports.

This script is still sandbox-only. It does not write production DB rows and does
not send Telegram messages.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_http.endpoints.live import (
    get_match_situation,
    get_match_timeline,
    get_match_timelinedelta,
)
from sandbox.sportradar_http.endpoints.matches import (
    get_match_details,
    get_match_head2head,
    get_match_info,
    get_match_snapshot,
    get_match_table_slice,
)
from sandbox.sportradar_http.endpoints.odds import get_match_markets
from sandbox.sportradar_http.endpoints.stats import (
    get_h2h,
    get_injuries,
    get_team_lastx,
    get_team_nextx,
    get_team_scoring_conceding,
    get_team_streaks,
    get_team_versus,
    get_top_assists,
    get_top_cards,
    get_top_goals,
)
from sandbox.sportradar_http.features_engine import build_match_features
from sandbox.sportradar_http.http_client import SportradarHTTPClient
from sandbox.sportradar_http.match_intelligence import build_match_intelligence
from sandbox.sportradar_http.normalizers import (
    make_raw_ref,
    normalize_h2h_payload,
    normalize_injuries,
    normalize_match_details,
    normalize_match_markets,
    normalize_match_metadata,
    normalize_match_situation,
    normalize_match_table_slice,
    normalize_match_timeline,
    normalize_player_leaders,
    normalize_team_recent_payload,
    normalize_team_scoring,
    normalize_team_streaks,
)
from sandbox.sportradar_http.session_manager import (
    BootstrapConfig,
    SportradarSessionManager,
    load_session_state,
    save_session_state,
)


DEFAULT_SESSION_STATE = Path("sandbox/sportradar_http/reports/session_state_headed.json")


def parse_args() -> argparse.Namespace:
    """Parse CLI args controlling match id, bootstrap, output and sample sizes."""

    parser = argparse.ArgumentParser(description="Build a compact Sportradar match snapshot/features/report.")
    parser.add_argument("--match-id", type=int, default=61624678)
    parser.add_argument("--session-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument("--out-dir", type=Path, default=Path("sandbox/sportradar_http/examples/match_61624678"))
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--lastx", type=int, default=8)
    parser.add_argument("--nextx", type=int, default=2)
    parser.add_argument("--top-players", type=int, default=8)
    parser.add_argument("--max-timeline-events", type=int, default=120)
    return parser.parse_args()


def main() -> int:
    """Run the full match pipeline and write JSON/Markdown artifacts."""

    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    state, manager = ensure_state(args.session_state, seconds=args.seconds)
    client = SportradarHTTPClient(
        session_state=state,
        session_manager=manager,
        auto_refresh=True,
        retries=1,
        timeout_seconds=args.timeout,
    )
    payloads, errors = fetch_match_payloads(client, args)
    snapshot = build_match_snapshot(args=args, payloads=payloads, errors=errors, client=client)
    features = build_match_features(snapshot)
    intelligence = build_match_intelligence(snapshot, features)
    report = render_match_report(snapshot=snapshot, features=features, metrics=client.metrics_json())
    write_json(args.out_dir / "match_snapshot.json", snapshot)
    write_json(args.out_dir / "match_features.json", features)
    write_json(args.out_dir / "match_intelligence.json", intelligence)
    (args.out_dir / "match_report.md").write_text(report, encoding="utf-8")
    (args.out_dir / "match_intelligence_report.md").write_text(
        intelligence.get("report_summary", "") + "\n",
        encoding="utf-8",
    )
    if client.state is not None:
        save_session_state(client.state, args.session_state)
    print(f"Wrote {args.out_dir / 'match_snapshot.json'}")
    print(f"Wrote {args.out_dir / 'match_features.json'}")
    print(f"Wrote {args.out_dir / 'match_intelligence.json'}")
    print(f"Wrote {args.out_dir / 'match_report.md'}")
    print(f"Wrote {args.out_dir / 'match_intelligence_report.md'}")
    return 0


def ensure_state(path: Path, *, seconds: float) -> tuple[Any, SportradarSessionManager]:
    """Load cached replay state or run browser bootstrap when needed."""

    manager = SportradarSessionManager(BootstrapConfig(headed=True, seconds_per_url=seconds))
    if path.exists():
        state = load_session_state(path)
        if state.signed_token and not state.signed_token.is_expired():
            return state, manager
    state = manager.refresh_session()
    save_session_state(state, path)
    return state, manager


def fetch_match_payloads(
    client: SportradarHTTPClient,
    args: argparse.Namespace,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Fetch all required/optional raw payloads for one match.

    Required payloads must succeed because they identify the teams and season.
    Optional payloads are captured best-effort and surfaced in `errors` so the
    snapshot can still be built with partial evidence.
    """

    payloads: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    required_calls: dict[str, Callable[[], dict[str, Any]]] = {
        "match_info": lambda: get_match_info(client, match_id=args.match_id),
        "match_snapshot": lambda: get_match_snapshot(client, match_id=args.match_id),
    }
    for name, call in required_calls.items():
        payloads[name] = call()

    metadata = normalize_match_metadata(payloads.get("match_info"), payloads.get("match_snapshot"))
    home_uid = metadata.get("home", {}).get("uid") if isinstance(metadata.get("home"), dict) else None
    away_uid = metadata.get("away", {}).get("uid") if isinstance(metadata.get("away"), dict) else None
    season_id = metadata.get("season_id")

    optional_calls: dict[str, Callable[[], dict[str, Any]]] = {
        "match_markets": lambda: get_match_markets(client, match_id=args.match_id),
        "match_details": lambda: get_match_details(client, match_id=args.match_id),
        "match_table_slice": lambda: get_match_table_slice(client, match_id=args.match_id),
        "match_head2head": lambda: get_match_head2head(client, match_id=args.match_id),
        "match_timeline": lambda: get_match_timeline(client, match_id=args.match_id),
        "match_timelinedelta": lambda: get_match_timelinedelta(client, match_id=args.match_id),
        "match_situation": lambda: get_match_situation(client, match_id=args.match_id),
    }
    if home_uid is not None:
        optional_calls.update(
            {
                "home_lastx": lambda: get_team_lastx(client, team_id=int(home_uid), count=args.lastx),
                "home_nextx": lambda: get_team_nextx(client, team_id=int(home_uid), count=args.nextx),
                "home_streaks": lambda: get_team_streaks(client, team_id=int(home_uid)),
            }
        )
    if away_uid is not None:
        optional_calls.update(
            {
                "away_lastx": lambda: get_team_lastx(client, team_id=int(away_uid), count=args.lastx),
                "away_nextx": lambda: get_team_nextx(client, team_id=int(away_uid), count=args.nextx),
                "away_streaks": lambda: get_team_streaks(client, team_id=int(away_uid)),
            }
        )
    if season_id is not None and home_uid is not None:
        optional_calls.update(
            {
                "home_scoring": lambda: get_team_scoring_conceding(client, season_id=int(season_id), team_id=int(home_uid)),
                "home_top_goals": lambda: get_top_goals(client, season_id=int(season_id), team_id=int(home_uid)),
                "home_top_cards": lambda: get_top_cards(client, season_id=int(season_id), team_id=int(home_uid)),
                "home_top_assists": lambda: get_top_assists(client, season_id=int(season_id), team_id=int(home_uid)),
            }
        )
    if season_id is not None and away_uid is not None:
        optional_calls.update(
            {
                "away_scoring": lambda: get_team_scoring_conceding(client, season_id=int(season_id), team_id=int(away_uid)),
                "away_top_goals": lambda: get_top_goals(client, season_id=int(season_id), team_id=int(away_uid)),
                "away_top_cards": lambda: get_top_cards(client, season_id=int(season_id), team_id=int(away_uid)),
                "away_top_assists": lambda: get_top_assists(client, season_id=int(season_id), team_id=int(away_uid)),
            }
        )
    if season_id is not None:
        optional_calls["season_injuries"] = lambda: get_injuries(client, season_id=int(season_id))
    if home_uid is not None and away_uid is not None:
        optional_calls["team_versus"] = lambda: get_team_versus(client, team_a_id=int(home_uid), team_b_id=int(away_uid))
        optional_calls["h2h_versus"] = lambda: get_h2h(
            client,
            team_a_id=int(home_uid),
            team_b_id=int(away_uid),
            match_id=args.match_id,
        )

    for name, call in optional_calls.items():
        try:
            payloads[name] = call()
        except Exception as exc:  # Research pipeline: keep going and expose endpoint gaps.
            errors[name] = repr(exc)
    return payloads, errors


def build_match_snapshot(
    *,
    args: argparse.Namespace,
    payloads: dict[str, dict[str, Any]],
    errors: dict[str, str],
    client: SportradarHTTPClient,
) -> dict[str, Any]:
    """Normalize raw payloads into the stable match snapshot schema."""

    metadata = normalize_match_metadata(payloads.get("match_info"), payloads.get("match_snapshot"))
    home = metadata.get("home") if isinstance(metadata.get("home"), dict) else {}
    away = metadata.get("away") if isinstance(metadata.get("away"), dict) else {}
    home_uid = home.get("uid")
    away_uid = away.get("uid")
    home_name = home.get("name")
    away_name = away.get("name")
    all_injuries = normalize_injuries(payloads.get("season_injuries"))
    odds = normalize_match_markets(payloads.get("match_markets"), home_name=home_name, away_name=away_name)
    snapshot = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "sportradar_statshub",
        "scope": "match",
        "inputs": {"match_id": args.match_id},
        "metadata": metadata,
        "odds": odds,
        "table_context": normalize_match_table_slice(payloads.get("match_table_slice")),
        "match_details": normalize_match_details(payloads.get("match_details")),
        "team_form": {
            "home": normalize_team_recent_payload(payloads.get("home_lastx"), team_uid=home_uid, max_matches=args.lastx),
            "away": normalize_team_recent_payload(payloads.get("away_lastx"), team_uid=away_uid, max_matches=args.lastx),
            "home_next": normalize_team_recent_payload(payloads.get("home_nextx"), team_uid=home_uid, max_matches=args.nextx),
            "away_next": normalize_team_recent_payload(payloads.get("away_nextx"), team_uid=away_uid, max_matches=args.nextx),
        },
        "team_scoring": {
            "home": normalize_team_scoring(payloads.get("home_scoring")),
            "away": normalize_team_scoring(payloads.get("away_scoring")),
        },
        "team_streaks": {
            "home": normalize_team_streaks(payloads.get("home_streaks")),
            "away": normalize_team_streaks(payloads.get("away_streaks")),
        },
        "h2h": normalize_h2h_payload(
            payloads.get("team_versus") or payloads.get("h2h_versus"),
            home_uid=home_uid,
            away_uid=away_uid,
        ),
        "injuries": {
            "home": [item for item in all_injuries if (item.get("team") or {}).get("uid") == home_uid],
            "away": [item for item in all_injuries if (item.get("team") or {}).get("uid") == away_uid],
            "other_count": len(
                [
                    item
                    for item in all_injuries
                    if (item.get("team") or {}).get("uid") not in {home_uid, away_uid}
                ]
            ),
        },
        "players": {
            "home": {
                "top_goals": normalize_player_leaders(payloads.get("home_top_goals"), max_items=args.top_players),
                "top_cards": normalize_player_leaders(payloads.get("home_top_cards"), max_items=args.top_players),
                "top_assists": normalize_player_leaders(payloads.get("home_top_assists"), max_items=args.top_players),
            },
            "away": {
                "top_goals": normalize_player_leaders(payloads.get("away_top_goals"), max_items=args.top_players),
                "top_cards": normalize_player_leaders(payloads.get("away_top_cards"), max_items=args.top_players),
                "top_assists": normalize_player_leaders(payloads.get("away_top_assists"), max_items=args.top_players),
            },
        },
        "live_state": normalize_match_timeline(payloads.get("match_timeline"), max_events=args.max_timeline_events),
        "live_delta": normalize_match_timeline(payloads.get("match_timelinedelta"), max_events=args.max_timeline_events),
        "live_situation": normalize_match_situation(payloads.get("match_situation")),
        "feature_quality": build_feature_quality(payloads, errors, odds=odds),
        "raw_refs": {
            "endpoints_used": sorted(payloads),
            "endpoint_errors": errors,
            "source_records": [make_raw_ref(name, payload) for name, payload in sorted(payloads.items())],
        },
        "client_metrics": client.metrics_json(),
        "limitations": [
            "This is an offline research provider snapshot, not wired into BetBot production.",
            "Full raw payloads are not embedded; use raw_refs for traceability.",
            "match_markets can be empty for ended/unpriced matches.",
        ],
    }
    return snapshot


def build_feature_quality(payloads: dict[str, Any], errors: dict[str, str], *, odds: dict[str, Any] | None = None) -> dict[str, Any]:
    """Summarize which important evidence groups were available."""

    important = {
        "match_info",
        "match_snapshot",
        "match_markets",
        "match_table_slice",
        "match_details",
        "home_lastx",
        "away_lastx",
        "home_scoring",
        "away_scoring",
        "team_versus",
        "match_timeline",
        "match_situation",
    }
    present = {key for key in important if key in payloads}
    missing = sorted((important - present) | (set(errors) & important))
    markets = ((odds or {}).get("markets") or {}) if isinstance(odds, dict) else {}
    has_priced_odds = bool(markets.get("1x2") or markets.get("handicap") or markets.get("totals"))
    return {
        "data_completeness": round(len(present) / len(important), 4),
        "has_metadata": "match_info" in payloads or "match_snapshot" in payloads,
        "has_odds_endpoint": "match_markets" in payloads,
        "has_priced_odds": has_priced_odds,
        "has_table": "match_table_slice" in payloads,
        "has_match_details": "match_details" in payloads,
        "has_team_form": "home_lastx" in payloads and "away_lastx" in payloads,
        "has_team_scoring": "home_scoring" in payloads and "away_scoring" in payloads,
        "has_h2h": "team_versus" in payloads or "h2h_versus" in payloads,
        "has_live_state": "match_timeline" in payloads,
        "missing_important_endpoints": missing,
    }


def render_match_report(*, snapshot: dict[str, Any], features: dict[str, Any], metrics: dict[str, Any]) -> str:
    """Render the verbose technical match report used for research/debugging."""

    metadata = snapshot.get("metadata") or {}
    home = metadata.get("home") or {}
    away = metadata.get("away") or {}
    competition = metadata.get("competition") or {}
    score = metadata.get("score") or {}
    values = features.get("values") or {}
    odds = ((snapshot.get("odds") or {}).get("markets") or {})
    details = ((snapshot.get("match_details") or {}).get("key_stats") or {})
    h2h = snapshot.get("h2h") or {}
    lines = [
        "# Sportradar Match Pipeline Report",
        "",
        f"- Generated at: `{snapshot.get('generated_at')}`",
        f"- Match: `{home.get('name')} vs {away.get('name')}`",
        f"- Competition: `{competition.get('season_name') or competition.get('name')}`",
        f"- Kickoff UTC: `{(metadata.get('kickoff') or {}).get('iso_utc')}`",
        f"- Status: `{(metadata.get('status') or {}).get('name') or (metadata.get('status') or {}).get('matchstatus')}`",
        f"- Score: `{score.get('home')} - {score.get('away')}`",
        "",
        "## Odds",
        "",
        f"- 1X2: `{odds.get('1x2')}`",
        f"- Handicap markets: `{len(odds.get('handicap') or [])}`",
        f"- Totals markets: `{len(odds.get('totals') or [])}`",
        "",
        "## Match Stats",
        "",
    ]
    for key in ("possession", "goal_attempts", "shots_on_target", "shots_off_target", "corners", "yellow_cards"):
        if key in details:
            item = details[key]
            lines.append(f"- `{item.get('name')}`: home={item.get('home')} away={item.get('away')}")
    lines.extend(
        [
            "",
            "## Features",
            "",
        ]
    )
    for key in (
        "form_gap",
        "table_position_gap",
        "attack_strength_home",
        "attack_strength_away",
        "btts_tendency_index",
        "h2h_home_edge",
        "live_pressure_home",
        "live_pressure_away",
    ):
        lines.append(f"- `{key}`: `{values.get(key)}`")
    lines.extend(
        [
            "",
            "## H2H",
            "",
            f"- Sample size: `{(h2h.get('summary') or {}).get('total_matches')}`",
        ]
    )
    for match in (h2h.get("matches") or [])[:5]:
        match_time = match.get("time") or {}
        match_score = match.get("score") or {}
        lines.append(
            "- `{date}` {home_team} {home_score}-{away_score} {away_team}".format(
                date=match_time.get("iso_utc") or match_time.get("date"),
                home_team=(match.get("home") or {}).get("name"),
                home_score=match_score.get("home"),
                away_score=match_score.get("away"),
                away_team=(match.get("away") or {}).get("name"),
            )
        )
    lines.extend(
        [
            "",
            "## Feature Definitions",
            "",
        ]
    )
    for key, definition in (features.get("definitions") or {}).items():
        lines.append(f"- `{key}`: {definition}")
    lines.extend(
        [
            "",
            "## Quality",
            "",
            f"```json\n{json.dumps(snapshot.get('feature_quality'), ensure_ascii=False, indent=2)}\n```",
            "",
            "## Client Metrics",
            "",
            f"```json\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n```",
            "",
            "## Limitations",
            "",
        ]
    )
    for item in snapshot.get("limitations") or []:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: object) -> None:
    """Write pretty JSON using UTF-8."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
