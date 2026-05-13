from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from common import decode_body, ensure_dir, iter_jsonl, sha256_bytes, write_json
from parse_markets_payload import looks_like_markets_payload, parse_markets_payload_text
from replay_brave_curl import (
    compare_with_fixture,
    is_useful_market_body,
    load_curl_command,
    looks_like_challenge,
    parse_curl_text,
    sanitize_request_payload,
    sanitize_response_headers,
)

API_ROOT = Path(__file__).resolve().parent
DEFAULT_SEQUENCE_FILE = API_ROOT / "sequence_urls.txt"
BODY_MARKERS = ("EV;", "MG;ID=40", "PA;", "FI=", "OD=")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prueba secuencias HTTP con aiohttp para el endpoint de Bet365 sin Playwright.",
    )
    parser.add_argument("curl_file", help="Ruta a captured_curl.txt")
    parser.add_argument(
        "--out-dir",
        default=str(API_ROOT / "aiohttp_attempts"),
        help="Directorio base donde guardar intentos.",
    )
    parser.add_argument(
        "--sequence-file",
        default=str(DEFAULT_SEQUENCE_FILE),
        help="Archivo opcional con URLs previas, una por línea.",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--sleep", type=float, default=0.75)
    return parser.parse_args()


def build_base_headers(captured_headers: dict[str, str]) -> dict[str, str]:
    allowed = {
        "accept",
        "accept-language",
        "cache-control",
        "pragma",
        "referer",
        "origin",
        "priority",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "sec-fetch-dest",
        "sec-fetch-mode",
        "sec-fetch-site",
        "sec-gpc",
        "upgrade-insecure-requests",
        "user-agent",
        "x-net-sync-term",
        "x-request-id",
    }
    return {
        key: value
        for key, value in captured_headers.items()
        if key.lower() in allowed
    }


def summarize_body(text: str | None) -> dict[str, Any]:
    return {
        "useful": is_useful_market_body(text),
        "contains_ev": "EV;" in (text or ""),
        "contains_market_40": "MG;ID=40" in (text or ""),
        "contains_pa": "PA;" in (text or ""),
        "contains_fi": "FI=" in (text or ""),
        "contains_od": "OD=" in (text or ""),
    }


def sanitize_step_request(request_data: dict[str, Any]) -> dict[str, Any]:
    return sanitize_request_payload(request_data)


def discover_pre_urls(captures_root: Path) -> dict[str, str | None]:
    sports_configuration = None
    sitecontent = None
    for network_file in captures_root.rglob("network.jsonl"):
        for record in iter_jsonl(network_file):
            url = record.get("url") or ""
            if not isinstance(url, str):
                continue
            lowered = url.lower()
            if sports_configuration is None and "sports-configuration" in lowered:
                sports_configuration = url
            if sitecontent is None and "sitecontent" in lowered:
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


def load_sequence_urls(path: Path) -> list[str]:
    if not path.exists():
        return []
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        urls.append(candidate)
    return urls


async def perform_get(
    session: Any,
    url: str,
    *,
    step_headers: dict[str, str],
) -> tuple[dict[str, Any], bytes, str | None]:
    async with session.get(url, headers=step_headers, allow_redirects=True) as response:
        raw = await response.read()
        content_type = response.headers.get("content-type")
        text, encoding = decode_body(raw, content_type)
        result = {
            "status_code": response.status,
            "reason_phrase": response.reason,
            "final_url": str(response.url),
            "content_type": content_type,
            "content_length_header": response.headers.get("content-length"),
            "content_encoding": response.headers.get("content-encoding"),
            "transfer_encoding": response.headers.get("transfer-encoding"),
            "raw_bytes_length": len(raw),
            "text_length": len(text) if text is not None else None,
            "body_sha256": sha256_bytes(raw),
            "body_preview": (text or "")[:1000] if text is not None else None,
            "hex_preview": raw[:200].hex(),
            "response_headers": dict(response.headers),
            "text_encoding": encoding,
            "history_count": len(response.history),
        }
        return result, raw, text


async def execute_sequence(
    sequence_name: str,
    steps: list[str],
    *,
    request_data: dict[str, Any],
    timeout: float,
    sleep_seconds: float,
    case_dir: Path,
) -> dict[str, Any]:
    try:
        import aiohttp
        from yarl import URL
    except Exception as error:  # noqa: BLE001
        return {
            "sequence": sequence_name,
            "error": f"aiohttp unavailable: {type(error).__name__}: {error}",
        }

    headers = build_base_headers(request_data["headers"])
    if "x-request-id" in headers:
        headers["x-request-id"] = headers["x-request-id"]
    else:
        headers["x-request-id"] = str(uuid.uuid4())

    requests_log: list[dict[str, Any]] = []
    warmup_results: list[dict[str, Any]] = []
    final_result: dict[str, Any] | None = None
    final_raw = b""
    final_text: str | None = None

    cookie_jar = aiohttp.CookieJar()
    for name, value in request_data["cookies"].items():
        cookie_jar.update_cookies({name: value}, response_url=URL(request_data["url"]))

    connector = aiohttp.TCPConnector(limit=1)
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    async with aiohttp.ClientSession(
        cookie_jar=cookie_jar,
        headers=headers,
        connector=connector,
        timeout=client_timeout,
        trust_env=False,
    ) as session:
        for index, url in enumerate(steps, start=1):
            step_headers = dict(headers)
            if url != request_data["url"]:
                step_headers.pop("x-net-sync-term", None)
            step_request = {
                "method": "GET",
                "url": url,
                "headers": step_headers,
                "cookies": request_data["cookies"],
                "data": None,
            }
            requests_log.append(sanitize_step_request(step_request))
            try:
                result, raw, text = await perform_get(session, url, step_headers=step_headers)
            except Exception as error:  # noqa: BLE001
                failure = {
                    "step": index,
                    "url": url,
                    "error": f"{type(error).__name__}: {error}",
                }
                if index == len(steps):
                    write_json(case_dir / "requests.json", requests_log)
                    write_json(case_dir / "summary.json", {"sequence": sequence_name, **failure})
                    return {"sequence": sequence_name, **failure}
                warmup_results.append(failure)
                await asyncio.sleep(sleep_seconds)
                continue

            step_summary = {
                "step": index,
                "url": url,
                "status": result["status_code"],
                "content_type": result["content_type"],
                "raw_bytes_length": result["raw_bytes_length"],
                "body_preview": result["body_preview"],
            }

            if index == len(steps):
                final_result = result
                final_raw = raw
                final_text = text
            else:
                warmup_results.append(step_summary)
                await asyncio.sleep(sleep_seconds)

    write_json(case_dir / "requests.json", requests_log)

    if final_result is None:
        summary = {
            "sequence": sequence_name,
            "error": "Final endpoint was not executed.",
            "warmup_steps": warmup_results,
        }
        write_json(case_dir / "summary.json", summary)
        return summary

    (case_dir / "response.raw").write_bytes(final_raw)
    (case_dir / "response.txt").write_text(final_text or "", encoding="utf-8")
    write_json(case_dir / "response_headers.json", sanitize_response_headers(final_result["response_headers"]))

    parsed_market: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
    if final_text and looks_like_markets_payload(final_text):
        parsed_market = parse_markets_payload_text(
            final_text,
            host=urlsplit(request_data["url"]).netloc or "www.bet365.es",
        )
        write_json(case_dir / "parsed_market.json", parsed_market)
        comparison = compare_with_fixture(parsed_market, API_ROOT / "output" / "parsed_market.json")

    body_summary = summarize_body(final_text)
    summary = {
        "sequence": sequence_name,
        "status": final_result["status_code"],
        "body_bytes": final_result["raw_bytes_length"],
        "content_type": final_result["content_type"],
        "content_encoding": final_result["content_encoding"],
        "cf_ray": final_result["response_headers"].get("cf-ray"),
        "preview": final_result["body_preview"],
        "challenge_like": looks_like_challenge(
            final_result["status_code"],
            final_text,
            final_result["content_type"],
        ),
        "warmup_steps": warmup_results,
        "final_url": final_result["final_url"],
        "comparison_to_output_fixture": comparison,
        "parsed_market": {
            "competition_name": (parsed_market or {}).get("competition", {}).get("name"),
            "match_count": len((parsed_market or {}).get("matches") or []),
        }
        if parsed_market
        else None,
        **body_summary,
    }
    write_json(case_dir / "summary.json", summary)
    return summary


def build_sequences(markets_url: str, discovered: dict[str, str | None], sequence_urls: list[str]) -> dict[str, list[str]]:
    split = urlsplit(markets_url)
    home_url = f"{split.scheme}://{split.netloc}/"
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    pd_value = query.get("pd", "").strip("#")
    competition_url = f"{home_url}#/{pd_value.replace('#', '/')}/" if pd_value else home_url
    web_config_url = f"{home_url}webConfig"

    sequences = {
        "A_endpoint_directo": [markets_url],
        "B_home_endpoint": [home_url, markets_url],
        "C_home_webConfig_endpoint": [home_url, web_config_url, markets_url],
        "D_home_sports_configuration_endpoint": [home_url, markets_url],
        "E_home_liga_endpoint": [home_url, competition_url, markets_url],
    }
    if discovered.get("sports_configuration"):
        sequences["D_home_sports_configuration_endpoint"] = [
            home_url,
            discovered["sports_configuration"],
            markets_url,
        ]
    if sequence_urls:
        sequences["F_sequence_file_endpoint"] = [*sequence_urls, markets_url]
    return sequences


def print_useful_summary(summary: dict[str, Any], parsed_market_path: Path) -> None:
    if not parsed_market_path.exists():
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    parsed_market = json.loads(parsed_market_path.read_text(encoding="utf-8"))
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
    print(json.dumps(summary, ensure_ascii=False, indent=2))


async def main_async(args: argparse.Namespace) -> int:
    curl_text = load_curl_command(Path(args.curl_file))
    request_data = parse_curl_text(curl_text)
    discovered = discover_pre_urls(API_ROOT / "captures")
    sequence_urls = load_sequence_urls(Path(args.sequence_file))
    sequences = build_sequences(request_data["url"], discovered, sequence_urls)

    root_dir = ensure_dir(Path(args.out_dir))
    run_dir = ensure_dir(root_dir / time.strftime("%Y%m%d-%H%M%S"))
    table_rows: list[dict[str, Any]] = []

    for name, steps in sequences.items():
        case_dir = ensure_dir(run_dir / name)
        summary = await execute_sequence(
            name,
            steps,
            request_data=request_data,
            timeout=args.timeout,
            sleep_seconds=args.sleep,
            case_dir=case_dir,
        )
        table_rows.append(
            {
                "client": "aiohttp",
                "sequence": name,
                "status": summary.get("status"),
                "bytes": summary.get("body_bytes"),
                "useful": summary.get("useful"),
                "notes": summary.get("error") or (
                    "payload útil"
                    if summary.get("useful")
                    else ("challenge" if summary.get("challenge_like") else "sin payload útil")
                ),
            }
        )

    write_json(run_dir / "table_rows.json", table_rows)
    print(json.dumps(table_rows, ensure_ascii=False, indent=2))

    useful_case = next((row for row in table_rows if row.get("useful")), None)
    if useful_case:
        parsed_market_path = run_dir / useful_case["sequence"] / "parsed_market.json"
        summary = json.loads((run_dir / useful_case["sequence"] / "summary.json").read_text(encoding="utf-8"))
        print_useful_summary(summary, parsed_market_path)
    return 0


def main() -> int:
    args = parse_args()
    try:
        import aiohttp  # noqa: F401
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "error": "aiohttp no está instalado en este venv.",
                    "detail": f"{type(error).__name__}: {error}",
                    "hint": "Instalar aiohttp en BetBot/betbot para ejecutar esta prueba real.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
