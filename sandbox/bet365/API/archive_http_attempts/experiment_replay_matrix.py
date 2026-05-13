from __future__ import annotations

import argparse
import copy
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from common import ensure_dir, write_json
from parse_markets_payload import looks_like_markets_payload, parse_markets_payload_text
from replay_brave_curl import (
    is_useful_market_body,
    load_curl_command,
    looks_like_challenge,
    parse_curl_text,
    sanitize_request_payload,
    sanitize_response_headers,
    try_backend,
)

API_ROOT = Path(__file__).resolve().parent
CaseMutator = Callable[[dict[str, Any]], dict[str, Any]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prueba una matriz controlada de variantes sobre un cURL capturado de Brave.",
    )
    parser.add_argument("curl_file", help="Ruta a captured_curl.txt")
    parser.add_argument(
        "--out-dir",
        default=str(API_ROOT / "attempts_matrix"),
        help="Directorio base para guardar la matriz de intentos.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--sleep", type=float, default=1.0)
    return parser.parse_args()


def filter_headers(headers: dict[str, str], *, prefix: str) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if not key.lower().startswith(prefix)
    }


def minimal_headers(base_headers: dict[str, str]) -> dict[str, str]:
    keep = ("accept", "accept-language", "referer", "user-agent")
    return {key: value for key, value in base_headers.items() if key.lower() in keep}


def build_cases() -> list[tuple[str, str, CaseMutator]]:
    def exact(request_data: dict[str, Any]) -> dict[str, Any]:
        return request_data

    def no_sync(request_data: dict[str, Any]) -> dict[str, Any]:
        request_data["headers"].pop("x-net-sync-term", None)
        return request_data

    def no_request_id(request_data: dict[str, Any]) -> dict[str, Any]:
        request_data["headers"].pop("x-request-id", None)
        return request_data

    def regen_request_id(request_data: dict[str, Any]) -> dict[str, Any]:
        request_data["headers"]["x-request-id"] = str(uuid.uuid4())
        return request_data

    def no_sec_fetch(request_data: dict[str, Any]) -> dict[str, Any]:
        request_data["headers"] = filter_headers(request_data["headers"], prefix="sec-fetch-")
        return request_data

    def no_sec_ch_ua(request_data: dict[str, Any]) -> dict[str, Any]:
        request_data["headers"] = filter_headers(request_data["headers"], prefix="sec-ch-ua")
        return request_data

    def with_ae_zstd(request_data: dict[str, Any]) -> dict[str, Any]:
        request_data["headers"]["accept-encoding"] = "gzip, deflate, br, zstd"
        return request_data

    def with_ae_no_zstd(request_data: dict[str, Any]) -> dict[str, Any]:
        request_data["headers"]["accept-encoding"] = "gzip, deflate, br"
        return request_data

    def minimal_with_cookies(request_data: dict[str, Any]) -> dict[str, Any]:
        request_data["headers"] = minimal_headers(request_data["headers"])
        return request_data

    def minimal_without_cookies(request_data: dict[str, Any]) -> dict[str, Any]:
        request_data["headers"] = minimal_headers(request_data["headers"])
        request_data["cookies"] = {}
        return request_data

    return [
        ("A_headers_exactos", "Headers exactos capturados", exact),
        ("B_sin_x_net_sync_term", "Headers exactos sin X-Net-Sync-Term", no_sync),
        ("C_sin_x_request_id", "Headers exactos sin X-Request-Id", no_request_id),
        ("D_x_request_id_random", "Headers exactos con X-Request-Id regenerado", regen_request_id),
        ("E_sin_sec_fetch", "Headers exactos quitando sec-fetch-*", no_sec_fetch),
        ("F_sin_sec_ch_ua", "Headers exactos quitando sec-ch-ua*", no_sec_ch_ua),
        ("G_con_accept_encoding_zstd", "Headers exactos con Accept-Encoding incluyendo zstd", with_ae_zstd),
        ("H_con_accept_encoding_br", "Headers exactos con Accept-Encoding gzip, deflate, br", with_ae_no_zstd),
        ("I_headers_minimos_con_cookies", "Headers mínimos tipo browser con cookies", minimal_with_cookies),
        ("J_headers_minimos_sin_cookies", "Headers mínimos tipo browser sin cookies", minimal_without_cookies),
    ]


def summarize_case(
    result: dict[str, Any],
    *,
    body_text: str | None,
) -> dict[str, Any]:
    markers = {
        "contains_ev": "EV;" in (body_text or ""),
        "contains_market_40": "MG;ID=40" in (body_text or ""),
        "contains_fixture": "FI=" in (body_text or ""),
        "contains_od": "OD=" in (body_text or ""),
    }
    return {
        "backend": result.get("backend"),
        "status": result.get("status_code"),
        "bytes": result.get("raw_bytes_length"),
        "useful": is_useful_market_body(body_text),
        "challenge_like": looks_like_challenge(
            result.get("status_code") or 0,
            body_text,
            result.get("content_type"),
        ),
        "content_encoding": result.get("content_encoding"),
        "cf_ray": result.get("response_headers", {}).get("cf-ray"),
        "body_preview": result.get("body_preview"),
        **markers,
    }


def main() -> int:
    args = parse_args()
    curl_text = load_curl_command(Path(args.curl_file))
    base_request = parse_curl_text(curl_text)

    root_dir = ensure_dir(Path(args.out_dir))
    run_dir = ensure_dir(root_dir / time.strftime("%Y%m%d-%H%M%S"))
    matrix_results: list[dict[str, Any]] = []

    for case_name, description, mutator in build_cases():
        case_dir = ensure_dir(run_dir / case_name)
        request_data = mutator(copy.deepcopy(base_request))
        write_json(case_dir / "request.json", sanitize_request_payload(request_data))

        try:
            result, raw, text = try_backend("curl_cffi", request_data, args.timeout)
        except Exception as error:  # noqa: BLE001
            summary = {
                "case": case_name,
                "description": description,
                "error": f"{type(error).__name__}: {error}",
                "useful": False,
            }
            write_json(case_dir / "summary.json", summary)
            matrix_results.append(summary)
            time.sleep(args.sleep)
            continue

        (case_dir / "response.raw").write_bytes(raw)
        (case_dir / "response.txt").write_text(text or "", encoding="utf-8")
        write_json(case_dir / "response_headers.json", sanitize_response_headers(result["response_headers"]))

        if text and looks_like_markets_payload(text):
            parsed_market = parse_markets_payload_text(
                text,
                host=request_data["url"].split("/")[2],
            )
            write_json(case_dir / "parsed_market.json", parsed_market)

        summary = {
            "case": case_name,
            "description": description,
            **summarize_case(result, body_text=text),
        }
        write_json(case_dir / "summary.json", summary)
        matrix_results.append(summary)
        time.sleep(args.sleep)

    write_json(run_dir / "matrix_summary.json", matrix_results)
    print(json.dumps(matrix_results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
