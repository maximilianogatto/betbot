from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# EXTRACTOR_JS = r"""
# () => {
#   function findFirst(node, predicate) {
#     if (!node) return null;
#     if (predicate(node)) return node;

#     for (const child of node._actualChildren || []) {
#       const found = findFirst(child, predicate);
#       if (found) return found;
#     }

#     return null;
#   }

#   function fractionalToDecimal(frac) {
#     if (!frac || typeof frac !== "string" || !frac.includes("/")) return null;
#     const [a, b] = frac.split("/").map(Number);
#     if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return null;
#     return +(a / b + 1).toFixed(2);
#   }

#   function extractLeagueMatchesFromStem(stem) {
#     const result = {
#       leagueId: stem?.data?.ID ?? null,
#       topic: stem?.data?.IT ?? null,
#       leagueName: null,
#       matches: []
#     };

#     const ev = findFirst(stem, n => n?.nodeName === "EV");
#     if (!ev) {
#       return { ...result, error: "No se encontró nodo EV." };
#     }

#     const marketGroups = ev._actualChildren || [];

#     const leagueMeta = marketGroups.find(
#       n => n?.nodeName === "MG" && n?.data?.ID === "LMAB"
#     );
#     if (leagueMeta?.data?.CC) {
#       result.leagueName = leagueMeta.data.CC;
#     }

#     const fullTimeGroup = marketGroups.find(
#       n => n?.nodeName === "MG" && n?.data?.ID === "40"
#     );
#     if (!fullTimeGroup) {
#       return { ...result, error: "No se encontró MG ID=40 (Full Time Result)." };
#     }

#     const markets = fullTimeGroup._actualChildren || [];

#     const teamsMarket = markets.find(
#       m => m?.nodeName === "MA" && m?.data?.NA === " "
#     );
#     const homeMarket = markets.find(
#       m => m?.nodeName === "MA" && m?.data?.NA === "1"
#     );
#     const drawMarket = markets.find(
#       m => m?.nodeName === "MA" && m?.data?.NA === "X"
#     );
#     const awayMarket = markets.find(
#       m => m?.nodeName === "MA" && m?.data?.NA === "2"
#     );

#     if (!teamsMarket || !homeMarket || !drawMarket || !awayMarket) {
#       return {
#         ...result,
#         error: "No se encontraron todas las ramas del mercado 1/X/2."
#       };
#     }

#     const fixtures = new Map();

#     for (const pa of teamsMarket?._actualChildren || []) {
#       const fi = pa?.data?.FI;
#       if (!fi) continue;

#       fixtures.set(fi, {
#         fixtureId: fi,
#         home: pa?.data?.NA ?? null,
#         away: pa?.data?.N2 ?? null,
#         oddsFractional: { "1": null, "X": null, "2": null },
#         oddsDecimal: { "1": null, "X": null, "2": null }
#       });
#     }

#     function mergeOdds(marketNode, key) {
#       for (const pa of marketNode?._actualChildren || []) {
#         const fi = pa?.data?.FI;
#         if (!fi || !fixtures.has(fi)) continue;

#         const frac = pa?.data?.OD ?? null;
#         fixtures.get(fi).oddsFractional[key] = frac;
#         fixtures.get(fi).oddsDecimal[key] = fractionalToDecimal(frac);
#       }
#     }

#     mergeOdds(homeMarket, "1");
#     mergeOdds(drawMarket, "X");
#     mergeOdds(awayMarket, "2");

#     result.matches = Array.from(fixtures.values());
#     return result;
#   }

#   try {
#     if (
#       typeof NavLib === "undefined" ||
#       !NavLib?.WebsiteNavigationManager?.CurrentPageData ||
#       typeof DataReactLib === "undefined" ||
#       typeof DataReactLib.getStemFromLookup !== "function"
#     ) {
#       return {
#         error: "NavLib/DataReactLib no disponibles todavía."
#       };
#     }

#     const topic = NavLib.WebsiteNavigationManager.CurrentPageData;
#     const stem = DataReactLib.getStemFromLookup(topic);

#     if (!stem) {
#       return {
#         error: "No se encontró stem para el topic actual.",
#         topic
#       };
#     }

#     return extractLeagueMatchesFromStem(stem);
#   } catch (err) {
#     return {
#       error: String(err)
#     };
#   }
# }
# """

# EXTRACTOR_JS = r"""
# () => {
#   function findFirst(node, predicate) {
#     if (!node) return null;
#     if (predicate(node)) return node;
#     for (const child of node._actualChildren || []) {
#       const found = findFirst(child, predicate);
#       if (found) return found;
#     }
#     return null;
#   }

#   function fractionalToDecimal(frac) {
#     if (!frac || typeof frac !== "string" || !frac.includes("/")) return null;
#     const [a, b] = frac.split("/").map(Number);
#     if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return null;
#     return +(a / b + 1).toFixed(2);
#   }

#   function norm(s) {
#     return (s || "").replace(/\s+/g, " ").trim();
#   }

#   function extractTreeMatches(stem) {
#     const ev = findFirst(stem, n => n?.nodeName === "EV");
#     if (!ev) return [];

#     const marketGroups = ev._actualChildren || [];

#     const leagueMeta = marketGroups.find(
#       n => n?.nodeName === "MG" && n?.data?.ID === "LMAB"
#     );

#     const fullTimeGroup = marketGroups.find(
#       n => n?.nodeName === "MG" && n?.data?.ID === "40"
#     );
#     if (!fullTimeGroup) return [];

#     const markets = fullTimeGroup._actualChildren || [];

#     const teamsMarket = markets.find(
#       m => m?.nodeName === "MA" && m?.data?.NA === " "
#     );
#     const homeMarket = markets.find(
#       m => m?.nodeName === "MA" && m?.data?.NA === "1"
#     );
#     const drawMarket = markets.find(
#       m => m?.nodeName === "MA" && m?.data?.NA === "X"
#     );
#     const awayMarket = markets.find(
#       m => m?.nodeName === "MA" && m?.data?.NA === "2"
#     );

#     if (!teamsMarket || !homeMarket || !drawMarket || !awayMarket) {
#       return [];
#     }

#     const fixtures = new Map();

#     for (const pa of teamsMarket?._actualChildren || []) {
#       const fi = pa?.data?.FI;
#       if (!fi) continue;

#       fixtures.set(fi, {
#         fixtureId: fi,
#         home: pa?.data?.NA ?? null,
#         away: pa?.data?.N2 ?? null,
#         dateLabel: null,
#         timeLabel: null,
#         oddsDecimal: { "1": null, "X": null, "2": null }
#       });
#     }

#     function mergeOdds(marketNode, key) {
#       for (const pa of marketNode?._actualChildren || []) {
#         const fi = pa?.data?.FI;
#         if (!fi || !fixtures.has(fi)) continue;

#         fixtures.get(fi).oddsDecimal[key] = fractionalToDecimal(pa?.data?.OD ?? null);
#       }
#     }

#     mergeOdds(homeMarket, "1");
#     mergeOdds(drawMarket, "X");
#     mergeOdds(awayMarket, "2");

#     return {
#       leagueName: leagueMeta?.data?.CC ?? null,
#       matches: Array.from(fixtures.values())
#     };
#   }

#   function extractDateHeaders() {
#     const dateRegex = /^(Lun|Mar|Mié|Mie|Jue|Vie|Sáb|Sab|Dom)\s+\d{1,2}\s+[a-záéíóú]{3}$/i;

#     return [...document.querySelectorAll("*")]
#       .map(el => ({
#         el,
#         text: norm(el.innerText),
#         top: el.getBoundingClientRect().top
#       }))
#       .filter(x => dateRegex.test(x.text));
#   }

#   function closestPreviousDate(top, headers) {
#     const prev = headers.filter(h => h.top <= top).sort((a, b) => b.top - a.top);
#     return prev[0]?.text || null;
#   }

#   function findRowForMatch(home, away) {
#     const teamNodes = [...document.querySelectorAll(".rcl-ParticipantFixtureDetailsTeam_TeamName")]
#       .filter(el => norm(el.innerText) === home);

#     for (const node of teamNodes) {
#       let cur = node;
#       for (let i = 0; i < 8 && cur; i++) {
#         const txt = norm(cur.innerText);
#         const hasHome = txt.includes(home);
#         const hasAway = txt.includes(away);
#         const hasTime = /\b([01]?\d|2[0-3]):[0-5]\d\b/.test(txt);
#         const smallEnough = txt.length < 80;

#         if (hasHome && hasAway && hasTime && smallEnough) {
#           return cur;
#         }
#         cur = cur.parentElement;
#       }
#     }

#     return null;
#   }

#   function mergeDomDateTime(matches) {
#     const headers = extractDateHeaders();

#     return matches.map(m => {
#       const row = findRowForMatch(m.home, m.away);
#       const txt = norm(row?.innerText || "");
#       const time = (txt.match(/\b([01]?\d|2[0-3]):[0-5]\d\b/) || [null])[0];
#       const top = row?.getBoundingClientRect?.().top ?? null;
#       const date = top != null ? closestPreviousDate(top, headers) : null;

#       return {
#         ...m,
#         dateLabel: date,
#         timeLabel: time
#       };
#     });
#   }

#   try {
#     if (
#       typeof NavLib === "undefined" ||
#       !NavLib?.WebsiteNavigationManager?.CurrentPageData ||
#       typeof DataReactLib === "undefined" ||
#       typeof DataReactLib.getStemFromLookup !== "function"
#     ) {
#       return {
#         error: "NavLib/DataReactLib no disponibles todavía."
#       };
#     }

#     const topic = NavLib.WebsiteNavigationManager.CurrentPageData;
#     const stem = DataReactLib.getStemFromLookup(topic);

#     if (!stem) {
#       return {
#         error: "No se encontró stem para el topic actual.",
#         topic
#       };
#     }

#     const base = extractTreeMatches(stem);

#     return {
#       leagueId: stem?.data?.ID ?? null,
#       topic: stem?.data?.IT ?? null,
#       leagueName: base.leagueName,
#       matches: mergeDomDateTime(base.matches)
#     };
#   } catch (err) {
#     return {
#       error: String(err)
#     };
#   }
# }
# """


EXTRACTOR_JS = r"""
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
        leagueName: leagueMeta?.data?.CC ?? null,
        matches: []
      };
    }

    const markets = fullTimeGroup._actualChildren || [];

    const teamsMarket = markets.find(
      m => m?.nodeName === "MA" && m?.data?.NA === " "
    );
    const homeMarket = markets.find(
      m => m?.nodeName === "MA" && m?.data?.NA === "1"
    );
    const drawMarket = markets.find(
      m => m?.nodeName === "MA" && m?.data?.NA === "X"
    );
    const awayMarket = markets.find(
      m => m?.nodeName === "MA" && m?.data?.NA === "2"
    );

    if (!teamsMarket || !homeMarket || !drawMarket || !awayMarket) {
      return {
        leagueName: leagueMeta?.data?.CC ?? null,
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
            ? Math.round(value * 100) / 100
            : null;
      }
    }

    mergeOdds(homeMarket, "1");
    mergeOdds(drawMarket, "X");
    mergeOdds(awayMarket, "2");

    return {
      leagueName: leagueMeta?.data?.CC ?? null,
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
      return {
        error: "NavLib/DataReactLib no disponibles todavía."
      };
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
    return {
      error: String(err)
    };
  }
}
"""

async def scrape_league(url: str, headless: bool = True, wait_ms: int = 4000) -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="es-ES",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
        )

        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            await page.wait_for_function(
                """
                () =>
                  typeof NavLib !== 'undefined' &&
                  typeof DataReactLib !== 'undefined' &&
                  NavLib?.WebsiteNavigationManager?.CurrentPageData &&
                  typeof DataReactLib.getStemFromLookup === 'function'
                """,
                timeout=60000,
            )

            await page.wait_for_timeout(wait_ms)

            data = await page.evaluate(EXTRACTOR_JS)

            if not isinstance(data, dict):
                raise RuntimeError("El extractor devolvió un formato inesperado.")

            return data

        except PlaywrightTimeoutError as exc:
            raise RuntimeError("Timeout cargando la página o el runtime interno.") from exc
        finally:
            await context.close()
            await browser.close()


async def main() -> None:
    if len(sys.argv) < 2:
        print("Uso:")
        print('  python3 bet365_data.py "<URL_DE_LA_LIGA>" [archivo_salida.json]')
        sys.exit(1)

    url = sys.argv[1]
    output_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("salida.json")

    data = await scrape_league(url)

    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"JSON guardado en: {output_path.resolve()}")
    print(f"Partidos extraídos: {len(data.get('matches', []))}")
    if data.get("leagueName"):
        print(f"Liga: {data['leagueName']}")
    if data.get("error"):
        print(f"Error reportado por extractor: {data['error']}")


if __name__ == "__main__":
    asyncio.run(main())