from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from common import ensure_dir, iter_jsonl, write_json
from replay_brave_curl import (
    is_useful_market_body,
    load_curl_command,
    parse_curl_text,
    try_backend,
)

API_ROOT = Path(__file__).resolve().parent

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prueba secuencias HTTP sin navegador usando curl_cffi.",
    )
    parser.add_argument("curl_file", help="Ruta a captured_curl.txt")
    parser.add_argument(
        "--capture-root",
        default=str(API_ROOT / "captures"),
        help="Raíz de capturas para descubrir URLs previas útiles.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(API_ROOT / "attempts"),
        help="Base de salida para guardar resultados de secuencia.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def discover_pre_urls(captures_root: Path) -> dict[str, str | None]:
    sports_configuration = None
    sitecontent = None
    for network_file in captures_root.rglob("network.jsonl"):
        for record in iter_jsonl(network_file):
            url = record.get("url") or ""
            if not isinstance(url, str):
                continue
            if sports_configuration is None and "sports-configuration" in url:
                sports_configuration = url
            if sitecontent is None and "sitecontent" in url:
                sitecontent = url
            if sports_configuration and sitecontent:
                return {
                    "sports_configuration": sports_configuration,
                    "sitecontent": sitecontent,
                }
    return {
        "sports_configuration": sports_configuration,
        "sitecontent": sitecontent,
    }


def execute_sequence(
    base_request: dict[str, Any],
    steps: list[str],
    timeout: float,
) -> dict[str, Any]:
    results = []
    for url in steps[:-1]:
        warm_request = {
            "method": "GET",
            "url": url,
            "headers": base_request["headers"],
            "cookies": base_request["cookies"],
            "data": None,
        }
        try:
            result, _, _ = try_backend("curl_cffi", warm_request, timeout)
            results.append({"url": url, "status": result.get("status_code")})
        except Exception as error:  # noqa: BLE001
            results.append({"url": url, "error": f"{type(error).__name__}: {error}"})

    try:
        final_result, _, text = try_backend("curl_cffi", base_request, timeout)
    except Exception as error:  # noqa: BLE001
        return {
            "warmup_steps": results,
            "error": f"{type(error).__name__}: {error}",
        }

    return {
        "warmup_steps": results,
        "final_status": final_result.get("status_code"),
        "final_content_length": final_result.get("content_length_header"),
        "final_raw_bytes_length": final_result.get("raw_bytes_length"),
        "useful": is_useful_market_body(text),
        "body_preview": final_result.get("body_preview"),
    }


def main() -> int:
    args = parse_args()
    curl_text = load_curl_command(Path(args.curl_file))
    base_request = parse_curl_text(curl_text)
    pre_urls = discover_pre_urls(Path(args.capture_root))
    host = base_request["url"].split("/", maxsplit=3)[:3]
    home_url = "/".join(host) + "/"

    sequences = {
        "A_endpoint_directo": [],
        "B_home_endpoint": [home_url],
        "C_home_sportsconfig_endpoint": [home_url] + ([pre_urls["sports_configuration"]] if pre_urls["sports_configuration"] else []),
        "D_home_sitecontent_endpoint": [home_url] + ([pre_urls["sitecontent"]] if pre_urls["sitecontent"] else []),
    }

    root = ensure_dir(Path(args.out_dir))
    run_dir = ensure_dir(root / f"sequence-{time.strftime('%Y%m%d-%H%M%S')}")
    summary = {
        "pre_urls": pre_urls,
        "sequences": {},
    }

    for name, warmups in sequences.items():
        summary["sequences"][name] = execute_sequence(base_request, [*warmups, base_request["url"]], args.timeout)

    write_json(run_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
