from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def render_endpoint_catalog(catalog: dict[str, Any]) -> str:
    lines = [
        "# Statshub/Sportradar Endpoint Catalog",
        "",
        f"- Records: `{catalog.get('records_count', 0)}`",
        f"- Endpoints: `{catalog.get('endpoint_count', 0)}`",
        "",
        "## Classification Coverage",
        "",
    ]
    classifications = catalog.get("classification_counts") or {}
    if classifications:
        for label, count in classifications.items():
            lines.append(f"- `{label}`: {count}")
    else:
        lines.append("- No classifications detected.")

    lines.extend(["", "## Endpoints", ""])
    for endpoint_key, endpoint in (catalog.get("endpoints") or {}).items():
        classifications_text = ", ".join(
            f"{label}={count}" for label, count in (endpoint.get("classifications") or {}).items()
        ) or "-"
        lines.extend(
            [
                f"### `{endpoint_key}`",
                "",
                f"- Count: `{endpoint.get('count')}`",
                f"- Statuses: `{endpoint.get('statuses')}`",
                f"- Classification: `{classifications_text}`",
                f"- Signed token: `{endpoint.get('has_signed_token')}`",
                f"- Query URLs: `{endpoint.get('query_urls')}`",
                f"- Normalized paths: `{endpoint.get('normalized_paths')}`",
                f"- Top-level keys: `{endpoint.get('top_level_keys')}`",
                f"- Example URL: `{endpoint.get('example_url')}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def render_http_replay_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Statshub HTTP Replay Report",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Source: `{payload.get('source')}`",
        f"- Targets: `{payload.get('target_count', 0)}`",
        "",
        "## Outcome Summary",
        "",
    ]
    for outcome, count in (payload.get("outcome_counts") or {}).items():
        lines.append(f"- `{outcome}`: {count}")
    if not payload.get("outcome_counts"):
        lines.append("- No attempts.")

    lines.extend(["", "## Targets", ""])
    for target in payload.get("targets") or []:
        lines.extend(
            [
                f"### `{target.get('endpoint_key')}`",
                "",
                f"- URL: `{target.get('url')}`",
                f"- Conclusion: `{target.get('conclusion')}`",
                "",
            ]
        )
        for attempt in target.get("attempts") or []:
            lines.append(
                "- `{label}` status={status} outcome={outcome} json={is_json} bytes={bytes}".format(
                    label=attempt.get("label"),
                    status=attempt.get("status"),
                    outcome=attempt.get("outcome"),
                    is_json=attempt.get("is_json"),
                    bytes=attempt.get("body_size_bytes"),
                )
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def render_token_analysis(payload: dict[str, Any]) -> str:
    lines = [
        "# Statshub Signed Token Analysis",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Source: `{payload.get('source')}`",
        f"- Signed URLs: `{payload.get('signed_url_count', 0)}`",
        "",
        "## Token Payloads",
        "",
    ]
    for item in payload.get("token_payloads") or []:
        lines.extend(
            [
                f"### exp `{item.get('exp')}`",
                "",
                f"- Expires UTC: `{item.get('expires_at_utc')}`",
                f"- ACL: `{item.get('acl')}`",
                f"- Data: `{item.get('data_json')}`",
                f"- Endpoints: `{item.get('endpoints')}`",
                "",
            ]
        )
    if not payload.get("token_payloads"):
        lines.append("- No signed tokens found.")

    lines.extend(["", "## Replay Mutations", ""])
    for result in payload.get("mutation_results") or []:
        lines.append(
            "- `{endpoint}` -> `{mutated_endpoint}` status={status} outcome={outcome}".format(
                endpoint=result.get("endpoint_key"),
                mutated_endpoint=result.get("mutated_endpoint"),
                status=result.get("status"),
                outcome=result.get("outcome"),
            )
        )
    return "\n".join(lines) + "\n"


def render_api_feasibility(
    *,
    catalog: dict[str, Any],
    replay_payload: dict[str, Any] | None,
    token_payload: dict[str, Any] | None,
) -> str:
    endpoints = catalog.get("endpoints") or {}
    signed = [key for key, endpoint in endpoints.items() if endpoint.get("has_signed_token")]
    direct_docs = [
        key
        for key, endpoint in endpoints.items()
        if not endpoint.get("has_signed_token") and "document" in (endpoint.get("resource_types") or {})
    ]
    replay_counts = (replay_payload or {}).get("outcome_counts") or {}
    reusable = int(replay_counts.get("reusable", 0) or 0)
    blocked = int(replay_counts.get("blocked", 0) or 0)
    expired = int(replay_counts.get("signature_expired", 0) or 0)
    replay_targets = (replay_payload or {}).get("targets") or []
    reusable_endpoints = [
        str(target.get("endpoint_key") or "")
        for target in replay_targets
        if str(target.get("conclusion") or "").lower() == "http reusable"
    ]
    no_header_blocked = 0
    referer_reusable = 0
    captured_reusable = 0
    for target in replay_targets:
        for attempt in target.get("attempts") or []:
            label = str(attempt.get("label") or "")
            outcome = str(attempt.get("outcome") or "")
            if label in {"no_headers", "user_agent"} and outcome == "blocked":
                no_header_blocked += 1
            if label == "referer_origin" and outcome == "reusable":
                referer_reusable += 1
            if label.startswith("captured_headers") and outcome == "reusable":
                captured_reusable += 1

    token_items = (token_payload or {}).get("token_payloads") or []
    token_summaries: list[str] = []
    for item in token_items[:5]:
        token_summaries.append(
            "exp={exp} expires={expires} acl={acl} data={data}".format(
                exp=item.get("exp"),
                expires=item.get("expires_at_utc"),
                acl=item.get("acl"),
                data=item.get("data_json"),
            )
        )

    recommendation = "B) browser bootstrap + HTTP replay"
    if reusable == 0 and (blocked or expired):
        recommendation = "C) Playwright response capture"
    elif signed and reusable:
        recommendation = "B) browser bootstrap + HTTP replay"

    lines = [
        "# Statshub/Sportradar API Feasibility",
        "",
        "## Evidence Summary",
        "",
        f"- Catalog endpoints: `{len(endpoints)}`",
        f"- Signed gismo endpoints: `{len(signed)}`",
        f"- Direct document endpoints observed: `{direct_docs}`",
        f"- Replay reusable attempts: `{reusable}`",
        f"- Replay blocked attempts: `{blocked}`",
        f"- Replay expired attempts: `{expired}`",
        f"- Reusable endpoints sampled: `{reusable_endpoints[:25]}`",
        f"- Attempts blocked without origin/referer: `{no_header_blocked}`",
        f"- Attempts reusable with minimal origin/referer: `{referer_reusable}`",
        f"- Attempts reusable with captured headers: `{captured_reusable}`",
        f"- Token samples: `{token_summaries}`",
        "",
        "## HTTP Replay Findings",
        "",
        "- Direct document URLs are useful as browser bootstrap pages, not as the main data API.",
        "- Useful data lives behind `/gismo/<endpoint>/...` URLs signed with `T=exp~acl~data~hmac`.",
        "- The captured token data points to an origin check for `https://statshub.sportradar.com` and app `bet365`.",
        "- Replays without `origin`/`referer` returned a small JSON exception body while still using HTTP 200.",
        "- Replays with `origin: https://statshub.sportradar.com` and `referer: https://statshub.sportradar.com/` returned full JSON payloads.",
        "- Token mutation tests show the same broad `acl=/*` token can be reused across at least some sibling endpoints while it is valid.",
        "- A headless browser run can get 403 on the document pages; headed capture produced the full gismo graph in this environment.",
        "",
        "## Options",
        "",
        "### A) HTTP puro",
        "",
        "- Lowest runtime cost if tokens can be generated offline.",
        "- Current evidence: gismo data URLs are signed with `T=exp~acl~data~hmac`; no local signer was found in captured payloads.",
        "- Risk: high unless a stable signing endpoint is discovered.",
        "",
        "### B) Browser bootstrap + HTTP replay",
        "",
        "- Use a headed/headless browser briefly to obtain signed gismo URLs/token and cookies, then replay with `httpx` while valid.",
        "- Runtime cost: medium at startup, low after bootstrap.",
        "- Stability: medium; depends on token TTL and Akamai/header behavior.",
        "",
        "### C) Playwright response capture",
        "",
        "- Keep the current model: let the browser produce signed requests and capture responses.",
        "- Runtime cost: highest, but most robust against signing changes.",
        "- Stability: currently best known fallback.",
        "",
        "## Recommendation",
        "",
        f"- Recommended path for BetBot research: `{recommendation}`.",
        "- Keep Playwright response-capture as fallback until token replay proves stable across sessions and expiration windows.",
        "- Do not integrate into production until replay has been validated on sport, tournament, fixtures, and match pages across multiple runs.",
    ]
    return "\n".join(lines) + "\n"


def summarize_outcomes(targets: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for target in targets:
        for attempt in target.get("attempts") or []:
            counter[str(attempt.get("outcome") or "unknown")] += 1
    return dict(counter.most_common())


def summarize_tokens(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for record in records:
        token = record.get("signed_token")
        if not isinstance(token, dict):
            continue
        raw = str(token.get("raw") or "")
        if not raw:
            continue
        bucket = buckets.setdefault(
            raw,
            {
                "exp": token.get("exp"),
                "expires_at_utc": token.get("expires_at_utc"),
                "acl": token.get("acl"),
                "data_json": token.get("data_json"),
                "endpoints": [],
            },
        )
        endpoint = str(record.get("endpoint_key") or "")
        if endpoint and endpoint not in bucket["endpoints"]:
            bucket["endpoints"].append(endpoint)
    return list(buckets.values())
