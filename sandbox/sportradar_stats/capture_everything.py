from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    Response,
    async_playwright,
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

BLOCKED_RESOURCE_TYPES = {
    "image",
    "font",
    "media",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_json_loads(raw: str) -> Any | None:
    raw = raw.strip()

    if not raw:
        return None

    if not (raw.startswith("{") or raw.startswith("[")):
        return None

    try:
        return json.loads(raw)
    except Exception:
        return None


async def build_context(
    playwright: Playwright,
    *,
    headless: bool,
    user_data_dir: str | None,
) -> BrowserContext:
    """
    Si user_data_dir está seteado:
    usa perfil persistente REAL de Chrome.

    Esto es MUY importante para bypass de 403/cookies.
    """

    chromium = playwright.chromium

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    if user_data_dir:
        context = await chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            viewport={"width": 1440, "height": 900},
            user_agent=USER_AGENT,
            locale="en-US",
            args=launch_args,
        )
        return context

    browser = await chromium.launch(
        headless=headless,
        args=launch_args,
    )

    return await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=USER_AGENT,
        locale="en-US",
    )


async def install_routes(context: BrowserContext) -> None:
    async def route_handler(route):
        request = route.request

        if request.resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort()
            return

        await route.continue_()

    await context.route("**/*", route_handler)


async def dump_storage_state(
    page: Page,
    out_dir: Path,
) -> None:
    try:
        local_storage = await page.evaluate(
            """
            () => {
                const out = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    out[k] = localStorage.getItem(k);
                }
                return out;
            }
            """
        )

        session_storage = await page.evaluate(
            """
            () => {
                const out = {};
                for (let i = 0; i < sessionStorage.length; i++) {
                    const k = sessionStorage.key(i);
                    out[k] = sessionStorage.getItem(k);
                }
                return out;
            }
            """
        )

        (out_dir / "local_storage.json").write_text(
            json.dumps(local_storage, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        (out_dir / "session_storage.json").write_text(
            json.dumps(session_storage, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    except Exception as exc:
        (out_dir / "storage_error.txt").write_text(str(exc))


async def capture_everything(
    stats_url: str,
    *,
    out_dir: Path,
    seconds: float,
    headless: bool,
    user_data_dir: str | None,
    bootstrap_url: str | None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    ndjson_path = out_dir / "responses.ndjson"

    async with async_playwright() as p:
        context = await build_context(
            p,
            headless=headless,
            user_data_dir=user_data_dir,
        )

        await install_routes(context)

        page = await context.new_page()

        responses_seen = 0
        requests_seen = 0

        started = time.monotonic()

        async def handle_response(response: Response) -> None:
            nonlocal responses_seen

            try:
                request = response.request

                body_text = ""

                try:
                    body_text = await response.text()
                except Exception as exc:
                    body_text = f"<<body read failed: {exc}>>"

                parsed_json = safe_json_loads(body_text)

                record = {
                    "captured_at": now_iso(),
                    "elapsed_ms": round(
                        (time.monotonic() - started) * 1000,
                        2,
                    ),
                    "url": response.url,
                    "host": urlparse(response.url).netloc,
                    "path": urlparse(response.url).path,
                    "query": urlparse(response.url).query,
                    "status": response.status,
                    "ok": response.ok,
                    "resource_type": request.resource_type,
                    "method": request.method,
                    "request_headers": await request.all_headers(),
                    "response_headers": response.headers,
                    "request_post_data": request.post_data,
                    "body_size": len(body_text.encode("utf-8")),
                    "body_json": parsed_json,
                    "body_preview": (
                        None
                        if parsed_json is not None
                        else body_text[:1000]
                    ),
                }

                with ndjson_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False))
                    f.write("\n")

                responses_seen += 1

                print(
                    f"[RESP {responses_seen}] "
                    f"{response.status} "
                    f"{request.resource_type:<8} "
                    f"{response.url[:140]}"
                )

            except Exception as exc:
                print(f"[response handler error] {exc}")

        async def handle_request(request) -> None:
            nonlocal requests_seen

            requests_seen += 1

            print(
                f"[REQ  {requests_seen}] "
                f"{request.method:<6} "
                f"{request.resource_type:<8} "
                f"{request.url[:140]}"
            )

        page.on("response", lambda r: asyncio.create_task(handle_response(r)))
        page.on("request", lambda r: asyncio.create_task(handle_request(r)))

        if bootstrap_url:
            print(f"\n→ bootstrap: {bootstrap_url}")
            await page.goto(
                bootstrap_url,
                wait_until="domcontentloaded",
                timeout=120000,
            )

            await asyncio.sleep(5)

        print(f"\n→ stats_url: {stats_url}")

        await page.goto(
            stats_url,
            wait_until="domcontentloaded",
            timeout=120000,
        )

        await asyncio.sleep(seconds)

        await dump_storage_state(page, out_dir)

        cookies = await context.cookies()

        (out_dir / "cookies.json").write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        metadata = {
            "stats_url": stats_url,
            "bootstrap_url": bootstrap_url,
            "captured_at": now_iso(),
            "responses_seen": responses_seen,
            "requests_seen": requests_seen,
            "seconds": seconds,
            "user_data_dir": user_data_dir,
        }

        (out_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        await context.close()


async def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("stats_url")

    parser.add_argument(
        "--bootstrap-url",
        default=None,
    )

    parser.add_argument(
        "--seconds",
        type=float,
        default=30,
    )

    parser.add_argument(
        "--out-dir",
        default="sandbox/sportradar_stats/captures/raw_capture",
    )

    parser.add_argument(
        "--headed",
        action="store_true",
    )

    parser.add_argument(
        "--user-data-dir",
        default=None,
        help=(
            "Perfil persistente REAL de Chrome/Chromium. "
            "MUY útil para evitar 403."
        ),
    )

    args = parser.parse_args()

    await capture_everything(
        args.stats_url,
        out_dir=Path(args.out_dir),
        seconds=args.seconds,
        headless=not args.headed,
        user_data_dir=args.user_data_dir,
        bootstrap_url=args.bootstrap_url,
    )


if __name__ == "__main__":
    asyncio.run(main())