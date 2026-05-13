from __future__ import annotations

import argparse
import json

from replay_candidate import (
    build_request_headers,
    normalize_profile,
    persist_replay,
    pick_capture_dir,
    replay_record_curl_cffi,
    scoped_cookies_from_capture,
    select_candidate,
)
from common import analyze_text_hits, build_search_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repite una request capturada usando curl_cffi con impersonation tipo Chrome.",
    )
    parser.add_argument("capture_dir", nargs="?")
    parser.add_argument("--captures-root", default="sandbox/bet365/API/captures")
    parser.add_argument("--record-id")
    parser.add_argument("--url-contains")
    parser.add_argument(
        "--profile",
        choices=("captured_exact", "minimal_browser", "browserlike"),
        default="browserlike",
    )
    parser.add_argument(
        "--header-profile",
        choices=("captured", "minimal", "browserlike"),
        help="Alias legacy.",
    )
    parser.add_argument("--no-cookies", action="store_true")
    parser.add_argument("--user-agent")
    parser.add_argument("--accept")
    parser.add_argument("--accept-language")
    parser.add_argument("--referer")
    parser.add_argument("--origin")
    parser.add_argument("--contains", action="append", default=[])
    parser.add_argument("--contains-fixture", action="append", default=[])
    parser.add_argument("--label", default="curl-cffi")
    parser.add_argument("--impersonate", default="chrome136")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--warmup-home", action="store_true")
    parser.add_argument("--warmup-url", action="append", default=[])
    parser.add_argument("--save-raw", action="store_true")
    parser.add_argument("--no-decode", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    capture_dir = pick_capture_dir(args)
    candidate = select_candidate(capture_dir, record_id=args.record_id, url_contains=args.url_contains)
    profile = normalize_profile(args.profile, args.header_profile)
    cookies = {} if args.no_cookies else scoped_cookies_from_capture(capture_dir, candidate["url"])
    headers = build_request_headers(
        candidate,
        profile=profile,
        overrides={
            "user-agent": args.user_agent,
            "accept": args.accept,
            "accept-language": args.accept_language,
            "referer": args.referer,
            "origin": args.origin,
        },
    )
    warmup_urls = list(args.warmup_url)
    if args.warmup_home:
        from urllib.parse import urlparse

        parsed = urlparse(candidate["url"])
        warmup_urls.insert(0, f"{parsed.scheme}://{parsed.netloc}/")

    replay_result = replay_record_curl_cffi(
        candidate,
        headers=headers,
        cookies=cookies,
        timeout=args.timeout,
        insecure=args.insecure,
        warmup_urls=warmup_urls,
        impersonate=args.impersonate,
        no_decode=args.no_decode,
    )
    search = build_search_context(args.contains, args.contains_fixture)
    text = replay_result["response"].get("text")
    text_hits = analyze_text_hits(text, search) if isinstance(text, str) else {}
    replay_result["candidate"] = {
        "id": candidate["id"],
        "url": candidate["url"],
        "captured_status": candidate.get("status"),
        "captured_body_hash": candidate.get("body_hash"),
    }
    replay_result["comparison"] = {
        "same_status": candidate.get("status") == replay_result["response"]["status_code"],
        "same_body_hash": candidate.get("body_hash") == replay_result["response"]["body_hash"],
        "text_hits": text_hits,
    }

    result_path = persist_replay(
        capture_dir,
        candidate,
        replay_result,
        text_hits,
        label=args.label,
        save_raw=args.save_raw or args.no_decode,
    )

    print(f"Capture dir: {capture_dir}")
    print(f"Candidate: {candidate['id']} {candidate['url']}")
    print(
        "Replay status/body_hash:",
        replay_result["response"]["status_code"],
        replay_result["response"]["body_hash"],
    )
    print("HTTP version:", replay_result["response"]["http_version"])
    print("Final URL:", replay_result["response"]["final_url"])
    print(
        "Same as captured:",
        replay_result["comparison"]["same_status"],
        replay_result["comparison"]["same_body_hash"],
    )
    print(json.dumps({"response_headers": replay_result["response"]["headers"]}, ensure_ascii=False))
    print(f"Replay guardado en: {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
