from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

try:
    from curl_cffi import requests as curl_cffi_requests
except ImportError:  # pragma: no cover
    curl_cffi_requests = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.capture_useful import detect_useful_endpoint_name, is_signed_url
from sandbox.sportradar_stats.filtering import extract_query_url, iter_ndjson_records


DEFAULT_HEADERS = {
    "accept": "application/json,text/plain,*/*",
    "origin": "https://statshub.sportradar.com",
    "referer": "https://statshub.sportradar.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
}
MAX_PREVIEW_LENGTH = 400


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe whether useful signed Sportradar endpoints can be replayed without a browser.",
    )
    parser.add_argument(
        "capture_dir",
        type=Path,
        help="Directory containing useful_fetch.ndjson or useful_fetch.json.",
    )
    parser.add_argument(
        "--storage-state",
        type=Path,
        help="Optional Playwright storage_state JSON file with cookies.",
    )
    parser.add_argument(
        "--cookies-json",
        type=Path,
        help="Optional cookies.json exported from a Playwright capture.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds for each replay attempt.",
    )
    return parser.parse_args()


def load_useful_records(capture_dir: Path) -> tuple[list[dict[str, Any]], Path]:
    ndjson_path = capture_dir / "useful_fetch.ndjson"
    json_path = capture_dir / "useful_fetch.json"

    if ndjson_path.exists():
        return list(iter_ndjson_records(ndjson_path)), ndjson_path

    if json_path.exists():
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [record for record in payload if isinstance(record, dict)], json_path

    raise FileNotFoundError(f"No existe {ndjson_path} ni {json_path}")


def select_probe_targets(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_urls: set[str] = set()
    selected: list[dict[str, Any]] = []

    for record in records:
        url = str(record.get("url") or "").strip()
        endpoint_name = str(
            record.get("endpoint_name")
            or record.get("endpoint_key")
            or detect_useful_endpoint_name(url, record.get("body_json"))
            or ""
        ).strip()
        if not url or not endpoint_name or not is_signed_url(url):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        selected.append(
            {
                "url": url,
                "endpoint_name": endpoint_name,
                "method": str(record.get("method") or "GET").upper(),
                "request_headers": record.get("request_headers") or {},
                "response_headers": record.get("response_headers") or {},
                "match_id": record.get("match_id"),
                "signed_url": True,
            }
        )

    return selected


def load_cookie_items(
    *,
    storage_state_path: Path | None,
    cookies_json_path: Path | None,
) -> tuple[list[dict[str, Any]], str | None]:
    if storage_state_path is not None:
        payload = json.loads(storage_state_path.read_text(encoding="utf-8"))
        cookies = payload.get("cookies") if isinstance(payload, dict) else None
        if isinstance(cookies, list):
            return [cookie for cookie in cookies if isinstance(cookie, dict)], str(storage_state_path)

    if cookies_json_path is not None:
        payload = json.loads(cookies_json_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [cookie for cookie in payload if isinstance(cookie, dict)], str(cookies_json_path)

    return [], None


def cookies_to_name_value_map(cookie_items: list[dict[str, Any]]) -> dict[str, str]:
    cookie_map: dict[str, str] = {}
    for cookie in cookie_items:
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "").strip()
        if not name:
            continue
        cookie_map[name] = value
    return cookie_map


def build_probe_headers(target: dict[str, Any]) -> dict[str, str]:
    headers = dict(DEFAULT_HEADERS)
    request_headers = target.get("request_headers")
    if isinstance(request_headers, dict):
        for key in ("accept-language", "user-agent"):
            raw_value = request_headers.get(key) or request_headers.get(key.title())
            if isinstance(raw_value, str) and raw_value.strip():
                headers[key] = raw_value.strip()
    return headers


def safe_json_parse(raw_text: str) -> object | None:
    normalized = raw_text.strip()
    if not normalized:
        return None
    if not (normalized.startswith("{") or normalized.startswith("[")):
        return None
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        return None


def extract_json_exception_info(body_json: object | None) -> dict[str, Any] | None:
    if not isinstance(body_json, dict):
        return None

    doc_entries = body_json.get("doc")
    if not isinstance(doc_entries, list) or not doc_entries:
        return None
    first_entry = doc_entries[0]
    if not isinstance(first_entry, dict):
        return None

    event_name = str(first_entry.get("event") or "").strip().lower()
    data = first_entry.get("data")
    if event_name != "exception" and not (
        isinstance(data, dict) and str(data.get("_doc") or "").strip().lower() == "exception"
    ):
        return None

    if not isinstance(data, dict):
        data = {}
    return {
        "event": event_name or "exception",
        "name": data.get("name"),
        "code": data.get("code"),
        "message": data.get("message"),
    }


def detect_response_endpoint_name(
    *,
    final_url: str,
    body_json: object | None,
) -> str | None:
    if extract_json_exception_info(body_json) is not None:
        return None
    query_url = extract_query_url(body_json)
    if query_url:
        endpoint_name = detect_useful_endpoint_name(query_url, body_json)
        if endpoint_name:
            return endpoint_name
    return detect_useful_endpoint_name(final_url, body_json)


def classify_probe_attempt(attempt: dict[str, Any], *, expected_endpoint_name: str) -> str:
    json_exception = attempt.get("json_exception")
    if isinstance(json_exception, dict):
        exception_name = str(json_exception.get("name") or "").lower()
        exception_message = str(json_exception.get("message") or "").lower()
        exception_code = json_exception.get("code")
        if "expired" in exception_message or "signature" in exception_message:
            return "signature_expired"
        if exception_name == "unauthorized" or exception_code in {401, 403}:
            return "blocked"
        return "json_exception"

    status = attempt.get("status")
    if isinstance(status, int) and status in {401, 403}:
        preview = str(attempt.get("preview") or "").lower()
        if "expired" in preview or "signature" in preview:
            return "signature_expired"
        return "blocked"
    if isinstance(status, int) and status >= 400:
        return "http_error"
    if attempt.get("exception"):
        return "request_failed"
    if attempt.get("body_size_bytes") == 0:
        return "empty_body"
    if not attempt.get("is_json"):
        preview = str(attempt.get("preview") or "").lower()
        if "access denied" in preview or "forbidden" in preview:
            return "blocked"
        return "non_json"
    if attempt.get("same_endpoint"):
        return "reusable"
    return "endpoint_mismatch"


def summarize_target_conclusion(attempts: list[dict[str, Any]]) -> str:
    outcomes = Counter(str(attempt.get("outcome") or "") for attempt in attempts)
    labels = {str(attempt.get("attempt_label") or "") for attempt in attempts}
    reusable = outcomes.get("reusable", 0) > 0
    blocked = outcomes.get("blocked", 0) > 0
    expired = outcomes.get("signature_expired", 0) > 0
    with_cookies_reusable = any(
        attempt.get("outcome") == "reusable" and "cookies" in str(attempt.get("attempt_label") or "")
        for attempt in attempts
    )
    anonymous_reusable = any(
        attempt.get("outcome") == "reusable" and "cookies" not in str(attempt.get("attempt_label") or "")
        for attempt in attempts
    )

    if reusable and anonymous_reusable:
        return "HTTP reusable"
    if reusable and with_cookies_reusable:
        return "HTTP requires cookies"
    if expired:
        return "signature expired"
    if blocked and any("cookies" in label for label in labels):
        return "HTTP blocked"
    if blocked:
        return "HTTP requires cookies"
    if outcomes.get("non_json", 0) > 0:
        return "HTTP returned non-JSON"
    if outcomes.get("empty_body", 0) > 0:
        return "HTTP empty body"
    return "HTTP inconclusive"


def summarize_probe_results(target_results: list[dict[str, Any]]) -> dict[str, Any]:
    endpoints: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for target in target_results:
        endpoints[str(target.get("endpoint_name") or "unknown")].append(target)

    endpoint_summaries: dict[str, Any] = {}
    global_conclusions: Counter[str] = Counter()

    for endpoint_name, endpoint_targets in sorted(endpoints.items()):
        endpoint_attempts = [attempt for target in endpoint_targets for attempt in target.get("attempts", [])]
        statuses = sorted(
            {
                int(status)
                for status in (attempt.get("status") for attempt in endpoint_attempts)
                if isinstance(status, int)
            }
        )
        summary = {
            "count": len(endpoint_targets),
            "statuses": statuses,
            "example_url": endpoint_targets[0].get("url"),
            "conclusion": summarize_target_conclusion(endpoint_attempts),
            "targets": endpoint_targets,
        }
        endpoint_summaries[endpoint_name] = summary
        global_conclusions[summary["conclusion"]] += 1

    return {
        "endpoint_count": len(endpoint_summaries),
        "target_count": len(target_results),
        "endpoint_summaries": endpoint_summaries,
        "global_conclusions": dict(sorted(global_conclusions.items())),
    }


def render_probe_report(results: dict[str, Any]) -> str:
    lines = [
        "# HTTP Probe Report",
        "",
        f"- Generado: `{results.get('generated_at')}`",
        f"- Source usado: `{results.get('source_file')}`",
        f"- Targets probados: `{results.get('target_count')}`",
        f"- Endpoints: `{results.get('endpoint_count')}`",
        f"- Cookie source: `{results.get('cookie_source') or 'none'}`",
        "",
        "## Conclusión global",
        "",
    ]

    for conclusion, count in sorted((results.get("global_conclusions") or {}).items()):
        lines.append(f"- `{conclusion}`: {count}")

    lines.extend(["", "## Endpoints", ""])
    endpoint_summaries = results.get("endpoint_summaries") or {}
    for endpoint_name, summary in sorted(endpoint_summaries.items()):
        lines.append(f"### `{endpoint_name}`")
        lines.append("")
        lines.append(f"- Conclusión: `{summary.get('conclusion')}`")
        lines.append(f"- Count: `{summary.get('count')}`")
        lines.append(f"- Statuses vistos: `{summary.get('statuses')}`")
        lines.append(f"- Example URL: `{summary.get('example_url')}`")
        lines.append("")
        for target in summary.get("targets", [])[:5]:
            lines.append(f"- URL: `{target.get('url')}`")
            lines.append(f"  Endpoint esperado: `{target.get('endpoint_name')}`")
            lines.append(f"  Conclusión target: `{target.get('conclusion')}`")
            for attempt in target.get("attempts", [])[:5]:
                json_exception = attempt.get("json_exception") if isinstance(attempt.get("json_exception"), dict) else None
                exception_suffix = ""
                if json_exception:
                    exception_suffix = (
                        f" json_exception={json_exception.get('name')}"
                        f" code={json_exception.get('code')}"
                    )
                lines.append(
                    "  "
                    + f"- `{attempt.get('attempt_label')}` status={attempt.get('status')} "
                    + f"json={attempt.get('is_json')} same_endpoint={attempt.get('same_endpoint')} "
                    + f"outcome=`{attempt.get('outcome')}` size={attempt.get('body_size_bytes')}"
                    + exception_suffix
                )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run_httpx_probe(
    *,
    url: str,
    headers: dict[str, str],
    cookies: dict[str, str] | None,
    timeout_seconds: float,
    attempt_label: str,
    expected_endpoint_name: str,
) -> dict[str, Any]:
    if httpx is None:
        return {
            "attempt_label": attempt_label,
            "status": None,
            "exception": "httpx is not installed",
            "is_json": False,
            "same_endpoint": False,
            "body_size_bytes": 0,
            "preview": None,
            "outcome": "request_failed",
        }

    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers=headers,
            cookies=cookies,
        ) as client:
            response = client.get(url)
    except Exception as exc:
        return {
            "attempt_label": attempt_label,
            "status": None,
            "exception": str(exc),
            "is_json": False,
            "same_endpoint": False,
            "body_size_bytes": 0,
            "preview": None,
            "outcome": "request_failed",
        }

    body_text = response.text
    body_json = safe_json_parse(body_text)
    response_endpoint = detect_response_endpoint_name(
        final_url=str(response.url),
        body_json=body_json,
    )
    json_exception = extract_json_exception_info(body_json)
    attempt = {
        "attempt_label": attempt_label,
        "status": response.status_code,
        "final_url": str(response.url),
        "content_type": response.headers.get("content-type"),
        "is_json": body_json is not None,
        "same_endpoint": response_endpoint == expected_endpoint_name,
        "response_endpoint_name": response_endpoint,
        "json_exception": json_exception,
        "body_size_bytes": len(response.content or b""),
        "preview": None if body_json is not None else body_text[:MAX_PREVIEW_LENGTH],
        "json_top_level_keys": list(body_json.keys())[:20] if isinstance(body_json, dict) else [],
        "exception": None,
    }
    attempt["outcome"] = classify_probe_attempt(
        attempt,
        expected_endpoint_name=expected_endpoint_name,
    )
    return attempt


def run_curl_cffi_probe(
    *,
    url: str,
    headers: dict[str, str],
    cookies: dict[str, str] | None,
    timeout_seconds: float,
    attempt_label: str,
    expected_endpoint_name: str,
) -> dict[str, Any]:
    if curl_cffi_requests is None:
        return {
            "attempt_label": attempt_label,
            "status": None,
            "exception": "curl_cffi is not installed",
            "is_json": False,
            "same_endpoint": False,
            "body_size_bytes": 0,
            "preview": None,
            "outcome": "request_failed",
        }

    try:
        response = curl_cffi_requests.get(
            url,
            headers=headers,
            cookies=cookies,
            timeout=timeout_seconds,
            impersonate="chrome124",
            allow_redirects=True,
        )
    except Exception as exc:
        return {
            "attempt_label": attempt_label,
            "status": None,
            "exception": str(exc),
            "is_json": False,
            "same_endpoint": False,
            "body_size_bytes": 0,
            "preview": None,
            "outcome": "request_failed",
        }

    body_text = response.text
    body_json = safe_json_parse(body_text)
    response_endpoint = detect_response_endpoint_name(
        final_url=str(response.url),
        body_json=body_json,
    )
    json_exception = extract_json_exception_info(body_json)
    attempt = {
        "attempt_label": attempt_label,
        "status": response.status_code,
        "final_url": str(response.url),
        "content_type": response.headers.get("content-type"),
        "is_json": body_json is not None,
        "same_endpoint": response_endpoint == expected_endpoint_name,
        "response_endpoint_name": response_endpoint,
        "json_exception": json_exception,
        "body_size_bytes": len(response.content or b""),
        "preview": None if body_json is not None else body_text[:MAX_PREVIEW_LENGTH],
        "json_top_level_keys": list(body_json.keys())[:20] if isinstance(body_json, dict) else [],
        "exception": None,
    }
    attempt["outcome"] = classify_probe_attempt(
        attempt,
        expected_endpoint_name=expected_endpoint_name,
    )
    return attempt


def probe_targets(
    targets: list[dict[str, Any]],
    *,
    timeout_seconds: float,
    cookie_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cookie_map = cookies_to_name_value_map(cookie_items)
    target_results: list[dict[str, Any]] = []

    for target in targets:
        headers = build_probe_headers(target)
        attempts: list[dict[str, Any]] = []

        attempts.append(
            run_httpx_probe(
                url=target["url"],
                headers=headers,
                cookies=None,
                timeout_seconds=timeout_seconds,
                attempt_label="httpx_anonymous",
                expected_endpoint_name=target["endpoint_name"],
            )
        )

        if cookie_map:
            attempts.append(
                run_httpx_probe(
                    url=target["url"],
                    headers=headers,
                    cookies=cookie_map,
                    timeout_seconds=timeout_seconds,
                    attempt_label="httpx_cookies",
                    expected_endpoint_name=target["endpoint_name"],
                )
            )

        needs_fallback = not any(attempt.get("outcome") == "reusable" for attempt in attempts)
        if needs_fallback:
            attempts.append(
                run_curl_cffi_probe(
                    url=target["url"],
                    headers=headers,
                    cookies=cookie_map or None,
                    timeout_seconds=timeout_seconds,
                    attempt_label="curl_cffi_cookies" if cookie_map else "curl_cffi_anonymous",
                    expected_endpoint_name=target["endpoint_name"],
                )
            )

        target_result = dict(target)
        target_result["attempts"] = attempts
        target_result["conclusion"] = summarize_target_conclusion(attempts)
        target_results.append(target_result)

    return target_results


def main() -> int:
    args = parse_args()
    capture_dir = args.capture_dir.resolve()
    records, source_path = load_useful_records(capture_dir)
    targets = select_probe_targets(records)
    cookie_items, cookie_source = load_cookie_items(
        storage_state_path=args.storage_state.resolve() if args.storage_state else None,
        cookies_json_path=args.cookies_json.resolve() if args.cookies_json else None,
    )

    target_results = probe_targets(
        targets,
        timeout_seconds=args.timeout,
        cookie_items=cookie_items,
    )
    summary = summarize_probe_results(target_results)
    rendered_results = {
        "generated_at": datetime.now(UTC).isoformat(),
        "capture_dir": str(capture_dir),
        "source_file": str(source_path),
        "cookie_source": cookie_source,
        **summary,
    }

    results_path = capture_dir / "http_probe_results.json"
    report_path = capture_dir / "http_probe_report.md"
    results_path.write_text(
        json.dumps(rendered_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path.write_text(
        render_probe_report(rendered_results),
        encoding="utf-8",
    )

    print(f"Wrote {results_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
