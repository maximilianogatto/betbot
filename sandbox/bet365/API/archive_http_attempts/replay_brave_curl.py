from __future__ import annotations

import argparse
import json
import re
import shlex
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from common import decode_body, ensure_dir, sha256_bytes, write_json
from parse_markets_payload import looks_like_markets_payload, parse_markets_payload_text

API_ROOT = Path(__file__).resolve().parent
SENSITIVE_HEADERS = {"cookie", "authorization", "x-net-sync-term"}
BODY_MARKERS = ("EV;", "MG;ID=40", "PA;", "FI=", "OD=")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reproduce una request Copy as cURL de Brave sin Playwright.",
    )
    parser.add_argument("curl_file", help="Archivo con la request cURL copiada desde Brave.")
    parser.add_argument(
        "--out-dir",
        default=str(API_ROOT / "attempts"),
        help="Directorio base donde guardar el intento.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--backend",
        choices=("auto", "curl_cffi", "httpx"),
        default="auto",
        help="Backend preferido para el replay.",
    )
    return parser.parse_args()


def load_curl_command(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.sub(r"\\\s*\n\s*", " ", text).strip()


def parse_cookie_string(raw: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", maxsplit=1)
        cookies[name.strip()] = value.strip()
    return cookies


def parse_curl_text(text: str) -> dict[str, Any]:
    tokens = shlex.split(text, posix=True)
    if not tokens or tokens[0] != "curl":
        raise ValueError("El archivo no parece contener un comando curl válido.")

    method = "GET"
    url: str | None = None
    headers: dict[str, str] = {}
    cookies: dict[str, str] = {}
    data: str | None = None

    index = 1
    while index < len(tokens):
        token = tokens[index]

        if token in {"-X", "--request"} and index + 1 < len(tokens):
            method = tokens[index + 1].upper()
            index += 2
            continue

        if token in {"-H", "--header"} and index + 1 < len(tokens):
            raw_header = tokens[index + 1]
            if ":" in raw_header:
                key, value = raw_header.split(":", maxsplit=1)
                headers[key.strip()] = value.strip()
            index += 2
            continue

        if token in {"-b", "--cookie"} and index + 1 < len(tokens):
            cookies.update(parse_cookie_string(tokens[index + 1]))
            index += 2
            continue

        if token in {"-A", "--user-agent"} and index + 1 < len(tokens):
            headers["user-agent"] = tokens[index + 1]
            index += 2
            continue

        if token in {"--data", "--data-raw", "--data-binary", "--data-urlencode"} and index + 1 < len(tokens):
            data = tokens[index + 1]
            if method == "GET":
                method = "POST"
            index += 2
            continue

        if token == "--url" and index + 1 < len(tokens):
            url = tokens[index + 1]
            index += 2
            continue

        if token.startswith("http://") or token.startswith("https://"):
            url = token
            index += 1
            continue

        index += 1

    if not url:
        raise ValueError("No encontré la URL dentro del cURL capturado.")

    header_cookie = headers.pop("cookie", None) or headers.pop("Cookie", None)
    if header_cookie:
        cookies.update(parse_cookie_string(header_cookie))

    return {
        "method": method,
        "url": url,
        "headers": headers,
        "cookies": cookies,
        "data": data,
    }


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            sanitized[key] = "<redacted>"
        else:
            sanitized[key] = value
    return sanitized


def sanitize_request_payload(request_data: dict[str, Any]) -> dict[str, Any]:
    parsed_url = urlparse(request_data["url"])
    return {
        "method": request_data["method"],
        "url": request_data["url"],
        "host": parsed_url.netloc,
        "path": parsed_url.path,
        "query_params": [
            {"key": key, "value": value}
            for key, value in parse_qsl(parsed_url.query, keep_blank_values=True)
        ],
        "header_names": sorted(request_data["headers"].keys()),
        "headers": sanitize_headers(request_data["headers"]),
        "cookie_names": sorted(request_data["cookies"].keys()),
        "cookie_count": len(request_data["cookies"]),
        "referer": request_data["headers"].get("referer"),
        "origin": request_data["headers"].get("origin"),
        "user_agent": request_data["headers"].get("user-agent"),
        "accept": request_data["headers"].get("accept"),
        "accept_language": request_data["headers"].get("accept-language"),
        "sec_headers": {
            key: value
            for key, value in request_data["headers"].items()
            if key.lower().startswith("sec-")
        },
        "has_body": request_data["data"] is not None,
    }


def sanitize_response_headers(headers: dict[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() == "set-cookie":
            sanitized[key] = "<redacted>"
        else:
            sanitized[key] = value
    return sanitized


def is_useful_market_body(text: str | None) -> bool:
    if not text:
        return False
    return all(marker in text for marker in BODY_MARKERS)


def looks_like_challenge(status_code: int, text: str | None, content_type: str | None) -> bool:
    preview = (text or "")[:1000].lower()
    normalized_ct = (content_type or "").lower()
    return (
        status_code == 403
        or ("html" in normalized_ct and any(term in preview for term in ("cloudflare", "attention required", "challenge", "captcha")))
    )


def compare_with_fixture(parsed_market: dict[str, Any], fixture_path: Path) -> dict[str, Any] | None:
    if not fixture_path.exists():
        return None

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    current_matches = parsed_market.get("matches") or []
    baseline_matches = fixture.get("matches") or []
    current_by_fi = {match["fixture_id"]: match for match in current_matches if match.get("fixture_id")}
    baseline_by_fi = {match["fixture_id"]: match for match in baseline_matches if match.get("fixture_id")}

    common_fixture_ids = sorted(set(current_by_fi).intersection(baseline_by_fi))
    only_current = sorted(set(current_by_fi) - set(baseline_by_fi))
    only_baseline = sorted(set(baseline_by_fi) - set(current_by_fi))

    elche_current = current_by_fi.get("193003384")
    elche_baseline = baseline_by_fi.get("193003384")

    return {
        "same_competition_name": (
            (parsed_market.get("competition") or {}).get("name")
            == (fixture.get("competition") or {}).get("name")
        ),
        "same_competition_topic": (
            (parsed_market.get("competition") or {}).get("topic")
            == (fixture.get("competition") or {}).get("topic")
        ),
        "current_match_count": len(current_matches),
        "baseline_match_count": len(baseline_matches),
        "common_fixture_ids_count": len(common_fixture_ids),
        "common_fixture_ids_sample": common_fixture_ids[:10],
        "only_current_sample": only_current[:10],
        "only_baseline_sample": only_baseline[:10],
        "elche_comparison": {
            "current": (elche_current or {}).get("odds_1x2"),
            "baseline": (elche_baseline or {}).get("odds_1x2"),
        },
    }


def _execute_with_httpx(request_data: dict[str, Any], timeout: float) -> tuple[dict[str, Any], bytes, str | None]:
    import httpx

    with httpx.Client(
        headers=request_data["headers"],
        cookies=request_data["cookies"],
        timeout=timeout,
        follow_redirects=True,
        http2=True,
    ) as client:
        response = client.request(
            request_data["method"],
            request_data["url"],
            content=request_data["data"],
        )

    raw = response.content
    content_type = response.headers.get("content-type")
    text, encoding = decode_body(raw, content_type)
    result = {
        "backend": "httpx",
        "status_code": response.status_code,
        "reason_phrase": response.reason_phrase,
        "http_version": response.http_version,
        "final_url": str(response.url),
        "redirect_count": len(response.history),
        "content_type": content_type,
        "content_length_header": response.headers.get("content-length"),
        "content_encoding": response.headers.get("content-encoding"),
        "transfer_encoding": response.headers.get("transfer-encoding"),
        "raw_bytes_length": len(raw),
        "text_length": len(text) if text is not None else None,
        "body_sha256": sha256_bytes(raw),
        "hex_preview": raw[:200].hex(),
        "body_preview": (text or "")[:1000] if text is not None else None,
        "response_headers": dict(response.headers),
        "text_encoding": encoding,
    }
    return result, raw, text


def _execute_with_curl_cffi(request_data: dict[str, Any], timeout: float) -> tuple[dict[str, Any], bytes, str | None]:
    from curl_cffi import requests as curl_requests

    with curl_requests.Session() as session:
        response = session.request(
            request_data["method"],
            request_data["url"],
            headers=request_data["headers"],
            cookies=request_data["cookies"],
            data=request_data["data"],
            timeout=timeout,
            allow_redirects=True,
            impersonate="chrome",
        )

    raw = response.content
    content_type = response.headers.get("content-type")
    text, encoding = decode_body(raw, content_type)
    history = getattr(response, "history", []) or []
    result = {
        "backend": "curl_cffi",
        "status_code": response.status_code,
        "reason_phrase": getattr(response, "reason", ""),
        "http_version": getattr(response, "http_version", None),
        "final_url": str(response.url),
        "redirect_count": len(history),
        "content_type": content_type,
        "content_length_header": response.headers.get("content-length"),
        "content_encoding": response.headers.get("content-encoding"),
        "transfer_encoding": response.headers.get("transfer-encoding"),
        "raw_bytes_length": len(raw),
        "text_length": len(text) if text is not None else None,
        "body_sha256": sha256_bytes(raw),
        "hex_preview": raw[:200].hex(),
        "body_preview": (text or "")[:1000] if text is not None else None,
        "response_headers": dict(response.headers),
        "text_encoding": encoding,
    }
    return result, raw, text


def try_backend(name: str, request_data: dict[str, Any], timeout: float) -> tuple[dict[str, Any], bytes, str | None]:
    if name == "curl_cffi":
        return _execute_with_curl_cffi(request_data, timeout)
    if name == "httpx":
        return _execute_with_httpx(request_data, timeout)
    raise ValueError(f"Backend desconocido: {name}")


def choose_backend_order(preferred: str) -> list[str]:
    if preferred == "curl_cffi":
        return ["curl_cffi"]
    if preferred == "httpx":
        return ["httpx"]
    return ["curl_cffi", "httpx"]


def main() -> int:
    args = parse_args()
    curl_file = Path(args.curl_file)
    curl_text = load_curl_command(curl_file)
    request_data = parse_curl_text(curl_text)

    attempts_root = ensure_dir(Path(args.out_dir))
    attempt_dir = ensure_dir(attempts_root / time.strftime("%Y%m%d-%H%M%S"))
    write_json(attempt_dir / "request_parsed.json", sanitize_request_payload(request_data))

    backend_results: list[dict[str, Any]] = []
    chosen_result: dict[str, Any] | None = None
    chosen_raw: bytes = b""
    chosen_text: str | None = None

    for backend in choose_backend_order(args.backend):
        try:
            result, raw, text = try_backend(backend, request_data, args.timeout)
        except Exception as error:  # noqa: BLE001
            backend_results.append(
                {
                    "backend": backend,
                    "error": f"{type(error).__name__}: {error}",
                    "useful_body": False,
                }
            )
            continue

        result["useful_body"] = is_useful_market_body(text)
        result["challenge_like"] = looks_like_challenge(
            result["status_code"],
            text,
            result["content_type"],
        )
        backend_results.append(result)
        chosen_result = result
        chosen_raw = raw
        chosen_text = text

        if result["useful_body"]:
            break

    if chosen_result is None:
        summary = {
            "success": False,
            "message": "No se pudo ejecutar ningún backend HTTP disponible.",
            "attempts": backend_results,
        }
        write_json(attempt_dir / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    (attempt_dir / "response.raw").write_bytes(chosen_raw)
    (attempt_dir / "response.txt").write_text(chosen_text or "", encoding="utf-8")
    write_json(
        attempt_dir / "response_headers.json",
        sanitize_response_headers(chosen_result["response_headers"]),
    )

    parsed_market: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
    if chosen_result["useful_body"] and chosen_text is not None and looks_like_markets_payload(chosen_text):
        parsed_market = parse_markets_payload_text(
            chosen_text,
            host=urlparse(request_data["url"]).netloc or "www.bet365.es",
        )
        write_json(attempt_dir / "parsed_market.json", parsed_market)
        comparison = compare_with_fixture(
            parsed_market,
            API_ROOT / "output" / "parsed_market.json",
        )

    summary = {
        "success": True,
        "source_curl_file": str(curl_file),
        "selected_backend": chosen_result["backend"],
        "request_url": request_data["url"],
        "method": request_data["method"],
        "status_code": chosen_result["status_code"],
        "content_type": chosen_result["content_type"],
        "content_length_header": chosen_result["content_length_header"],
        "raw_bytes_length": chosen_result["raw_bytes_length"],
        "final_url": chosen_result["final_url"],
        "useful_body": chosen_result["useful_body"],
        "challenge_like": chosen_result["challenge_like"],
        "body_preview": chosen_result["body_preview"],
        "parsed_market": {
            "competition_name": (parsed_market or {}).get("competition", {}).get("name"),
            "match_count": len((parsed_market or {}).get("matches") or []),
        }
        if parsed_market
        else None,
        "comparison_to_output_fixture": comparison,
        "attempts": backend_results,
    }
    write_json(attempt_dir / "summary.json", summary)

    if parsed_market:
        competition = parsed_market.get("competition") or {}
        matches = parsed_market.get("matches") or []
        print(f"Liga: {competition.get('name') or 'N/D'}")
        print(f"Partidos: {len(matches)}")
        for match in matches[:5]:
            odds = match.get("odds_1x2") or {}
            print(
                f" - {match.get('home')} vs {match.get('away')} | "
                f"1={odds.get('1')} X={odds.get('X')} 2={odds.get('2')}"
            )
    else:
        print(
            json.dumps(
                {
                    "status": chosen_result["status_code"],
                    "content_length": chosen_result["content_length_header"],
                    "raw_bytes_length": chosen_result["raw_bytes_length"],
                    "body_preview": chosen_result["body_preview"],
                    "challenge_like": chosen_result["challenge_like"],
                    "final_url": chosen_result["final_url"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
