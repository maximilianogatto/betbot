"""
statshub_client.py
==================
Cliente liviano para los endpoints de Sportradar StatsHub que usa Playwright
SOLO para obtener el token Akamai (~2-3s), luego httpx puro para todo lo demás.

Flujo:
  1. grab_token(stats_url)  ->  abre el widget, intercepta el primer request a
                                sh.fn.sportradar.com, extrae ?T=, cierra el browser.
  2. StatsHubClient(token)  ->  httpx puro con el token cacheado, dura ~16h.

Uso rápido:
    import asyncio
    from statshub_client import grab_token, StatsHubClient

    async def main():
        # Una sola vez por sesión / día
        token_info = await grab_token("https://s5.sir.sportradar.com/bet365/es/match/61624682")
        client = StatsHubClient(token_info)

        # Esto ya es httpx puro, sin browser
        snapshot = client.match_snapshot(match_id=61624682, home_uid=2833, away_uid=2858)
        print(snapshot)

    asyncio.run(main())
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Any

import httpx

# Playwright es opcional — solo se usa en grab_token()
try:
    from playwright.async_api import async_playwright, Request
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

STATSHUB_BASE = "https://sh.fn.sportradar.com"
STATSHUB_ORIGIN = "https://statshub.sportradar.com"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

# Headers que el CDN Akamai acepta desde el widget
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Origin": STATSHUB_ORIGIN,
    "Referer": STATSHUB_ORIGIN + "/",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}

# Ruta del cache local del token (en el directorio de trabajo del bot)
TOKEN_CACHE_PATH = Path(".sportradar_token_cache.json")


# ---------------------------------------------------------------------------
# TokenInfo
# ---------------------------------------------------------------------------

@dataclass
class TokenInfo:
    raw: str           # El valor completo del param ?T=
    exp: int           # Unix timestamp de expiración
    client: str        # Ej: "bet365"
    origin: str        # Ej: "https://statshub.sportradar.com"
    grabbed_at: float  # time.time() cuando fue capturado

    @classmethod
    def from_url(cls, url: str) -> "TokenInfo":
        """Extrae el TokenInfo desde una URL completa que contenga ?T="""
        qs = parse_qs(urlparse(url).query)
        t_values = qs.get("T")
        if not t_values:
            raise ValueError(f"No se encontró el param ?T= en la URL: {url[:120]}")
        raw = t_values[0]
        return cls.from_raw(raw)

    @classmethod
    def from_raw(cls, raw: str) -> "TokenInfo":
        import base64
        parts = {}
        for segment in raw.split("~"):
            if "=" in segment:
                k, v = segment.split("=", 1)
                parts[k] = v
        
        exp = int(parts.get("exp", 0))
        
        data_b64 = parts.get("data", "")
        data_b64 += "=" * (-len(data_b64) % 4)
        try:
            data = json.loads(base64.b64decode(data_b64))
        except Exception:
            data = {}
        
        return cls(
            raw=raw,
            exp=exp,
            client=data.get("a", "unknown"),
            origin=data.get("o", STATSHUB_ORIGIN),
            grabbed_at=time.time(),
        )

    def is_valid(self, margin_seconds: int = 300) -> bool:
        """True si el token todavía no expiró (con margen de 5 min por defecto)."""
        return int(time.time()) < (self.exp - margin_seconds)

    def expires_in(self) -> float:
        return max(0.0, self.exp - time.time())

    def save(self, path: Path = TOKEN_CACHE_PATH) -> None:
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = TOKEN_CACHE_PATH) -> "TokenInfo | None":
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            return cls(**d)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# grab_token — la única parte que usa Playwright
# ---------------------------------------------------------------------------

def _resolve_user_data_dir(explicit: str | None) -> str | None:
    """
    Mismo orden de resolución que capture_runtime.py:
    1. Argumento explícito
    2. Variables de entorno SPORTRADAR_USER_DATA_DIR / BETBOT_SPORTRADAR_USER_DATA_DIR
    3. /tmp/chrome-sportradar-profile si existe
    """
    import os
    if explicit:
        return explicit
    for env in ("SPORTRADAR_USER_DATA_DIR", "BETBOT_SPORTRADAR_USER_DATA_DIR"):
        val = os.environ.get(env)
        if val:
            return val
    fallback = Path("/tmp/chrome-sportradar-profile")
    if fallback.exists():
        return str(fallback)
    return None


async def grab_token(
    stats_url: str,
    *,
    bootstrap_url: str | None = None,
    timeout_ms: int = 30_000,
    headless: bool = True,
    user_data_dir: str | None = None,
    cache_path: Path = TOKEN_CACHE_PATH,
    force_refresh: bool = False,
) -> TokenInfo:
    """
    Obtiene el token Akamai de Sportradar usando Playwright mínimo (~3-5s).

    El token se cachea y dura ~16h; Playwright solo corre una vez por sesión/día.
    Las siguientes llamadas usan el cache y entran directo a httpx.

    Parámetros:
        stats_url:     URL del widget de Sportradar (s5.sir.sportradar.com/bet365/es/match/ID)
                       O una URL de bet365 que tenga el widget embebido.
        bootstrap_url: URL de bet365 a cargar PRIMERO para tener sesión/cookies antes de
                       navegar al widget. Ej: "https://www.bet365.bet.ar/"
                       Recomendado cuando stats_url es de s5.sir.sportradar.com.
        user_data_dir: Perfil persistente de Chromium con las cookies de bet365.
                       Se auto-detecta por variable de entorno o /tmp/chrome-sportradar-profile.
    """
    if not force_refresh:
        cached = TokenInfo.load(cache_path)
        if cached and cached.is_valid():
            print(f"[token] Cache válido. Expira en {cached.expires_in()/3600:.1f}h.")
            return cached

    if not _HAS_PLAYWRIGHT:
        raise ImportError(
            "Playwright no instalado. Ejecutá:\n"
            "  pip install playwright && playwright install chromium"
        )

    resolved_profile = _resolve_user_data_dir(user_data_dir)
    is_direct_sr = "s5.sir.sportradar.com" in stats_url

    print(f"[token] Perfil: {resolved_profile or 'ninguno (sesión limpia)'}")
    if is_direct_sr and not bootstrap_url and not resolved_profile:
        print(
            "[token] ⚠  s5.sir.sportradar.com necesita sesión de bet365 para cargar el widget.\n"
            "         → Pasá --bootstrap-url 'https://www.bet365.bet.ar/' para entrar por bet365,\n"
            "         → o --user-data-dir con tu perfil real de Chrome que ya tiene la sesión."
        )

    token_info: TokenInfo | None = None
    seen_sr_urls: list[str] = []

    async with async_playwright() as p:
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
        ]

        if resolved_profile:
            ctx = await p.chromium.launch_persistent_context(
                resolved_profile,
                headless=headless,
                args=launch_args,
                viewport={"width": 1280, "height": 900},
                user_agent=UA,
                locale="es-AR",
                timezone_id="America/Argentina/Cordoba",
            )
            _browser = None
        else:
            _browser = await p.chromium.launch(headless=headless, args=launch_args)
            ctx = await _browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=UA,
                locale="es-AR",
                timezone_id="America/Argentina/Cordoba",
            )

        found = asyncio.Event()

        def on_request(request: Request) -> None:
            nonlocal token_info
            url = request.url
            if "sh.fn.sportradar.com" in url and "gismo" in url:
                seen_sr_urls.append(url[:140])
                if not found.is_set():
                    try:
                        info = TokenInfo.from_url(url)
                        token_info = info
                        found.set()
                        ep = url[url.find("/gismo/"):url.find("?")]
                        print(f"[token] ✓ Capturado en {ep!r}, válido {info.expires_in()/3600:.1f}h")
                    except ValueError:
                        pass

        # Escuchar en TODO el contexto (cubre iframes y páginas nuevas)
        ctx.on("request", on_request)

        page = await ctx.new_page()

        # Bloquear assets pesados para ir más rápido
        async def _block_assets(route):
            if route.request.resource_type in {"image", "font", "media", "stylesheet"}:
                await route.abort()
            elif any(route.request.url.endswith(ext) for ext in (".svg", ".woff2", ".woff", ".ttf")):
                await route.abort()
            else:
                await route.continue_()
        await ctx.route("**/*", _block_assets)

        try:
            # Paso 1 (opcional): ir a bet365 primero para establecer sesión
            if bootstrap_url:
                print(f"[token] Bootstrap → {bootstrap_url}")
                try:
                    await page.goto(bootstrap_url, wait_until="domcontentloaded", timeout=20_000)
                    await page.wait_for_timeout(2_000)
                except Exception as e:
                    print(f"[token] Bootstrap parcial ({type(e).__name__}), continuando...")

            # Paso 2: ir al widget de Sportradar
            print(f"[token] Widget → {stats_url}")
            try:
                await page.goto(stats_url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as e:
                print(f"[token] goto parcial ({type(e).__name__}), esperando requests...")

            # Esperar el token con el tiempo restante
            elapsed = 2.0 if bootstrap_url else 0.0
            wait_secs = max(5.0, timeout_ms / 1000 - elapsed)
            try:
                await asyncio.wait_for(found.wait(), timeout=wait_secs)
            except asyncio.TimeoutError:
                pass

        finally:
            await page.close()
            await ctx.close()
            if _browser:
                await _browser.close()

    if not token_info:
        if seen_sr_urls:
            diag = f"\n  URLs vistas sin token: {seen_sr_urls[:2]}"
        else:
            diag = (
                "\n  No llegó ningún request a sh.fn.sportradar.com."
                "\n\n  Causas más comunes:"
                "\n  1. El widget no cargó porque s5.sir.sportradar.com está bloqueado sin"
                "\n     sesión activa de bet365."
                "\n  2. Solución A: pasá --bootstrap-url 'https://www.bet365.bet.ar/' para"
                "\n     entrar por bet365 primero."
                "\n  3. Solución B: pasá --user-data-dir con tu perfil de Chrome que ya"
                "\n     tiene la sesión de bet365 (el mismo que usás en capture_everything.py)."
                "\n  4. Solución C: extraé el token de una captura existente:"
                "\n       python statshub_client.py --inject-token captures/realsociedad_valencia_full"
            )
        raise RuntimeError(f"No se pudo capturar el token desde {stats_url}.{diag}")

    token_info.save(cache_path)
    return token_info


# ---------------------------------------------------------------------------
# StatsHubClient — httpx puro
# ---------------------------------------------------------------------------

class StatsHubClient:
    """
    Cliente httpx puro para la API gismo de Sportradar StatsHub.
    No usa Playwright. Requiere un TokenInfo válido (obtenido con grab_token).

    Todos los métodos son síncronos. Para uso async, usar httpx.AsyncClient
    o correr en un thread con asyncio.to_thread().
    """

    def __init__(
        self,
        token: TokenInfo,
        client_slug: str = "bet365",
        lang: str = "en",
        tz: str = "Etc:UTC",
        timeout: float = 12.0,
    ) -> None:
        self.token = token
        self.client_slug = client_slug
        self.lang = lang
        self.tz = tz
        self._base = f"{STATSHUB_BASE}/{client_slug}/{lang}/{tz}/gismo"
        self._common_base = f"{STATSHUB_BASE}/common/{lang}/{tz}/gismo"
        self._timeout = timeout
        self._http = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={**BASE_HEADERS, "Origin": token.origin},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "StatsHubClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _url(self, endpoint: str, common: bool = False) -> str:
        base = self._common_base if common else self._base
        return f"{base}/{endpoint}?T={self.token.raw}"

    def _get(self, endpoint: str, common: bool = False) -> Any:
        if not self.token.is_valid():
            raise RuntimeError(
                f"El token Akamai expiró hace {(time.time() - self.token.exp)/60:.0f} minutos. "
                "Llamá a grab_token() para renovarlo."
            )
        url = self._url(endpoint, common=common)
        r = self._http.get(url)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Endpoints de metadata del partido
    # ------------------------------------------------------------------

    def match_timeline(self, match_id: int) -> dict:
        """Score y estado del partido. Candidato principal para live tracking."""
        return self._get(f"match_timeline/{match_id}")

    def match_timelinedelta(self, match_id: int) -> dict:
        """Delta del timeline. Más liviano para polling frecuente en vivo."""
        return self._get(f"match_timelinedelta/{match_id}")

    def match_info(self, match_id: int) -> dict:
        """Metadata del partido: estadio, árbitro, torneo, cobertura."""
        return self._get(f"match_info_statshub/{match_id}")

    def match_details(self, match_id: int) -> dict:
        """Detalle auxiliar del match (puede venir vacío en pre-match)."""
        return self._get(f"match_details/{match_id}")

    def stats_match_get(self, match_id: int) -> dict:
        """Snapshot del match con ids, equipos, resultado y señales live."""
        return self._get(f"stats_match_get/{match_id}")

    # ------------------------------------------------------------------
    # Odds / mercados
    # ------------------------------------------------------------------

    def match_markets(self, match_id: int) -> dict:
        """Mercados/odds del partido por HTTP. El hallazgo más fuerte."""
        return self._get(f"match_markets/{match_id}")

    def uniqueteam_markets(self, team_uid: int) -> dict:
        """Mercados del equipo (contexto de apuestas más amplio)."""
        return self._get(f"uniqueteam_markets/{team_uid}")

    def odds_ukformat(self) -> dict:
        """Tabla de conversión de odds en formato UK."""
        return self._get("odds_ukformat/", common=True)

    # ------------------------------------------------------------------
    # Contexto pre-match
    # ------------------------------------------------------------------

    def h2h_versus(self, home_uid: int, away_uid: int, match_id: int) -> dict:
        """Historial head-to-head entre los dos equipos."""
        return self._get(f"stats_h2h_versus/{home_uid}/{away_uid}/{match_id}")

    def team_versus(self, home_uid: int, away_uid: int) -> dict:
        """Stats versus completo entre los dos equipos."""
        return self._get(f"stats_team_versus/{home_uid}/{away_uid}/")

    def team_lastx(self, team_uid: int, n: int = 10) -> dict:
        """Últimos N partidos del equipo."""
        return self._get(f"stats_team_lastx/{team_uid}/{n}")

    def team_nextx(self, team_uid: int, n: int = 1) -> dict:
        """Próximos N partidos del equipo."""
        return self._get(f"stats_team_nextx/{team_uid}/{n}")

    def team_streaks(self, team_uid: int) -> dict:
        """Rachas del equipo (victorias, goles, etc.)."""
        return self._get(f"stats_team_streaks/{team_uid}", common=True)

    # ------------------------------------------------------------------
    # Tabla y standings
    # ------------------------------------------------------------------

    def season_tables(self, season_id: int, round_id: int | None = None) -> dict:
        """Tabla de posiciones de la temporada."""
        path = f"stats_season_tables/{season_id}"
        if round_id is not None:
            path += f"/{round_id}/"
        else:
            path += "//"
        return self._get(path)

    def formtable(self, season_id: int) -> dict:
        """Tabla de forma (últimos X partidos por equipo)."""
        return self._get(f"stats_formtable/{season_id}")

    def season_teamscoringconceding(self, season_id: int, team_uid: int, group: int = -1) -> dict:
        """Stats de goles a favor/en contra por equipo en la temporada."""
        return self._get(f"stats_season_teamscoringconceding/{season_id}/{team_uid}/{group}")

    # ------------------------------------------------------------------
    # Leaders
    # ------------------------------------------------------------------

    def season_topgoals(self, season_id: int, team_uid: int) -> dict:
        return self._get(f"stats_season_topgoals/{season_id}/{team_uid}")

    def season_topassists(self, season_id: int, team_uid: int) -> dict:
        return self._get(f"stats_season_topassists/{season_id}/{team_uid}")

    def season_topcards(self, season_id: int, team_uid: int) -> dict:
        return self._get(f"stats_season_topcards/{season_id}/{team_uid}")

    # ------------------------------------------------------------------
    # Lesiones
    # ------------------------------------------------------------------

    def season_injuries(self, season_id: int) -> dict:
        return self._get(f"stats_season_injuries/{season_id}")

    # ------------------------------------------------------------------
    # Live
    # ------------------------------------------------------------------

    def event_get(self) -> list:
        """Feed live global de eventos. Scope exacto a validar."""
        return self._get("event_get/")

    # ------------------------------------------------------------------
    # Snapshot rápido de un partido (llama varios endpoints en paralelo)
    # ------------------------------------------------------------------

    def match_snapshot(
        self,
        match_id: int,
        home_uid: int,
        away_uid: int,
        season_id: int | None = None,
        *,
        include_leaders: bool = False,
        include_injuries: bool = False,
        n_lastx: int = 10,
    ) -> dict:
        """
        Llama a los endpoints más relevantes para un partido en un solo método.
        Devuelve un dict con secciones: meta, timeline, markets, context.
        
        Para llamadas en paralelo (más rápido), usar match_snapshot_async().
        """
        snapshot: dict[str, Any] = {
            "match_id": match_id,
            "home_uid": home_uid,
            "away_uid": away_uid,
            "fetched_at": time.time(),
            "errors": {},
        }

        def safe(key: str, fn):
            try:
                snapshot[key] = fn()
            except Exception as e:
                snapshot["errors"][key] = str(e)
                snapshot[key] = None

        safe("meta",        lambda: self.match_info(match_id))
        safe("match",       lambda: self.stats_match_get(match_id))
        safe("timeline",    lambda: self.match_timeline(match_id))
        safe("markets",     lambda: self.match_markets(match_id))
        safe("h2h",         lambda: self.h2h_versus(home_uid, away_uid, match_id))
        safe("lastx_home",  lambda: self.team_lastx(home_uid, n_lastx))
        safe("lastx_away",  lambda: self.team_lastx(away_uid, n_lastx))
        safe("streaks_home",lambda: self.team_streaks(home_uid))
        safe("streaks_away",lambda: self.team_streaks(away_uid))

        if season_id:
            safe("tables",  lambda: self.season_tables(season_id))
            if include_leaders:
                safe("topgoals_home",   lambda: self.season_topgoals(season_id, home_uid))
                safe("topgoals_away",   lambda: self.season_topgoals(season_id, away_uid))
                safe("topassists_home", lambda: self.season_topassists(season_id, home_uid))
                safe("topassists_away", lambda: self.season_topassists(season_id, away_uid))
            if include_injuries:
                safe("injuries", lambda: self.season_injuries(season_id))

        return snapshot

    async def match_snapshot_async(
        self,
        match_id: int,
        home_uid: int,
        away_uid: int,
        season_id: int | None = None,
        *,
        include_leaders: bool = False,
        n_lastx: int = 10,
        concurrency: int = 6,
    ) -> dict:
        """
        Versión async del snapshot: lanza todos los requests en paralelo
        usando asyncio.to_thread. Mucho más rápido que la versión síncrona.
        """
        tasks_spec = {
            "meta":         (self.match_info,       (match_id,)),
            "match":        (self.stats_match_get,  (match_id,)),
            "timeline":     (self.match_timeline,   (match_id,)),
            "markets":      (self.match_markets,    (match_id,)),
            "h2h":          (self.h2h_versus,       (home_uid, away_uid, match_id)),
            "lastx_home":   (self.team_lastx,       (home_uid, n_lastx)),
            "lastx_away":   (self.team_lastx,       (away_uid, n_lastx)),
            "streaks_home": (self.team_streaks,     (home_uid,)),
            "streaks_away": (self.team_streaks,     (away_uid,)),
        }

        if season_id:
            tasks_spec["tables"] = (self.season_tables, (season_id,))
            if include_leaders:
                tasks_spec.update({
                    "topgoals_home":   (self.season_topgoals,   (season_id, home_uid)),
                    "topgoals_away":   (self.season_topgoals,   (season_id, away_uid)),
                    "topassists_home": (self.season_topassists, (season_id, home_uid)),
                    "topassists_away": (self.season_topassists, (season_id, away_uid)),
                })

        semaphore = asyncio.Semaphore(concurrency)
        snapshot: dict[str, Any] = {
            "match_id": match_id,
            "home_uid": home_uid,
            "away_uid": away_uid,
            "fetched_at": time.time(),
            "errors": {},
        }

        async def run_one(key: str, fn, args: tuple) -> None:
            async with semaphore:
                try:
                    result = await asyncio.to_thread(fn, *args)
                    snapshot[key] = result
                except Exception as e:
                    snapshot["errors"][key] = str(e)
                    snapshot[key] = None

        await asyncio.gather(*(run_one(k, fn, args) for k, (fn, args) in tasks_spec.items()))
        return snapshot


# ---------------------------------------------------------------------------
# Helpers CLI
# ---------------------------------------------------------------------------

def _token_from_capture(capture_dir: "Path") -> "TokenInfo | None":
    """
    Extrae el token Akamai de una captura existente (useful_fetch.ndjson o
    filtered_fetch.ndjson). Útil para inyectar un token sin abrir Playwright.
    """
    for fname in ("useful_fetch.ndjson", "filtered_fetch.ndjson"):
        fpath = capture_dir / fname
        if not fpath.exists():
            continue
        with fpath.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    url = rec.get("url", "")
                    if "sh.fn.sportradar.com" in url and "gismo" in url and "?T=" in url:
                        info = TokenInfo.from_url(url)
                        print(f"[token] Extraído de {fname}: cliente={info.client}, "
                              f"exp={info.exp}")
                        return info
                except Exception:
                    continue
    return None


# ---------------------------------------------------------------------------
# CLI de prueba rápida
# ---------------------------------------------------------------------------

def _resolve_uids_from_match(client: "StatsHubClient", match_id: int) -> tuple[int, int, int | None]:
    """
    Llama a stats_match_get para extraer home_uid, away_uid y season_id
    automáticamente cuando no se pasan como argumento.
    """
    data = client.stats_match_get(match_id)
    teams = data.get("teams", {})
    home_uid = teams.get("home", {}).get("uid")
    away_uid = teams.get("away", {}).get("uid")
    season_id = data.get("_seasonid")
    if not home_uid or not away_uid:
        raise ValueError(
            f"No se pudieron extraer los UIDs desde stats_match_get/{match_id}. "
            f"Respuesta: {json.dumps(data)[:300]}"
        )
    home_name = teams.get("home", {}).get("name", "?")
    away_name = teams.get("away", {}).get("name", "?")
    print(f"  Auto-resuelto: {home_name} (uid={home_uid}) vs {away_name} (uid={away_uid}), season={season_id}")
    return home_uid, away_uid, season_id


async def _cli_main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Prueba el cliente StatsHub (Playwright mínimo + httpx puro).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Auto-detecta UIDs y season desde el match_id:
  python statshub_client.py "https://s5.sir.sportradar.com/bet365/es/match/61624682" --match-id 61624682

  # Con UIDs explícitos (Celta=2817, Sevilla=2833):
  python statshub_client.py "https://s5.sir.sportradar.com/bet365/es/match/61624682" \\
    --match-id 61624682 --home-uid 2817 --away-uid 2833 --season-id 130805

  # Solo un endpoint:
  python statshub_client.py "https://..." --match-id 61624682 --endpoint match_markets

  # Reusar token cacheado (no abre Playwright):
  python statshub_client.py "https://..." --match-id 61624682 --no-browser
        """
    )
    parser.add_argument("stats_url", help="URL del widget de Sportradar")
    parser.add_argument("--match-id", type=int, required=True)
    parser.add_argument("--home-uid", type=int, default=None,
                        help="UID del equipo local (se auto-detecta si se omite)")
    parser.add_argument("--away-uid", type=int, default=None,
                        help="UID del equipo visitante (se auto-detecta si se omite)")
    parser.add_argument("--season-id", type=int, default=None,
                        help="ID de temporada (se auto-detecta si se omite)")
    parser.add_argument("--endpoint", default="snapshot",
                        help="Endpoint a probar: snapshot | match_timeline | match_markets | "
                             "h2h | tables | match_info | stats_match_get")
    parser.add_argument("--bootstrap-url", default=None,
                        help="URL de bet365 a cargar primero (establece sesión). "
                             "Ej: 'https://www.bet365.bet.ar/'  <- necesario cuando el widget "
                             "no carga sin cookies de bet365.")
    parser.add_argument("--user-data-dir", default=None,
                        help="Perfil de Chromium con sesión de bet365. Auto-detecta "
                             "BETBOT_SPORTRADAR_USER_DATA_DIR o /tmp/chrome-sportradar-profile.")
    parser.add_argument("--inject-token", type=Path, default=None, metavar="CAPTURE_DIR",
                        help="Extraer token de una captura existente sin abrir Playwright. "
                             "Ej: --inject-token captures/realsociedad_valencia_full")
    parser.add_argument("--force-token", action="store_true",
                        help="Forzar renovación del token aunque haya uno cacheado válido")
    parser.add_argument("--no-browser", action="store_true",
                        help="No abrir Playwright; usar solo el token cacheado")
    parser.add_argument("--out", type=Path, default=None,
                        help="Guardar el resultado en este archivo JSON")
    args = parser.parse_args()

    t0 = time.time()

    # ----- Token -----
    if args.inject_token:
        token = _token_from_capture(args.inject_token)
        if not token:
            raise SystemExit(f"No se encontró ?T= en capturas de {args.inject_token}")
        if not token.is_valid():
            hrs = (time.time() - token.exp) / 3600
            print(f"[token] ⚠  Token expiró hace {hrs:.1f}h — solo sirve para probar flujo.")
        else:
            print(f"[token] Inyectado desde captura, válido {token.expires_in()/3600:.1f}h más.")
        token.save()
    elif args.no_browser:
        token = TokenInfo.load()
        if not token or not token.is_valid():
            raise SystemExit("No hay token cacheado válido. Corré sin --no-browser primero.")
        print(f"[token] Cache válido, expira en {token.expires_in()/3600:.1f}h.")
    else:
        print(f"[1] Obteniendo token (Playwright mínimo)...")
        token = await grab_token(
            args.stats_url,
            bootstrap_url=getattr(args, "bootstrap_url", None),
            user_data_dir=getattr(args, "user_data_dir", None),
            force_refresh=args.force_token,
        )
    t1 = time.time()
    print(f"[1] Token listo en {t1-t0:.1f}s\n")

    # ----- Cliente httpx -----
    with StatsHubClient(token) as client:

        # Auto-resolver UIDs si no se pasaron
        home_uid = args.home_uid
        away_uid = args.away_uid
        season_id = args.season_id

        if args.endpoint in ("snapshot", "h2h") and (not home_uid or not away_uid):
            print(f"[2] Auto-detectando UIDs desde stats_match_get/{args.match_id}...")
            home_uid, away_uid, auto_season = _resolve_uids_from_match(client, args.match_id)
            if not season_id:
                season_id = auto_season

        t2 = time.time()

        # ----- Llamada -----
        print(f"[3] Fetching: {args.endpoint}...")
        if args.endpoint == "snapshot":
            result = await client.match_snapshot_async(
                args.match_id, home_uid, away_uid,
                season_id=season_id,
            )
        elif args.endpoint == "match_timeline":
            result = client.match_timeline(args.match_id)
        elif args.endpoint == "match_markets":
            result = client.match_markets(args.match_id)
        elif args.endpoint == "match_info":
            result = client.match_info(args.match_id)
        elif args.endpoint == "stats_match_get":
            result = client.stats_match_get(args.match_id)
        elif args.endpoint == "h2h":
            result = client.h2h_versus(home_uid, away_uid, args.match_id)
        elif args.endpoint == "tables":
            if not season_id:
                raise SystemExit("--season-id requerido para tables")
            result = client.season_tables(season_id)
        else:
            raise SystemExit(f"Endpoint desconocido: {args.endpoint}")

    t3 = time.time()
    print(f"[3] Fetch en {t3-t2:.1f}s | Total: {t3-t0:.1f}s (Playwright: {t1-t0:.1f}s)\n")

    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"→ Guardado en: {args.out}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])

    if isinstance(result, dict) and result.get("errors"):
        print(f"\n⚠ Endpoints con error: {result['errors']}")


if __name__ == "__main__":
    asyncio.run(_cli_main())