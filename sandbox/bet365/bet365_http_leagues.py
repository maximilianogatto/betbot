from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from curl_cffi.requests import AsyncSession


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
        return round(1 + float(a) / float(b), 6)
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
    fields: dict[str, str] = {}

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
    frag = unquote(frag)

    if not frag:
        raise ValueError("La URL no tiene fragmento #/.../")

    return "#" + frag.replace("/", "#") + "#"


def pd_to_visual_url(host: str, pd: str | None) -> str | None:
    if not pd:
        return None
    return f"https://{host}/#/{pd.strip('#').replace('#', '/')}/"


def build_markets_url(host: str, pd: str) -> str:
    return (
        f"https://{host}/matchmarketscontentapi/markets"
        f"?lid=36&zid=0&pd={quote(pd, safe='')}"
        "&cid=271&cgid=1&ctid=271"
    )


def normalize_payload(text: str) -> str:
    text = text.replace("\x08", "").strip()
    idx = text.find("F|")
    if idx >= 0:
        text = text[idx:]
    return text


def looks_like_league_payload(payload: str, expected_pd: str | None = None) -> bool:
    if not payload.startswith("F|"):
        return False
    if "MG;ID=40" not in payload:
        return False
    if expected_pd and expected_pd not in payload:
        # No lo hago obligatorio porque a veces Bet365 devuelve PDs derivados.
        pass
    return True


def extract_sportradar_url(ex: str | None) -> str | None:
    if not ex:
        return None
    m = re.search(r"puw~(https?://[^~]+)~Bet365Stats", ex)
    return m.group(1) if m else None


def parse_league_1x2(payload: str, *, host: str, source_url: str) -> dict[str, Any]:
    tokens = tokenize_payload(payload)

    league_name = None
    source_meta: dict[str, Any] = {}
    events: dict[str, dict[str, Any]] = {}

    current_market: str | None = None
    current_selection: str | None = None

    for tag, f in tokens:
        if tag == "CL":
            source_meta.update(f)

        elif tag == "EV":
            tb = f.get("TB", "")
            if "¬" in tb:
                maybe = tb.split("¬")[-1]
                if "," in maybe:
                    maybe = maybe.split(",", 1)[0]
                league_name = maybe.strip() or league_name

        elif tag == "MA":
            ma = f.get("MA")
            na = f.get("NA")

            if ma == "40" or f.get("ID") == "M40":
                current_market = "40"
                current_selection = na.strip() if na else None
            else:
                current_market = None
                current_selection = None

        elif tag == "PA":
            fi = f.get("FI")

            if f.get("ID", "").startswith("PC") and fi and f.get("PD"):
                home = (f.get("NA") or "").strip()
                away = (f.get("N2") or "").strip()

                events[fi] = {
                    "fixture_id": fi,
                    "event_token": f.get("IT"),
                    "home": home,
                    "away": away,
                    "name": (f.get("FD") or f"{home} v {away}").strip(),
                    "start_raw": f.get("BC"),
                    "start_iso": parse_bet365_datetime(f.get("BC")),
                    "event_pd": f.get("PD"),
                    "event_url": pd_to_visual_url(host, f.get("PD")),
                    "league": f.get("L3") or league_name,
                    "sportradar_url": extract_sportradar_url(f.get("EX")),
                    "odds_1x2": {"1": None, "X": None, "2": None},
                    "raw_event": f,
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
                        "start_raw": None,
                        "start_iso": None,
                        "event_pd": None,
                        "event_url": None,
                        "league": league_name,
                        "sportradar_url": None,
                        "odds_1x2": {"1": None, "X": None, "2": None},
                        "raw_event": {},
                    },
                )

                frac = f.get("OD")
                events[fi]["odds_1x2"][current_selection] = {
                    "selection": current_selection,
                    "odds_fractional": frac,
                    "odds_decimal": fraction_to_decimal(frac),
                    "suspended": f.get("SU") == "1",
                    "raw": f,
                }

    matches = list(events.values())
    matches = [
        m for m in matches
        if any(m["odds_1x2"].get(k) for k in ("1", "X", "2"))
    ]
    matches.sort(key=lambda m: (m.get("start_raw") or "", m.get("fixture_id") or ""))

    return {
        "source_url": source_url,
        "host": host,
        "league_name": league_name,
        "source_meta": source_meta,
        "matches_count": len(matches),
        "matches": matches,
    }


def candidate_pds_from_visual(url: str) -> list[str]:
    pd = visual_url_to_pd(url)
    candidates = [pd]

    # Si viene como #AC#B1#C1#D1002#E120757998#G40#H^1#
    # probamos también sin el H^1 final.
    no_h = re.sub(r"#H\^?\d+#?$", "#", pd)
    if no_h != pd:
        candidates.append(no_h)

    # Evitar duplicados preservando orden.
    out = []
    for x in candidates:
        if x not in out:
            out.append(x)
    return out


async def get_text(session: AsyncSession, url: str, *, referer: str) -> tuple[int, str, str]:
    r = await session.get(
        url,
        headers={
            "Referer": referer,
            "Origin": f"{urlparse(url).scheme}://{urlparse(url).netloc}",
            "Accept": "*/*",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )

    raw = r.content or b""
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        text = r.text or ""

    return r.status_code, r.headers.get("content-type", ""), text

def pd_variants_from_visual_url(url: str) -> list[str]:
    base = visual_url_to_pd(url).rstrip("#")

    variants = [
        base + "#",
        base + "#H^1#",
        base + "#H^1#I1#",
    ]

    # Si ya venía con H^1, evitamos duplicados.
    out = []
    for v in variants:
        if v not in out:
            out.append(v)
    return out

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("league_url")
    parser.add_argument("--out-dir", default="bet365_http_league_output")
    parser.add_argument("--save-raw", action="store_true")
    args = parser.parse_args()

    league_url = args.league_url
    host = urlparse(league_url).netloc or "www.bet365.bet.ar"

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    }

    async with AsyncSession(
        impersonate="chrome120",
        headers=headers,
        timeout=30,
    ) as session:
        # print("→ GET documento visual")
        # home_status, home_ctype, home_text = await get_text(
        #     session,
        #     league_url,
        #     referer=f"https://{host}/",
        # )
        print("→ bootstrap home")
        await get_text(
            session,
            f"https://{host}/",
            referer=f"https://{host}/",
        )

        print("→ bootstrap sports-config")
        await get_text(
            session,
            f"https://{host}/defaultapi/sports-configuration",
            referer=league_url,
        )

        print("→ bootstrap leftnav")
        await get_text(
            session,
            f"https://{host}/leftnavcontentapi",
            referer=league_url,
        )

        print("→ GET documento visual")
        home_status, home_ctype, home_text = await get_text(
            session,
            league_url,
            referer=f"https://{host}/",
        )
        print(session.cookies)
        print(f"home: {home_status} | {home_ctype} | len={len(home_text)}")

        captured_payload = None
        captured_url = None

        league_payload = ""
        markets_url = None

        for pd in pd_variants_from_visual_url(league_url):
            test_url = build_markets_url(host, pd)

            print("\n→ Probando markets con PD:")
            print(pd)
            print(test_url)

            status, ctype, body = await get_text(
                session,
                test_url,
                referer=league_url,
            )

            body = body.replace("\x08", "").strip()

            print(f"status: {status} | {ctype} | len={len(body)}")
            print("preview:", repr(body[:200]))

            if status == 200 and body.startswith("F|") and "MG;ID=40" in body:
                league_payload = body
                markets_url = test_url
                print("✓ Payload válido encontrado")
                break

        if not league_payload:
            raise SystemExit("No pude obtener payload válido de liga con ninguna variante de PD.")
        # for pd in candidate_pds_from_visual(league_url):
        #     markets_url = build_markets_url(host, pd)

        #     print("\n→ Probando markets con PD:")
        #     print(pd)
        #     print(markets_url)

        #     status, ctype, text = await get_text(
        #         session,
        #         markets_url,
        #         referer=league_url,
        #     )

        #     payload = normalize_payload(text)

        #     print(f"status: {status} | {ctype} | len={len(payload)}")
        #     print(f"preview: {repr(payload[:180])}")

        #     if status == 200 and looks_like_league_payload(payload, pd):
        #         captured_payload = payload
        #         captured_url = markets_url
        #         print("✓ Payload de liga válido")
        #         break

        if not captured_payload:
            raise SystemExit("No pude obtener payload válido de liga con HTTP.")

        if args.save_raw:
            (out_dir / "raw_league_markets.txt").write_text(
                captured_payload,
                encoding="utf-8",
            )

        parsed = parse_league_1x2(
            captured_payload,
            host=host,
            source_url=captured_url or league_url,
        )

        out_path = out_dir / "parsed_league_1x2.json"
        out_path.write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"\n→ Partidos extraídos: {parsed['matches_count']}")
        print(f"→ Guardado en: {out_path}")

        for m in parsed["matches"]:
            odds = m["odds_1x2"]
            print(
                f"{m['start_iso']} | {m['fixture_id']} | "
                f"{m['home']} vs {m['away']} | "
                f"1={odds['1']['odds_decimal'] if odds['1'] else None} "
                f"X={odds['X']['odds_decimal'] if odds['X'] else None} "
                f"2={odds['2']['odds_decimal'] if odds['2'] else None}"
            )


if __name__ == "__main__":
    asyncio.run(main())