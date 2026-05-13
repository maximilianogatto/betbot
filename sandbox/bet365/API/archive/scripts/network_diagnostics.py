from __future__ import annotations

import argparse
import asyncio
import os
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from common import ensure_dir, now_ts, truncate, write_json

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnóstico de red para comparar corridas Bet365 con y sin VPN/proxy.",
    )
    parser.add_argument("--host-url", default="https://www.bet365.es/")
    parser.add_argument("--dns-host", default="www.bet365.es")
    parser.add_argument("--ip-url", default="https://api.ipify.org?format=json")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--output-root",
        default="sandbox/bet365/API/diagnostics",
        help="Directorio donde guardar el reporte.",
    )
    parser.add_argument("--label", default="", help="Etiqueta opcional, por ejemplo no_vpn.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    return parser.parse_args()


def masked_proxy_env() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        raw = os.environ.get(key)
        if not raw:
            result[key] = {"present": False, "preview": None}
            continue

        parsed = urlparse(raw)
        if parsed.scheme and parsed.hostname:
            preview = f"{parsed.scheme}://{parsed.hostname}"
            if parsed.port:
                preview += f":{parsed.port}"
        else:
            preview = "<set>"
        result[key] = {"present": True, "preview": preview}
    return result


def resolve_dns(host: str) -> dict[str, Any]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as error:
        return {"ok": False, "error": str(error), "addresses": []}

    addresses = sorted({item[4][0] for item in infos if item and len(item) >= 5 and item[4]})
    return {"ok": True, "addresses": addresses}


async def fetch_probe(
    url: str,
    *,
    timeout: float,
    user_agent: str,
    trust_env: bool,
) -> dict[str, Any]:
    headers = {
        "user-agent": user_agent,
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "es-ES,es;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
    }
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
            trust_env=trust_env,
        ) as client:
            response = await client.get(url)
        return {
            "ok": True,
            "url": str(response.request.url),
            "status_code": response.status_code,
            "http_version": response.http_version,
            "content_type": response.headers.get("content-type"),
            "server": response.headers.get("server"),
            "cf_ray": response.headers.get("cf-ray"),
            "body_preview": truncate(response.text, limit=300),
        }
    except Exception as error:  # pragma: no cover - diagnostics only
        return {
            "ok": False,
            "url": url,
            "error_type": error.__class__.__name__,
            "error": str(error),
        }


async def main() -> int:
    args = parse_args()
    timestamp = int(now_ts())
    base_name = f"{timestamp}-network-diagnostics"
    if args.label:
        base_name = f"{args.label}_{base_name}"
    output_dir = ensure_dir(Path(args.output_root))
    output_path = output_dir / f"{base_name}.json"

    report = {
        "timestamp": timestamp,
        "label": args.label or None,
        "host_url": args.host_url,
        "dns_host": args.dns_host,
        "user_agent": args.user_agent,
        "proxy_env": masked_proxy_env(),
        "dns": resolve_dns(args.dns_host),
    }

    report["bet365_direct"] = await fetch_probe(
        args.host_url,
        timeout=args.timeout,
        user_agent=args.user_agent,
        trust_env=False,
    )
    report["bet365_trust_env"] = await fetch_probe(
        args.host_url,
        timeout=args.timeout,
        user_agent=args.user_agent,
        trust_env=True,
    )
    report["public_ip_direct"] = await fetch_probe(
        args.ip_url,
        timeout=args.timeout,
        user_agent=args.user_agent,
        trust_env=False,
    )
    report["public_ip_trust_env"] = await fetch_probe(
        args.ip_url,
        timeout=args.timeout,
        user_agent=args.user_agent,
        trust_env=True,
    )

    write_json(output_path, report)
    print(f"Diagnóstico guardado en: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
