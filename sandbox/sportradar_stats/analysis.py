"""Pure helpers for inspecting captured Sportradar / Bet365Stats network feeds."""

from __future__ import annotations

import base64
from collections import Counter, defaultdict
from datetime import datetime
import json
import math
import re
from statistics import mean, median
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


SPANISH_CAPABILITY_LABELS = {
    "match_id": "match_id",
    "team_id": "team_id",
    "player_id": "player_id",
    "competition_id": "competition_id",
    "timeline": "timeline",
    "live_state": "live_state",
    "score": "score",
    "current_period": "current_period",
    "time_played": "time_played",
    "cards": "cards",
    "corners": "corners",
    "shots": "shots",
    "shots_on_target": "shots_on_target",
    "possession": "possession",
    "attacks": "attacks",
    "dangerous_attacks": "dangerous_attacks",
    "lineups": "lineups",
    "injuries": "injuries",
    "player_stats": "player_stats",
    "team_stats": "team_stats",
    "standings": "standings",
    "recent_form": "recent_form",
    "win_probability": "win_probability",
    "odds": "odds",
}

ID_SEGMENT_RE = re.compile(r"^\d+$")
HEXISH_SEGMENT_RE = re.compile(r"^[0-9a-f]{12,}$", re.IGNORECASE)
DATEISH_SEGMENT_RE = re.compile(r"^\d{8,14}$")


def extract_sportradar_match_id(stats_url: str | None) -> str | None:
    """Extract the match id from a Bet365Stats / Sportradar match URL."""

    normalized_url = (stats_url or "").strip()
    if not normalized_url:
        return None

    parsed = urlparse(normalized_url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return None

    for segment in reversed(segments):
        if ID_SEGMENT_RE.fullmatch(segment):
            return segment

    return None


def decode_embedded_data_from_url(url: str) -> dict[str, Any] | list[Any] | None:
    """Decode the base64url-ish `data` query parameter used by some widget calls."""

    parsed = urlparse(url)
    raw_values = parse_qs(parsed.query).get("data")
    if not raw_values:
        return None

    for raw_value in raw_values:
        decoded = decode_maybe_base64_json(raw_value)
        if decoded is not None:
            return decoded

    return None


def decode_maybe_base64_json(raw_value: str | None) -> dict[str, Any] | list[Any] | None:
    """Try to decode one URL-safe base64 JSON blob."""

    normalized = unquote((raw_value or "").strip())
    if not normalized:
        return None

    candidates = [normalized]
    if "%3D" in raw_value.lower() if raw_value else False:
        candidates.append((raw_value or "").strip())

    for candidate in candidates:
        padding = "=" * (-len(candidate) % 4)
        try:
            decoded_bytes = base64.urlsafe_b64decode(candidate + padding)
        except Exception:
            continue

        try:
            decoded_text = decoded_bytes.decode("utf-8")
        except UnicodeDecodeError:
            continue

        try:
            parsed = json.loads(decoded_text)
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, (dict, list)):
            return parsed

    return None


def normalize_endpoint_path(url: str) -> str:
    """Normalize a URL path so repeated ids collapse into a stable endpoint key."""

    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return "/"

    normalized_segments = [_normalize_segment(segment) for segment in segments]
    return "/" + "/".join(normalized_segments)


def build_endpoint_key(
    url: str,
    *,
    decoded_request_data: object | None = None,
    parsed_json: object | None = None,
) -> str:
    """Build a meaningful grouping key for one captured response."""

    hinted = (
        _endpoint_hint_from_payload(decoded_request_data)
        or _endpoint_hint_from_payload(parsed_json)
    )
    if hinted:
        return hinted

    return normalize_endpoint_path(url)


def classify_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    """Enrich one raw record with derived endpoint and capability metadata."""

    decoded_request_data = record.get("decoded_request_data")
    parsed_json = record.get("body_json")
    endpoint_key = build_endpoint_key(
        str(record.get("url") or ""),
        decoded_request_data=decoded_request_data,
        parsed_json=parsed_json,
    )
    capabilities = sorted(
        detect_capabilities(endpoint_key, parsed_json, decoded_request_data)
    )
    match_id = (
        extract_sportradar_match_id(str(record.get("url") or ""))
        or _extract_first_id(parsed_json, {"match_id", "matchid", "match"})
        or _extract_first_id(decoded_request_data, {"match_id", "matchid", "match"})
    )

    enriched = dict(record)
    enriched["normalized_path"] = normalize_endpoint_path(str(record.get("url") or ""))
    enriched["endpoint_key"] = endpoint_key
    enriched["capabilities"] = capabilities
    enriched["match_id"] = match_id
    enriched["main_fields"] = summarize_json_fields(parsed_json)
    return enriched


def summarize_capture_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize captured responses by endpoint."""

    enriched_records = [classify_record(record) for record in records]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in enriched_records:
        grouped[str(record["endpoint_key"])].append(record)

    endpoint_summaries: list[dict[str, Any]] = []
    overall_capabilities: Counter[str] = Counter()
    for endpoint_key, endpoint_records in sorted(
        grouped.items(),
        key=lambda item: (-len(item[1]), item[0]),
    ):
        summary = summarize_endpoint_records(endpoint_key, endpoint_records)
        endpoint_summaries.append(summary)
        overall_capabilities.update(summary["capabilities"])

    return {
        "records_count": len(enriched_records),
        "endpoints_count": len(endpoint_summaries),
        "overall_capabilities": dict(sorted(overall_capabilities.items())),
        "endpoints": endpoint_summaries,
    }


def summarize_endpoint_records(
    endpoint_key: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize repeated captures for one logical endpoint."""

    body_sizes = [int(record.get("body_size_bytes") or 0) for record in records]
    statuses = Counter(int(record.get("status") or 0) for record in records)
    content_types = Counter(str(record.get("content_type") or "") for record in records)
    resource_types = Counter(str(record.get("resource_type") or "") for record in records)
    capabilities = Counter(
        capability
        for record in records
        for capability in record.get("capabilities", [])
    )
    main_fields = Counter(
        field
        for record in records
        for field in record.get("main_fields", [])
    )
    timestamps = [
        _parse_iso_datetime(str(record.get("captured_at") or ""))
        for record in records
    ]
    parsed_timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    polling_summary = infer_polling_behavior(parsed_timestamps, len(records))

    preview_record = next(
        (
            record
            for record in records
            if record.get("body_json") is not None or record.get("preview")
        ),
        records[0],
    )

    return {
        "endpoint_key": endpoint_key,
        "normalized_path": str(records[0].get("normalized_path") or ""),
        "count": len(records),
        "statuses": dict(statuses),
        "blocked": any(status in {401, 403} for status in statuses),
        "content_types": dict(content_types),
        "resource_types": dict(resource_types),
        "polling_likely": polling_summary["polling_likely"],
        "polling_reason": polling_summary["reason"],
        "median_interval_seconds": polling_summary["median_interval_seconds"],
        "avg_body_size_bytes": round(mean(body_sizes), 2) if body_sizes else 0,
        "median_body_size_bytes": round(median(body_sizes), 2) if body_sizes else 0,
        "max_body_size_bytes": max(body_sizes) if body_sizes else 0,
        "capabilities": dict(capabilities),
        "main_fields": [field for field, _ in main_fields.most_common(20)],
        "sample_urls": unique_preserving_order(
            str(record.get("url") or "") for record in records
        )[:3],
        "sample_preview": build_sample_preview(preview_record),
        "sample_request_data": preview_record.get("decoded_request_data"),
        "match_ids": unique_preserving_order(
            str(record.get("match_id") or "")
            for record in records
            if record.get("match_id")
        )[:10],
    }


def infer_polling_behavior(
    timestamps: list[datetime],
    count: int,
) -> dict[str, Any]:
    """Infer whether one endpoint looks like live polling."""

    if count <= 1 or len(timestamps) <= 1:
        return {
            "polling_likely": False,
            "median_interval_seconds": None,
            "reason": "single_capture",
        }

    sorted_timestamps = sorted(timestamps)
    intervals = [
        max(0.0, (right - left).total_seconds())
        for left, right in zip(sorted_timestamps, sorted_timestamps[1:], strict=False)
    ]
    non_zero_intervals = [interval for interval in intervals if interval > 0]
    if not non_zero_intervals:
        return {
            "polling_likely": count >= 3,
            "median_interval_seconds": 0.0,
            "reason": "same_second_repeats",
        }

    median_interval = median(non_zero_intervals)
    polling_likely = count >= 3 and median_interval <= 5.0
    if polling_likely:
        reason = "high_frequency_repeats"
    elif count >= 3:
        reason = "repeated_but_slow"
    else:
        reason = "few_repeats"

    return {
        "polling_likely": polling_likely,
        "median_interval_seconds": round(median_interval, 3),
        "reason": reason,
    }


def summarize_json_fields(payload: object, *, max_depth: int = 2) -> list[str]:
    """Return compact key paths discovered in a JSON payload."""

    field_counter: Counter[str] = Counter()

    def visit(value: object, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return

        if isinstance(value, dict):
            for key, child in value.items():
                key_name = str(key)
                path = f"{prefix}.{key_name}" if prefix else key_name
                field_counter[path] += 1
                visit(child, path, depth + 1)
            return

        if isinstance(value, list):
            if not value:
                return
            sample = value[0]
            visit(sample, f"{prefix}[]" if prefix else "[]", depth + 1)

    visit(payload, "", 0)
    return [field for field, _ in field_counter.most_common(25)]


def detect_capabilities(
    endpoint_key: str,
    parsed_json: object | None,
    decoded_request_data: object | None = None,
) -> set[str]:
    """Detect what kind of sports data an endpoint appears to contain."""

    haystacks = [
        endpoint_key.lower(),
        json.dumps(parsed_json, ensure_ascii=False).lower()
        if parsed_json is not None
        else "",
        json.dumps(decoded_request_data, ensure_ascii=False).lower()
        if decoded_request_data is not None
        else "",
    ]
    combined = " ".join(part for part in haystacks if part)

    checks = {
        "match_id": ("match_id", "matchid", "\"match\":", "/match/"),
        "team_id": ("team_id", "teamid", "\"team\":", "home_team", "away_team"),
        "player_id": ("player_id", "playerid", "\"player\":"),
        "competition_id": ("competition_id", "tournament_id", "season_id", "\"competition\":"),
        "timeline": ("match_timeline", "timeline", "events", "incident"),
        "live_state": ("live", "status", "state", "matchstatus"),
        "score": ("score", "scores", "result"),
        "current_period": ("period", "quarter", "half", "inning"),
        "time_played": ("minute", "clock", "elapsed", "time_played"),
        "cards": ("card", "yellow", "red"),
        "corners": ("corner", "corners"),
        "shots": ("shots", "shot"),
        "shots_on_target": ("shots_on_target", "shot_on_target", "on target"),
        "possession": ("possession",),
        "attacks": ("attacks",),
        "dangerous_attacks": ("dangerous_attacks", "dangerous attacks"),
        "lineups": ("lineup", "lineups", "formation", "starting_xi"),
        "injuries": ("injury", "injuries"),
        "player_stats": ("player_stats", "players", "assists", "saves"),
        "team_stats": ("statistics", "team_stats", "teamstatistics"),
        "standings": ("standings", "table", "ranking"),
        "recent_form": ("form", "recent_results", "last_matches"),
        "win_probability": ("win_probability", "probability", "probabilities"),
        "odds": ("odds", "odds_ukformat", "market"),
    }

    detected = {
        capability
        for capability, tokens in checks.items()
        if any(token in combined for token in tokens)
    }
    return detected


def build_sample_preview(record: dict[str, Any]) -> dict[str, Any]:
    """Build a compact example blob for one captured response."""

    preview: dict[str, Any] = {
        "status": record.get("status"),
        "content_type": record.get("content_type"),
    }

    if record.get("body_json") is not None:
        preview["json_summary"] = summarize_json_value(record["body_json"])
    elif record.get("preview"):
        preview["preview"] = str(record["preview"])[:300]

    return preview


def summarize_json_value(value: object, *, max_list_items: int = 3) -> object:
    """Return a compact human-readable summary of a JSON-ish value."""

    if isinstance(value, dict):
        summary: dict[str, object] = {}
        for key, child in list(value.items())[:10]:
            summary[str(key)] = summarize_json_value(child, max_list_items=max_list_items)
        return summary

    if isinstance(value, list):
        return [
            summarize_json_value(item, max_list_items=max_list_items)
            for item in value[:max_list_items]
        ]

    if isinstance(value, str):
        return value[:120]

    return value


def render_endpoint_report(summary: dict[str, Any], *, capture_dir: str) -> str:
    """Render a Markdown report from a summarized capture."""

    lines = [
        "# Sportradar / Bet365Stats Endpoint Report",
        "",
        f"- Capture dir: `{capture_dir}`",
        f"- Responses captured: {summary.get('records_count', 0)}",
        f"- Logical endpoints: {summary.get('endpoints_count', 0)}",
        "",
        "## Endpoints Detectados",
        "",
        "| Endpoint | Hits | Polling | Tamaño med. | Señales |",
        "| --- | ---: | :---: | ---: | --- |",
    ]

    endpoints = summary.get("endpoints", [])
    for endpoint in endpoints:
        capabilities = ", ".join(endpoint.get("capabilities", {}).keys()) or "-"
        polling = "Sí" if endpoint.get("polling_likely") else "No"
        size_label = _format_bytes(endpoint.get("median_body_size_bytes", 0))
        lines.append(
            f"| `{endpoint.get('endpoint_key')}` | {endpoint.get('count', 0)} | {polling} | {size_label} | {capabilities} |"
        )

    lines.extend(
        [
            "",
            "## Endpoints Útiles para BetBot",
            "",
        ]
    )

    useful_endpoints = [
        endpoint
        for endpoint in endpoints
        if _endpoint_is_useful(endpoint)
    ]
    if useful_endpoints:
        for endpoint in useful_endpoints:
            lines.append(f"### `{endpoint['endpoint_key']}`")
            lines.append(
                f"- Frecuencia: {endpoint['count']} | Polling: {'sí' if endpoint['polling_likely'] else 'no'} ({endpoint['polling_reason']})"
            )
            if endpoint.get("match_ids"):
                lines.append(f"- Match ids vistos: {', '.join(endpoint['match_ids'])}")
            if endpoint.get("main_fields"):
                lines.append(f"- Campos principales: {', '.join(endpoint['main_fields'][:12])}")
            capabilities = ", ".join(endpoint.get("capabilities", {}).keys()) or "-"
            lines.append(f"- Señales detectadas: {capabilities}")
            lines.append(f"- Payload mediano: {_format_bytes(endpoint.get('median_body_size_bytes', 0))}")
            sample_preview = endpoint.get("sample_preview")
            if sample_preview:
                lines.append("- Ejemplo resumido:")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(sample_preview, ensure_ascii=False, indent=2))
                lines.append("```")
            lines.append("")
    else:
        lines.append("No se detectaron endpoints claramente útiles con la captura actual.")
        lines.append("")

    blocked_endpoints = [
        endpoint
        for endpoint in endpoints
        if endpoint.get("blocked")
    ]
    lines.extend(
        [
            "## Restricciones de Acceso",
            "",
        ]
    )
    if blocked_endpoints:
        for endpoint in blocked_endpoints:
            lines.append(f"### `{endpoint['endpoint_key']}`")
            lines.append(
                f"- Status observado(s): {', '.join(str(status) for status in endpoint.get('statuses', {}).keys())}"
            )
            lines.append(
                "- Resultado: la página o feed quedó bloqueado por control de acceso antes de exponer JSON útil."
            )
            sample_preview = endpoint.get("sample_preview")
            if sample_preview:
                lines.append("- Ejemplo resumido:")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(sample_preview, ensure_ascii=False, indent=2))
                lines.append("```")
            lines.append("")
    else:
        lines.append("No se detectaron bloqueos explícitos 401/403 en esta captura.")
        lines.append("")

    lines.extend(
        [
            "## Datos Disponibles",
            "",
            _render_capability_findings(summary),
            "",
            "## Datos que No Aparecieron Claramente",
            "",
            _render_missing_findings(summary),
            "",
            "## Estructura Mínima Recomendada",
            "",
            "```json",
            json.dumps(
                {
                    "bet365_event_id": "string",
                    "sportradar_match_id": "string",
                    "stats_url": "string",
                    "home_team": "string | null",
                    "away_team": "string | null",
                    "start_time_utc": "ISO-8601 | null",
                    "coverage_flags": {
                        "timeline": True,
                        "lineups": False,
                        "standings": False,
                        "player_stats": False,
                        "live_metrics": True,
                    },
                    "available_stats": ["timeline", "score", "cards"],
                    "latest_live_state": {
                        "status": "string | null",
                        "score_home": "number | null",
                        "score_away": "number | null",
                        "period": "string | null",
                        "clock": "string | null",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
            "## Conclusión",
            "",
            _render_recommendation(summary),
            "",
        ]
    )

    return "\n".join(lines)


def unique_preserving_order(values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _normalize_segment(segment: str) -> str:
    if ID_SEGMENT_RE.fullmatch(segment):
        return ":id"
    if DATEISH_SEGMENT_RE.fullmatch(segment):
        return ":id"
    if HEXISH_SEGMENT_RE.fullmatch(segment):
        return ":token"
    return segment


def _endpoint_hint_from_payload(payload: object | None) -> str | None:
    if not isinstance(payload, dict):
        return None

    candidates = [
        payload.get("endpoint"),
        payload.get("path"),
        payload.get("route"),
        payload.get("feed"),
        payload.get("resource"),
        payload.get("type"),
        payload.get("operation"),
        payload.get("name"),
    ]
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        normalized = candidate.strip()
        if not normalized:
            continue
        if "/" in normalized:
            return normalize_endpoint_path(normalized)
        return normalized

    return None


def _extract_first_id(payload: object | None, keys: set[str]) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in keys and isinstance(value, (str, int, float)):
                candidate = str(value).strip()
                if candidate:
                    return candidate
            nested = _extract_first_id(value, keys)
            if nested:
                return nested
    elif isinstance(payload, list):
        for item in payload[:5]:
            nested = _extract_first_id(item, keys)
            if nested:
                return nested
    return None


def _parse_iso_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_bytes(raw_value: float | int) -> str:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return "-"

    if value <= 0:
        return "0 B"
    units = ("B", "KB", "MB")
    unit_index = min(int(math.log(value, 1024)), len(units) - 1)
    scaled = value / (1024 ** unit_index)
    return f"{scaled:.1f} {units[unit_index]}"


def _endpoint_is_useful(endpoint: dict[str, Any]) -> bool:
    capability_keys = set(endpoint.get("capabilities", {}).keys())
    useful = {
        "timeline",
        "live_state",
        "score",
        "cards",
        "corners",
        "shots",
        "shots_on_target",
        "possession",
        "lineups",
        "injuries",
        "standings",
        "win_probability",
        "odds",
    }
    return bool(capability_keys & useful)


def _render_capability_findings(summary: dict[str, Any]) -> str:
    overall = summary.get("overall_capabilities", {})
    if not overall:
        return "No se detectaron señales suficientes en la captura actual."

    ordered = sorted(overall.items(), key=lambda item: (-item[1], item[0]))
    return "\n".join(
        f"- `{capability}`: visto en {count} endpoint(s)"
        for capability, count in ordered
    )


def _render_missing_findings(summary: dict[str, Any]) -> str:
    observed = set(summary.get("overall_capabilities", {}).keys())
    expected = {
        "timeline",
        "live_state",
        "score",
        "current_period",
        "time_played",
        "cards",
        "corners",
        "shots",
        "shots_on_target",
        "possession",
        "attacks",
        "dangerous_attacks",
        "lineups",
        "injuries",
        "player_stats",
        "team_stats",
        "standings",
        "recent_form",
        "win_probability",
        "odds",
    }
    missing = sorted(expected - observed)
    if not missing:
        return "- La captura mostró señales para todas las categorías objetivo."
    return "\n".join(f"- `{item}` no apareció claramente" for item in missing)


def _render_recommendation(summary: dict[str, Any]) -> str:
    observed = set(summary.get("overall_capabilities", {}).keys())
    blocked_endpoints = [
        endpoint for endpoint in summary.get("endpoints", []) if endpoint.get("blocked")
    ]
    has_live = {"timeline", "live_state", "score"} & observed
    has_stats = {"cards", "corners", "shots", "possession", "lineups"} & observed
    has_context = {"standings", "recent_form", "win_probability", "odds"} & observed

    conclusions: list[str] = []
    if blocked_endpoints:
        conclusions.append(
            "- Hallazgo principal: desde Playwright puro, la stats URL respondió `403 Access Denied`, incluso probando bootstrap previo desde Bet365. Eso sugiere una protección adicional de Akamai / first-party session."
        )

    if has_live:
        conclusions.append(
            "- Sí conviene integrar una segunda etapa de research enfocada en señales live: hay material suficiente para detectar estado de partido, score o timeline."
        )
    else:
        conclusions.append(
            "- La captura actual no mostró suficientes señales live para justificar una integración inmediata desde este entorno aislado."
        )

    if has_stats:
        conclusions.append(
            "- También parece prometedor para enriquecer alertas pre-match o live con métricas de partido."
        )
    else:
        conclusions.append(
            "- Las métricas avanzadas de partido todavía no quedaron confirmadas con esta muestra."
        )

    if has_context:
        conclusions.append(
            "- Hay indicios de endpoints útiles para un futuro agente de análisis o filtros de partidos interesantes."
        )
    else:
        conclusions.append(
            "- Standings, forma reciente o probabilidades no quedaron suficientemente expuestos en esta captura."
        )

    conclusions.append(
        "- Recomendación práctica: mantener esta investigación aislada y, si se quiere profundizar, probar una captura desde una sesión real de navegador con contexto/cookies del usuario antes de integrar `bet365_event_id -> sportradar_match_id -> latest_live_state`."
    )
    return "\n".join(conclusions)


FILTERED_REPORT_SECTIONS = {
    "Metadata del partido": {
        "match_info_statshub",
        "stats_match_get",
        "match_details",
    },
    "Score y estado live": {
        "match_timeline",
        "match_timelinedelta",
        "event_get",
        "stats_match_get",
    },
    "Timeline y eventos live": {
        "match_timeline",
        "match_timelinedelta",
        "event_get",
    },
    "Stats pre-match y contexto": {
        "stats_match_head2head",
        "stats_h2h_versus",
        "stats_team_lastx",
        "stats_team_nextx",
        "stats_team_versus",
        "stats_team_streaks",
        "stats_match_tableslice",
        "stats_season_teamscoringconceding",
    },
    "Forma reciente": {
        "stats_formtable",
        "stats_team_lastx",
        "stats_team_nextx",
        "stats_team_streaks",
        "stats_team_versus",
    },
    "Tabla y standings": {
        "stats_season_tables",
        "stats_match_tableslice",
        "stats_formtable",
    },
    "Jugadores y leaders": {
        "stats_season_topgoals",
        "stats_season_topcards",
        "stats_season_topassists",
    },
    "Lesiones": {
        "stats_season_injuries",
    },
    "Mercados y odds": {
        "match_markets",
        "uniqueteam_markets",
        "odds_ukformat",
    },
}

FILTERED_LOW_PRIORITY_ENDPOINTS = {"odds_ukformat"}


def categorize_filtered_endpoint(endpoint_key: str) -> list[str]:
    categories = [
        label
        for label, endpoints in FILTERED_REPORT_SECTIONS.items()
        if endpoint_key in endpoints
    ]
    if not categories:
        categories.append("Otros")
    return categories


def render_filtered_capture_report(
    index_payload: dict[str, Any],
    endpoint_samples: dict[str, dict[str, Any]],
    *,
    capture_dir: str,
    source_name: str,
) -> str:
    endpoints = index_payload.get("endpoints", {})
    filtered_records_count = index_payload.get("filtered_records_count", 0)
    endpoint_count = index_payload.get("endpoint_count", 0)

    lines = [
        "# Sportradar Stats Filtered Endpoint Report",
        "",
        f"- Capture dir: `{capture_dir}`",
        f"- Source usado: `{source_name}`",
        f"- Responses útiles filtradas: {filtered_records_count}",
        f"- Endpoints limpios detectados: {endpoint_count}",
        "",
        "## Resumen Ejecutivo",
        "",
    ]
    lines.extend(_render_filtered_highlights(endpoints, endpoint_samples))
    lines.extend(
        [
            "",
            "## Endpoints Detectados",
            "",
            "| Endpoint | Hits | Polling | Tamaño aprox. | Categorías |",
            "| --- | ---: | :---: | ---: | --- |",
        ]
    )

    for endpoint_key, endpoint_summary in sorted(
        endpoints.items(),
        key=lambda item: (-int(item[1].get("count", 0)), item[0]),
    ):
        categories = ", ".join(categorize_filtered_endpoint(endpoint_key))
        polling = "Sí" if endpoint_summary.get("polling_likely") else "No"
        lines.append(
            f"| `{endpoint_key}` | {endpoint_summary.get('count', 0)} | {polling} | "
            f"{_format_bytes(endpoint_summary.get('body_size_avg_bytes', 0))} | {categories} |"
        )

    lines.extend(
        [
            "",
            "## Endpoints por Caso de Uso",
            "",
        ]
    )

    for section_name, section_endpoints in FILTERED_REPORT_SECTIONS.items():
        section_keys = [
            endpoint_key
            for endpoint_key in endpoints
            if endpoint_key in section_endpoints
        ]
        if not section_keys:
            continue

        lines.append(f"### {section_name}")
        lines.append("")
        for endpoint_key in sorted(section_keys):
            endpoint_summary = endpoints[endpoint_key]
            sample_record = endpoint_samples.get(endpoint_key, {})
            lines.extend(
                _render_one_filtered_endpoint(
                    endpoint_key,
                    endpoint_summary,
                    sample_record,
                )
            )

    low_priority = [
        endpoint_key
        for endpoint_key in sorted(endpoints)
        if endpoint_key in FILTERED_LOW_PRIORITY_ENDPOINTS
    ]
    if low_priority:
        lines.extend(
            [
                "## Endpoints de Baja Prioridad",
                "",
            ]
        )
        for endpoint_key in low_priority:
            lines.append(
                f"- `{endpoint_key}` aparece en la captura, pero por ahora parece más un helper o tabla auxiliar que un feed principal para BetBot."
            )
        lines.append("")

    lines.extend(
        [
            "## Datos Útiles Detectados",
            "",
            _render_filtered_detected_data(endpoints),
            "",
            "## Datos que No Aparecieron Claramente",
            "",
            _render_filtered_missing_data(endpoints),
            "",
            "## Recomendación para BetBot",
            "",
            _render_filtered_recommendation(endpoints, endpoint_samples),
            "",
        ]
    )

    return "\n".join(lines)


def _render_filtered_highlights(
    endpoints: dict[str, Any],
    endpoint_samples: dict[str, dict[str, Any]],
) -> list[str]:
    highlights: list[str] = []

    if "match_markets" in endpoints:
        markets_count = _extract_list_length(
            endpoint_samples.get("match_markets"),
            "markets",
        )
        if markets_count is not None:
            highlights.append(
                f"- `match_markets` expone mercados/odds por HTTP. En esta captura devolvió {markets_count} markets, incluyendo 1X2 y handicaps."
            )
        else:
            highlights.append(
                "- `match_markets` expone mercados/odds por HTTP y es uno de los endpoints con más potencial para integración futura."
            )

    if "match_timeline" in endpoints or "match_timelinedelta" in endpoints:
        highlights.append(
            "- `match_timeline` / `match_timelinedelta` son los candidatos más fuertes para detectar `live`, score, estado y timeline. Ambos usan `_maxage` corto."
        )

    if "event_get" in endpoints:
        primary_match_ids = _primary_match_ids(endpoints)
        event_match_ids = endpoints["event_get"].get("match_ids", [])
        if primary_match_ids and event_match_ids and not set(event_match_ids).intersection(primary_match_ids):
            highlights.append(
                f"- `event_get` parece un feed live global y no necesariamente del partido abierto: en esta captura apunta a match id(s) {', '.join(event_match_ids[:5])}, mientras el match principal fue {', '.join(primary_match_ids[:5])}."
            )
        else:
            highlights.append(
                "- `event_get` parece un feed live muy útil; hay que confirmar en más muestras si es del match abierto o un ticker global."
            )

    if {"stats_formtable", "stats_season_tables", "stats_team_lastx"} & set(endpoints):
        highlights.append(
            "- Hay buen contexto pre-match por HTTP: forma reciente, tabla, streaks, head-to-head y slices de standings."
        )

    if {"stats_season_injuries", "stats_season_topgoals", "stats_season_topcards", "stats_season_topassists"} & set(endpoints):
        highlights.append(
            "- También aparecen endpoints útiles para enriquecer análisis: lesiones y leaders de goles, tarjetas y asistencias."
        )

    if not highlights:
        highlights.append("- No se detectaron hallazgos fuertes con la captura actual.")

    return highlights


def _render_one_filtered_endpoint(
    endpoint_key: str,
    endpoint_summary: dict[str, Any],
    sample_record: dict[str, Any],
) -> list[str]:
    lines = [f"#### `{endpoint_key}`"]
    status_label = ", ".join(
        f"{status}:{count}"
        for status, count in sorted(endpoint_summary.get("statuses", {}).items())
    ) or "-"
    lines.append(
        f"- Hits: {endpoint_summary.get('count', 0)} | Status: {status_label} | "
        f"Polling: {'sí' if endpoint_summary.get('polling_likely') else 'no'} ({endpoint_summary.get('polling_reason')})"
    )
    lines.append(
        f"- Tamaño aprox.: min {_format_bytes(endpoint_summary.get('body_size_min_bytes', 0))} | "
        f"max {_format_bytes(endpoint_summary.get('body_size_max_bytes', 0))} | "
        f"avg {_format_bytes(endpoint_summary.get('body_size_avg_bytes', 0))}"
    )
    if endpoint_summary.get("query_urls"):
        lines.append(f"- queryUrl: {', '.join(endpoint_summary['query_urls'][:3])}")
    if endpoint_summary.get("match_ids"):
        lines.append(f"- Match ids detectados: {', '.join(endpoint_summary['match_ids'][:10])}")
    if endpoint_summary.get("top_level_keys"):
        lines.append(f"- Campos principales: {', '.join(endpoint_summary['top_level_keys'][:12])}")
    lines.append(f"- Qué aporta: {_filtered_endpoint_blurb(endpoint_key)}")

    example_payload = _extract_report_sample_payload(sample_record)
    if example_payload is not None:
        lines.append("- Estructura resumida:")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(summarize_json_value(example_payload), ensure_ascii=False, indent=2))
        lines.append("```")

    lines.append("")
    return lines


def _extract_report_sample_payload(sample_record: dict[str, Any]) -> object | None:
    body_json = sample_record.get("body_json")
    if not isinstance(body_json, dict):
        return None

    doc_entries = body_json.get("doc")
    if isinstance(doc_entries, list) and doc_entries and isinstance(doc_entries[0], dict):
        data = doc_entries[0].get("data")
        if data is not None:
            return data

    return body_json


def _filtered_endpoint_blurb(endpoint_key: str) -> str:
    blurbs = {
        "match_info_statshub": "Metadata fuerte del partido: torneo, estadio, ciudades, coverage y contexto del evento.",
        "stats_match_get": "Snapshot del match con ids, hora, equipos, resultado y señales de live/inlivescore.",
        "match_details": "Detalle auxiliar del match; en esta muestra vino vacío.",
        "match_timeline": "Estado del partido y timeline principal. Es el candidato más claro para live state del fixture abierto.",
        "match_timelinedelta": "Delta del timeline, ideal para polling liviano cuando el partido está en vivo.",
        "event_get": "Feed de eventos live que parece más global; hay que validar alcance exacto en más capturas.",
        "stats_match_head2head": "Head-to-head compacto entre los equipos.",
        "stats_h2h_versus": "Historial comparativo y versus stats entre ambos equipos.",
        "stats_team_lastx": "Últimos partidos de un equipo, útil para forma reciente.",
        "stats_team_nextx": "Próximos partidos del equipo, útil para congestión de calendario.",
        "stats_team_versus": "Cruces entre equipos con contexto extra.",
        "stats_team_streaks": "Rachas y forma condensada del equipo.",
        "stats_match_tableslice": "Slice de tabla alrededor del partido, útil para contexto competitivo.",
        "stats_formtable": "Tabla de forma reciente, muy útil para filtros pre-match.",
        "stats_season_tables": "Tabla/standings completa de la temporada.",
        "stats_season_teamscoringconceding": "Distribución de goles anotados/recibidos por equipo y temporada.",
        "stats_season_topgoals": "Top scorers de la temporada.",
        "stats_season_topcards": "Leaders de tarjetas.",
        "stats_season_topassists": "Leaders de asistencias.",
        "stats_season_injuries": "Listado de lesionados / ausentes por equipo y jugador.",
        "match_markets": "Mercados y odds del partido por HTTP; hoy es el hallazgo más fuerte del lado odds.",
        "uniqueteam_markets": "Mercados por equipo sobre matches relacionados, útil para análisis complementario.",
        "odds_ukformat": "Tabla auxiliar de formatos de cuotas; parece soporte más que feed principal.",
    }
    return blurbs.get(endpoint_key, "Endpoint útil a investigar con más muestras.")


def _render_filtered_detected_data(endpoints: dict[str, Any]) -> str:
    bullets: list[str] = []
    available = set(endpoints)

    if {"match_info_statshub", "stats_match_get"} & available:
        bullets.append("- Metadata del partido: sí.")
    if {"match_timeline", "match_timelinedelta", "event_get"} & available:
        bullets.append("- Señales live / status / timeline: sí.")
    if "match_markets" in available:
        bullets.append("- Odds / mercados por HTTP: sí, con `match_markets`.")
    if {"stats_season_tables", "stats_formtable", "stats_match_tableslice"} & available:
        bullets.append("- Tabla / standings / forma: sí.")
    if {"stats_season_topgoals", "stats_season_topcards", "stats_season_topassists"} & available:
        bullets.append("- Leaders de jugadores: sí.")
    if "stats_season_injuries" in available:
        bullets.append("- Lesiones: sí.")

    if not bullets:
        return "No aparecieron bloques de datos útiles en esta captura."
    return "\n".join(bullets)


def _render_filtered_missing_data(endpoints: dict[str, Any]) -> str:
    available = set(endpoints)
    missing: list[str] = []

    if not {"match_timeline", "match_timelinedelta"} & available:
        missing.append("- No apareció un timeline de partido claro.")
    if "match_markets" not in available:
        missing.append("- No apareció un endpoint de mercados del partido.")
    if "stats_season_injuries" not in available:
        missing.append("- No apareció un endpoint de lesiones.")
    if not {"stats_season_tables", "stats_formtable"} & available:
        missing.append("- No apareció tabla / forma reciente.")

    missing.extend(
        [
            "- No apareció un endpoint dedicado de lineups detalladas en esta muestra.",
            "- No apareció win probability explícita.",
            "- Corners, shots, possession y cards live no quedaron confirmados en el match abierto; probablemente haga falta una captura con el partido realmente en vivo.",
        ]
    )

    return "\n".join(missing)


def _render_filtered_recommendation(
    endpoints: dict[str, Any],
    endpoint_samples: dict[str, dict[str, Any]],
) -> str:
    recommendations: list[str] = []
    available = set(endpoints)

    if "match_markets" in available:
        recommendations.append(
            "- Sí conviene seguir por este camino: `match_markets` ya demuestra que hay odds/markets útiles por HTTP sin scraping DOM."
        )

    if {"match_timeline", "match_timelinedelta"} & available:
        recommendations.append(
            "- Para un futuro tracker `in live`, los mejores candidatos son `match_timeline` y `match_timelinedelta`, idealmente validados en un partido efectivamente en juego."
        )

    if "event_get" in available:
        primary_match_ids = _primary_match_ids(endpoints)
        event_match_ids = endpoints["event_get"].get("match_ids", [])
        if primary_match_ids and event_match_ids and not set(event_match_ids).intersection(primary_match_ids):
            recommendations.append(
                "- `event_get` merece investigación aparte: podría ser un feed live global complementario, pero no conviene integrarlo sin validar su scope."
            )

    if {"stats_formtable", "stats_season_tables", "stats_season_injuries"} & available:
        recommendations.append(
            "- Los endpoints de contexto (tabla, forma, lesiones, leaders) son buenos candidatos para enriquecer un futuro agente de análisis o filtros de partidos interesantes."
        )

    recommendations.append(
        "- Próximo paso recomendado: repetir el mismo pipeline con una captura de partido en vivo para confirmar score, clock, timeline real, cards/corners/shots y estabilidad de polling."
    )

    return "\n".join(recommendations)


def _extract_list_length(sample_record: dict[str, Any], field_name: str) -> int | None:
    payload = _extract_report_sample_payload(sample_record)
    if not isinstance(payload, dict):
        return None
    field_value = payload.get(field_name)
    if isinstance(field_value, list):
        return len(field_value)
    return None


def _primary_match_ids(endpoints: dict[str, Any]) -> list[str]:
    match_ids: list[str] = []
    for endpoint_key in (
        "stats_match_get",
        "match_timeline",
        "match_timelinedelta",
        "match_markets",
        "match_info_statshub",
    ):
        endpoint_summary = endpoints.get(endpoint_key)
        if not isinstance(endpoint_summary, dict):
            continue
        match_ids.extend(endpoint_summary.get("match_ids", []))
    return unique_preserving_order(match_ids)


__all__ = [
    "build_endpoint_key",
    "categorize_filtered_endpoint",
    "classify_record",
    "decode_embedded_data_from_url",
    "decode_maybe_base64_json",
    "detect_capabilities",
    "extract_sportradar_match_id",
    "infer_polling_behavior",
    "normalize_endpoint_path",
    "render_endpoint_report",
    "render_filtered_capture_report",
    "summarize_capture_records",
    "summarize_endpoint_records",
    "summarize_json_fields",
]
