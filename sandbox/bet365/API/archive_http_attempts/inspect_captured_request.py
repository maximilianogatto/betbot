from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from replay_brave_curl import load_curl_command, parse_curl_text

RELEVANT_COOKIES = (
    "cf_clearance",
    "__cf_bm",
    "pstk",
    "swt",
    "aps03",
    "rmbs",
    "cc",
    "cc2",
)

APS03_KEYS = ("cg", "ct", "lng")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspecciona una request Copy as cURL de Brave sin exponer valores sensibles.",
    )
    parser.add_argument("curl_file", help="Ruta a captured_curl.txt")
    return parser.parse_args()


def redact_value(value: str | None) -> dict[str, Any]:
    if value is None:
        return {"present": False, "length": 0}
    return {
        "present": True,
        "length": len(value),
        "preview": f"{value[:6]}...{value[-6:]}" if len(value) > 16 else "<short-redacted>",
    }


def parse_aps03(raw: str | None) -> dict[str, str]:
    result: dict[str, str] = {}
    if not raw:
        return result
    for chunk in raw.split("&"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", maxsplit=1)
        result[key] = value
    return result


def build_summary(request_data: dict[str, Any]) -> dict[str, Any]:
    headers = request_data["headers"]
    cookies = request_data["cookies"]
    aps03_fields = parse_aps03(cookies.get("aps03"))

    return {
        "url": request_data["url"],
        "method": request_data["method"],
        "query_params": request_data["url"].split("?", maxsplit=1)[1] if "?" in request_data["url"] else "",
        "header_names": sorted(headers.keys()),
        "cookie_names": sorted(cookies.keys()),
        "has_x_net_sync_term": "x-net-sync-term" in {key.lower() for key in headers},
        "x_net_sync_term_length": len(headers.get("x-net-sync-term", "")),
        "has_x_request_id": "x-request-id" in {key.lower() for key in headers},
        "relevant_cookies": {
            name: redact_value(cookies.get(name))
            for name in RELEVANT_COOKIES
        },
        "aps03_fields": {
            key: aps03_fields.get(key)
            for key in APS03_KEYS
        },
        "request_id_preview": redact_value(headers.get("x-request-id")),
        "user_agent_preview": headers.get("user-agent"),
        "referer": headers.get("referer"),
        "accept_language": headers.get("accept-language"),
    }


def main() -> int:
    args = parse_args()
    curl_text = load_curl_command(Path(args.curl_file))
    request_data = parse_curl_text(curl_text)
    print(json.dumps(build_summary(request_data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
