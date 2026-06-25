"""Bot-ready sandbox adapter for the Sportradar HTTP provider.

Purpose:
    Expose stable method boundaries that resemble a future production BetBot
    stats provider without importing `bot/`, `core/`, `extractors/`, `storage/`
    or writing to the DB.

Public flow:
    - `get_tournament_navigation()` resolves tournament ids and lists fixtures.
    - `get_match_report()` builds snapshot, features and `match_intelligence`.
    - `get_league_snapshot()` builds league-level context.
    - `get_live_match_state()` builds compact live polling state.

Output contract:
    Every method returns JSON-serializable dictionaries. Presentation layers
    should consume these dicts; Telegram rendering should remain separate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

from stats_providers.sportradar_http.engine.endpoints.discovery import get_config_tree_mini
from stats_providers.sportradar_http.engine.endpoints.live import (
    get_match_situation,
    get_match_timeline,
    get_match_timelinedelta,
)
from stats_providers.sportradar_http.engine.endpoints.matches import get_match_info, get_match_snapshot
from stats_providers.sportradar_http.engine.endpoints.tournaments import get_tournament_fixtures
from stats_providers.sportradar_http.engine.features_engine import build_league_features, build_match_features
from stats_providers.sportradar_http.engine.http_client import SportradarHTTPClient
from stats_providers.sportradar_http.engine.match_intelligence import build_match_intelligence
from stats_providers.sportradar_http.engine.normalizers import (
    make_raw_ref,
    normalize_match_metadata,
    normalize_match_situation,
    normalize_match_timeline,
)
from stats_providers.sportradar_http.engine.run_league_pipeline import (
    fetch_league_payloads,
    build_league_snapshot,
    resolve_season_id,
)
from stats_providers.sportradar_http.engine.run_match_pipeline import (
    build_match_snapshot,
    fetch_match_payloads,
    render_match_report,
)
from stats_providers.sportradar_http.engine.runtime import BootstrapMode, BootstrapSessionManager
from stats_providers.sportradar_http.engine.session_manager import (
    SportradarSessionState,
    load_session_state,
    parse_signed_t,
    save_session_state,
    signed_token_from_parsed,
)
from stats_providers.sportradar_http.engine.tournament_navigation import (
    build_tournament_navigation_snapshot,
    build_tournament_tree,
    render_tournament_navigation_report,
    resolve_tournament,
)


DEFAULT_SESSION_STATE = Path("stats_providers/sportradar_http/engine/reports/session_state_headed.json")


@dataclass(frozen=True, slots=True)
class BotReadyRuntimeConfig:
    """Runtime knobs for sandbox provider calls.

    Args:
        session_state_path: Cached bootstrap state path.
        bootstrap_seconds: Browser wait time when a refresh is required.
        timeout_seconds: HTTP request timeout.
        retries: HTTP retry count.
        bootstrap_mode: `headless` opens no GUI, `headed` opens a visible
            browser, and `auto` tries headless then headed.
        lastx/nextx/top_players/max_timeline_events/max_fixtures: output size
            controls for compact provider responses.
    """

    session_state_path: Path = DEFAULT_SESSION_STATE
    bootstrap_profile_dir: Path = Path("stats_providers/sportradar_http/engine/reports/chrome_profile")
    bootstrap_seconds: float = 4.0
    bootstrap_mode: BootstrapMode = "headless"
    # The background/startup token pre-refresh stays headless-only so it NEVER
    # opens a visible window at boot. A visible (headed) fallback is reserved for
    # the on-demand path (a real /stats call) when `bootstrap_mode` allows it; a
    # successful headed run warms the shared profile so later headless refreshes
    # reuse its Akamai cookies and stay invisible.
    background_bootstrap_mode: BootstrapMode = "headless"
    timeout_seconds: float = 25.0
    retries: int = 1
    lastx: int = 8
    nextx: int = 2
    top_players: int = 8
    max_timeline_events: int = 120
    max_fixtures: int = 500


@dataclass(frozen=True, slots=True)
class BotReadyMatchRequest:
    """Request object for match-level methods."""

    match_id: int


@dataclass(frozen=True, slots=True)
class BotReadyLeagueRequest:
    """Request object for league/season snapshot generation."""

    sport_id: int = 1
    tournament_id: int = 8
    season_id: int | None = None


@dataclass(frozen=True, slots=True)
class BotReadyTournamentRequest:
    """Request object for tournament navigation.

    `tournament_id` is the URL-facing Statshub id. The provider resolves it to a
    concrete current `season_id` before fetching fixtures.
    """

    sport_id: int = 1
    tournament_id: int = 8
    category_id: int = 67
    depth: int = 0


def _is_replay_only() -> bool:
    """Return True when SPORTRADAR_REPLAY_ONLY is set in the environment.

    In replay-only mode the provider never opens a browser; it relies
    exclusively on a pre-imported token (via /sportradar_token in Telegram).
    """
    return os.getenv("SPORTRADAR_REPLAY_ONLY", "false").strip().lower() in {"true", "1", "yes"}


class SportradarBotReadyProvider:
    """Research-only adapter shaped like a future BetBot provider.

    This class intentionally lives in sandbox and does not import bot/core/storage
    code. It exposes stable method boundaries that can later be moved behind a
    production provider interface after the data model is accepted.
    """

    def __init__(self, config: BotReadyRuntimeConfig | None = None) -> None:
        self.config = config or BotReadyRuntimeConfig()
        self.replay_only = _is_replay_only()
        # A stable Chromium profile lets a successful bootstrap (even a one-time
        # headed one) leave Akamai clearance cookies behind, so later headless
        # refreshes reuse them instead of arriving cold and getting a 403.
        profile_dir = self.config.bootstrap_profile_dir
        profile_dir.mkdir(parents=True, exist_ok=True)
        self.session_manager = BootstrapSessionManager(
            mode=self.config.bootstrap_mode,
            seconds_per_url=self.config.bootstrap_seconds,
            user_data_dir=str(profile_dir),
        )
        # Separate manager for the background/startup pre-refresh: headless-only so
        # it never opens a visible window at boot. Shares the same Chromium profile,
        # so a one-time headed on-demand run warms cookies this one can reuse.
        self._background_session_manager = BootstrapSessionManager(
            mode=self.config.background_bootstrap_mode,
            seconds_per_url=self.config.bootstrap_seconds,
            user_data_dir=str(profile_dir),
        )

    def get_match_report(self, request: BotReadyMatchRequest) -> dict[str, Any]:
        """Return match snapshot, features, compact intelligence and reports."""

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
        """Resolve tournament navigation and return compact fixtures."""

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
        """Return compact league snapshot/features for a known season."""

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
        """Return compact live-state document for one match id."""

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

    def ensure_fresh_session(self, *, min_ttl_seconds: float = 3600.0) -> bool:
        """Refresh the cached token ahead of expiry so it is never minted mid-use.

        Returns True when a bootstrap (browser) refresh was performed. Designed to
        run from a background job, keeping the token-minting browser launch off the
        user-facing `/stats` path.

        In replay-only mode this is a no-op: the token is managed externally.
        """

        if self.replay_only:
            return False
        state = None
        if self.config.session_state_path.exists():
            state = load_session_state(self.config.session_state_path)
        token = state.signed_token if state is not None else None
        if token is not None and not token.is_expired():
            seconds_left = token.seconds_until_expiration()
            if seconds_left is not None and seconds_left >= min_ttl_seconds:
                return False
        # Background refresh is headless-only: if Akamai blocks headless it raises
        # (caught by the caller) and no visible window opens at startup — the token
        # is then minted on-demand during the next real /stats call.
        state = self._background_session_manager.refresh_session()
        save_session_state(state, self.config.session_state_path)
        return True

    def _client(self) -> SportradarHTTPClient:
        state = None
        if self.config.session_state_path.exists():
            state = load_session_state(self.config.session_state_path)
        if state is None or state.signed_token is None or state.signed_token.is_expired():
            if self.replay_only:
                raise RuntimeError(
                    "🔑 Token de Sportradar ausente o vencido.\n"
                    "Modo replay-only: el bot no abre Chrome.\n"
                    "Renová el token con /sportradar_token <token>."
                )
            state = self.session_manager.refresh_session()
            save_session_state(state, self.config.session_state_path)
        return SportradarHTTPClient(
            session_state=state,
            # In replay-only mode, never auto-refresh (which would open Chrome on a
            # mid-request 403). Let it fail fast so the user can re-import the token.
            session_manager=None if self.replay_only else self.session_manager,
            auto_refresh=not self.replay_only,
            retries=self.config.retries,
            timeout_seconds=self.config.timeout_seconds,
        )

    def _persist_state(self, client: SportradarHTTPClient) -> None:
        if client.state is not None:
            save_session_state(client.state, self.config.session_state_path)

    # -- Token management (used by /sportradar_token handler) ------------------

    def import_token_string(self, raw_token: str) -> dict[str, Any]:
        """Import a raw Sportradar token string and persist it as session state.

        The token is the ``T`` query parameter value (e.g.
        ``acl=/*~exp=1750000000~hmac=abc123``). This builds a minimal
        ``SportradarSessionState`` suitable for HTTP replay.

        Returns a status dict with ``ok``, ``expires_at_utc``, and
        ``seconds_left``.
        """

        parsed = parse_signed_t(_extract_raw_token(raw_token))
        if parsed is None or not parsed.get("raw") or parsed.get("exp") is None:
            return {"ok": False, "error": "No se pudo parsear el token. Debe contener acl=, exp= y hmac=."}
        signed = signed_token_from_parsed(parsed)
        if signed.is_expired():
            return {"ok": False, "error": "El token ya está vencido."}
        from stats_providers.sportradar_http.engine.session_manager import (
            DEFAULT_ORIGIN,
            DEFAULT_REFERER,
            build_replay_headers,
            utc_now_iso,
        )
        state = SportradarSessionState(
            generated_at=utc_now_iso(),
            headed=False,
            headless=False,
            bootstrap_urls=[],
            origin=DEFAULT_ORIGIN,
            referer=DEFAULT_REFERER,
            replay_headers=build_replay_headers(),
            cookies={},
            signed_token=signed,
            sample_signed_url=None,
        )
        save_session_state(state, self.config.session_state_path)
        return {
            "ok": True,
            "expires_at_utc": signed.expires_at_utc,
            "seconds_left": signed.seconds_until_expiration(),
        }

    def import_session_json(self, json_text: str) -> dict[str, Any]:
        """Import a full session state JSON (from the session_manager CLI)."""

        import json
        try:
            payload = json.loads(json_text)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"JSON inválido: {exc}"}
        state = SportradarSessionState.from_json_dict(payload)
        if not state.is_usable():
            return {"ok": False, "error": "El session state no es usable (token vencido o bloqueado)."}
        save_session_state(state, self.config.session_state_path)
        return {
            "ok": True,
            "expires_at_utc": state.token_expiration(),
            "seconds_left": (
                state.signed_token.seconds_until_expiration()
                if state.signed_token else None
            ),
        }

    def get_token_status(self) -> dict[str, Any]:
        """Return the current token status for display in Telegram."""

        if not self.config.session_state_path.exists():
            return {"has_token": False, "usable": False}
        try:
            state = load_session_state(self.config.session_state_path)
        except Exception:
            return {"has_token": False, "usable": False}
        token = state.signed_token
        if token is None:
            return {"has_token": False, "usable": False}
        seconds_left = token.seconds_until_expiration()
        return {
            "has_token": True,
            "usable": state.is_usable(),
            "expired": token.is_expired(),
            "expires_at_utc": token.expires_at_utc,
            "seconds_left": seconds_left,
            "hours_left": round(seconds_left / 3600, 1) if seconds_left is not None else None,
            "replay_only": self.replay_only,
        }


def _extract_raw_token(value: str) -> str:
    """Return a Sportradar ``T`` token from raw text, ``T=...``, or a URL."""

    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed_url = urlparse(raw)
    query_values = parse_qs(parsed_url.query).get("T")
    if query_values:
        return query_values[0].strip()
    if raw.startswith("T="):
        return raw[2:].strip()
    return raw


def build_live_state_document(
    *,
    match_id: int,
    payloads: dict[str, dict[str, Any]],
    errors: dict[str, str],
) -> dict[str, Any]:
    """Build JSON-safe live state from raw live endpoint payloads."""

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
