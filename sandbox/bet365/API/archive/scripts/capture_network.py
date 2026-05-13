from __future__ import annotations

import argparse
import asyncio
import os
import socket
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, async_playwright

from common import (
    analyze_text_hits,
    append_jsonl,
    build_search_context,
    decode_body,
    ensure_dir,
    extract_bet365_identifiers,
    guess_body_kind,
    infer_capture_slug,
    now_ts,
    safe_filename_from_url,
    score_record,
    sha256_bytes,
    slugify,
    summarize_header_subset,
    truncate,
    try_parse_json,
    write_json,
)

DEFAULT_CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEFAULT_REMOTE_DEBUG_PORT = 9222


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Captura tráfico de red y WebSocket de Bet365 para investigar endpoints reutilizables.",
    )
    parser.add_argument("url", help="URL de liga o evento Bet365 a inspeccionar.")
    parser.add_argument(
        "--contains",
        action="append",
        default=[],
        help="String a buscar en respuestas. Se puede repetir.",
    )
    parser.add_argument(
        "--contains-fixture",
        action="append",
        default=[],
        help="Fixture/event ID a buscar en respuestas. Se puede repetir.",
    )
    parser.add_argument(
        "--capture-root",
        default="sandbox/bet365/API/captures",
        help="Directorio donde se guarda la captura.",
    )
    parser.add_argument(
        "--capture-prefix",
        default="",
        help="Prefijo opcional para distinguir corridas, por ejemplo no_vpn.",
    )
    parser.add_argument(
        "--wait-ms",
        type=int,
        default=15000,
        help="Tiempo de observación después de navegar, en ms.",
    )
    parser.add_argument(
        "--navigation-timeout-ms",
        type=int,
        default=60000,
        help="Timeout de navegación inicial.",
    )
    parser.add_argument(
        "--network-idle-timeout-ms",
        type=int,
        default=5000,
        help="Timeout opcional para intentar esperar networkidle.",
    )
    parser.add_argument(
        "--max-body-bytes",
        type=int,
        default=2_500_000,
        help="Límite para guardar bodies completos en disco.",
    )
    parser.add_argument(
        "--max-preview-chars",
        type=int,
        default=1500,
        help="Máximo de caracteres inline en el preview.",
    )
    parser.add_argument(
        "--browser-mode",
        choices=("connect", "launch"),
        default="connect",
        help="connect: CDP a Chrome real. launch: Chromium/Chrome lanzado por Playwright.",
    )
    parser.add_argument(
        "--cdp-endpoint",
        default=f"http://127.0.0.1:{DEFAULT_REMOTE_DEBUG_PORT}",
        help="Endpoint CDP cuando browser-mode=connect.",
    )
    parser.add_argument(
        "--launch-chrome-if-needed",
        action="store_true",
        help="Si no hay Chrome escuchando en el puerto CDP, lo lanza con remote debugging.",
    )
    parser.add_argument(
        "--chrome-path",
        default=DEFAULT_CHROME_PATH,
        help="Path de Chrome real para connect/launch.",
    )
    parser.add_argument(
        "--user-data-dir",
        default="/tmp/chrome-bet365-network-capture",
        help="Perfil de usuario a usar si se lanza Chrome real.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Muestra la ventana al usar browser-mode=launch.",
    )
    parser.add_argument(
        "--channel",
        default="chrome",
        help="Channel de Playwright para browser-mode=launch.",
    )
    parser.add_argument(
        "--save-all-bodies",
        action="store_true",
        help="Guardar todos los bodies textuales por debajo del límite.",
    )
    parser.add_argument(
        "--save-har",
        action="store_true",
        help="Guardar HAR si el modo de navegador lo soporta.",
    )
    return parser.parse_args()


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def launch_chrome_if_needed(args: argparse.Namespace) -> subprocess.Popen[bytes] | None:
    if args.browser_mode != "connect" or not args.launch_chrome_if_needed:
        return None

    parsed = args.cdp_endpoint.removeprefix("http://").removeprefix("https://")
    host, _, port_str = parsed.partition(":")
    port = int(port_str or DEFAULT_REMOTE_DEBUG_PORT)

    if is_port_open(host or "127.0.0.1", port):
        return None

    chrome_path = Path(args.chrome_path)
    if not chrome_path.exists():
        raise FileNotFoundError(f"No encontré Chrome en {chrome_path}")

    cmd = [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={args.user_data_dir}",
    ]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


async def wait_for_cdp_endpoint(endpoint: str, timeout_s: float = 20.0) -> None:
    parsed = endpoint.removeprefix("http://").removeprefix("https://")
    host, _, port_str = parsed.partition(":")
    host = host or "127.0.0.1"
    port = int(port_str or DEFAULT_REMOTE_DEBUG_PORT)

    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if is_port_open(host, port):
            return
        await asyncio.sleep(0.25)

    raise TimeoutError(f"No abrió el endpoint CDP {endpoint} dentro de {timeout_s:.1f}s")


class CaptureSession:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.search = build_search_context(args.contains, args.contains_fixture)
        capture_name = f"{int(now_ts())}-{infer_capture_slug(args.url)}"
        if args.capture_prefix:
            capture_name = f"{slugify(args.capture_prefix)}_{capture_name}"
        self.capture_dir = ensure_dir(
            Path(args.capture_root) / capture_name
        )
        self.bodies_dir = ensure_dir(self.capture_dir / "bodies")
        self.network_path = self.capture_dir / "network.jsonl"
        self.metadata_path = self.capture_dir / "metadata.json"
        self.summary_path = self.capture_dir / "summary.json"
        self.cookies_path = self.capture_dir / "cookies.json"
        self.records_written = 0
        self.response_counter = 0
        self.ws_counter = 0
        self.pending_tasks: set[asyncio.Task[Any]] = set()
        self.counts = Counter()
        self.best_records: list[dict[str, Any]] = []

    def schedule(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self.pending_tasks.add(task)
        task.add_done_callback(self.pending_tasks.discard)

    def write_record(self, record: dict[str, Any]) -> None:
        self.records_written += 1
        append_jsonl(self.network_path, record)
        self.counts[record.get("type", "unknown")] += 1

        record_score = score_record(record)
        if record_score <= 0:
            return

        candidate = {
            "score": record_score,
            "type": record.get("type"),
            "url": record.get("url"),
            "status": record.get("status"),
            "resource_type": record.get("resource_type"),
            "body_kind": record.get("body_kind"),
            "body_path": record.get("body_path"),
            "text_hits": record.get("text_hits"),
        }
        self.best_records.append(candidate)
        self.best_records = sorted(self.best_records, key=lambda item: item["score"], reverse=True)[:25]

    async def handle_response(self, response: Any) -> None:
        request = response.request
        self.response_counter += 1
        record_id = f"response-{self.response_counter:05d}"

        request_headers: dict[str, str] = {}
        response_headers: dict[str, str] = {}
        try:
            request_headers = await request.all_headers()
        except PlaywrightError:
            request_headers = {}
        try:
            response_headers = await response.all_headers()
        except PlaywrightError:
            response_headers = {}

        content_type = response_headers.get("content-type", "")
        request_post_data = request.post_data

        raw_body = b""
        body_error: str | None = None
        try:
            raw_body = await response.body()
        except PlaywrightError as error:
            body_error = str(error)

        body_hash = sha256_bytes(raw_body) if raw_body else None
        text, body_encoding = decode_body(raw_body, content_type)
        text_hits: dict[str, Any] = {
            "contains_terms": [],
            "markers": [],
            "fixture_ids": [],
            "market_ids": [],
        }
        body_kind: str | None = None
        body_preview: str | None = None
        body_path: str | None = None
        json_top_level: list[str] | None = None

        if text is not None:
            body_kind = guess_body_kind(text, content_type)
            body_preview = truncate(text, limit=self.args.max_preview_chars)
            text_hits = analyze_text_hits(text, self.search)
            parsed_json = try_parse_json(text) if body_kind == "json_like" else None
            if isinstance(parsed_json, dict):
                json_top_level = list(parsed_json.keys())[:30]
            elif isinstance(parsed_json, list):
                json_top_level = [f"[{len(parsed_json)} items]"]

            should_save = (
                self.args.save_all_bodies
                or body_kind in {"json_like", "script"}
                or any(text_hits.values())
            )
            if should_save and len(raw_body) <= self.args.max_body_bytes:
                suffix = ".json" if body_kind == "json_like" else ".txt"
                file_name = safe_filename_from_url(response.url, record_id, suffix)
                target_path = self.bodies_dir / file_name
                target_path.write_text(text, encoding="utf-8")
                body_path = str(target_path.relative_to(self.capture_dir))
        elif raw_body and len(raw_body) <= self.args.max_body_bytes:
            body_path = str((self.bodies_dir / safe_filename_from_url(response.url, record_id, ".bin")).relative_to(self.capture_dir))
            (self.capture_dir / body_path).write_bytes(raw_body)

        record = {
            "id": record_id,
            "type": "response",
            "timestamp": now_ts(),
            "url": response.url,
            "method": request.method,
            "status": response.status,
            "resource_type": request.resource_type,
            "request_headers": summarize_header_subset(request_headers, kind="request"),
            "request_post_data": request_post_data,
            "response_headers": summarize_header_subset(response_headers, kind="response"),
            "content_type": content_type,
            "body_size": len(raw_body),
            "body_hash": body_hash,
            "body_encoding": body_encoding,
            "body_kind": body_kind,
            "body_preview": body_preview,
            "body_path": body_path,
            "body_error": body_error,
            "json_top_level": json_top_level,
            "text_hits": text_hits,
        }
        self.write_record(record)

    def handle_request_failed(self, request: Any) -> None:
        self.write_record(
            {
                "id": f"request-failed-{self.records_written + 1:05d}",
                "type": "request_failed",
                "timestamp": now_ts(),
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "failure": request.failure,
            }
        )

    def handle_websocket_event(self, event_type: str, params: dict[str, Any]) -> None:
        self.ws_counter += 1
        payload = ""
        if isinstance(params.get("response"), dict):
            payload = str(params["response"].get("payloadData") or "")

        text_hits = analyze_text_hits(payload, self.search) if payload else {
            "contains_terms": [],
            "markers": [],
            "fixture_ids": [],
            "market_ids": [],
        }

        preview = truncate(payload, limit=self.args.max_preview_chars) if payload else None
        record = {
            "id": f"ws-{self.ws_counter:05d}",
            "type": "websocket_frame" if "Frame" in event_type else "websocket_event",
            "timestamp": now_ts(),
            "event_type": event_type,
            "url": params.get("url"),
            "request_id": params.get("requestId"),
            "opcode": params.get("response", {}).get("opcode") if isinstance(params.get("response"), dict) else None,
            "payload_size": len(payload.encode("utf-8")) if payload else 0,
            "body_kind": "websocket_text" if payload else None,
            "body_preview": preview,
            "text_hits": text_hits,
        }

        if payload and len(payload.encode("utf-8")) <= self.args.max_body_bytes and any(text_hits.values()):
            target = self.bodies_dir / safe_filename_from_url(
                params.get("url") or "websocket",
                record["id"],
                ".txt",
            )
            target.write_text(payload, encoding="utf-8")
            record["body_path"] = str(target.relative_to(self.capture_dir))

        self.write_record(record)

    async def finalize(self, context: Any) -> None:
        if self.pending_tasks:
            await asyncio.gather(*self.pending_tasks, return_exceptions=True)

        cookies = await context.cookies()
        write_json(self.cookies_path, cookies)
        write_json(
            self.summary_path,
            {
                "capture_dir": str(self.capture_dir),
                "records_written": self.records_written,
                "counts": dict(self.counts),
                "top_candidates": self.best_records,
            },
        )


async def open_browser(args: argparse.Namespace) -> tuple[Any, Any, Any]:
    playwright = await async_playwright().start()

    if args.browser_mode == "connect":
        await wait_for_cdp_endpoint(args.cdp_endpoint)
        browser = await playwright.chromium.connect_over_cdp(args.cdp_endpoint)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()
        return playwright, browser, context, page

    browser = await playwright.chromium.launch(
        headless=not args.headed,
        channel=args.channel or None,
    )
    context_kwargs: dict[str, Any] = {}
    if args.save_har:
        context_kwargs["record_har_path"] = str(
            Path(args.capture_root) / f"{slugify(args.capture_prefix or 'har')}-{infer_capture_slug(args.url)}.har"
        )
    context = await browser.new_context(**context_kwargs)
    page = await context.new_page()
    return playwright, browser, context, page


async def attach_cdp_websocket_capture(context: Any, page: Page, session: CaptureSession) -> Any | None:
    try:
        cdp = await context.new_cdp_session(page)
    except PlaywrightError:
        return None

    await cdp.send("Network.enable")

    for event_name in (
        "Network.webSocketCreated",
        "Network.webSocketWillSendHandshakeRequest",
        "Network.webSocketHandshakeResponseReceived",
        "Network.webSocketFrameSent",
        "Network.webSocketFrameReceived",
        "Network.webSocketClosed",
    ):
        cdp.on(event_name, lambda params, event_name=event_name: session.handle_websocket_event(event_name, params))

    return cdp


async def main() -> int:
    args = parse_args()
    capture = CaptureSession(args)

    launch_process = launch_chrome_if_needed(args)

    metadata = {
        "target_url": args.url,
        "capture_dir": str(capture.capture_dir),
        "search_terms": list(capture.search.contains_terms),
        "fixture_ids": list(capture.search.fixture_ids),
        "identifiers": extract_bet365_identifiers(args.url),
        "browser_mode": args.browser_mode,
        "cdp_endpoint": args.cdp_endpoint if args.browser_mode == "connect" else None,
        "save_har": args.save_har,
        "har_supported": args.save_har and args.browser_mode != "connect",
        "pid": os.getpid(),
        "argv": sys.argv,
    }
    write_json(capture.metadata_path, metadata)

    playwright = browser = context = page = None
    try:
        playwright, browser, context, page = await open_browser(args)
        await attach_cdp_websocket_capture(context, page, capture)

        page.on("response", lambda response: capture.schedule(capture.handle_response(response)))
        page.on("requestfailed", capture.handle_request_failed)

        await page.goto(args.url, wait_until="domcontentloaded", timeout=args.navigation_timeout_ms)

        try:
            await page.wait_for_load_state("networkidle", timeout=args.network_idle_timeout_ms)
        except PlaywrightError:
            pass

        await page.wait_for_timeout(args.wait_ms)
        await capture.finalize(context)
    finally:
        if page is not None:
            await page.close()
        if context is not None and args.browser_mode != "connect":
            await context.close()
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()
        if launch_process is not None:
            launch_process.terminate()

    print(f"Captura guardada en: {capture.capture_dir}")
    print(f"Registros: {capture.records_written}")
    print(f"Tipos: {dict(capture.counts)}")
    if capture.best_records:
        print("Top candidatos:")
        for item in capture.best_records[:10]:
            print(
                f"  score={item['score']:>3} type={item['type']:<16} "
                f"resource={item.get('resource_type') or '-':<10} status={item.get('status') or '-':<3} "
                f"url={item['url']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
