from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from playwright.async_api import async_playwright, Response


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def fraction_to_decimal(frac: str | None) -> float | None:
    if not frac:
        return None

    frac = frac.strip()

    if "/" not in frac:
        try:
            return float(frac)
        except ValueError:
            return None

    a, b = frac.split("/", 1)

    try:
        return round(1.0 + float(a) / float(b), 6)
    except ValueError:
        return None


def parse_record(record: str) -> tuple[str, dict[str, str]]:
    parts = [p for p in record.split(";") if p != ""]
    if not parts:
        return "", {}

    tag = parts[0]
    fields: dict[str, str] = {}

    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            fields[k] = v

    return tag, fields


def tokenize_payload(payload: str) -> list[tuple[str, dict[str, str]]]:
    payload = payload.replace("\x08", "")
    records = payload.split("|")

    parsed = []
    for record in records:
        record = record.strip()
        if not record:
            continue

        tag, fields = parse_record(record)
        if tag:
            parsed.append((tag, fields))

    return parsed


def pd_to_event_url(host: str, pd: str | None) -> str | None:
    if not pd:
        return None

    path = pd.strip("#").replace("#", "/")
    return f"https://{host}/#/{path}/"


def extract_sportradar_url(ex: str | None) -> str | None:
    if not ex:
        return None

    # Ejemplo:
    # EX=puw~https://s5.sir.sportradar.com/bet365/en/match/71428876~Bet365Stats~...
    m = re.search(r"puw~(https?://[^~]+)~Bet365Stats", ex)
    if m:
        return m.group(1)

    return None


def parse_bet365_league_1x2(
    payload: str,
    *,
    host: str,
    source_url: str | None = None,
) -> dict[str, Any]:
    tokens = tokenize_payload(payload)

    league_name: str | None = None
    competition_pd: str | None = None
    source_meta: dict[str, Any] = {}

    events_by_fi: dict[str, dict[str, Any]] = {}
    current_market_id: str | None = None
    current_selection: str | None = None

    for tag, f in tokens:
        if tag == "CL":
            source_meta.update(f)

        elif tag == "EV":
            # En payload de liga, EV suele traer el nombre de liga en TB.
            tb = f.get("TB", "")
            if "¬" in tb:
                maybe_league = tb.split("¬")[-1]
                if "," in maybe_league:
                    maybe_league = maybe_league.split(",")[0]
                league_name = maybe_league.strip() or league_name

        elif tag == "MA":
            ma = f.get("MA")
            na = f.get("NA")

            if f.get("PD") and "#D1002#" in f.get("PD", ""):
                competition_pd = f.get("PD")

            if ma == "40" or f.get("ID") == "M40":
                current_market_id = "40"
                current_selection = na.strip() if na else None
            else:
                current_market_id = None
                current_selection = None

        elif tag == "PA":
            fi = f.get("FI")

            # Primero aparecen eventos como PA con ID=PC...
            # Ejemplo:
            # PA;ID=PC...;NA=Belgrano;N2=Union Santa Fe;FI=194428321;BC=...;PD=...;EX=...
            if f.get("ID", "").startswith("PC") and fi and f.get("PD"):
                home = (f.get("NA") or "").strip()
                away = (f.get("N2") or "").strip()
                full_name = (f.get("FD") or f"{home} v {away}").strip()

                events_by_fi[fi] = {
                    "fixture_id": fi,
                    "event_token": f.get("IT"),
                    "home": home,
                    "away": away,
                    "name": full_name,
                    "start_raw": f.get("BC"),
                    "start_iso": parse_bet365_datetime(f.get("BC")),
                    "event_pd": f.get("PD"),
                    "event_url": pd_to_event_url(host, f.get("PD")),
                    "sportradar_url": extract_sportradar_url(f.get("EX")),
                    "stats_provider": "Bet365Stats" if extract_sportradar_url(f.get("EX")) else None,
                    "league": f.get("L3") or league_name,
                    "odds_1x2": {
                        "1": None,
                        "X": None,
                        "2": None,
                    },
                    "raw_event": f,
                }

                continue

            # Después aparecen odds 1/X/2 en bloques MA;NA=1/X/2
            if current_market_id == "40" and current_selection in {"1", "X", "2"} and fi:
                if fi not in events_by_fi:
                    events_by_fi[fi] = {
                        "fixture_id": fi,
                        "home": None,
                        "away": None,
                        "name": None,
                        "start_raw": None,
                        "start_iso": None,
                        "event_pd": None,
                        "event_url": None,
                        "sportradar_url": None,
                        "stats_provider": None,
                        "league": league_name,
                        "odds_1x2": {
                            "1": None,
                            "X": None,
                            "2": None,
                        },
                        "raw_event": {},
                    }

                frac = f.get("OD")
                events_by_fi[fi]["odds_1x2"][current_selection] = {
                    "selection": current_selection,
                    "odds_fractional": frac,
                    "odds_decimal": fraction_to_decimal(frac),
                    "suspended": f.get("SU") == "1",
                    "raw": f,
                }

    matches = list(events_by_fi.values())

    matches.sort(
        key=lambda x: (
            x.get("start_raw") or "",
            x.get("fixture_id") or "",
        )
    )

    # Dejamos solo partidos que tengan al menos una cuota 1X2.
    matches = [
        m for m in matches
        if any(m["odds_1x2"].get(k) is not None for k in ("1", "X", "2"))
    ]

    return {
        "source_url": source_url,
        "host": host,
        "competition_pd": competition_pd,
        "competition_url": pd_to_event_url(host, competition_pd),
        "league_name": league_name,
        "source_meta": source_meta,
        "matches_count": len(matches),
        "matches": matches,
    }


def parse_bet365_datetime(raw: str | None) -> str | None:
    if not raw:
        return None

    # Bet365 usa YYYYMMDDHHMMSS
    try:
        dt = datetime.strptime(raw, "%Y%m%d%H%M%S")
        return dt.isoformat(sep=" ")
    except ValueError:
        return None


def visual_url_to_expected_pd(url: str) -> str | None:
    parsed = urlparse(url)
    frag = parsed.fragment

    if not frag:
        return None

    frag = frag.strip("/")

    if not frag:
        return None

    return "#" + frag.replace("/", "#") + "#"


def looks_like_league_markets(url: str, body: str, expected_pd: str | None) -> bool:
    if "matchmarketscontentapi/markets" not in url:
        return False

    if not body.startswith("F|"):
        return False

    if "MG;ID=40" not in body:
        return False

    if expected_pd and expected_pd not in body:
        return False

    return True


async def capture_bet365_league_1x2(
    url: str,
    *,
    out_dir: Path,
    max_wait_ms: int = 25000,
    stable_ms: int = 2500,
    headless: bool = True,
) -> dict[str, Any]:
    host = urlparse(url).netloc
    expected_pd = visual_url_to_expected_pd(url)

    out_dir.mkdir(parents=True, exist_ok=True)

    captured_payload: str | None = None
    captured_url: str | None = None
    debug_responses: list[dict[str, Any]] = []

    start = time.monotonic()
    last_capture = time.monotonic()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=USER_AGENT,
            locale="es-AR",
            timezone_id="America/Argentina/Cordoba",
        )

        async def route_handler(route):
            req = route.request
            rtype = req.resource_type
            req_url = req.url

            # Dejamos document/script/xhr/fetch.
            if rtype in {"image", "font", "media"}:
                await route.abort()
                return

            if req_url.endswith(".svg"):
                await route.abort()
                return

            blocked_hosts = (
                "googletagmanager.com",
                "google-analytics.com",
                "facebook.net",
                "intercom.io",
                "sentry.io",
            )

            if any(h in req_url for h in blocked_hosts):
                await route.abort()
                return

            await route.continue_()

        await context.route("**/*", route_handler)

        page = await context.new_page()

        async def handle_response(response: Response) -> None:
            nonlocal captured_payload, captured_url, last_capture

            rurl = response.url
            ctype = response.headers.get("content-type", "")

            if (
                "matchmarketscontentapi/markets" not in rurl
                and "leftnavcontentapi" not in rurl
                and "defaultapi/sports-configuration" not in rurl
            ):
                return

            item: dict[str, Any] = {
                "url": rurl,
                "status": response.status,
                "resource_type": response.request.resource_type,
                "content_type": ctype,
            }

            try:
                text = await response.text()
                item["body_preview"] = text[:300].replace("\n", " ")

                if looks_like_league_markets(rurl, text, expected_pd):
                    captured_payload = text
                    captured_url = rurl
                    last_capture = time.monotonic()
                    print(f"✓ Capturado matchmarketscontentapi/markets: {rurl}")

            except Exception as e:
                item["error"] = repr(e)

            debug_responses.append(item)

        page.on("response", handle_response)

        print(f"→ Abriendo: {url}")
        print(f"→ expected_pd: {expected_pd}")

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        while True:
            await page.wait_for_timeout(250)

            elapsed_ms = int((time.monotonic() - start) * 1000)
            quiet_ms = int((time.monotonic() - last_capture) * 1000)

            if captured_payload and quiet_ms >= stable_ms:
                break

            if elapsed_ms >= max_wait_ms:
                break

        await context.close()
        await browser.close()

    (out_dir / "debug_responses.json").write_text(
        json.dumps(debug_responses, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary: dict[str, Any] = {
        "source_url": url,
        "host": host,
        "expected_pd": expected_pd,
        "captured": captured_payload is not None,
        "captured_url": captured_url,
        "debug_responses_count": len(debug_responses),
    }

    if not captured_payload:
        (out_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary

    raw_path = out_dir / "raw_league_market.txt"
    raw_path.write_text(captured_payload, encoding="utf-8")

    parsed = parse_bet365_league_1x2(
        captured_payload,
        host=host,
        source_url=url,
    )

    parsed_path = out_dir / "parsed_league_1x2.json"
    parsed_path.write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary.update(
        {
            "raw_path": str(raw_path),
            "parsed_path": str(parsed_path),
            "matches_count": parsed["matches_count"],
        }
    )

    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return summary


def default_out_dir(url: str) -> Path:
    host = urlparse(url).netloc.replace(".", "-")
    frag = urlparse(url).fragment.strip("/").replace("/", "-").lower()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    name = f"{stamp}-{host}"
    if frag:
        name += f"-{frag}"

    return Path("playwright_captures") / name


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url_or_payload")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--max-wait-ms", type=int, default=25000)
    parser.add_argument("--stable-ms", type=int, default=2500)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    src = args.url_or_payload

    if args.offline or Path(src).exists():
        payload_path = Path(src)
        payload = payload_path.read_text(encoding="utf-8")

        host = args.host or "www.bet365.bet.ar"

        parsed = parse_bet365_league_1x2(
            payload,
            host=host,
            source_url=str(payload_path),
        )

        out_dir = Path(args.out_dir or "output")
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = out_dir / "parsed_league_1x2.json"
        out_path.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"→ Partidos extraídos: {parsed['matches_count']}")
        print(f"→ Guardado en: {out_path}")

        for m in parsed["matches"]:
            odds = m["odds_1x2"]
            print(
                f"{m['start_iso']} | {m['home']} vs {m['away']} | "
                f"1={odds['1']['odds_decimal'] if odds['1'] else None} "
                f"X={odds['X']['odds_decimal'] if odds['X'] else None} "
                f"2={odds['2']['odds_decimal'] if odds['2'] else None} | "
                f"stats={m['sportradar_url']}"
            )

        return

    url = src
    out_dir = Path(args.out_dir) if args.out_dir else default_out_dir(url)

    summary = await capture_bet365_league_1x2(
        url,
        out_dir=out_dir,
        max_wait_ms=args.max_wait_ms,
        stable_ms=args.stable_ms,
        headless=not args.headed,
    )

    print()
    print(f"→ Capturado: {summary['captured']}")
    print(f"→ Carpeta: {out_dir}")

    if summary.get("matches_count") is not None:
        print(f"→ Partidos extraídos: {summary['matches_count']}")


if __name__ == "__main__":
    asyncio.run(main())