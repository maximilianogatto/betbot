from __future__ import annotations

import argparse
import asyncio
import binascii
import importlib.util
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

import httpx

from common import (
    analyze_text_hits,
    build_search_context,
    decode_body,
    ensure_dir,
    iter_jsonl,
    latest_capture_dir,
    load_json,
    safe_filename_from_url,
    score_record,
    sha256_bytes,
    summarize_header_subset,
    truncate,
    try_parse_json,
    write_json,
)

SENSITIVE_REQUEST_HEADERS = {"host", "content-length", "connection"}
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repite por HTTP una request capturada para evaluar si Bet365 responde fuera del navegador.",
    )
    parser.add_argument("capture_dir", nargs="?", help="Directorio de captura. Si se omite, usa el último.")
    parser.add_argument("--captures-root", default="sandbox/bet365/API/captures")
    parser.add_argument("--record-id", help="ID exacto de network.jsonl a repetir.")
    parser.add_argument("--url-contains", help="Substring para elegir la request candidata.")
    parser.add_argument("--contains", action="append", default=[])
    parser.add_argument("--contains-fixture", action="append", default=[])
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--insecure", action="store_true", help="Desactiva verificación TLS.")
    parser.add_argument(
        "--profile",
        choices=("captured_exact", "minimal_browser", "browserlike", "curl_cffi_chrome"),
        default="captured_exact",
        help="Perfil de replay.",
    )
    parser.add_argument(
        "--header-profile",
        choices=("captured", "minimal", "browserlike"),
        help="Alias legacy. Se mapea a --profile.",
    )
    parser.add_argument("--no-cookies", action="store_true", help="No reenviar cookies capturadas.")
    parser.add_argument("--http2", action="store_true", help="Intentar replay con HTTP/2.")
    parser.add_argument("--trust-env", action="store_true", help="Permite usar proxies y settings del entorno.")
    parser.add_argument("--user-agent", help="Override del User-Agent.")
    parser.add_argument("--accept", help="Override de Accept.")
    parser.add_argument("--accept-language", help="Override de Accept-Language.")
    parser.add_argument("--referer", help="Override de Referer.")
    parser.add_argument("--origin", help="Override de Origin.")
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Hace un GET a la home del host antes del endpoint.",
    )
    parser.add_argument(
        "--warmup-home",
        action="store_true",
        help="Alias explícito de --warmup.",
    )
    parser.add_argument(
        "--warmup-url",
        action="append",
        default=[],
        help="URL adicional para calentar la sesión antes del replay. Se puede repetir.",
    )
    parser.add_argument("--save-raw", action="store_true", help="Guardar body raw bytes.")
    parser.add_argument("--no-decode", action="store_true", help="No decodificar el body como texto.")
    parser.add_argument("--label", default="", help="Etiqueta opcional para el nombre del archivo de salida.")
    parser.add_argument("--impersonate", default="chrome136", help="Perfil de impersonation para curl_cffi.")
    return parser.parse_args()


def normalize_profile(profile: str | None, legacy_profile: str | None) -> str:
    if profile == "captured":
        return "captured_exact"
    if profile == "minimal":
        return "minimal_browser"
    if profile:
        return profile
    if legacy_profile == "captured":
        return "captured_exact"
    if legacy_profile == "minimal":
        return "minimal_browser"
    if legacy_profile == "browserlike":
        return "browserlike"
    return "captured_exact"


def pick_capture_dir(args: argparse.Namespace) -> Path:
    if args.capture_dir:
        return Path(args.capture_dir)
    latest = latest_capture_dir(Path(args.captures_root))
    if latest is None:
        raise SystemExit("No encontré capturas. Corré primero capture_network.py")
    return latest


def cookie_names_from_header(cookie_header: str | None) -> list[str]:
    if not cookie_header:
        return []
    names: list[str] = []
    for part in cookie_header.split(";"):
        name, _, _ = part.strip().partition("=")
        if name:
            names.append(name)
    return sorted(dict.fromkeys(names))


def sanitize_request_headers(headers: dict[str, str]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in SENSITIVE_REQUEST_HEADERS:
            continue
        sanitized[lowered] = value
    return sanitized


def minimal_browser_headers(candidate: dict[str, Any], captured_headers: dict[str, str]) -> dict[str, str]:
    parsed = urlparse(candidate["url"])
    host = f"{parsed.scheme}://{parsed.netloc}"
    defaults = {
        "accept": "*/*",
        "accept-language": "es-ES,es;q=0.9,en;q=0.8",
        "accept-encoding": "gzip, deflate, br, zstd",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": host + "/",
        "origin": host,
        "user-agent": DEFAULT_UA,
    }
    for key in ("accept", "accept-language", "referer", "origin", "user-agent"):
        if captured_headers.get(key):
            defaults[key] = captured_headers[key]
    return defaults


def build_request_headers(
    candidate: dict[str, Any],
    *,
    profile: str,
    overrides: dict[str, str | None],
) -> dict[str, str]:
    captured_headers = sanitize_request_headers(candidate.get("request_headers") or {})
    normalized = normalize_profile(profile, None)
    if normalized == "captured_exact":
        headers = dict(captured_headers)
    elif normalized == "minimal_browser":
        headers = minimal_browser_headers(candidate, captured_headers)
    else:
        headers = minimal_browser_headers(candidate, captured_headers)
        for key in (
            "priority",
            "sec-ch-ua",
            "sec-ch-ua-mobile",
            "sec-ch-ua-platform",
            "sec-fetch-dest",
            "sec-fetch-mode",
            "sec-fetch-site",
            "sec-fetch-user",
            "x-net-sync-term",
            "x-request-id",
        ):
            value = captured_headers.get(key)
            if value:
                headers[key] = value

    for key, value in overrides.items():
        if value:
            headers[key] = value
    return headers


def cookies_from_capture(capture_dir: Path) -> dict[str, str]:
    cookies_path = capture_dir / "cookies.json"
    if not cookies_path.exists():
        return {}
    cookies = load_json(cookies_path)
    return {
        item["name"]: item["value"]
        for item in cookies
        if isinstance(item, dict) and item.get("name") and item.get("value") is not None
    }


def scoped_cookies_from_capture(capture_dir: Path, target_url: str) -> dict[str, str]:
    cookies_path = capture_dir / "cookies.json"
    if not cookies_path.exists():
        return {}
    parsed = urlparse(target_url)
    host = parsed.hostname or ""
    is_https = parsed.scheme == "https"
    raw_cookies = load_json(cookies_path)
    scoped: dict[str, str] = {}
    for item in raw_cookies:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        domain = str(item.get("domain") or "").lstrip(".")
        secure = bool(item.get("secure"))
        if not name or value is None:
            continue
        if secure and not is_https:
            continue
        if domain and host != domain and not host.endswith("." + domain):
            continue
        scoped[name] = value
    return scoped


def select_candidate(
    capture_dir: Path,
    *,
    record_id: str | None,
    url_contains: str | None,
) -> dict[str, Any]:
    records = iter_jsonl(capture_dir / "network.jsonl")
    responses = [record for record in records if record.get("type") == "response"]
    if record_id:
        for record in responses:
            if record.get("id") == record_id:
                return record
        raise SystemExit(f"No encontré record_id={record_id}")
    if url_contains:
        filtered = [record for record in responses if url_contains in (record.get("url") or "")]
        if not filtered:
            raise SystemExit(f"No encontré responses que contengan '{url_contains}'")
        filtered.sort(key=score_record, reverse=True)
        return filtered[0]
    ranked = sorted(responses, key=score_record, reverse=True)
    if not ranked:
        raise SystemExit("La captura no tiene responses para replay.")
    return ranked[0]


def query_params_list(url: str) -> list[tuple[str, str]]:
    return parse_qsl(urlparse(url).query, keep_blank_values=True)


def serialize_request_meta(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    cookies: dict[str, str],
    warmup_urls: list[str],
    http2: bool,
    trust_env: bool,
    backend: str,
) -> dict[str, Any]:
    return {
        "method": method,
        "url": url,
        "final_url": url,
        "headers": headers,
        "header_names": list(headers.keys()),
        "query_params": [{"name": key, "value": value} for key, value in query_params_list(url)],
        "cookies_count": len(cookies),
        "cookie_names": sorted(cookies.keys()),
        "warmup_urls": warmup_urls,
        "http2": http2,
        "trust_env": trust_env,
        "backend": backend,
    }


def serialize_response_meta(
    *,
    status_code: int,
    http_version: str | int | None,
    headers: dict[str, str],
    raw_body: bytes,
    content_type: str,
    text: str | None,
    encoding: str | None,
    body_kind: str | None,
    body_preview: str | None,
    json_top_level: list[str] | None,
    final_url: str,
    redirect_history: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status_code": status_code,
        "http_version": http_version,
        "headers": headers,
        "content_type": content_type,
        "content_length_header": headers.get("content-length"),
        "content_encoding": headers.get("content-encoding"),
        "transfer_encoding": headers.get("transfer-encoding"),
        "body_size": len(raw_body),
        "raw_bytes_length": len(raw_body),
        "text_length": len(text) if text is not None else None,
        "body_hash": sha256_bytes(raw_body),
        "body_encoding": encoding,
        "body_kind": body_kind,
        "body_preview": body_preview,
        "hex_preview": binascii.hexlify(raw_body[:200]).decode("ascii") if raw_body else "",
        "json_top_level": json_top_level,
        "final_url": final_url,
        "redirect_history": redirect_history,
        "text": text,
        "raw_body": raw_body,
    }


async def replay_record(
    candidate: dict[str, Any],
    *,
    headers: dict[str, str],
    cookies: dict[str, str],
    timeout: float,
    insecure: bool,
    http2: bool,
    trust_env: bool,
    warmup_urls: list[str],
    no_decode: bool = False,
) -> dict[str, Any]:
    method = (candidate.get("method") or "GET").upper()
    post_data = candidate.get("request_post_data")
    url = candidate["url"]

    if http2 and importlib.util.find_spec("h2") is None:
        raise SystemExit("Se pidió --http2 pero la dependencia 'h2' no está instalada.")

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        verify=not insecure,
        headers=headers,
        cookies=cookies,
        http2=http2,
        trust_env=trust_env,
    ) as client:
        for warmup_url in warmup_urls:
            await client.get(warmup_url)
        response = await client.request(
            method,
            url,
            content=post_data.encode("utf-8") if isinstance(post_data, str) else None,
        )

    raw_body = response.content
    content_type = response.headers.get("content-type", "")
    text, encoding = (None, None) if no_decode else decode_body(raw_body, content_type)
    body_kind = None
    body_preview = None
    json_top_level = None
    if text is not None:
        from common import guess_body_kind

        body_kind = guess_body_kind(text, content_type)
        body_preview = truncate(text, limit=1500)
        parsed = try_parse_json(text) if body_kind == "json_like" else None
        if isinstance(parsed, dict):
            json_top_level = list(parsed.keys())[:30]
        elif isinstance(parsed, list):
            json_top_level = [f"[{len(parsed)} items]"]

    redirect_history = [
        {
            "status_code": item.status_code,
            "url": str(item.url),
            "location": item.headers.get("location"),
        }
        for item in response.history
    ]

    return {
        "request": serialize_request_meta(
            method=method,
            url=url,
            headers=headers,
            cookies=cookies,
            warmup_urls=warmup_urls,
            http2=http2,
            trust_env=trust_env,
            backend="httpx",
        ),
        "response": serialize_response_meta(
            status_code=response.status_code,
            http_version=response.http_version,
            headers=dict(response.headers),
            raw_body=raw_body,
            content_type=content_type,
            text=text,
            encoding=encoding,
            body_kind=body_kind,
            body_preview=body_preview,
            json_top_level=json_top_level,
            final_url=str(response.url),
            redirect_history=redirect_history,
        ),
    }


def replay_record_curl_cffi(
    candidate: dict[str, Any],
    *,
    headers: dict[str, str],
    cookies: dict[str, str],
    timeout: float,
    insecure: bool,
    warmup_urls: list[str],
    impersonate: str,
    no_decode: bool = False,
) -> dict[str, Any]:
    try:
        from curl_cffi import requests as curl_requests
    except ImportError as error:  # pragma: no cover
        raise SystemExit("curl_cffi no está instalado.") from error

    method = (candidate.get("method") or "GET").upper()
    post_data = candidate.get("request_post_data")
    url = candidate["url"]
    session = curl_requests.Session()
    session.headers.update(headers)
    if cookies:
        session.cookies.update(cookies)
    for warmup_url in warmup_urls:
        session.get(
            warmup_url,
            impersonate=impersonate,
            timeout=timeout,
            verify=not insecure,
            allow_redirects=True,
        )
    response = session.request(
        method,
        url,
        data=post_data.encode("utf-8") if isinstance(post_data, str) else None,
        impersonate=impersonate,
        timeout=timeout,
        verify=not insecure,
        allow_redirects=True,
    )
    raw_body = response.content
    content_type = response.headers.get("content-type", "")
    text, encoding = (None, None) if no_decode else decode_body(raw_body, content_type)
    body_kind = None
    body_preview = None
    json_top_level = None
    if text is not None:
        from common import guess_body_kind

        body_kind = guess_body_kind(text, content_type)
        body_preview = truncate(text, limit=1500)
        parsed = try_parse_json(text) if body_kind == "json_like" else None
        if isinstance(parsed, dict):
            json_top_level = list(parsed.keys())[:30]
        elif isinstance(parsed, list):
            json_top_level = [f"[{len(parsed)} items]"]

    redirects = []
    if hasattr(response, "history"):
        redirects = [
            {
                "status_code": item.status_code,
                "url": item.url,
                "location": item.headers.get("location"),
            }
            for item in response.history
        ]

    return {
        "request": serialize_request_meta(
            method=method,
            url=url,
            headers=headers,
            cookies=cookies,
            warmup_urls=warmup_urls,
            http2=False,
            trust_env=False,
            backend=f"curl_cffi:{impersonate}",
        ),
        "response": serialize_response_meta(
            status_code=response.status_code,
            http_version=getattr(response, "http_version", None),
            headers=dict(response.headers),
            raw_body=raw_body,
            content_type=content_type,
            text=text,
            encoding=encoding,
            body_kind=body_kind,
            body_preview=body_preview,
            json_top_level=json_top_level,
            final_url=getattr(response, "url", url),
            redirect_history=redirects,
        ),
    }


def persist_replay(
    capture_dir: Path,
    candidate: dict[str, Any],
    replay_result: dict[str, Any],
    search_terms: dict[str, Any],
    *,
    label: str,
    save_raw: bool,
) -> Path:
    replays_dir = ensure_dir(capture_dir / "replays")
    prefix = f"replay-{label}-{candidate['id']}" if label else f"replay-{candidate['id']}"
    result_path = replays_dir / safe_filename_from_url(candidate["url"], prefix, ".json")

    response_payload = replay_result["response"]
    text = response_payload.pop("text", None)
    raw_body = response_payload.pop("raw_body", b"")
    if text is not None:
        body_path = replays_dir / safe_filename_from_url(candidate["url"], prefix, ".body.txt")
        body_path.write_text(text, encoding="utf-8")
        response_payload["body_path"] = str(body_path.relative_to(capture_dir))
        response_payload["text_hits"] = search_terms
    if save_raw:
        raw_path = replays_dir / safe_filename_from_url(candidate["url"], prefix, ".body.bin")
        raw_path.write_bytes(raw_body)
        response_payload["raw_body_path"] = str(raw_path.relative_to(capture_dir))

    write_json(result_path, replay_result)
    return result_path


async def main() -> int:
    args = parse_args()
    profile = normalize_profile(args.profile, args.header_profile)
    capture_dir = pick_capture_dir(args)
    candidate = select_candidate(capture_dir, record_id=args.record_id, url_contains=args.url_contains)
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
    if args.warmup or args.warmup_home:
        parsed = urlparse(candidate["url"])
        warmup_urls.insert(0, f"{parsed.scheme}://{parsed.netloc}/")

    if profile == "curl_cffi_chrome":
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
    else:
        replay_result = await replay_record(
            candidate,
            headers=headers,
            cookies=cookies,
            timeout=args.timeout,
            insecure=args.insecure,
            http2=args.http2,
            trust_env=args.trust_env,
            warmup_urls=warmup_urls,
            no_decode=args.no_decode,
        )

    search = build_search_context(args.contains, args.contains_fixture)
    text = replay_result["response"].get("text")
    text_hits = analyze_text_hits(text, search) if isinstance(text, str) else {}
    replay_result["candidate"] = {
        "id": candidate["id"],
        "url": candidate["url"],
        "query_params": [{"name": k, "value": v} for k, v in query_params_list(candidate["url"])],
        "captured_status": candidate.get("status"),
        "captured_body_hash": candidate.get("body_hash"),
        "captured_body_kind": candidate.get("body_kind"),
        "captured_resource_type": candidate.get("resource_type"),
        "captured_body_path": candidate.get("body_path"),
    }
    replay_result["comparison"] = {
        "same_status": candidate.get("status") == replay_result["response"]["status_code"],
        "same_body_hash": candidate.get("body_hash") == replay_result["response"]["body_hash"],
        "text_hits": text_hits,
    }

    label_parts = [profile]
    if args.no_cookies:
        label_parts.append("no-cookies")
    if args.http2:
        label_parts.append("http2")
    if args.trust_env:
        label_parts.append("trust-env")
    if args.label:
        label_parts.append(args.label)
    label = "-".join(label_parts)
    result_path = persist_replay(
        capture_dir,
        candidate,
        replay_result,
        text_hits,
        label=label,
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
    if text_hits:
        print("Hits:", text_hits)
    print(f"Replay guardado en: {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
