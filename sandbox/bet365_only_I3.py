import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright


CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEBUG_PORT = 9222
USER_DATA_DIR = "/tmp/chrome-bet365-debug"


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
    markets: groups.map(g => ({
      id: g?.data?.ID ?? null,
      name: g?.data?.NA ?? null
    })),
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


async def wait_for_runtime(page, timeout_ms: int = 30000) -> None:
    await page.wait_for_function(
        """
        () => !!(
          window.NavLib &&
          window.DataReactLib &&
          window.NavLib.WebsiteNavigationManager &&
          typeof window.DataReactLib.getStemFromLookup === "function"
        )
        """,
        timeout=timeout_ms,
    )


async def wait_for_i3_markets(page, timeout_ms: int = 15000) -> None:
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


async def extract_i3(page, fixture_id: str) -> dict:
    url = f"https://www.bet365.bet.ar/#/AC/B1/C1/D8/E{fixture_id}/F3/I3/"

    print("→ Navegando:", url)
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)

    print("→ Esperando runtime...")
    await wait_for_runtime(page, 30000)

    print("→ Esperando markets I3...")
    await wait_for_i3_markets(page, 15000)

    print("→ Extrayendo I3...")
    data = await page.evaluate(EXTRACT_I3_JS)
    return data


async def main():
    if len(sys.argv) < 2:
        print("Uso: python bet365_only_I3.py <fixture_id> [salida.json]")
        raise SystemExit(1)

    fixture_id = sys.argv[1]
    output_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else None

    launch_chrome_if_needed()
    await wait_for_debug_port()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        data = await extract_i3(page, fixture_id)

        if output_path:
            output_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            print(f"JSON guardado en: {output_path.resolve()}")

        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())