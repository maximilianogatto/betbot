from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from common import load_json, write_json
from replay_candidate import (
    build_request_headers,
    normalize_profile,
    pick_capture_dir,
    replay_record,
    replay_record_curl_cffi,
    scoped_cookies_from_capture,
    select_candidate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prueba distintas secuencias previas antes de pedir un endpoint útil de Bet365.",
    )
    parser.add_argument("capture_dir", nargs="?", help="Directorio de captura.")
    parser.add_argument("--captures-root", default="sandbox/bet365/API/captures")
    parser.add_argument("--record-id")
    parser.add_argument("--url-contains")
    parser.add_argument(
        "--profile",
        choices=("captured_exact", "minimal_browser", "browserlike", "curl_cffi_chrome"),
        default="captured_exact",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--http2", action="store_true")
    parser.add_argument("--trust-env", action="store_true")
    parser.add_argument("--no-cookies", action="store_true")
    parser.add_argument("--home-url")
    parser.add_argument("--document-url")
    parser.add_argument("--pre-url", action="append", default=[])
    parser.add_argument("--impersonate", default="chrome136")
    parser.add_argument("--output")
    return parser.parse_args()


async def run_sequence(
    candidate: dict[str, Any],
    *,
    profile: str,
    headers: dict[str, str],
    cookies: dict[str, str],
    timeout: float,
    insecure: bool,
    http2: bool,
    trust_env: bool,
    warmup_urls: list[str],
    impersonate: str,
) -> dict[str, Any]:
    if profile == "curl_cffi_chrome":
        return replay_record_curl_cffi(
            candidate,
            headers=headers,
            cookies=cookies,
            timeout=timeout,
            insecure=insecure,
            warmup_urls=warmup_urls,
            impersonate=impersonate,
            no_decode=False,
        )
    return await replay_record(
        candidate,
        headers=headers,
        cookies=cookies,
        timeout=timeout,
        insecure=insecure,
        http2=http2,
        trust_env=trust_env,
        warmup_urls=warmup_urls,
        no_decode=False,
    )


async def main() -> int:
    args = parse_args()
    capture_dir = pick_capture_dir(args)
    candidate = select_candidate(capture_dir, record_id=args.record_id, url_contains=args.url_contains)
    profile = normalize_profile(args.profile, None)
    cookies = {} if args.no_cookies else scoped_cookies_from_capture(capture_dir, candidate["url"])
    headers = build_request_headers(
        candidate,
        profile=profile,
        overrides={},
    )

    parsed = urlparse(candidate["url"])
    home_url = args.home_url or f"{parsed.scheme}://{parsed.netloc}/"
    metadata_path = Path(capture_dir) / "metadata.json"
    metadata = load_json(metadata_path) if metadata_path.exists() else {}
    document_url = args.document_url or metadata.get("target_url") or home_url

    sequences = {
        "A_direct": [],
        "B_home_then_endpoint": [home_url],
        "C_home_document_then_endpoint": [home_url, document_url],
        "D_home_document_pre_then_endpoint": [home_url, document_url, *args.pre_url],
    }

    results: dict[str, Any] = {
        "capture_dir": str(capture_dir),
        "candidate_url": candidate["url"],
        "profile": profile,
        "results": {},
    }
    for name, warmup_urls in sequences.items():
        replay_result = await run_sequence(
            candidate,
            profile=profile,
            headers=headers,
            cookies=cookies,
            timeout=args.timeout,
            insecure=args.insecure,
            http2=args.http2,
            trust_env=args.trust_env,
            warmup_urls=warmup_urls,
            impersonate=args.impersonate,
        )
        results["results"][name] = {
            "warmup_urls": warmup_urls,
            "status_code": replay_result["response"]["status_code"],
            "http_version": replay_result["response"]["http_version"],
            "body_size": replay_result["response"]["body_size"],
            "body_hash": replay_result["response"]["body_hash"],
            "content_type": replay_result["response"]["content_type"],
            "final_url": replay_result["response"]["final_url"],
        }

    output_path = Path(args.output) if args.output else Path(capture_dir) / "replays" / f"sequence-{profile}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, results)

    print(f"Sequence report guardado en: {output_path}")
    for name, item in results["results"].items():
        print(
            f"{name}: status={item['status_code']} http={item['http_version']} body={item['body_size']} type={item['content_type']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
