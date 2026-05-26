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

from sandbox.sportradar_http.endpoints.standings import get_formtable, get_season_tables
from sandbox.sportradar_http.endpoints.stats import (
    get_injuries,
    get_team_scoring_conceding,
    get_team_streaks,
    get_top_assists,
    get_top_cards,
    get_top_goals,
)
from sandbox.sportradar_http.endpoints.tournaments import (
    get_tournament_fixtures,
    get_tournament_info,
    get_tournament_teams,
    get_tournament_venues,
)
from sandbox.sportradar_http.features_engine import build_league_features
from sandbox.sportradar_http.http_client import SportradarHTTPClient
from sandbox.sportradar_http.normalizers import (
    make_raw_ref,
    normalize_fixtures,
    normalize_formtable,
    normalize_injuries,
    normalize_league_summary,
    normalize_player_leaders,
    normalize_standings,
    normalize_teams,
    normalize_venues,
)
from sandbox.sportradar_http.session_manager import (
    BootstrapConfig,
    SportradarSessionManager,
    load_session_state,
    save_session_state,
)


KNOWN_CURRENT_SEASONS = {
    8: 130805,  # LaLiga observed from Statshub tournament/8 on 2026-05-26.
}
DEFAULT_SESSION_STATE = Path("sandbox/sportradar_http/reports/session_state_headed.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a compact Sportradar league snapshot/features/report.")
    parser.add_argument("--sport-id", type=int, default=1)
    parser.add_argument("--tournament-id", type=int, default=8)
    parser.add_argument("--season-id", type=int)
    parser.add_argument("--session-state", type=Path, default=DEFAULT_SESSION_STATE)
    parser.add_argument("--out-dir", type=Path, default=Path("sandbox/sportradar_http/examples/league_laliga"))
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--top-players", type=int, default=20)
    parser.add_argument("--max-fixtures", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    season_id = resolve_season_id(args.tournament_id, args.season_id)
    state = ensure_state(args.session_state, seconds=args.seconds)
    client = SportradarHTTPClient(session_state=state, auto_refresh=False, retries=1)
    payloads = fetch_league_payloads(client, season_id=season_id)
    snapshot = build_league_snapshot(args=args, season_id=season_id, payloads=payloads, client=client)
    features = build_league_features(snapshot)
    report = render_league_report(snapshot=snapshot, features=features, metrics=client.metrics_json())
    write_json(args.out_dir / "league_snapshot.json", snapshot)
    write_json(args.out_dir / "league_features.json", features)
    (args.out_dir / "league_report.md").write_text(report, encoding="utf-8")
    print(f"Wrote {args.out_dir / 'league_snapshot.json'}")
    print(f"Wrote {args.out_dir / 'league_features.json'}")
    print(f"Wrote {args.out_dir / 'league_report.md'}")
    return 0


def resolve_season_id(tournament_id: int, season_id: int | None) -> int:
    if season_id is not None:
        return season_id
    if tournament_id in KNOWN_CURRENT_SEASONS:
        return KNOWN_CURRENT_SEASONS[tournament_id]
    raise SystemExit("Pass --season-id. Automatic tournament->season discovery is not implemented yet.")


def ensure_state(path: Path, *, seconds: float):
    if path.exists():
        state = load_session_state(path)
        if state.signed_token and not state.signed_token.is_expired():
            return state
    manager = SportradarSessionManager(BootstrapConfig(headed=True, seconds_per_url=seconds))
    state = manager.refresh_session()
    save_session_state(state, path)
    return state


def fetch_league_payloads(client: SportradarHTTPClient, *, season_id: int) -> dict[str, dict[str, Any]]:
    calls: dict[str, Callable[[], dict[str, Any]]] = {
        "league_summary": lambda: get_tournament_info(client, season_id=season_id),
        "teams": lambda: get_tournament_teams(client, season_id=season_id),
        "fixtures": lambda: get_tournament_fixtures(client, season_id=season_id),
        "standings": lambda: get_season_tables(client, season_id=season_id),
        "formtable": lambda: get_formtable(client, season_id=season_id),
        "venues": lambda: get_tournament_venues(client, season_id=season_id),
        "injuries": lambda: get_injuries(client, season_id=season_id),
        "top_goals": lambda: get_top_goals(client, season_id=season_id, team_id=""),
        "top_cards": lambda: get_top_cards(client, season_id=season_id, team_id=""),
        "top_assists": lambda: get_top_assists(client, season_id=season_id, team_id=""),
    }
    payloads: dict[str, dict[str, Any]] = {}
    for name, call in calls.items():
        payloads[name] = call()
    return payloads


def build_league_snapshot(
    *,
    args: argparse.Namespace,
    season_id: int,
    payloads: dict[str, dict[str, Any]],
    client: SportradarHTTPClient,
) -> dict[str, Any]:
    standings = normalize_standings(payloads["standings"])
    teams = normalize_teams(payloads["teams"])
    first_table = (standings.get("tables") or [{}])[0]
    top_team_uid = (((first_table.get("rows") or [{}])[0].get("team") or {}).get("uid") if isinstance(first_table, dict) else None)
    team_scoring = None
    team_streaks = None
    if top_team_uid:
        scoring_payload = get_team_scoring_conceding(client, season_id=season_id, team_id=int(top_team_uid))
        streaks_payload = get_team_streaks(client, team_id=int(top_team_uid))
        team_scoring = {
            "team_uid": top_team_uid,
            "raw_ref": make_raw_ref("stats_season_teamscoringconceding", scoring_payload),
        }
        team_streaks = {
            "team_uid": top_team_uid,
            "raw_ref": make_raw_ref("stats_team_streaks", streaks_payload),
        }
        payloads["top_team_scoring"] = scoring_payload
        payloads["top_team_streaks"] = streaks_payload
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "sportradar_statshub",
        "scope": "league",
        "inputs": {
            "sport_id": args.sport_id,
            "tournament_id": args.tournament_id,
            "season_id": season_id,
            "season_id_source": "explicit" if args.season_id else "known_current_seasons_fallback",
        },
        "league_summary": normalize_league_summary(payloads["league_summary"]),
        "teams": teams,
        "fixtures": normalize_fixtures(payloads["fixtures"], max_items=args.max_fixtures),
        "standings": standings,
        "formtable": normalize_formtable(payloads["formtable"]),
        "venues": normalize_venues(payloads["venues"]),
        "players": {
            "top_goals": normalize_player_leaders(payloads["top_goals"], max_items=args.top_players),
            "top_cards": normalize_player_leaders(payloads["top_cards"], max_items=args.top_players),
            "top_assists": normalize_player_leaders(payloads["top_assists"], max_items=args.top_players),
        },
        "injuries": normalize_injuries(payloads["injuries"]),
        "sample_team_deep_stats": {
            "scoring": team_scoring,
            "streaks": team_streaks,
        },
        "raw_refs": [make_raw_ref(name, payload) for name, payload in payloads.items()],
        "client_metrics": client.metrics_json(),
        "limitations": [
            "Tournament to current season resolution is currently a small observed mapping, not a full resolver.",
            "Payloads are normalized compactly; raw responses are intentionally not embedded.",
            "Deep team scoring/streaks are sampled for the table leader only in this phase.",
        ],
    }


def render_league_report(*, snapshot: dict[str, Any], features: dict[str, Any], metrics: dict[str, Any]) -> str:
    summary = snapshot.get("league_summary") or {}
    standings = snapshot.get("standings") or {}
    first_table = (standings.get("tables") or [{}])[0]
    rows = first_table.get("rows") if isinstance(first_table, dict) else []
    values = features.get("values") or {}
    lines = [
        "# Sportradar League Pipeline Report",
        "",
        f"- Generated at: `{snapshot.get('generated_at')}`",
        f"- Inputs: `{snapshot.get('inputs')}`",
        f"- Teams: `{len(snapshot.get('teams') or [])}`",
        f"- Fixtures normalized: `{len(snapshot.get('fixtures') or [])}`",
        f"- Injuries normalized: `{len(snapshot.get('injuries') or [])}`",
        "",
        "## League Summary",
        "",
        f"- Matches played: `{summary.get('matches_played')}`",
        f"- Goals per match: `{summary.get('goals_per_match')}`",
        f"- BTTS rate: `{values.get('league_btts_rate')}`",
        f"- Clean sheet rate: `{values.get('league_clean_sheet_rate')}`",
        f"- Season progress: `{values.get('season_progress')}`",
        "",
        "## Top Table Rows",
        "",
    ]
    for row in (rows or [])[:8]:
        team = row.get("team") or {}
        lines.append(
            "- {pos}. {team} P={played} Pts={points} PPM={ppm} GF={gf} GA={ga} GD={gd}".format(
                pos=row.get("position"),
                team=team.get("name"),
                played=row.get("played"),
                points=row.get("points"),
                ppm=row.get("points_per_match"),
                gf=row.get("goals_for"),
                ga=row.get("goals_against"),
                gd=row.get("goal_difference"),
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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

