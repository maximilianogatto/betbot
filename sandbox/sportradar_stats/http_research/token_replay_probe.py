from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.http_research.core import (
    parse_signed_t_from_url,
    replace_endpoint_path_in_signed_url,
)
from sandbox.sportradar_stats.http_research.http_probe import probe_once, classify_attempt, build_attempt_headers
from sandbox.sportradar_stats.http_research.reporting import (
    render_token_analysis,
    utc_now_iso,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay and mutate captured Statshub signed T URLs.")
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def iter_records(path: Path):
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


def load_signed_records(capture_dir: Path, limit: int) -> list[dict[str, Any]]:
    path = capture_dir / "fetch_only.ndjson"
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    for record in iter_records(path):
        url = str(record.get("url") or "")
        if not url or url in seen or parse_signed_t_from_url(url) is None:
            continue
        seen.add(url)
        selected.append(record)
        if len(selected) >= limit:
            break
    return selected


def mutation_for(record: dict[str, Any]) -> str | None:
    endpoint = str(record.get("endpoint_key") or "")
    query_urls = ((record.get("response_json_summary") or {}).get("query_url") or "")
    if endpoint == "match_markets":
        return query_urls.replace("match_markets", "match_timeline") if query_urls else None
    if endpoint == "match_timeline":
        return query_urls.replace("match_timeline", "match_markets") if query_urls else None
    if endpoint == "unified_sport_matches":
        return query_urls.replace("unified_sport_matches", "unified_sport_matches_markets") if query_urls else None
    if endpoint == "unified_sport_matches_markets":
        return query_urls.replace("unified_sport_matches_markets", "unified_sport_matches") if query_urls else None
    return None


def build_token_payloads(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for record in records:
        url = str(record.get("url") or "")
        token = parse_signed_t_from_url(url)
        if not token:
            continue
        raw = str(token.get("raw") or "")
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


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir or args.capture_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    records = load_signed_records(args.capture_dir, args.limit)
    mutation_results: list[dict[str, Any]] = []
    exact_results: list[dict[str, Any]] = []

    for record in records:
        endpoint = str(record.get("endpoint_key") or "")
        url = str(record.get("url") or "")
        exact = probe_once(
            url=url,
            label="exact_signed_url",
            headers=build_attempt_headers(record, "captured_headers"),
            cookies={},
            timeout=args.timeout,
        )
        exact["outcome"] = classify_attempt(exact, endpoint)
        exact_results.append({"endpoint_key": endpoint, "status": exact.get("status"), "outcome": exact.get("outcome")})

        mutated_path = mutation_for(record)
        if not mutated_path:
            continue
        mutated_url = replace_endpoint_path_in_signed_url(url, mutated_path)
        mutated = probe_once(
            url=mutated_url,
            label="mutated_path_same_T",
            headers=build_attempt_headers(record, "captured_headers"),
            cookies={},
            timeout=args.timeout,
        )
        expected = str(mutated_path.split("/", 1)[0])
        mutated["outcome"] = classify_attempt(mutated, expected)
        mutation_results.append(
            {
                "endpoint_key": endpoint,
                "mutated_endpoint": expected,
                "status": mutated.get("status"),
                "outcome": mutated.get("outcome"),
                "url": mutated_url,
            }
        )

    payload = {
        "generated_at": utc_now_iso(),
        "source": str(args.capture_dir / "fetch_only.ndjson"),
        "signed_url_count": len(records),
        "exact_replay_outcomes": dict(Counter(item["outcome"] for item in exact_results)),
        "token_payloads": build_token_payloads(records),
        "mutation_results": mutation_results,
    }
    (out_dir / "token_replay_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "token_analysis.md").write_text(render_token_analysis(payload), encoding="utf-8")
    print(f"Wrote {out_dir / 'token_replay_results.json'}")
    print(f"Wrote {out_dir / 'token_analysis.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
