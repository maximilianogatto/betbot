from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Response


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


ASIAN_MARKETS = {
    "938": "Asian Handicap",
    "10143": "Goal Line",
    "50138": "Alternative Asian Handicap",
    "50139": "Alternative Goal Line",
    "50137": "1st Half Asian Handicap",
    "50136": "1st Half Goal Line",
    "50265": "Alternative 1st Half Asian Handicap",
    "50266": "Alternative 1st Half Goal Line",
}


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
        return round(1 + float(a) / float(b), 6)
    except ValueError:
        return None


def parse_datetime(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d%H%M%S").isoformat(sep=" ")
    except ValueError:
        return None


def parse_record(record: str) -> tuple[str, dict[str, str]]:
    parts = [p for p in record.split(";") if p]
    if not parts:
        return "", {}

    tag = parts[0]
    fields = {}

    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            fields[k] = v

    return tag, fields


def tokenize(payload: str) -> list[tuple[str, dict[str, str]]]:
    payload = payload.replace("\x08", "")
    out = []

    for record in payload.split("|"):
        record = record.strip()
        if not record:
            continue
        tag, fields = parse_record(record)
        if tag:
            out.append((tag, fields))

    return out


def visual_url_to_pd(url: str) -> str | None:
    frag = urlparse(url).fragment.strip("/")
    if not frag:
        return None
    return "#" + frag.replace("/", "#") + "#"


def event_visual_url(host: str, event_id: str, section: str = "I3") -> str:
    return f"https://{host}/#/AC/B1/C1/D8/E{event_id}/F3/{section}/"


def looks_like_league_payload(url: str, body: str, expected_pd: str | None) -> bool:
    if "matchmarketscontentapi/markets" not in url:
        return False
    if not body.startswith("F|"):
        return False
    if "MG;ID=40" not in body:
        return False
    if expected_pd and expected_pd not in body:
        return False
    return True


def looks_like_asian_payload(url: str, body: str, event_id: str) -> bool:
    if "matchbettingcontentapi/coupon" not in url:
        return False
    if not body.startswith("F|"):
        return False
    if f"E{event_id}" not in body:
        return False
    return "MG;ID=938" in body or "MG;ID=10143" in body


def parse_league(payload: str) -> dict[str, Any]:
    tokens = tokenize(payload)

    league_name = None
    matches: dict[str, dict[str, Any]] = {}

    current_market = None
    current_selection = None

    for tag, f in tokens:
        if tag == "EV":
            tb = f.get("TB", "")
            if "¬" in tb:
                league_name = tb.split("¬")[-1].split(",")[0].strip() or league_name

        elif tag == "MA":
            if f.get("MA") == "40" or f.get("ID") == "M40":
                current_market = "40"
                current_selection = (f.get("NA") or "").strip()
            else:
                current_market = None
                current_selection = None

        elif tag == "PA":
            fi = f.get("FI")

            if f.get("ID", "").startswith("PC") and fi and f.get("PD"):
                home = (f.get("NA") or "").strip()
                away = (f.get("N2") or "").strip()

                matches[fi] = {
                    "event_id": fi,
                    "home": home,
                    "away": away,
                    "name": f"{home} v {away}",
                    "league": f.get("L3") or league_name,
                    "start_raw": f.get("BC"),
                    "start_iso": parse_datetime(f.get("BC")),
                    "odds_1x2": {"1": None, "X": None, "2": None},
                }

            elif current_market == "40" and current_selection in {"1", "X", "2"} and fi:
                if fi not in matches:
                    matches[fi] = {
                        "event_id": fi,
                        "home": None,
                        "away": None,
                        "name": None,
                        "league": league_name,
                        "start_raw": None,
                        "start_iso": None,
                        "odds_1x2": {"1": None, "X": None, "2": None},
                    }

                frac = f.get("OD")
                matches[fi]["odds_1x2"][current_selection] = {
                    "fractional": frac,
                    "decimal": fraction_to_decimal(frac),
                    "suspended": f.get("SU") == "1",
                }

    clean_matches = [
        m for m in matches.values()
        if any(m["odds_1x2"].get(k) for k in ("1", "X", "2"))
    ]

    clean_matches.sort(key=lambda m: (m.get("start_raw") or "", m.get("event_id") or ""))

    return {
        "league_name": league_name,
        "matches_count": len(clean_matches),
        "matches": clean_matches,
    }


def parse_asian(payload: str, event_id: str) -> dict[str, Any]:
    tokens = tokenize(payload)

    event = {
        "event_id": event_id,
        "name": None,
        "home": None,
        "away": None,
        "league": None,
        "start_raw": None,
        "start_iso": None,
    }

    markets = []

    current_mg = None
    current_ma = None
    pending_line = None

    for tag, f in tokens:
        if tag == "EV" and f.get("ID") == "EMB":
            event.update(
                {
                    "event_id": f.get("FI") or event_id,
                    "name": f.get("EX"),
                    "home": f.get("N2"),
                    "away": f.get("N3"),
                    "league": f.get("CC") or f.get("L3"),
                    "start_raw": f.get("BC"),
                    "start_iso": parse_datetime(f.get("BC")),
                }
            )

        elif tag == "MG":
            mg_id = f.get("ID")

            if mg_id in ASIAN_MARKETS:
                current_mg = {
                    "market_id": mg_id,
                    "market_name": f.get("NA") or ASIAN_MARKETS[mg_id],
                    "expanded": f.get("DO") == "1",
                    "selections": [],
                }
                markets.append(current_mg)
            else:
                current_mg = None

            current_ma = None
            pending_line = None

        elif tag == "MA" and current_mg:
            current_ma = f

        elif tag == "PA" and current_mg:
            if f.get("ID", "").startswith("PC"):
                pending_line = f.get("NA")
                continue

            frac = f.get("OD")

            current_mg["selections"].append(
                {
                    "selection": (current_ma or {}).get("NA"),
                    "line": pending_line or f.get("HD") or f.get("HA"),
                    "handicap": f.get("HA"),
                    "handicap_display": f.get("HD"),
                    "odds_fractional": frac,
                    "odds_decimal": fraction_to_decimal(frac),
                    "suspended": f.get("SU") == "1",
                }
            )

    markets = [m for m in markets if m["selections"]]

    return {
        "event": event,
        "markets": markets,
    }


async def make_context(playwright):
    browser = await playwright.chromium.launch(
        headless=True,
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
        if req.resource_type in {"image", "font", "media"}:
            await route.abort()
            return
        if req.url.endswith(".svg"):
            await route.abort()
            return
        await route.continue_()

    await context.route("**/*", route_handler)
    return browser, context


async def capture_payload(
    context,
    url: str,
    predicate,
    *,
    max_wait_ms: int,
    stable_ms: int,
) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    page = await context.new_page()

    captured_payload = None
    captured_url = None
    debug = []

    start = time.monotonic()
    last_capture = time.monotonic()

    async def handle_response(response: Response):
        nonlocal captured_payload, captured_url, last_capture

        rurl = response.url

        if (
            "matchmarketscontentapi/markets" not in rurl
            and "matchbettingcontentapi/coupon" not in rurl
        ):
            return

        item = {
            "url": rurl,
            "status": response.status,
            "content_type": response.headers.get("content-type", ""),
        }

        try:
            text = await response.text()
            item["preview"] = text[:300].replace("\n", " ")

            if predicate(rurl, text):
                captured_payload = text
                captured_url = rurl
                last_capture = time.monotonic()
                print(f"✓ Capturado: {rurl}")

        except Exception as e:
            item["error"] = repr(e)

        debug.append(item)

    page.on("response", handle_response)

    print(f"→ Abriendo: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)

    while True:
        await page.wait_for_timeout(250)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        quiet_ms = int((time.monotonic() - last_capture) * 1000)

        if captured_payload and quiet_ms >= stable_ms:
            break

        if elapsed_ms >= max_wait_ms:
            break

    await page.close()
    return captured_payload, captured_url, debug


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("league_url")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--save-raw", action="store_true")
    parser.add_argument("--max-wait-ms", type=int, default=25000)
    parser.add_argument("--stable-ms", type=int, default=2000)
    args = parser.parse_args()

    league_url = args.league_url
    host = urlparse(league_url).netloc
    expected_pd = visual_url_to_pd(league_url)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out_dir or f"bet365_capture_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser, context = await make_context(p)

        league_payload, league_capture_url, league_debug = await capture_payload(
            context,
            league_url,
            lambda rurl, body: looks_like_league_payload(rurl, body, expected_pd),
            max_wait_ms=args.max_wait_ms,
            stable_ms=args.stable_ms,
        )

        (out_dir / "debug_league.json").write_text(
            json.dumps(league_debug, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if not league_payload:
            await context.close()
            await browser.close()
            raise SystemExit("No pude capturar payload de liga.")

        if args.save_raw:
            (out_dir / "raw_league.txt").write_text(league_payload, encoding="utf-8")

        league = parse_league(league_payload)
        league["source_url"] = league_url
        league["captured_url"] = league_capture_url

        matches = league["matches"]
        if args.limit:
            matches = matches[: args.limit]

        print(f"\n→ Partidos encontrados: {len(league['matches'])}")
        print(f"→ Procesando Asian Lines: {len(matches)}")

        asian_by_event = {}

        for i, match in enumerate(matches, start=1):
            event_id = match["event_id"]
            asian_url = event_visual_url(host, event_id, section="I3")

            print(f"\n[{i}/{len(matches)}] {event_id} | {match['name']}")

            asian_payload, asian_capture_url, asian_debug = await capture_payload(
                context,
                asian_url,
                lambda rurl, body, eid=event_id: looks_like_asian_payload(rurl, body, eid),
                max_wait_ms=20000,
                stable_ms=1500,
            )

            (out_dir / f"debug_asian_{event_id}.json").write_text(
                json.dumps(asian_debug, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            if not asian_payload:
                asian_by_event[event_id] = {
                    "error": "not_captured",
                    "event": match,
                    "markets": [],
                }
                continue

            if args.save_raw:
                (out_dir / f"raw_asian_{event_id}.txt").write_text(
                    asian_payload,
                    encoding="utf-8",
                )

            parsed_asian = parse_asian(asian_payload, event_id)
            parsed_asian["captured_url"] = asian_capture_url
            parsed_asian["event"].update(
                {
                    "home": parsed_asian["event"].get("home") or match.get("home"),
                    "away": parsed_asian["event"].get("away") or match.get("away"),
                    "name": parsed_asian["event"].get("name") or match.get("name"),
                    "league": parsed_asian["event"].get("league") or match.get("league"),
                    "start_iso": parsed_asian["event"].get("start_iso") or match.get("start_iso"),
                }
            )

            asian_by_event[event_id] = parsed_asian

            for market in parsed_asian["markets"]:
                if market["market_id"] in {"938", "10143"}:
                    print(f"  {market['market_name']}")
                    for s in market["selections"]:
                        print(
                            f"   - {s['selection']} | line={s['line']} | "
                            f"OD={s['odds_fractional']} | dec={s['odds_decimal']}"
                        )

        await context.close()
        await browser.close()

    output = {
        "league": {
            "name": league["league_name"],
            "source_url": league["source_url"],
            "captured_url": league["captured_url"],
            "matches_count": league["matches_count"],
            "matches": matches,
        },
        "asian_by_event": asian_by_event,
    }

    out_path = out_dir / "bet365_league_asian_clean.json"
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n→ Guardado en: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())