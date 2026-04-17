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


PROBE_JS = r"""
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

  const topic = window.NavLib?.WebsiteNavigationManager?.CurrentPageData ?? null;
  const hasDataReact = !!window.DataReactLib;
  const hasGetStem = typeof window.DataReactLib?.getStemFromLookup === "function";
  const stem = topic && hasGetStem ? window.DataReactLib.getStemFromLookup(topic) : null;
  const ev = findFirst(stem, n => n?.nodeName === "EV");
  const groups = (ev?._actualChildren || []).filter(n => n?.nodeName === "MG");

  return {
    topic,
    hasDataReact,
    hasGetStem,
    hasStem: !!stem,
    hasEV: !!ev,
    groupsCount: groups.length,
    marketIds: groups.map(g => ({
      id: g?.data?.ID ?? null,
      name: g?.data?.NA ?? null,
      sy: g?.data?.SY ?? null
    })),
    eventName: ev?.data?.EX ?? null,
    startTimeRaw: ev?.data?.CM ?? null,
  };
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


async def wait_for_i1_markets(page, timeout_ms: int = 15000) -> None:
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


async def main():
    if len(sys.argv) != 2:
        print("Uso: python bet365_probe_i1.py <fixture_id>")
        raise SystemExit(1)

    fixture_id = sys.argv[1]
    url = f"https://www.bet365.bet.ar/#/AC/B1/C1/D8/E{fixture_id}/F3/I1/"

    chrome_process = launch_chrome_if_needed()
    await wait_for_debug_port()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        print("→ Navegando:", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        print("→ Esperando runtime...")
        await wait_for_runtime(page, 30000)

        print("→ Esperando markets I1...")
        await wait_for_i1_markets(page, 15000)

        print("→ Extrayendo estado final...")
        data = await page.evaluate(PROBE_JS)
        print(json.dumps(data, ensure_ascii=False, indent=2))

        # No cierro browser porque está conectado a Chrome real.
        # Si querés cerrar Chrome lanzado por este script, descomentá:
        # if chrome_process is not None:
        #     chrome_process.terminate()


if __name__ == "__main__":
    asyncio.run(main())