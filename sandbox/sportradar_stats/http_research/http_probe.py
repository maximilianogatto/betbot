from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.http_research.core import (
    extract_gismo_endpoint_key,
    safe_json_loads,
    select_important_headers,
)
from sandbox.sportradar_stats.http_research.reporting import (
    render_http_replay_report,
    summarize_outcomes,
    utc_now_iso,
)


BASE_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
DEFAULT_ORIGIN = "https://statshub.sportradar.com"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay captured Statshub/Sportradar URLs with httpx.")
    parser.add_argument("url", nargs="?", help="Captured URL to probe.")
    parser.add_argument("--capture-dir", type=Path, help="Directory with fetch_only.ndjson.")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--cookies-json", type=Path)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def iter_ndjson(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def load_targets(args: argparse.Namespace) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    if args.url:
        targets.append({"url": args.url, "endpoint_key": extract_gismo_endpoint_key(args.url), "request_headers": {}})
    if args.capture_dir:
        seen: set[str] = set()
        path = args.capture_dir / "fetch_only.ndjson"
        for record in iter_ndjson(path):
            url = str(record.get("url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            targets.append(record)
            if len(targets) >= args.limit:
                break
    if not targets:
        raise SystemExit("Pass URL or --capture-dir with fetch_only.ndjson.")
    return targets[: args.limit]


def load_cookie_map(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    cookies: dict[str, str] = {}
    if isinstance(payload, dict) and isinstance(payload.get("cookies"), list):
        payload = payload["cookies"]
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            value = str(item.get("value") or "")
            if name:
                cookies[name] = value
    return cookies


def build_attempt_headers(target: dict[str, Any], label: str) -> dict[str, str]:
    captured_headers = select_important_headers(target.get("request_headers"))
    if label == "no_headers":
        return {}
    if label == "user_agent":
        return {"user-agent": captured_headers.get("user-agent") or BASE_UA}
    if label == "referer_origin":
        return {
            "user-agent": captured_headers.get("user-agent") or BASE_UA,
            "accept": "application/json,text/plain,*/*",
            "origin": DEFAULT_ORIGIN,
            "referer": DEFAULT_ORIGIN + "/",
        }
    if label == "captured_headers":
        headers = {
            "user-agent": BASE_UA,
            "accept": "application/json,text/plain,*/*",
            "origin": DEFAULT_ORIGIN,
            "referer": DEFAULT_ORIGIN + "/",
        }
        headers.update(captured_headers)
        return headers
    raise ValueError(label)


def probe_once(
    *,
    url: str,
    label: str,
    headers: dict[str, str],
    cookies: dict[str, str],
    timeout: float,
    http2: bool = False,
) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, http2=http2, headers=headers, cookies=cookies) as client:
            response = client.get(url)
            body_text = response.text
            body_json = safe_json_loads(body_text)
            endpoint = extract_gismo_endpoint_key(str(response.url), body_json)
            return {
                "label": label,
                "status": response.status_code,
                "final_url": str(response.url),
                "is_json": body_json is not None,
                "response_endpoint_key": endpoint,
                "body_size_bytes": len(body_text.encode("utf-8")),
                "content_type": response.headers.get("content-type"),
                "preview": None if body_json is not None else body_text[:500],
                "json_exception": extract_exception(body_json),
            }
    except Exception as exc:
        return {
            "label": label,
            "exception": str(exc),
            "status": None,
            "is_json": False,
            "body_size_bytes": 0,
            "outcome": "request_failed",
        }


def extract_exception(body_json: object | None) -> dict[str, Any] | None:
    if not isinstance(body_json, dict):
        return None
    doc = body_json.get("doc")
    if not isinstance(doc, list) or not doc or not isinstance(doc[0], dict):
        return None
    first = doc[0]
    data = first.get("data") if isinstance(first.get("data"), dict) else {}
    event = str(first.get("event") or "")
    if event.lower() != "exception" and str(data.get("_doc") or "").lower() != "exception":
        return None
    return {
        "event": event,
        "name": data.get("name"),
        "code": data.get("code"),
        "message": data.get("message"),
    }


def classify_attempt(attempt: dict[str, Any], expected_endpoint: str | None) -> str:
    if attempt.get("exception"):
        return "request_failed"
    status = attempt.get("status")
    preview = str(attempt.get("preview") or "").lower()
    exception = attempt.get("json_exception")
    if isinstance(exception, dict):
        message = str(exception.get("message") or "").lower()
        name = str(exception.get("name") or "").lower()
        if "expired" in message or "signature" in message:
            return "signature_expired"
        if "unauthorized" in name or exception.get("code") in {401, 403}:
            return "blocked"
        return "json_exception"
    if status in {401, 403}:
        if "expired" in preview or "signature" in preview:
            return "signature_expired"
        return "blocked"
    if isinstance(status, int) and status >= 400:
        return "http_error"
    if not attempt.get("is_json"):
        if "access denied" in preview or "forbidden" in preview:
            return "blocked"
        return "non_json"
    if expected_endpoint and attempt.get("response_endpoint_key") == expected_endpoint:
        return "reusable"
    if not expected_endpoint and attempt.get("is_json"):
        return "json_ok"
    return "endpoint_mismatch"


def probe_target(target: dict[str, Any], *, cookies: dict[str, str], timeout: float) -> dict[str, Any]:
    url = str(target.get("url") or "")
    endpoint = str(target.get("endpoint_key") or target.get("gismo_endpoint") or extract_gismo_endpoint_key(url) or "")
    attempts: list[dict[str, Any]] = []
    labels = ("no_headers", "user_agent", "referer_origin", "captured_headers")
    for label in labels:
        attempt = probe_once(
            url=url,
            label=label,
            headers=build_attempt_headers(target, label),
            cookies={},
            timeout=timeout,
        )
        attempt["outcome"] = classify_attempt(attempt, endpoint)
        attempts.append(attempt)
    if cookies:
        attempt = probe_once(
            url=url,
            label="captured_headers_with_cookies",
            headers=build_attempt_headers(target, "captured_headers"),
            cookies=cookies,
            timeout=timeout,
        )
        attempt["outcome"] = classify_attempt(attempt, endpoint)
        attempts.append(attempt)
    attempt = probe_once(
        url=url,
        label="captured_headers_http2",
        headers=build_attempt_headers(target, "captured_headers"),
        cookies=cookies,
        timeout=timeout,
        http2=True,
    )
    attempt["outcome"] = classify_attempt(attempt, endpoint)
    attempts.append(attempt)

    outcomes = Counter(str(attempt.get("outcome") or "") for attempt in attempts)
    if outcomes.get("reusable"):
        conclusion = "HTTP reusable"
    elif outcomes.get("signature_expired"):
        conclusion = "signature expired"
    elif outcomes.get("blocked"):
        conclusion = "HTTP blocked"
    else:
        conclusion = "HTTP inconclusive"
    return {
        "url": url,
        "endpoint_key": endpoint,
        "conclusion": conclusion,
        "attempts": attempts,
    }


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    targets = load_targets(args)
    cookies = load_cookie_map(args.cookies_json)
    results = [probe_target(target, cookies=cookies, timeout=args.timeout) for target in targets]
    payload = {
        "generated_at": utc_now_iso(),
        "source": str(args.capture_dir or args.url),
        "target_count": len(results),
        "outcome_counts": summarize_outcomes(results),
        "targets": results,
    }
    (args.out_dir / "http_probe_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.out_dir / "http_replay_report.md").write_text(
        render_http_replay_report(payload),
        encoding="utf-8",
    )
    print(f"Wrote {args.out_dir / 'http_probe_results.json'}")
    print(f"Wrote {args.out_dir / 'http_replay_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
