from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sandbox.sportradar_http.endpoints.discovery import get_config_tree_mini
from sandbox.sportradar_http.endpoints.live import (
    get_match_situation,
    get_match_timeline,
    get_match_timelinedelta,
)
from sandbox.sportradar_http.endpoints.matches import get_match_info, get_match_snapshot
from sandbox.sportradar_http.endpoints.tournaments import get_tournament_fixtures
from sandbox.sportradar_http.features_engine import build_league_features, build_match_features
from sandbox.sportradar_http.http_client import SportradarHTTPClient
from sandbox.sportradar_http.match_intelligence import build_match_intelligence
from sandbox.sportradar_http.normalizers import (
    make_raw_ref,
    normalize_match_metadata,
    normalize_match_situation,
    normalize_match_timeline,
)
from sandbox.sportradar_http.run_league_pipeline import (
    fetch_league_payloads,
    build_league_snapshot,
    resolve_season_id,
)
from sandbox.sportradar_http.run_match_pipeline import (
    build_match_snapshot,
    fetch_match_payloads,
    render_match_report,
)
from sandbox.sportradar_http.session_manager import (
    BootstrapConfig,
    SportradarSessionManager,
    load_session_state,
    save_session_state,
)
from sandbox.sportradar_http.tournament_navigation import (
    build_tournament_navigation_snapshot,
    build_tournament_tree,
    render_tournament_navigation_report,
    resolve_tournament,
)


DEFAULT_SESSION_STATE = Path("sandbox/sportradar_http/reports/session_state_headed.json")


@dataclass(frozen=True, slots=True)
class BotReadyRuntimeConfig:
    session_state_path: Path = DEFAULT_SESSION_STATE
    bootstrap_seconds: float = 4.0
    timeout_seconds: float = 25.0
    retries: int = 1
    lastx: int = 8
    nextx: int = 2
    top_players: int = 8
    max_timeline_events: int = 120
    max_fixtures: int = 500


@dataclass(frozen=True, slots=True)
class BotReadyMatchRequest:
    match_id: int


@dataclass(frozen=True, slots=True)
class BotReadyLeagueRequest:
    sport_id: int = 1
    tournament_id: int = 8
    season_id: int | None = None


@dataclass(frozen=True, slots=True)
class BotReadyTournamentRequest:
    sport_id: int = 1
    tournament_id: int = 8
    category_id: int = 67
    depth: int = 0


class SportradarBotReadyProvider:
    """Research-only adapter shaped like a future BetBot provider.

    This class intentionally lives in sandbox and does not import bot/core/storage
    code. It exposes stable method boundaries that can later be moved behind a
    production provider interface after the data model is accepted.
    """

    def __init__(self, config: BotReadyRuntimeConfig | None = None) -> None:
        self.config = config or BotReadyRuntimeConfig()
        self.session_manager = SportradarSessionManager(
            BootstrapConfig(headed=True, seconds_per_url=self.config.bootstrap_seconds)
        )

    def get_match_report(self, request: BotReadyMatchRequest) -> dict[str, Any]:
        client = self._client()
        args = SimpleNamespace(
            match_id=request.match_id,
            lastx=self.config.lastx,
            nextx=self.config.nextx,
            top_players=self.config.top_players,
            max_timeline_events=self.config.max_timeline_events,
        )
        payloads, errors = fetch_match_payloads(client, args)
        snapshot = build_match_snapshot(args=args, payloads=payloads, errors=errors, client=client)
        features = build_match_features(snapshot)
        intelligence = build_match_intelligence(snapshot, features)
        report = render_match_report(snapshot=snapshot, features=features, metrics=client.metrics_json())
        self._persist_state(client)
        return {
            "schema_version": 1,
            "kind": "match_report",
            "snapshot": snapshot,
            "features": features,
            "intelligence": intelligence,
            "report_markdown": report,
            "intelligence_markdown": intelligence.get("report_summary"),
            "client_metrics": client.metrics_json(),
        }

    def get_tournament_navigation(self, request: BotReadyTournamentRequest) -> dict[str, Any]:
        client = self._client()
        config_tree = get_config_tree_mini(
            client,
            sport_id=request.sport_id,
            category_id=request.category_id,
            depth=request.depth,
        )
        resolved = resolve_tournament(build_tournament_tree(config_tree), request.tournament_id)
        fixtures_payload: dict[str, Any] = {}
        if resolved.get("season_id") is not None:
            fixtures_payload = get_tournament_fixtures(client, season_id=int(resolved["season_id"]))
        snapshot = build_tournament_navigation_snapshot(
            sport_id=request.sport_id,
            tournament_id=request.tournament_id,
            config_tree_payload=config_tree,
            fixtures_payload=fixtures_payload,
            max_fixtures=self.config.max_fixtures,
        )
        snapshot["client_metrics"] = client.metrics_json()
        report = render_tournament_navigation_report(snapshot)
        self._persist_state(client)
        return {
            "schema_version": 1,
            "kind": "tournament_navigation",
            "snapshot": snapshot,
            "fixtures": snapshot.get("fixtures") or [],
            "report_markdown": report,
            "client_metrics": client.metrics_json(),
        }

    def get_league_snapshot(self, request: BotReadyLeagueRequest) -> dict[str, Any]:
        client = self._client()
        season_id = resolve_season_id(request.tournament_id, request.season_id)
        args = SimpleNamespace(
            sport_id=request.sport_id,
            tournament_id=request.tournament_id,
            season_id=request.season_id,
            max_fixtures=self.config.max_fixtures,
            top_players=self.config.top_players,
        )
        payloads = fetch_league_payloads(client, season_id=season_id)
        snapshot = build_league_snapshot(args=args, season_id=season_id, payloads=payloads, client=client)
        features = build_league_features(snapshot)
        self._persist_state(client)
        return {
            "schema_version": 1,
            "kind": "league_snapshot",
            "snapshot": snapshot,
            "features": features,
            "client_metrics": client.metrics_json(),
        }

    def get_live_match_state(self, request: BotReadyMatchRequest) -> dict[str, Any]:
        client = self._client()
        payloads: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}
        calls = {
            "match_info": lambda: get_match_info(client, match_id=request.match_id),
            "match_snapshot": lambda: get_match_snapshot(client, match_id=request.match_id),
            "match_timeline": lambda: get_match_timeline(client, match_id=request.match_id),
            "match_timelinedelta": lambda: get_match_timelinedelta(client, match_id=request.match_id),
            "match_situation": lambda: get_match_situation(client, match_id=request.match_id),
        }
        for name, call in calls.items():
            try:
                payloads[name] = call()
            except Exception as exc:
                errors[name] = repr(exc)
        document = build_live_state_document(match_id=request.match_id, payloads=payloads, errors=errors)
        document["client_metrics"] = client.metrics_json()
        self._persist_state(client)
        return document

    def _client(self) -> SportradarHTTPClient:
        state = None
        if self.config.session_state_path.exists():
            state = load_session_state(self.config.session_state_path)
        if state is None or state.signed_token is None or state.signed_token.is_expired():
            state = self.session_manager.refresh_session()
            save_session_state(state, self.config.session_state_path)
        return SportradarHTTPClient(
            session_state=state,
            session_manager=self.session_manager,
            auto_refresh=True,
            retries=self.config.retries,
            timeout_seconds=self.config.timeout_seconds,
        )

    def _persist_state(self, client: SportradarHTTPClient) -> None:
        if client.state is not None:
            save_session_state(client.state, self.config.session_state_path)


def build_live_state_document(
    *,
    match_id: int,
    payloads: dict[str, dict[str, Any]],
    errors: dict[str, str],
) -> dict[str, Any]:
    metadata = normalize_match_metadata(payloads.get("match_info"), payloads.get("match_snapshot"))
    live_state = normalize_match_timeline(payloads.get("match_timeline"), max_events=40)
    live_delta = normalize_match_timeline(payloads.get("match_timelinedelta"), max_events=40)
    live_situation = normalize_match_situation(payloads.get("match_situation"))
    return {
        "schema_version": 1,
        "kind": "live_match_state",
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "sportradar_statshub",
        "match_id": match_id,
        "metadata": metadata,
        "live_state": live_state,
        "live_delta": live_delta,
        "live_situation": live_situation,
        "feature_quality": {
            "has_metadata": bool(metadata.get("match_id")),
            "has_timeline": "match_timeline" in payloads,
            "has_delta": "match_timelinedelta" in payloads,
            "has_situation": "match_situation" in payloads,
            "endpoint_errors": errors,
        },
        "raw_refs": [make_raw_ref(name, payload) for name, payload in sorted(payloads.items())],
    }
