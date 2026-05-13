from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from replay_brave_curl import load_curl_command, parse_curl_text, sanitize_request_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara la request capturada del navegador contra un intento replay guardado.",
    )
    parser.add_argument("curl_file", help="Ruta a captured_curl.txt")
    parser.add_argument("attempt_dir", help="Directorio del intento con request_parsed.json y summary.json")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    browser_request = parse_curl_text(load_curl_command(Path(args.curl_file)))
    browser_view = sanitize_request_payload(browser_request)

    attempt_dir = Path(args.attempt_dir)
    replay_request = load_json(attempt_dir / "request_parsed.json")
    replay_summary = load_json(attempt_dir / "summary.json")

    browser_headers = set(browser_view["header_names"])
    replay_headers = set(replay_request["header_names"])
    browser_cookies = set(browser_view["cookie_names"])
    replay_cookies = set(replay_request["cookie_names"])

    report = {
        "browser_expected": {
            "status": 200,
            "useful_payload": True,
        },
        "replay_observed": {
            "status": replay_summary.get("status_code"),
            "useful_payload": replay_summary.get("useful_body"),
            "selected_backend": replay_summary.get("selected_backend"),
        },
        "headers_omitted_in_replay": sorted(browser_headers - replay_headers),
        "extra_headers_in_replay": sorted(replay_headers - browser_headers),
        "cookies_omitted_in_replay": sorted(browser_cookies - replay_cookies),
        "extra_cookies_in_replay": sorted(replay_cookies - browser_cookies),
        "accept_encoding_browser": browser_view["headers"].get("accept-encoding"),
        "accept_encoding_replay": replay_request["headers"].get("accept-encoding"),
        "user_agent_browser": browser_view["headers"].get("user-agent"),
        "user_agent_replay": replay_request["headers"].get("user-agent"),
        "sec_ch_ua_browser": browser_view["headers"].get("sec-ch-ua"),
        "sec_ch_ua_replay": replay_request["headers"].get("sec-ch-ua"),
        "x_net_sync_term_in_browser": "x-net-sync-term" in browser_headers,
        "x_net_sync_term_in_replay": "x-net-sync-term" in replay_headers,
        "x_request_id_in_browser": "x-request-id" in browser_headers,
        "x_request_id_in_replay": "x-request-id" in replay_headers,
        "x_request_id_browser": browser_view["headers"].get("x-request-id"),
        "x_request_id_replay": replay_request["headers"].get("x-request-id"),
        "observation": None,
    }

    if report["x_net_sync_term_in_replay"] and not replay_summary.get("useful_body"):
        report["observation"] = "X-Net-Sync-Term fue enviado en replay pero no alcanzó para obtener payload útil."
    elif not report["x_net_sync_term_in_replay"]:
        report["observation"] = "Replay omitió X-Net-Sync-Term."

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
