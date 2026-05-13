from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from curl_cffi.requests import AsyncSession


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


def fraction_to_decimal(frac: str | None) -> float | None:
    if not frac:
        return None
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


def parse_bet365_datetime(raw: str | None) -> str | None:
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


def tokenize_payload(payload: str) -> list[tuple[str, dict[str, str]]]:
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


def visual_url_to_pd(url: str) -> str:
    frag = urlparse(url).fragment.strip("/")
    return "#" + frag.replace("/", "#") + "#"


def pd_to_url(host: str, pd: str | None) -> str | None:
    if not pd:
        return None
    return f"https://{host}/#/{pd.strip('#').replace('#', '/')}/"


def build_markets_url(host: str, pd: str) -> str:
    return (
        f"https://{host}/matchmarketscontentapi/markets"
        f"?lid=36&zid=0&pd={quote(pd, safe='')}"
        "&cid=271&cgid=1&ctid=271"
    )


def build_asian_coupon_url(host: str, event_id: str, *, p_code: str = "P36082") -> str:
    pd = f"#AC#B1#C1#D8#E{event_id}#F3#I3#{p_code}#H1#"
    return (
        f"https://{host}/matchbettingcontentapi/coupon"
        f"?lid=36&zid=0&pd={quote(pd, safe='')}"
        "&cid=271&cgid=1&ctid=271"
    )


def parse_league_matches(payload: str, *, host: str, source_url: str) -> dict[str, Any]:
    tokens = tokenize_payload(payload)

    events: dict[str, dict[str, Any]] = {}
    current_market: str | None = None
    current_selection: str | None = None

    league_name = None

    for tag, f in tokens:
        if tag == "EV":
            tb = f.get("TB", "")
            if "¬" in tb:
                league_name = tb.split("¬")[-1].split(",")[0].strip() or league_name

        elif tag == "PA":
            fi = f.get("FI")

            if f.get("ID", "").startswith("PC") and fi and f.get("PD"):
                home = (f.get("NA") or "").strip()
                away = (f.get("N2") or "").strip()

                events[fi] = {
                    "fixture_id": fi,
                    "home": home,
                    "away": away,
                    "name": f"{home} v {away}",
                    "league": f.get("L3") or league_name,
                    "start_raw": f.get("BC"),
                    "start_iso": parse_bet365_datetime(f.get("BC")),
                    "event_pd": f.get("PD"),
                    "event_url": pd_to_url(host, f.get("PD")),
                    "odds_1x2": {"1": None, "X": None, "2": None},
                }
                continue

            if current_market == "40" and current_selection in {"1", "X", "2"} and fi:
                events.setdefault(
                    fi,
                    {
                        "fixture_id": fi,
                        "home": None,
                        "away": None,
                        "name": None,
                        "league": league_name,
                        "start_raw": None,
                        "start_iso": None,
                        "event_pd": None,
                        "event_url": None,
                        "odds_1x2": {"1": None, "X": None, "2": None},
                    },
                )

                frac = f.get("OD")
                events[fi]["odds_1x2"][current_selection] = {
                    "fractional": frac,
                    "decimal": fraction_to_decimal(frac),
                    "suspended": f.get("SU") == "1",
                }

        elif tag == "MA":
            ma = f.get("MA")
            na = f.get("NA")

            if ma == "40" or f.get("ID") == "M40":
                current_market = "40"
                current_selection = na.strip() if na else None
            else:
                current_market = None
                current_selection = None

    matches = list(events.values())
    matches = [
        m for m in matches
        if any(m["odds_1x2"].get(k) for k in ("1", "X", "2"))
    ]
    matches.sort(key=lambda m: (m.get("start_raw") or "", m.get("fixture_id") or ""))

    return {
        "source_url": source_url,
        "league_name": league_name,
        "matches_count": len(matches),
        "matches": matches,
    }


def market_name_from_id(mg_id: str | None) -> str | None:
    return {
        "938": "Asian Handicap",
        "10143": "Goal Line",
        "50138": "Alternative Asian Handicap",
        "50139": "Alternative Goal Line",
        "50137": "1st Half Asian Handicap",
        "50136": "1st Half Goal Line",
        "50265": "Alternative 1st Half Asian Handicap",
        "50266": "Alternative 1st Half Goal Line",
        "10164": "Asian Total Corners",
        "10165": "Asian Handicap Corners",
        "10233": "1st Half Asian Corners",
        "10166": "Asian Total Cards",
        "10239": "Asian Handicap Cards",
    }.get(mg_id)


def parse_asian_coupon(payload: str, *, event_id: str, source_url: str) -> dict[str, Any]:
    tokens = tokenize_payload(payload)

    markets: list[dict[str, Any]] = []
    current_mg: dict[str, Any] | None = None
    current_ma: dict[str, Any] | None = None
    pending_line: str | None = None

    wanted_ids = {
        "938",
        "10143",
        "50138",
        "50139",
        "50137",
        "50136",
        "50265",
        "50266",
        "10164",
        "10165",
        "10233",
        "10166",
        "10239",
    }

    for tag, f in tokens:
        if tag == "MG":
            mg_id = f.get("ID")
            name = f.get("NA") or market_name_from_id(mg_id)

            if mg_id in wanted_ids:
                current_mg = {
                    "market_id": mg_id,
                    "market_name": name,
                    "expanded": f.get("DO") == "1",
                    "pd": f.get("PD"),
                    "selections": [],
                }
                markets.append(current_mg)
            else:
                current_mg = None

            current_ma = None
            pending_line = None

        elif tag == "MA" and current_mg:
            current_ma = f
            if f.get("ID", "").startswith("RB"):
                pending_line = None

        elif tag == "PA" and current_mg:
            if f.get("ID", "").startswith("PC"):
                pending_line = f.get("NA")
                continue

            frac = f.get("OD")
            selection_name = None

            if current_ma:
                selection_name = current_ma.get("NA")

            current_mg["selections"].append(
                {
                    "selection": selection_name,
                    "line_label": pending_line,
                    "handicap": f.get("HA"),
                    "handicap_display": f.get("HD"),
                    "odds_fractional": frac,
                    "odds_decimal": fraction_to_decimal(frac),
                    "suspended": f.get("SU") == "1",
                    "raw": f,
                }
            )

    return {
        "event_id": event_id,
        "source_url": source_url,
        "markets": markets,
    }


async def get_text(session: AsyncSession, url: str, *, referer: str | None = None) -> tuple[int, str, str]:
    extra_headers = {}
    if referer:
        extra_headers["Referer"] = referer

    r = await session.get(url, headers=extra_headers)

    raw = r.content or b""
    text = r.text or ""

    if not text and raw:
        text = raw.decode("utf-8", errors="replace")

    print("debug status:", r.status_code)
    print("debug final_url:", r.url)
    print("debug content-length header:", r.headers.get("content-length"))
    print("debug raw len:", len(raw))
    print("debug text len:", len(text))

    return r.status_code, r.headers.get("content-type", ""), text

def build_league_coupon_url(host: str, pd: str) -> str:
    return (
        f"https://{host}/matchbettingcontentapi/coupon"
        f"?lid=36&zid=0&pd={quote(pd, safe='')}"
        "&cid=271&cgid=1&ctid=271"
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("league_url")
    parser.add_argument("--out-dir", default="bet365_http_output")
    parser.add_argument("--p-code", default="P36082")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--save-raw", action="store_true")
    args = parser.parse_args()

    league_url = args.league_url
    host = urlparse(league_url).netloc or "www.bet365.bet.ar"
    league_pd = visual_url_to_pd(league_url)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # headers = {
    #     "User-Agent": USER_AGENT,
    #     "Accept": "*/*",
    #     "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    #     "Referer": f"https://{host}/",
    #     "Origin": f"https://{host}",
    # }
    
    headers = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": league_url,
    "Origin": f"https://{host}",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "X-Requested-With": "XMLHttpRequest",
}

    async with AsyncSession(
        impersonate="chrome120",
        headers=headers,
        timeout=30,
    ) as session:
        print("→ GET documento base")
        # home_status, _, _ = await get_text(session, f"https://{host}/")
        home_status, _, _ = await get_text(session, league_url, referer=f"https://{host}/")

        status, ctype, league_payload = await get_text(
            session,
            markets_url,
            referer=league_url,
        )
        print(f"home: {home_status}")

        markets_url = build_markets_url(host, league_pd)

        print("→ GET markets liga")
        print(markets_url)

        status, ctype, league_payload = await get_text(session, markets_url)
        print(f"markets: {status} | {ctype}")

        # if status != 200 or not league_payload.startswith("F|"):
        #     print(league_payload[:800])
        #     raise SystemExit("No pude obtener payload válido de liga.")
        league_payload = league_payload.replace("\x08", "").strip()

        idx = league_payload.find("F|")
        if idx != -1:
            league_payload = league_payload[idx:]

        print("payload len:", len(league_payload))
        print("payload preview:", repr(league_payload[:300]))

        if status != 200 or "F|" not in league_payload[:20]:
            raise SystemExit("No pude obtener payload válido de liga.")

        if args.save_raw:
            (out_dir / "raw_league_markets.txt").write_text(
                league_payload,
                encoding="utf-8",
            )

        league = parse_league_matches(
            league_payload,
            host=host,
            source_url=markets_url,
        )

        matches = league["matches"]
        if args.limit:
            matches = matches[: args.limit]

        print(f"→ Partidos encontrados: {len(matches)}")

        all_results = {
            "league": league,
            "asian_by_event": {},
        }

        for i, m in enumerate(matches, start=1):
            event_id = m["fixture_id"]
            name = m["name"]

            asian_url = build_asian_coupon_url(
                host,
                event_id,
                p_code=args.p_code,
            )

            print(f"\n[{i}/{len(matches)}] {event_id} | {name}")
            print(f"→ GET Asian Lines")

            status, ctype, payload = await get_text(session, asian_url)
            print(f"coupon: {status} | {ctype}")

            if status != 200 or not payload.startswith("F|"):
                all_results["asian_by_event"][event_id] = {
                    "error": "invalid_payload",
                    "status": status,
                    "preview": payload[:500],
                    "source_url": asian_url,
                }
                continue

            if args.save_raw:
                (out_dir / f"raw_asian_{event_id}.txt").write_text(
                    payload,
                    encoding="utf-8",
                )

            parsed_asian = parse_asian_coupon(
                payload,
                event_id=event_id,
                source_url=asian_url,
            )

            all_results["asian_by_event"][event_id] = parsed_asian

            for market in parsed_asian["markets"]:
                if market["market_id"] in {"938", "10143"}:
                    print(f"  {market['market_name']}:")
                    for s in market["selections"]:
                        print(
                            "   - "
                            f"{s['selection']} "
                            f"line={s['line_label'] or s['handicap'] or s['handicap_display']} "
                            f"odds={s['odds_fractional']} "
                            f"dec={s['odds_decimal']}"
                        )

        out_path = out_dir / "bet365_league_with_asian.json"
        out_path.write_text(
            json.dumps(all_results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"\n→ Guardado en: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())