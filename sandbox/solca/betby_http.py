"""HTTP-only helpers for Betby prematch/live snapshots.

This module intentionally stays in sandbox. It models the observed public
snapshot/chunk feed without integrating it into the production bot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx


DEFAULT_API_HOST = "api-g-c7818b61-607.sptpub.com"
DEMO_API_HOST = "demoapi.betby.com"
DEFAULT_BRAND_ID = "2392759269461204992"
DEMO_BRAND_ID = "1653815133341880320"
DEFAULT_LANG = "en"
SUPPORTED_FEEDS = {"prematch", "live"}

SUPPORTED_BRANDS: dict[str, dict[str, str]] = {
    "solcasino.io": {
        "platform": "solcasino",
        "api_host": DEFAULT_API_HOST,
        "brand_id": DEFAULT_BRAND_ID,
    },
    "rainbet.com": {
        "platform": "rainbet",
        "api_host": DEFAULT_API_HOST,
        "brand_id": DEFAULT_BRAND_ID,
    },
    "demo.betby.com": {
        "platform": "betby_demo",
        "api_host": DEMO_API_HOST,
        "brand_id": DEMO_BRAND_ID,
    },
}


@dataclass(frozen=True)
class BetbyBrandConfig:
    """Connection details for one Betby/sptpub clone."""

    platform: str
    site_origin: str
    api_host: str = DEFAULT_API_HOST
    brand_id: str = DEFAULT_BRAND_ID
    language: str = DEFAULT_LANG


def extract_tournament_id(url: str) -> str:
    """Extract the numeric Betby tournament id from a sportsbook URL."""

    parsed = urlparse(url)
    bt_path = parse_qs(parsed.query).get("bt-path", [""])[0]
    decoded_path = unquote(bt_path or parsed.path)
    match = re.search(r"-(\d{12,})/?$", decoded_path)
    if not match:
        raise ValueError(f"No tournament id found in path={decoded_path!r}.")
    return match.group(1)


def config_from_site_url(url: str, *, language: str = DEFAULT_LANG) -> BetbyBrandConfig:
    """Return the known sptpub config for one sportsbook clone URL."""

    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host not in SUPPORTED_BRANDS:
        raise ValueError(f"Unsupported Solcasino/Rainbet clone host: {host}")

    raw = SUPPORTED_BRANDS[host]
    return BetbyBrandConfig(
        platform=raw["platform"],
        site_origin=f"{parsed.scheme or 'https'}://{host}",
        api_host=raw["api_host"],
        brand_id=raw["brand_id"],
        language=language,
    )


def build_feed_url(
    config: BetbyBrandConfig,
    *,
    feed: str = "prematch",
    version: int | str = 0,
) -> str:
    """Build one Betby snapshot/chunk URL for a supported feed."""

    if feed not in SUPPORTED_FEEDS:
        raise ValueError(f"Unsupported Betby feed: {feed!r}")
    return (
        f"https://{config.api_host}/api/v4/{feed}/brand/"
        f"{config.brand_id}/{config.language}/{version}"
    )


def build_prematch_url(config: BetbyBrandConfig, version: int | str = 0) -> str:
    """Build one Betby prematch snapshot/chunk URL."""

    return build_feed_url(config, feed="prematch", version=version)


def build_live_url(config: BetbyBrandConfig, version: int | str = 0) -> str:
    """Build one Betby live snapshot/chunk URL."""

    return build_feed_url(config, feed="live", version=version)


def default_headers(config: BetbyBrandConfig) -> dict[str, str]:
    """Headers that are enough for the observed sptpub HTTP endpoints."""

    return {
        "accept": "application/json,text/plain,*/*",
        "accept-language": "es-AR,es;q=0.9,en;q=0.8",
        "origin": config.site_origin,
        "referer": f"{config.site_origin}/",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        ),
    }


def snapshot_versions_from_manifest(manifest: dict[str, Any]) -> list[int]:
    """Return ordered chunk versions from a Betby version=0 manifest."""

    versions: list[int] = []
    for key in ("top_events_versions", "rest_events_versions"):
        raw_versions = manifest.get(key)
        if not isinstance(raw_versions, list):
            continue
        for raw_version in raw_versions:
            try:
                version = int(raw_version)
            except (TypeError, ValueError):
                continue
            if version not in versions:
                versions.append(version)
    return versions


def deep_merge(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Merge Betby snapshot chunks by top-level dictionaries."""

    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def empty_snapshot() -> dict[str, Any]:
    """Return the minimum merge target used by the snapshot/chunk feed."""

    return {
        "sports": {},
        "categories": {},
        "tournaments": {},
        "events": {},
    }


def fetch_json(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str],
) -> dict[str, Any]:
    """Fetch one JSON object and fail loudly if the endpoint is not usable."""

    response = client.get(url, headers=headers)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object from {url}.")
    return payload


def fetch_snapshot(
    config: BetbyBrandConfig,
    *,
    feed: str = "prematch",
    timeout_seconds: float = 30.0,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Fetch version=0, then all advertised snapshot chunks, and merge them."""

    headers = default_headers(config)
    manifest_url = build_feed_url(config, feed=feed, version=0)
    merged = empty_snapshot()
    chunks: list[dict[str, Any]] = []

    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        manifest = fetch_json(client, manifest_url, headers=headers)
        versions = snapshot_versions_from_manifest(manifest)
        if not versions and any(isinstance(manifest.get(key), dict) for key in ("events", "tournaments")):
            versions = [int(manifest.get("version") or 0)]
            deep_merge(merged, manifest)
            chunks.append(_chunk_summary(version=versions[0], status=200, payload=manifest))
            return manifest, merged, chunks

        for version in versions:
            chunk_url = build_feed_url(config, feed=feed, version=version)
            chunk = fetch_json(client, chunk_url, headers=headers)
            deep_merge(merged, chunk)
            chunks.append(_chunk_summary(version=version, status=200, payload=chunk))

    return manifest, merged, chunks


def fetch_prematch_snapshot(
    config: BetbyBrandConfig,
    *,
    timeout_seconds: float = 30.0,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Fetch and merge the Betby prematch snapshot."""

    return fetch_snapshot(config, feed="prematch", timeout_seconds=timeout_seconds)


def fetch_live_snapshot(
    config: BetbyBrandConfig,
    *,
    timeout_seconds: float = 30.0,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Fetch and merge the Betby live snapshot."""

    return fetch_snapshot(config, feed="live", timeout_seconds=timeout_seconds)


def build_league_odds_document(
    snapshot: dict[str, Any],
    *,
    config: BetbyBrandConfig,
    source_url: str,
    tournament_id: str,
    manifest: dict[str, Any] | None = None,
    chunks: list[dict[str, Any]] | None = None,
    feed: str = "prematch",
) -> dict[str, Any]:
    """Build a compact tracking-ready league odds JSON from a merged snapshot."""

    tournament = (snapshot.get("tournaments") or {}).get(str(tournament_id), {})
    category_id = tournament.get("category_id")
    category = (snapshot.get("categories") or {}).get(str(category_id), {}) if category_id else {}
    matches = extract_league_matches(
        snapshot,
        tournament_id=tournament_id,
        platform=config.platform,
        feed=feed,
    )

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": {
            "platform": config.platform,
            "provider": "betby_sptpub",
            "source_url": source_url,
            "api_host": config.api_host,
            "brand_id": config.brand_id,
            "language": config.language,
            "feed": feed,
            "snapshot_endpoint": build_feed_url(config, feed=feed, version=0),
            "manifest_version": (manifest or {}).get("version"),
            "chunk_versions": [item["version"] for item in (chunks or [])],
        },
        "league": {
            "league_id": str(tournament_id),
            "league": tournament.get("name"),
            "slug": tournament.get("slug"),
            "country": category.get("name"),
            "country_id": category_id,
            "sport_id": _infer_sport_id(matches),
        },
        "summary": {
            "matches_count": len(matches),
            "matches_with_1x2": sum(1 for item in matches if item["market_status"]["has_1x2"]),
            "matches_with_handicap": sum(1 for item in matches if item["market_status"]["has_handicap"]),
            "matches_with_totals": sum(1 for item in matches if item["market_status"]["has_totals"]),
            "matches_in_live_feed": sum(1 for item in matches if item["live_state"]["in_live_feed"]),
            "matches_currently_live": sum(1 for item in matches if item["live_state"]["is_live"]),
        },
        "matches": matches,
    }


def extract_league_matches(
    snapshot: dict[str, Any],
    *,
    tournament_id: str,
    platform: str,
    feed: str = "prematch",
) -> list[dict[str, Any]]:
    """Extract normalized football-ish matches for one tournament id."""

    tournament = (snapshot.get("tournaments") or {}).get(str(tournament_id), {})
    category_id = tournament.get("category_id")
    category = (snapshot.get("categories") or {}).get(str(category_id), {}) if category_id else {}
    matches: list[dict[str, Any]] = []

    for event_id, event in (snapshot.get("events") or {}).items():
        if not isinstance(event, dict):
            continue
        desc = event.get("desc") or {}
        if desc.get("type") != "match":
            continue
        if str(desc.get("tournament")) != str(tournament_id):
            continue

        competitors = desc.get("competitors") or []
        if len(competitors) < 2:
            continue

        markets = event.get("markets") or {}
        home = str(competitors[0].get("name") or "").strip()
        away = str(competitors[1].get("name") or "").strip()
        kickoff = _kickoff_payload(desc.get("scheduled"))
        odds_1x2 = extract_1x2(markets)
        handicap = extract_handicap(markets)
        totals = extract_totals(markets)
        live_state = extract_live_state(event, feed=feed)

        missing: list[str] = []
        if not any(value is not None for value in odds_1x2.values()):
            missing.append("1x2")
        if not handicap:
            missing.append("handicap")
        if not totals:
            missing.append("totals")

        matches.append(
            {
                "platform": platform,
                "external_event_id": str(event_id),
                "external_competition_id": str(tournament_id),
                "competition_name": tournament.get("name"),
                "category_name": category.get("name"),
                "home": home,
                "away": away,
                "home_id": _safe_str(competitors[0].get("id")),
                "away_id": _safe_str(competitors[1].get("id")),
                "sport_id": _safe_str(desc.get("sport")),
                "kickoff": kickoff,
                "odds_1x2": odds_1x2,
                "handicap": handicap,
                "totals": totals,
                "live_state": live_state,
                "market_status": {
                    "has_1x2": "1x2" not in missing,
                    "has_handicap": bool(handicap),
                    "has_totals": bool(totals),
                    "missing": missing,
                },
                "raw_refs": {
                    "market_keys": sorted(str(key) for key in markets.keys()),
                    "raw_market_count": len(markets),
                    "desc_flags": {
                        "all_markets": desc.get("all_markets"),
                        "bet_builder": desc.get("bet_builder"),
                        "player_props": desc.get("player_props"),
                    },
                },
            }
        )

    return sorted(matches, key=lambda item: item["kickoff"]["unix"] or 0)


def extract_live_state(event: dict[str, Any], *, feed: str = "prematch") -> dict[str, Any]:
    """Extract a compact, defensive live-state view from one Betby event."""

    state = event.get("state") or {}
    if not isinstance(state, dict):
        state = {}
    clock = state.get("clock") if isinstance(state.get("clock"), dict) else {}
    status = state.get("status")
    match_status = state.get("match_status")

    return {
        "in_live_feed": feed == "live",
        "is_live": status == 1 or bool(clock),
        "status_code": status,
        "match_status_code": match_status,
        "clock": {
            "match_time": _safe_str(clock.get("match_time")),
            "stopped": clock.get("stopped") if isinstance(clock.get("stopped"), bool) else None,
            "timestamp": clock.get("timestamp"),
        }
        if clock
        else None,
        "score_home": _extract_score_value(state, side="home"),
        "score_away": _extract_score_value(state, side="away"),
        "raw_state": state,
    }


def extract_1x2(markets: dict[str, Any]) -> dict[str, float | None]:
    """Extract standard 1/X/2 odds from Betby market id 1."""

    market = ((markets.get("1") or {}).get("") or {})
    return {
        "1": _coerce_float((market.get("1") or {}).get("k")),
        "X": _coerce_float((market.get("2") or {}).get("k")),
        "2": _coerce_float((market.get("3") or {}).get("k")),
    }


def extract_totals(markets: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract totals from any market/spec containing `total=<line>`.

    Observed soccer totals use market id `18`, outcome `12` as Over and `13` as Under.
    """

    totals: list[dict[str, Any]] = []
    for market_id, market in markets.items():
        if not isinstance(market, dict):
            continue
        for spec, outcomes in market.items():
            line = _extract_spec_number(str(spec), "total")
            if line is None or not isinstance(outcomes, dict):
                continue
            totals.append(
                {
                    "line": line,
                    "over": _coerce_float((outcomes.get("12") or {}).get("k")),
                    "under": _coerce_float((outcomes.get("13") or {}).get("k")),
                    "raw_market_id": str(market_id),
                    "raw_spec": str(spec),
                }
            )

    return sorted(totals, key=lambda item: abs(float(item["line"]) - 2.5))


def extract_handicap(markets: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract observed Betby handicap specs.

    Mapping note: old captures show outcome ids `1714` and `1715` for two-way handicap.
    We keep the raw outcome ids and expose home/away as a transparent current assumption.
    """

    handicap: list[dict[str, Any]] = []
    for market_id, market in markets.items():
        if not isinstance(market, dict):
            continue
        for spec, outcomes in market.items():
            line = _extract_spec_number(str(spec), "hcp")
            if line is None or not isinstance(outcomes, dict):
                continue
            handicap.append(
                {
                    "line": line,
                    "home": _coerce_float((outcomes.get("1714") or {}).get("k")),
                    "away": _coerce_float((outcomes.get("1715") or {}).get("k")),
                    "raw_market_id": str(market_id),
                    "raw_spec": str(spec),
                    "raw_outcomes": {
                        key: _coerce_float((value or {}).get("k"))
                        for key, value in outcomes.items()
                        if isinstance(value, dict)
                    },
                    "mapping_note": "assumes outcome 1714=home and 1715=away; keep raw_outcomes for verification",
                }
            )

    return sorted(handicap, key=lambda item: abs(float(item["line"])))


def _chunk_summary(*, version: int, status: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": version,
        "status": status,
        "payload_version": payload.get("version"),
        "generated": payload.get("generated"),
        "snapshot_complete": payload.get("snapshot_complete"),
        "fixtures_complete": payload.get("fixtures_complete"),
        "sports_count": len(payload.get("sports") or {}),
        "categories_count": len(payload.get("categories") or {}),
        "tournaments_count": len(payload.get("tournaments") or {}),
        "events_count": len(payload.get("events") or {}),
    }


def _kickoff_payload(raw_value: Any) -> dict[str, Any]:
    unix_value: int | None
    try:
        unix_value = int(raw_value)
    except (TypeError, ValueError):
        unix_value = None

    if unix_value is None:
        return {"unix": None, "utc": None, "date_utc": None, "time_utc": None}

    kickoff = datetime.fromtimestamp(unix_value, tz=UTC)
    return {
        "unix": unix_value,
        "utc": kickoff.isoformat(),
        "date_utc": kickoff.date().isoformat(),
        "time_utc": kickoff.strftime("%H:%M"),
    }


def _infer_sport_id(matches: list[dict[str, Any]]) -> str | None:
    for match in matches:
        sport_id = match.get("sport_id")
        if sport_id:
            return str(sport_id)
    return None


def _extract_spec_number(spec: str, key: str) -> float | None:
    match = re.search(rf"(?:^|\|){re.escape(key)}=([-+]?\d+(?:\.\d+)?)", spec)
    if not match:
        return None
    return _coerce_float(match.group(1))


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_score_value(state: dict[str, Any], *, side: str) -> int | None:
    """Best-effort score extraction; observed live samples often omit score."""

    direct_keys = (
        ("home_score", "score_home", "homeScore", "team1_score", "score1")
        if side == "home"
        else ("away_score", "score_away", "awayScore", "team2_score", "score2")
    )
    for key in direct_keys:
        score = _coerce_int(state.get(key))
        if score is not None:
            return score

    score_payload = state.get("score")
    if isinstance(score_payload, dict):
        nested_keys = (
            ("home", "home_score", "score_home", "1")
            if side == "home"
            else ("away", "away_score", "score_away", "2")
        )
        for key in nested_keys:
            score = _coerce_int(score_payload.get(key))
            if score is not None:
                return score

    return None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
