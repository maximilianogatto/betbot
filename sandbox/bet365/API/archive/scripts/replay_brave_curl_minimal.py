from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


USEFUL_MARKERS = ["EV;", "MG;ID=40", "PA;", "FI=", "OD="]


def parse_curl_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    tokens = shlex.split(text)

    if not tokens or tokens[0] != "curl":
        raise ValueError("El archivo no parece ser un cURL válido.")

    url = None
    headers: dict[str, str] = {}
    method = "GET"
    data = None

    i = 1
    while i < len(tokens):
        token = tokens[i]

        if token in ("-H", "--header"):
            i += 1
            raw = tokens[i]
            if ":" in raw:
                k, v = raw.split(":", 1)
                headers[k.strip()] = v.strip()

        elif token in ("-X", "--request"):
            i += 1
            method = tokens[i].upper()

        elif token in ("--data", "--data-raw", "--data-binary", "-d"):
            i += 1
            data = tokens[i]
            method = "POST"

        elif token.startswith("http"):
            url = token

        i += 1

    if not url:
        raise ValueError("No encontré URL en el cURL.")

    return {
        "url": url,
        "method": method,
        "headers": headers,
        "data": data,
    }


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    sensitive = {"cookie", "authorization", "x-auth-token"}
    clean = {}
    for k, v in headers.items():
        if k.lower() in sensitive:
            clean[k] = "<redacted>"
        else:
            clean[k] = v
    return clean


def is_useful_body(body: bytes) -> bool:
    if not body:
        return False
    text = body.decode("utf-8", errors="ignore")
    return all(marker in text for marker in USEFUL_MARKERS)


def save_attempt(out_dir: Path, request_info: dict[str, Any], status: int | None, headers: dict[str, str], body: bytes, error: str | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "request_parsed.json").write_text(
        json.dumps(
            {
                **request_info,
                "headers": sanitize_headers(request_info.get("headers", {})),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    (out_dir / "response_headers.json").write_text(
        json.dumps(headers, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (out_dir / "response.raw").write_bytes(body)

    (out_dir / "response.txt").write_text(
        body.decode("utf-8", errors="replace"),
        encoding="utf-8",
    )

    summary = {
        "status": status,
        "error": error,
        "body_bytes": len(body),
        "useful": is_useful_body(body),
        "body_preview": body[:500].decode("utf-8", errors="replace"),
    }

    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_with_curl_cffi(request_info: dict[str, Any]) -> tuple[int, dict[str, str], bytes]:
    try:
        from curl_cffi import requests
    except ImportError as exc:
        raise RuntimeError("curl_cffi no está instalado.") from exc

    method = request_info["method"]
    url = request_info["url"]
    headers = request_info["headers"]
    data = request_info.get("data")

    response = requests.request(
        method,
        url,
        headers=headers,
        data=data,
        impersonate="chrome",
        timeout=30,
    )

    return response.status_code, dict(response.headers), response.content


def fetch_with_httpx(request_info: dict[str, Any]) -> tuple[int, dict[str, str], bytes]:
    import httpx

    method = request_info["method"]
    url = request_info["url"]
    headers = request_info["headers"]
    data = request_info.get("data")

    with httpx.Client(timeout=30, follow_redirects=True, http2=True) as client:
        response = client.request(method, url, headers=headers, content=data)

    return response.status_code, dict(response.headers), response.content


def run_parser(body_path: Path, host: str, parsed_out: Path) -> None:
    parser_path = Path(__file__).with_name("parse_markets_payload.py")

    if not parser_path.exists():
        print("⚠️ No encontré parse_markets_payload.py, salteo parseo.")
        return

    cmd = [
        sys.executable,
        str(parser_path),
        str(body_path),
        "--host",
        host,
        "--out",
        str(parsed_out),
    ]

    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("curl_file", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("sandbox/bet365/API/attempts"))
    parser.add_argument("--client", choices=["curl_cffi", "httpx", "both"], default="both")
    args = parser.parse_args()

    request_info = parse_curl_file(args.curl_file)
    host = urlparse(request_info["url"]).netloc or "www.bet365.es"

    stamp = time.strftime("%Y%m%d-%H%M%S")
    base_out = args.out_dir / stamp
    base_out.mkdir(parents=True, exist_ok=True)

    clients = ["curl_cffi", "httpx"] if args.client == "both" else [args.client]

    for client_name in clients:
        print(f"\n→ Probando con {client_name}...")
        client_out = base_out / client_name

        try:
            if client_name == "curl_cffi":
                status, headers, body = fetch_with_curl_cffi(request_info)
            else:
                status, headers, body = fetch_with_httpx(request_info)

            save_attempt(client_out, request_info, status, headers, body)

            useful = is_useful_body(body)

            print(f"   status={status}")
            print(f"   bytes={len(body)}")
            print(f"   useful={useful}")

            if useful:
                parsed_out = client_out / "parsed_market.json"
                run_parser(client_out / "response.raw", host, parsed_out)
                print(f"   ✅ Parseado en: {parsed_out}")
            else:
                print(f"   ⚠️ Body no útil. Ver: {client_out / 'summary.json'}")

        except Exception as exc:
            save_attempt(client_out, request_info, None, {}, b"", error=str(exc))
            print(f"   ❌ Error: {exc}")

    print(f"\n→ Intentos guardados en: {base_out}")


if __name__ == "__main__":
    main()