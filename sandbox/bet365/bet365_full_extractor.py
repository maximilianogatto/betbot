from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEBUG_PORT = 9222
USER_DATA_DIR = "/tmp/chrome-bet365-debug"

NAV_TIMEOUT_MS = 60000
RUNTIME_TIMEOUT_MS = 30000
# LEAGUE_TIMEOUT_MS = 25000
# I1_TIMEOUT_MS = 2000
# I3_TIMEOUT_MS = 2000
# MAX_RETRIES = 10
LEAGUE_TIMEOUT_MS = 12000
I1_TIMEOUT_MS = 10000
I3_TIMEOUT_MS = 10000
MAX_RETRIES = 3


EXTRACT_LEAGUE_JS = r"""
() => {
  function findFirst(node, predicate) {
    if (!node) return null;
    if (predicate(node)) return node;
    for (const child of node._actualChildren || []) {
      const found = findFirst(child, predicate);
      if (found) return found;
    }
    return null;
  }

  function norm(s) {
    return (s || "").replace(/\s+/g, " ").trim();
  }

  function extractTreeMatches(stem) {
    const ev = findFirst(stem, n => n?.nodeName === "EV");
    if (!ev) return { leagueName: null, matches: [] };

    const marketGroups = ev._actualChildren || [];

    const leagueMeta = marketGroups.find(
      n => n?.nodeName === "MG" && n?.data?.ID === "LMAB"
    );

    const fullTimeGroup = marketGroups.find(
      n => n?.nodeName === "MG" && n?.data?.ID === "40"
    );

    if (!fullTimeGroup) {
      return {
        leagueName: leagueMeta?.data?.CC ?? ev?.data?.L3 ?? null,
        matches: []
      };
    }

    const markets = fullTimeGroup._actualChildren || [];

    const teamsMarket = markets.find(m => m?.nodeName === "MA" && m?.data?.NA === " ");
    const homeMarket = markets.find(m => m?.nodeName === "MA" && m?.data?.NA === "1");
    const drawMarket = markets.find(m => m?.nodeName === "MA" && m?.data?.NA === "X");
    const awayMarket = markets.find(m => m?.nodeName === "MA" && m?.data?.NA === "2");

    if (!teamsMarket || !homeMarket || !drawMarket || !awayMarket) {
      return {
        leagueName: leagueMeta?.data?.CC ?? ev?.data?.L3 ?? null,
        matches: []
      };
    }

    const fixtures = new Map();

    for (const pa of teamsMarket?._actualChildren || []) {
      const fi = pa?.data?.FI;
      if (!fi) continue;

      fixtures.set(fi, {
        fixtureId: fi,
        home: pa?.data?.NA ?? null,
        away: pa?.data?.N2 ?? null,
        dateLabel: null,
        timeLabel: null,
        oddsDecimal: { "1": null, "X": null, "2": null }
      });
    }

    function mergeOdds(marketNode, key) {
      for (const pa of marketNode?._actualChildren || []) {
        const fi = pa?.data?.FI;
        if (!fi || !fixtures.has(fi)) continue;

        const rawDo = pa?.data?.DO ?? null;
        const value = rawDo !== null && rawDo !== "" ? Number(rawDo) : null;

        fixtures.get(fi).oddsDecimal[key] =
          value !== null && Number.isFinite(value)
            ? Math.round(value * 1000) / 1000
            : null;
      }
    }

    mergeOdds(homeMarket, "1");
    mergeOdds(drawMarket, "X");
    mergeOdds(awayMarket, "2");

    return {
      leagueName: leagueMeta?.data?.CC ?? ev?.data?.L3 ?? null,
      matches: Array.from(fixtures.values())
    };
  }

  function extractDateHeaders() {
    const dateRegex = /^(Lun|Mar|Mié|Mie|Jue|Vie|Sáb|Sab|Dom)\s+\d{1,2}\s+[a-záéíóú]{3}$/i;

    return [...document.querySelectorAll("*")]
      .map(el => ({
        el,
        text: norm(el.innerText),
        top: el.getBoundingClientRect().top
      }))
      .filter(x => dateRegex.test(x.text));
  }

  function closestPreviousDate(top, headers) {
    const prev = headers.filter(h => h.top <= top).sort((a, b) => b.top - a.top);
    return prev[0]?.text || null;
  }

  function findRowForMatch(home, away) {
    const teamNodes = [...document.querySelectorAll(".rcl-ParticipantFixtureDetailsTeam_TeamName")]
      .filter(el => norm(el.innerText) === home);

    for (const node of teamNodes) {
      let cur = node;
      for (let i = 0; i < 8 && cur; i++) {
        const txt = norm(cur.innerText);
        const hasHome = txt.includes(home);
        const hasAway = txt.includes(away);
        const hasTime = /\b([01]?\d|2[0-3]):[0-5]\d\b/.test(txt);
        const smallEnough = txt.length < 80;

        if (hasHome && hasAway && hasTime && smallEnough) {
          return cur;
        }
        cur = cur.parentElement;
      }
    }

    return null;
  }

  function mergeDomDateTime(matches) {
    const headers = extractDateHeaders();

    return matches.map(m => {
      const row = findRowForMatch(m.home, m.away);
      const txt = norm(row?.innerText || "");
      const time = (txt.match(/\b([01]?\d|2[0-3]):[0-5]\d\b/) || [null])[0];
      const top = row?.getBoundingClientRect?.().top ?? null;
      const date = top != null ? closestPreviousDate(top, headers) : null;

      return {
        ...m,
        dateLabel: date,
        timeLabel: time
      };
    });
  }

  try {
    if (
      typeof NavLib === "undefined" ||
      !NavLib?.WebsiteNavigationManager?.CurrentPageData ||
      typeof DataReactLib === "undefined" ||
      typeof DataReactLib.getStemFromLookup !== "function"
    ) {
      return { error: "NavLib/DataReactLib no disponibles todavía." };
    }

    const topic = NavLib.WebsiteNavigationManager.CurrentPageData;
    const stem = DataReactLib.getStemFromLookup(topic);

    if (!stem) {
      return {
        error: "No se encontró stem para el topic actual.",
        topic
      };
    }

    const base = extractTreeMatches(stem);

    return {
      leagueId: stem?.data?.ID ?? null,
      topic: stem?.data?.IT ?? null,
      leagueName: base.leagueName,
      matches: mergeDomDateTime(base.matches)
    };
  } catch (err) {
    return { error: String(err) };
  }
}
"""

EXTRACT_I1_JS = r"""
() => {
  function findFirst(node, predicate) {
    if (!node) return null;
    if (predicate(node)) return node;
    for (const child of node._actualChildren || []) {
      const found = findFirst(child, predicate);
      if (found) return found;
    }
    return null;
  }

  function toDecimal(pa) {
    const rawDo = pa?.data?.DO ?? null;
    if (rawDo !== null && rawDo !== "") {
      const value = Number(rawDo);
      if (Number.isFinite(value)) return Math.round(value * 1000) / 1000;
    }

    const rawOd = pa?.data?.OD ?? null;
    if (rawOd && rawOd.includes("/")) {
      const [a, b] = rawOd.split("/").map(Number);
      if (Number.isFinite(a) && Number.isFinite(b) && b !== 0) {
        return Math.round((a / b + 1) * 1000) / 1000;
      }
    }

    return null;
  }

  function normalizeLineValue(value) {
    if (value == null) return null;
    const s = String(value).trim().replace(/\s+/g, "");
    if (["-0","+0","0","0.0","-0.0","+0.0"].includes(s)) return "0.0";
    return String(value).trim();
  }

  const topic = NavLib?.WebsiteNavigationManager?.CurrentPageData ?? null;
  const stem = topic ? DataReactLib?.getStemFromLookup?.(topic) : null;
  const ev = findFirst(stem, n => n?.nodeName === "EV");
  const groups = (ev?._actualChildren || []).filter(n => n?.nodeName === "MG");

  const findMarket = id => groups.find(g => g?.data?.ID === id);

  const fullTime = findMarket("40");
  const ou = findMarket("981");

  const result = {
    topic,
    eventInfo: {
      name: ev?.data?.EX ?? null,
      startTimeRaw: ev?.data?.CM ?? null,
    },
    fullTimeResult: null,
    goalsOverUnder: null,
  };

  if (fullTime) {
    const ma = (fullTime._actualChildren || []).find(n => n?.nodeName === "MA");
    result.fullTimeResult = ((ma?._actualChildren || []).filter(n => n?.nodeName === "PA")).map(pa => ({
      id: pa?.data?.ID ?? null,
      name: pa?.data?.NA ?? null,
      side: pa?.data?.N2 ?? null,
      oddsDecimal: toDecimal(pa),
    }));
  }

  if (ou) {
    const mas = (ou._actualChildren || []).filter(n => n?.nodeName === "MA");
    const lineMa = mas.find(m => (m?._actualChildren || []).some(pa => pa?.data?.NA));
    const overMa = mas.find(m => m?.data?.NA === "Over");
    const underMa = mas.find(m => m?.data?.NA === "Under");

    const linePa = (lineMa?._actualChildren || []).find(n => n?.nodeName === "PA");
    const overPa = (overMa?._actualChildren || []).find(n => n?.nodeName === "PA");
    const underPa = (underMa?._actualChildren || []).find(n => n?.nodeName === "PA");

    result.goalsOverUnder = {
      marketId: "981",
      marketName: ou?.data?.NA ?? "Goals Over/Under",
      lineDisplay: normalizeLineValue(
        linePa?.data?.NA ?? overPa?.data?.HD ?? underPa?.data?.HD ?? null
      ),
      lineAverage: normalizeLineValue(
        overPa?.data?.HA ?? underPa?.data?.HA ?? null
      ),
      over: overPa ? { oddsDecimal: toDecimal(overPa) } : null,
      under: underPa ? { oddsDecimal: toDecimal(underPa) } : null,
    };
  }

  return result;
}
"""

EXTRACT_I3_JS = r"""
() => {
  function findFirst(node, predicate) {
    if (!node) return null;
    if (predicate(node)) return node;
    for (const child of node._actualChildren || []) {
      const found = findFirst(child, predicate);
      if (found) return found;
    }
    return null;
  }

  function toDecimal(pa) {
    const rawDo = pa?.data?.DO ?? null;
    if (rawDo !== null && rawDo !== "") {
      const value = Number(rawDo);
      if (Number.isFinite(value)) return Math.round(value * 1000) / 1000;
    }

    const rawOd = pa?.data?.OD ?? null;
    if (rawOd && rawOd.includes("/")) {
      const [a, b] = rawOd.split("/").map(Number);
      if (Number.isFinite(a) && Number.isFinite(b) && b !== 0) {
        return Math.round((a / b + 1) * 1000) / 1000;
      }
    }
    return null;
  }

  function normalizeLineValue(value) {
    if (value == null) return null;
    const s = String(value).trim().replace(/\s+/g, "");
    if (["-0","+0","0","0.0","-0.0","+0.0"].includes(s)) return "0.0";
    return String(value).trim();
  }

  const topic = NavLib?.WebsiteNavigationManager?.CurrentPageData ?? null;
  const stem = topic ? DataReactLib?.getStemFromLookup?.(topic) : null;
  const ev = findFirst(stem, n => n?.nodeName === "EV");
  const groups = (ev?._actualChildren || []).filter(n => n?.nodeName === "MG");

  const findMarket = id => groups.find(g => g?.data?.ID === id);

  const handicap = findMarket("938");
  const goalLine = findMarket("10143");

  const result = {
    topic,
    eventInfo: {
      name: ev?.data?.EX ?? null,
      startTimeRaw: ev?.data?.CM ?? null,
    },
    asianHandicap: null,
    goalLine: null,
  };

  if (handicap) {
    result.asianHandicap = {
      marketId: "938",
      marketName: handicap?.data?.NA ?? "Asian Handicap",
      selections: (handicap._actualChildren || [])
        .filter(n => n?.nodeName === "MA")
        .map(ma => {
          const pa = (ma?._actualChildren || []).find(x => x?.nodeName === "PA");
          return {
            team: ma?.data?.NA ?? null,
            lineDisplay: normalizeLineValue(pa?.data?.HD ?? null),
            lineAverage: normalizeLineValue(pa?.data?.HA ?? null),
            oddsDecimal: toDecimal(pa),
          };
        }),
    };
  }

  if (goalLine) {
    const mas = (goalLine._actualChildren || []).filter(n => n?.nodeName === "MA");
    const lineMa = mas.find(m => (m?._actualChildren || []).some(pa => pa?.data?.NA));
    const overMa = mas.find(m => m?.data?.NA === "Over");
    const underMa = mas.find(m => m?.data?.NA === "Under");

    const linePa = (lineMa?._actualChildren || []).find(n => n?.nodeName === "PA");
    const overPa = (overMa?._actualChildren || []).find(n => n?.nodeName === "PA");
    const underPa = (underMa?._actualChildren || []).find(n => n?.nodeName === "PA");

    result.goalLine = {
      marketId: "10143",
      marketName: goalLine?.data?.NA ?? "Goal Line",
      lineDisplay: normalizeLineValue(
        linePa?.data?.NA ?? overPa?.data?.HD ?? underPa?.data?.HD ?? null
      ),
      lineAverage: normalizeLineValue(
        overPa?.data?.HA ?? underPa?.data?.HA ?? null
      ),
      over: overPa ? { oddsDecimal: toDecimal(overPa) } : null,
      under: underPa ? { oddsDecimal: toDecimal(underPa) } : null,
    };
  }

  return result;
}
"""


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def launch_chrome_if_needed() -> subprocess.Popen | None:
    if is_port_open("127.0.0.1", DEBUG_PORT):
        print("→ Chrome con remote debugging ya está corriendo.")
        return None

    if not Path(CHROME_PATH).exists():
        raise FileNotFoundError(f"No encontré Chrome en: {CHROME_PATH}")

    cmd = [
        CHROME_PATH,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
    ]

    print("→ Lanzando Chrome real con remote debugging...")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return process


async def wait_for_debug_port(timeout_s: float = 15.0) -> None:
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        if is_port_open("127.0.0.1", DEBUG_PORT):
            return
        await asyncio.sleep(0.2)
    raise TimeoutError(f"No abrió el puerto {DEBUG_PORT} dentro de {timeout_s} s.")


async def wait_for_runtime(page, timeout_ms: int = RUNTIME_TIMEOUT_MS) -> None:
    await page.wait_for_function(
        """
        () => !!(
          window.NavLib &&
          window.DataReactLib &&
          window.NavLib.WebsiteNavigationManager &&
          typeof window.DataReactLib.getStemFromLookup === "function" &&
          window.NavLib.WebsiteNavigationManager.CurrentPageData
        )
        """,
        timeout=timeout_ms,
    )


async def wait_for_league_markets(page, timeout_ms: int = LEAGUE_TIMEOUT_MS) -> None:
    await page.wait_for_function(
        """
        () => {
          function findFirst(node, predicate) {
            if (!node) return null;
            if (predicate(node)) return node;
            for (const child of node._actualChildren || []) {
              const found = findFirst(child, predicate);
              if (found) return found;
            }
            return null;
          }

          if (
            !window.NavLib ||
            !window.DataReactLib ||
            !window.NavLib.WebsiteNavigationManager ||
            typeof window.DataReactLib.getStemFromLookup !== "function"
          ) {
            return false;
          }

          const topic = window.NavLib.WebsiteNavigationManager.CurrentPageData;
          if (!topic) return false;

          const stem = window.DataReactLib.getStemFromLookup(topic);
          if (!stem) return false;

          const ev = findFirst(stem, n => n?.nodeName === "EV");
          if (!ev) return false;

          const groups = (ev._actualChildren || []).filter(n => n?.nodeName === "MG");
          const ids = groups.map(g => g?.data?.ID ?? null);

          return ids.includes("40");
        }
        """,
        timeout=timeout_ms,
    )


async def wait_for_i1_markets(page, timeout_ms: int = I1_TIMEOUT_MS) -> None:
    await page.wait_for_function(
        """
        () => {
          function findFirst(node, predicate) {
            if (!node) return null;
            if (predicate(node)) return node;
            for (const child of node._actualChildren || []) {
              const found = findFirst(child, predicate);
              if (found) return found;
            }
            return null;
          }

          if (
            !window.NavLib ||
            !window.DataReactLib ||
            !window.NavLib.WebsiteNavigationManager ||
            typeof window.DataReactLib.getStemFromLookup !== "function"
          ) {
            return false;
          }

          const topic = window.NavLib.WebsiteNavigationManager.CurrentPageData;
          if (!topic) return false;

          const stem = window.DataReactLib.getStemFromLookup(topic);
          if (!stem) return false;

          const ev = findFirst(stem, n => n?.nodeName === "EV");
          if (!ev) return false;

          const groups = (ev._actualChildren || []).filter(n => n?.nodeName === "MG");
          const ids = groups.map(g => g?.data?.ID ?? null);

          return ids.includes("40") && ids.includes("981");
        }
        """,
        timeout=timeout_ms,
    )


async def wait_for_i3_markets(page, timeout_ms: int = I3_TIMEOUT_MS) -> None:
    await page.wait_for_function(
        """
        () => {
          function findFirst(node, predicate) {
            if (!node) return null;
            if (predicate(node)) return node;
            for (const child of node._actualChildren || []) {
              const found = findFirst(child, predicate);
              if (found) return found;
            }
            return null;
          }

          if (
            !window.NavLib ||
            !window.DataReactLib ||
            !window.NavLib.WebsiteNavigationManager ||
            typeof window.DataReactLib.getStemFromLookup !== "function"
          ) {
            return false;
          }

          const topic = window.NavLib.WebsiteNavigationManager.CurrentPageData;
          if (!topic) return false;

          const stem = window.DataReactLib.getStemFromLookup(topic);
          if (!stem) return false;

          const ev = findFirst(stem, n => n?.nodeName === "EV");
          if (!ev) return false;

          const groups = (ev._actualChildren || []).filter(n => n?.nodeName === "MG");
          const ids = groups.map(g => g?.data?.ID ?? null);

          return ids.includes("938") && ids.includes("10143");
        }
        """,
        timeout=timeout_ms,
    )


async def goto_with_retries(page, url: str, wait_condition, timeout_ms: int, label: str) -> None:
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            await wait_for_runtime(page, RUNTIME_TIMEOUT_MS)
            await wait_condition(page, timeout_ms)
            return
        except Exception as exc:
            last_error = exc
            print(f"   ↳ {label}: intento {attempt}/{MAX_RETRIES} falló: {exc}")

            if attempt < MAX_RETRIES:
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                    await wait_for_runtime(page, RUNTIME_TIMEOUT_MS)
                    await wait_condition(page, timeout_ms)
                    return
                except Exception as exc2:
                    last_error = exc2
                    print(f"   ↳ {label}: reload tras intento {attempt} también falló: {exc2}")

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"{label}: fallo desconocido.")


async def extract_fixture_in_isolated_page(context, fixture_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        page = await context.new_page()
        try:
            print(f"   ↳ fixture {fixture_id}: intento {attempt}/{MAX_RETRIES}")

            i1_data = await extract_i1(page, fixture_id)
            i3_data = await extract_i3(page, fixture_id)

            await page.close()
            return i1_data, i3_data, None

        except Exception as exc:
            last_error = str(exc)
            print(f"   ↳ fixture {fixture_id}: falló intento {attempt}: {exc}")

            try:
                await page.close()
            except Exception:
                pass

    return None, None, last_error

async def extract_league(page, league_url: str) -> dict[str, Any]:
    print("→ Navegando a liga...")
    await goto_with_retries(
        page,
        league_url,
        wait_for_league_markets,
        LEAGUE_TIMEOUT_MS,
        "liga",
    )

    print("→ Extrayendo liga...")
    data = await page.evaluate(EXTRACT_LEAGUE_JS)
    return data


async def extract_i1(page, fixture_id: str) -> dict[str, Any]:
    url = f"https://www.bet365.bet.ar/#/AC/B1/C1/D8/E{fixture_id}/F3/I1/"
    await goto_with_retries(page, url, wait_for_i1_markets, I1_TIMEOUT_MS, f"I1 {fixture_id}")
    return await page.evaluate(EXTRACT_I1_JS)


async def extract_i3(page, fixture_id: str) -> dict[str, Any]:
    url = f"https://www.bet365.bet.ar/#/AC/B1/C1/D8/E{fixture_id}/F3/I3/"
    await goto_with_retries(page, url, wait_for_i3_markets, I3_TIMEOUT_MS, f"I3 {fixture_id}")
    return await page.evaluate(EXTRACT_I3_JS)


async def scrape_full_league(league_url: str) -> dict[str, Any]:
    launch_chrome_if_needed()
    await wait_for_debug_port()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        # league_data = await extract_league(page, league_url)
        league_page = context.pages[0] if context.pages else await context.new_page()
        league_data = await extract_league(league_page, league_url)

        if not isinstance(league_data, dict):
            raise RuntimeError("El extractor de liga devolvió un formato inválido.")

        matches = league_data.get("matches", [])
        enriched_matches: list[dict[str, Any]] = []

        total = len(matches)
        for idx, match in enumerate(matches, start=1):
            fixture_id = match.get("fixtureId")
            home = match.get("home")
            away = match.get("away")

            print(f"→ [{idx}/{total}] {home} vs {away} ({fixture_id})")

            i1_data: dict[str, Any] | None = None
            i3_data: dict[str, Any] | None = None
            error: str | None = None

            i1_data, i3_data, error = await extract_fixture_in_isolated_page(context, fixture_id)
            # try:
            #     i1_data = await extract_i1(page, fixture_id)
            # except Exception as exc:
            #     error = f"I1: {exc}"

            # try:
            #     i3_data = await extract_i3(page, fixture_id)
            # except Exception as exc:
            #     error = f"{error} | I3: {exc}" if error else f"I3: {exc}"

            enriched_matches.append({
                "fixtureId": fixture_id,
                "home": home,
                "away": away,
                "dateLabel": match.get("dateLabel"),
                "timeLabel": match.get("timeLabel"),
                "leagueOdds1X2": match.get("oddsDecimal"),
                "details": {
                    "eventInfo": (
                        (i1_data or {}).get("eventInfo")
                        or (i3_data or {}).get("eventInfo")
                    ),
                    "fullTimeResult": (i1_data or {}).get("fullTimeResult"),
                    "goalsOverUnder": (i1_data or {}).get("goalsOverUnder"),
                    "asianHandicap": (i3_data or {}).get("asianHandicap"),
                    "goalLine": (i3_data or {}).get("goalLine"),
                    "error": error,
                }
            })

        return {
            "leagueId": league_data.get("leagueId"),
            "topic": league_data.get("topic"),
            "leagueName": league_data.get("leagueName"),
            "matches": enriched_matches,
        }


async def main() -> None:
    if len(sys.argv) < 2:
        print("Uso:")
        print('  python bet365_full_scraper.py "<URL_DE_LA_LIGA>" [salida.json]')
        raise SystemExit(1)

    league_url = sys.argv[1]
    output_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("salida.json")

    data = await scrape_full_league(league_url)

    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\nJSON guardado en: {output_path.resolve()}")
    print(f"Liga: {data.get('leagueName')}")
    print(f"Partidos extraídos: {len(data.get('matches', []))}")


if __name__ == "__main__":
    asyncio.run(main())