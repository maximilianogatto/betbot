from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.async_api import BrowserContext, Request, Response, async_playwright


DEFAULT_ORIGIN = "https://statshub.sportradar.com"
DEFAULT_REFERER = DEFAULT_ORIGIN + "/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
DEFAULT_BOOTSTRAP_URLS = (
    "https://statshub.sportradar.com/bet365/en/sport/1",
    "https://statshub.sportradar.com/bet365/en/match/61624678",
)
STATIC_RESOURCE_TYPES = {"font", "image", "media"}
IMPORTANT_HEADERS = {
    "accept",
    "accept-language",
    "content-type",
    "origin",
    "referer",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "user-agent",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_json_loads(raw: str) -> object | None:
    text = raw.strip()
    if not text or text[0] not in "{[":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def select_important_headers(headers: dict[str, str] | None) -> dict[str, str]:
    selected: dict[str, str] = {}
    for raw_key, raw_value in (headers or {}).items():
        key = str(raw_key).strip().lower()
        value = str(raw_value).strip()
        if not key or not value:
            continue
        if key in IMPORTANT_HEADERS or key.startswith("x-"):
            selected[key] = value
    return dict(sorted(selected.items()))


def extract_gismo_endpoint_key(url: str) -> str | None:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if "gismo" not in parts:
        return None
    index = parts.index("gismo")
    if index + 1 >= len(parts):
        return None
    return parts[index + 1]


def parse_signed_t(raw_t: str | None) -> dict[str, Any] | None:
    raw = str(raw_t or "").strip()
    if not raw:
        return None
    parts: dict[str, str] = {}
    for segment in raw.split("~"):
        if "=" not in segment:
            continue
        key, value = segment.split("=", 1)
        parts[key] = value
    exp = _safe_int(parts.get("exp"))
    return {
        "raw": raw,
        "exp": exp,
        "expires_at_utc": datetime.fromtimestamp(exp, tz=UTC).isoformat() if exp else None,
        "acl": parts.get("acl"),
        "data_raw": parts.get("data"),
        "data_json": decode_token_data(parts.get("data")),
        "hmac": parts.get("hmac"),
    }


def parse_signed_t_from_url(url: str) -> dict[str, Any] | None:
    values = parse_qs(urlparse(url).query).get("T")
    if not values:
        return None
    return parse_signed_t(values[0])


def decode_token_data(raw_data: str | None) -> object | None:
    raw = str(raw_data or "").strip()
    if not raw:
        return None
    padded = raw + "=" * (-len(raw) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            decoded = decoder(padded.encode("utf-8")).decode("utf-8")
            return safe_json_loads(decoded) or {"decoded_text": decoded}
        except Exception:
            continue
    return None


def is_blocked_payload(body_json: object | None, body_text: str = "") -> bool:
    if isinstance(body_json, dict):
        doc = body_json.get("doc")
        if isinstance(doc, list) and doc and isinstance(doc[0], dict):
            first = doc[0]
            data = first.get("data") if isinstance(first.get("data"), dict) else {}
            event = str(first.get("event") or "").lower()
            name = str(data.get("name") or "").lower()
            message = str(data.get("message") or "").lower()
            code = data.get("code")
            if event == "exception" or name in {"unauthorized", "forbidden"}:
                return True
            if code in {401, 403}:
                return True
            if "origin" in message and "check" in message:
                return True
    preview = body_text[:600].lower()
    return "access denied" in preview or "forbidden" in preview or "unauthorized" in preview


def is_expired_payload(body_json: object | None, body_text: str = "") -> bool:
    if isinstance(body_json, dict):
        text = json.dumps(body_json, ensure_ascii=False).lower()
    else:
        text = body_text[:1000].lower()
    return "expired" in text and ("token" in text or "signature" in text or "hmac" in text)


@dataclass(slots=True)
class SignedToken:
    raw: str
    exp: int | None = None
    expires_at_utc: str | None = None
    acl: str | None = None
    data_json: object | None = None
    hmac: str | None = None

    @classmethod
    def from_url(cls, url: str) -> "SignedToken | None":
        parsed = parse_signed_t_from_url(url)
        if not parsed:
            return None
        return signed_token_from_parsed(parsed)

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any] | None) -> "SignedToken | None":
        if not isinstance(payload, dict) or not payload.get("raw"):
            return None
        return cls(
            raw=str(payload.get("raw") or ""),
            exp=_safe_int(payload.get("exp")),
            expires_at_utc=payload.get("expires_at_utc"),
            acl=payload.get("acl"),
            data_json=payload.get("data_json"),
            hmac=payload.get("hmac"),
        )

    def seconds_until_expiration(self, now: datetime | None = None) -> float | None:
        if not self.exp:
            return None
        reference = now or datetime.now(UTC)
        return float(self.exp - reference.timestamp())

    def is_expired(self, *, skew_seconds: float = 60.0) -> bool:
        seconds_left = self.seconds_until_expiration()
        return seconds_left is not None and seconds_left <= skew_seconds


@dataclass(slots=True)
class BootstrapConfig:
    bootstrap_urls: tuple[str, ...] = DEFAULT_BOOTSTRAP_URLS
    headed: bool = False
    seconds_per_url: float = 5.0
    wait_between_urls: float = 0.5
    user_data_dir: str | None = None
    timeout_ms: int = 45000
    block_heavy_resources: bool = True

    @property
    def headless(self) -> bool:
        return not self.headed


@dataclass(slots=True)
class CapturedEndpoint:
    endpoint_key: str
    url: str
    status: int | None
    body_size_bytes: int
    blocked: bool
    expired: bool
    elapsed_ms: float


@dataclass(slots=True)
class SportradarSessionState:
    generated_at: str
    headed: bool
    headless: bool
    bootstrap_urls: list[str]
    origin: str
    referer: str
    replay_headers: dict[str, str]
    cookies: dict[str, str]
    signed_token: SignedToken | None
    sample_signed_url: str | None
    endpoints_seen: list[str] = field(default_factory=list)
    captured_endpoints: list[CapturedEndpoint] = field(default_factory=list)
    document_statuses: dict[str, int] = field(default_factory=dict)
    fetch_count: int = 0
    blocked_count: int = 0
    expired_count: int = 0
    error: str | None = None

    def token_expiration(self) -> str | None:
        return self.signed_token.expires_at_utc if self.signed_token else None

    def is_usable(self) -> bool:
        return self.signed_token is not None and not self.signed_token.is_expired() and self.blocked_count == 0

    def to_json_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["is_usable"] = self.is_usable()
        payload["token_expiration"] = self.token_expiration()
        return payload

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> "SportradarSessionState":
        return cls(
            generated_at=str(payload.get("generated_at") or utc_now_iso()),
            headed=bool(payload.get("headed")),
            headless=bool(payload.get("headless")),
            bootstrap_urls=[str(item) for item in payload.get("bootstrap_urls") or []],
            origin=str(payload.get("origin") or DEFAULT_ORIGIN),
            referer=str(payload.get("referer") or DEFAULT_REFERER),
            replay_headers={str(k): str(v) for k, v in (payload.get("replay_headers") or {}).items()},
            cookies={str(k): str(v) for k, v in (payload.get("cookies") or {}).items()},
            signed_token=SignedToken.from_json_dict(payload.get("signed_token")),
            sample_signed_url=payload.get("sample_signed_url"),
            endpoints_seen=[str(item) for item in payload.get("endpoints_seen") or []],
            captured_endpoints=[
                CapturedEndpoint(
                    endpoint_key=str(item.get("endpoint_key") or ""),
                    url=str(item.get("url") or ""),
                    status=_safe_int(item.get("status")),
                    body_size_bytes=_safe_int(item.get("body_size_bytes")) or 0,
                    blocked=bool(item.get("blocked")),
                    expired=bool(item.get("expired")),
                    elapsed_ms=float(item.get("elapsed_ms") or 0),
                )
                for item in payload.get("captured_endpoints") or []
                if isinstance(item, dict)
            ],
            document_statuses={str(k): int(v) for k, v in (payload.get("document_statuses") or {}).items()},
            fetch_count=_safe_int(payload.get("fetch_count")) or 0,
            blocked_count=_safe_int(payload.get("blocked_count")) or 0,
            expired_count=_safe_int(payload.get("expired_count")) or 0,
            error=payload.get("error"),
        )


class SportradarSessionManager:
    """Owns browser bootstrap and exposes HTTP replay session state.

    This class intentionally separates browser bootstrap from HTTP replay. It
    uses Playwright only inside `refresh_session_async`; `get_http_session`
    returns an `httpx.Client` configured with captured replay headers/cookies.
    """

    def __init__(self, config: BootstrapConfig | None = None) -> None:
        self.config = config or BootstrapConfig()
        self.state: SportradarSessionState | None = None

    def token_expiration(self) -> str | None:
        return self.state.token_expiration() if self.state else None

    def refresh_session(self) -> SportradarSessionState:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.state = asyncio.run(self.refresh_session_async())
            return self.state
        raise RuntimeError("Use refresh_session_async() from inside an active event loop.")

    async def refresh_session_async(self) -> SportradarSessionState:
        self.state = await bootstrap_sportradar_session(self.config)
        return self.state

    def get_http_session(self, *, refresh_if_needed: bool = True) -> httpx.Client:
        if refresh_if_needed and (self.state is None or not self.state.is_usable()):
            self.refresh_session()
        if self.state is None:
            raise RuntimeError("No Sportradar session available. Call refresh_session() first.")
        return httpx.Client(
            headers=self.state.replay_headers,
            cookies=self.state.cookies,
            timeout=20.0,
            follow_redirects=True,
        )


async def bootstrap_sportradar_session(config: BootstrapConfig) -> SportradarSessionState:
    generated_at = utc_now_iso()
    captured: list[CapturedEndpoint] = []
    document_statuses: dict[str, int] = {}
    request_headers_by_url: dict[str, dict[str, str]] = {}
    token: SignedToken | None = None
    sample_signed_url: str | None = None
    endpoints_seen: list[str] = []
    blocked_count = 0
    expired_count = 0
    fetch_count = 0
    error: str | None = None
    started_at = time.monotonic()

    async with async_playwright() as playwright:
        user_data_dir = config.user_data_dir or tempfile.mkdtemp(prefix="sportradar-http-profile-")
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir,
            headless=config.headless,
            user_agent=DEFAULT_USER_AGENT,
            viewport={"width": 1365, "height": 900},
        )
        try:
            context.set_default_timeout(config.timeout_ms)
            if config.block_heavy_resources:
                await context.route("**/*", _route_static_resources)
            page = await context.new_page()

            async def on_request(request: Request) -> None:
                try:
                    request_headers_by_url[request.url] = select_important_headers(await request.all_headers())
                except Exception:
                    request_headers_by_url[request.url] = {}

            async def on_response(response: Response) -> None:
                nonlocal token, sample_signed_url, blocked_count, expired_count, fetch_count
                url = response.url
                endpoint_key = extract_gismo_endpoint_key(url)
                resource_type = response.request.resource_type
                if resource_type == "document" and "statshub.sportradar.com" in urlparse(url).netloc:
                    document_statuses[url] = response.status
                if endpoint_key is None:
                    return
                fetch_count += 1
                body_text = ""
                try:
                    body_text = await response.text()
                except Exception:
                    body_text = ""
                body_json = safe_json_loads(body_text)
                blocked = is_blocked_payload(body_json, body_text)
                expired = is_expired_payload(body_json, body_text)
                blocked_count += int(blocked)
                expired_count += int(expired)
                if endpoint_key not in endpoints_seen:
                    endpoints_seen.append(endpoint_key)
                parsed_token = SignedToken.from_url(url)
                if parsed_token is not None and token is None:
                    token = parsed_token
                    sample_signed_url = url
                captured.append(
                    CapturedEndpoint(
                        endpoint_key=endpoint_key,
                        url=url,
                        status=response.status,
                        body_size_bytes=len(body_text.encode("utf-8")),
                        blocked=blocked,
                        expired=expired,
                        elapsed_ms=round((time.monotonic() - started_at) * 1000, 2),
                    )
                )

            page.on("request", on_request)
            page.on("response", on_response)
            for url in config.bootstrap_urls:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=config.timeout_ms)
                    await page.wait_for_timeout(int(config.seconds_per_url * 1000))
                    await page.wait_for_timeout(int(config.wait_between_urls * 1000))
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
            await page.close()
            cookies = {cookie["name"]: cookie["value"] for cookie in await context.cookies() if cookie.get("name")}
        finally:
            await context.close()

    replay_headers = build_replay_headers(request_headers_by_url)
    return SportradarSessionState(
        generated_at=generated_at,
        headed=config.headed,
        headless=config.headless,
        bootstrap_urls=list(config.bootstrap_urls),
        origin=DEFAULT_ORIGIN,
        referer=DEFAULT_REFERER,
        replay_headers=replay_headers,
        cookies=cookies,
        signed_token=token,
        sample_signed_url=sample_signed_url,
        endpoints_seen=endpoints_seen,
        captured_endpoints=captured,
        document_statuses=document_statuses,
        fetch_count=fetch_count,
        blocked_count=blocked_count,
        expired_count=expired_count,
        error=error,
    )


async def _route_static_resources(route: Any) -> None:
    request = route.request
    if request.resource_type in STATIC_RESOURCE_TYPES:
        await route.abort()
        return
    await route.continue_()


def build_replay_headers(request_headers_by_url: dict[str, dict[str, str]] | None = None) -> dict[str, str]:
    headers = {
        "accept": "application/json,text/plain,*/*",
        "origin": DEFAULT_ORIGIN,
        "referer": DEFAULT_REFERER,
        "user-agent": DEFAULT_USER_AGENT,
    }
    for request_headers in (request_headers_by_url or {}).values():
        for key in ("accept-language", "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site"):
            if key in request_headers:
                headers[key] = request_headers[key]
    return dict(sorted(headers.items()))


def signed_token_from_parsed(parsed: dict[str, Any]) -> SignedToken:
    return SignedToken(
        raw=str(parsed.get("raw") or ""),
        exp=_safe_int(parsed.get("exp")),
        expires_at_utc=parsed.get("expires_at_utc"),
        acl=parsed.get("acl"),
        data_json=parsed.get("data_json"),
        hmac=parsed.get("hmac"),
    )


def load_session_state(path: Path) -> SportradarSessionState:
    return SportradarSessionState.from_json_dict(json.loads(path.read_text(encoding="utf-8")))


def save_session_state(state: SportradarSessionState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def render_session_bootstrap_report(states: list[SportradarSessionState]) -> str:
    lines = [
        "# Sportradar Session Bootstrap Report",
        "",
        f"- Generated at: `{utc_now_iso()}`",
        f"- Runs: `{len(states)}`",
        "",
        "## Summary",
        "",
    ]
    for state in states:
        mode = "headed" if state.headed else "headless"
        token = state.signed_token
        lines.extend(
            [
                f"### `{mode}`",
                "",
                f"- Usable for HTTP replay: `{state.is_usable()}`",
                f"- Token expiration UTC: `{state.token_expiration()}`",
                f"- Token ACL: `{token.acl if token else None}`",
                f"- Token data: `{token.data_json if token else None}`",
                f"- Document statuses: `{state.document_statuses}`",
                f"- Fetch/gismo responses: `{state.fetch_count}`",
                f"- Blocked payloads: `{state.blocked_count}`",
                f"- Expired payloads: `{state.expired_count}`",
                f"- Endpoints seen: `{state.endpoints_seen}`",
                f"- Error: `{state.error}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Operational Notes",
            "",
            "- Browser bootstrap and HTTP replay are intentionally separate.",
            "- `origin` and `referer` are mandatory replay headers based on prior probes.",
            "- Headless may receive 403 at the document/bootstrap layer; headed is kept as fallback evidence.",
            "- No token signing is attempted here. The manager only captures and reuses valid signed URLs.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_session_artifacts(states: list[SportradarSessionState], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for state in states:
        mode = "headed" if state.headed else "headless"
        (out_dir / f"session_state_{mode}.json").write_text(
            json.dumps(state.to_json_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (out_dir / "session_bootstrap_report.md").write_text(
        render_session_bootstrap_report(states),
        encoding="utf-8",
    )


def _safe_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap Statshub/Sportradar HTTP replay session.")
    parser.add_argument("--url", action="append", dest="urls", help="Bootstrap URL. Can be passed multiple times.")
    parser.add_argument("--out-dir", type=Path, default=Path("sandbox/sportradar_http/reports"))
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--wait-between", type=float, default=0.5)
    parser.add_argument("--user-data-dir")
    parser.add_argument("--headed", action="store_true", help="Run only headed bootstrap.")
    parser.add_argument("--headless", action="store_true", help="Run only headless bootstrap.")
    parser.add_argument("--compare", action="store_true", help="Run headless and headed bootstrap.")
    parser.add_argument("--no-block-heavy-resources", action="store_true")
    return parser.parse_args()


async def run_cli_async(args: argparse.Namespace) -> int:
    urls = tuple(args.urls or DEFAULT_BOOTSTRAP_URLS)
    if args.compare:
        modes = [False, True]
    elif args.headed:
        modes = [True]
    else:
        modes = [False]
    states: list[SportradarSessionState] = []
    for headed in modes:
        config = BootstrapConfig(
            bootstrap_urls=urls,
            headed=headed,
            seconds_per_url=args.seconds,
            wait_between_urls=args.wait_between,
            user_data_dir=args.user_data_dir,
            block_heavy_resources=not args.no_block_heavy_resources,
        )
        states.append(await bootstrap_sportradar_session(config))
    write_session_artifacts(states, args.out_dir)
    for state in states:
        mode = "headed" if state.headed else "headless"
        print(
            f"{mode}: usable={state.is_usable()} token_expiration={state.token_expiration()} "
            f"fetch_count={state.fetch_count} blocked={state.blocked_count}"
        )
    print(f"Wrote {args.out_dir / 'session_bootstrap_report.md'}")
    return 0


def main() -> int:
    return asyncio.run(run_cli_async(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
