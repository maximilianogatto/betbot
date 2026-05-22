"""
probe_http_investigation.py
============================
Herramienta de investigación para determinar si los endpoints de Sportradar
se pueden golpear con HTTP puro (httpx) sin Playwright.

Paso 1: Extrae las URLs completas (con query params) de las capturas existentes.
Paso 2: Las prueba directamente con httpx usando distintas combinaciones de headers.
Paso 3: Reporta cuáles funcionan, cuáles necesitan cookies, y cuáles están firmadas.

Uso:
    python probe_http_investigation.py <capture_dir>
    python probe_http_investigation.py captures/realsociedad_valencia_full

    # Con cookies exportadas desde el navegador (EditThisCookie o similar):
    python probe_http_investigation.py captures/test --cookies cookies.json

    # Para ver todas las URLs capturadas sin probar nada:
    python probe_http_investigation.py captures/test --list-only
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    import httpx
except ImportError:
    raise SystemExit("Instalá httpx: pip install httpx")


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

GISMO_RE = re.compile(r"/gismo/([^/?]+)")

# Headers que simulan que el pedido viene desde el widget embebido en bet365
HEADER_SETS = {
    "plain": {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    },
    "with_referer_sportradar": {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-AR,es;q=0.9",
        "Referer": "https://s5.sir.sportradar.com/",
        "Origin": "https://s5.sir.sportradar.com",
    },
    "with_referer_bet365": {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-AR,es;q=0.9",
        "Referer": "https://www.bet365.bet.ar/",
        "Origin": "https://www.bet365.bet.ar",
    },
    "with_referer_bet365_com": {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-AR,es;q=0.9",
        "Referer": "https://www.bet365.com/",
        "Origin": "https://www.bet365.com",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
    },
}


# ---------------------------------------------------------------------------
# Carga de capturas
# ---------------------------------------------------------------------------

def load_urls_from_capture(capture_dir: Path) -> list[dict]:
    """
    Extrae URLs completas de useful_fetch.ndjson o filtered_fetch.ndjson.
    Prioriza useful_fetch si existe.
    """
    for fname in ["useful_fetch.ndjson", "filtered_fetch.ndjson", "responses.ndjson"]:
        fpath = capture_dir / fname
        if fpath.exists():
            print(f"  Fuente: {fpath.name}")
            records = []
            with fpath.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        url = rec.get("url", "")
                        if "gismo" in url or "sir.sportradar" in url:
                            records.append({
                                "url": url,
                                "endpoint": _extract_endpoint(url),
                                "status": rec.get("status"),
                                "size": len(rec.get("body", "") or rec.get("text", "")),
                            })
                    except json.JSONDecodeError:
                        continue
            return records
    return []


def _extract_endpoint(url: str) -> str:
    m = GISMO_RE.search(url)
    return m.group(1) if m else urlparse(url).path.split("/")[-1]


def _has_query_params(url: str) -> bool:
    return bool(urlparse(url).query)


def _classify_params(url: str) -> dict:
    """Analiza los query params para detectar firmas o tokens."""
    params = parse_qs(urlparse(url).query)
    result = {
        "has_params": bool(params),
        "param_keys": list(params.keys()),
        "likely_signed": False,
        "likely_session": False,
    }
    sign_keywords = {"_bcid", "_ck", "token", "sig", "sign", "auth", "key", "expires", "_t", "ts"}
    session_keywords = {"session", "sid", "ssid", "_sid", "bouId", "bou_id"}
    
    for k in params:
        kl = k.lower()
        if any(sk in kl for sk in sign_keywords):
            result["likely_signed"] = True
        if any(sk in kl for sk in session_keywords):
            result["likely_session"] = True
    return result


# ---------------------------------------------------------------------------
# Probe HTTP
# ---------------------------------------------------------------------------

def probe_url(url: str, cookies: dict | None = None) -> dict:
    """Prueba una URL con distintos header sets y reporta resultados."""
    results = {}
    
    for label, headers in HEADER_SETS.items():
        try:
            with httpx.Client(timeout=12, follow_redirects=True) as client:
                r = client.get(url, headers=headers, cookies=cookies or {})
                body_preview = ""
                is_json = False
                try:
                    data = r.json()
                    is_json = True
                    body_preview = json.dumps(data)[:200]
                except Exception:
                    body_preview = r.text[:200].replace("\n", " ")
                
                results[label] = {
                    "status": r.status_code,
                    "ok": r.status_code == 200 and is_json,
                    "content_type": r.headers.get("content-type", "?"),
                    "deny_reason": r.headers.get("x-deny-reason"),
                    "body_preview": body_preview,
                    "is_json": is_json,
                }
        except httpx.TimeoutException:
            results[label] = {"status": "TIMEOUT", "ok": False}
        except Exception as e:
            results[label] = {"status": "ERROR", "ok": False, "error": str(e)}
        
        # Si ya funcionó, no hace falta probar los demás headers
        if results[label].get("ok"):
            break
        time.sleep(0.3)
    
    return results


# ---------------------------------------------------------------------------
# Análisis de parámetros de firma
# ---------------------------------------------------------------------------

def analyze_signing_pattern(urls: list[str]) -> None:
    """
    Compara los query params de varias URLs del mismo endpoint para detectar
    si hay tokens variables (firma por request) o fijos (config estática).
    """
    by_endpoint: dict[str, list[str]] = {}
    for url in urls:
        ep = _extract_endpoint(url)
        by_endpoint.setdefault(ep, []).append(url)
    
    print("\n=== Análisis de parámetros de firma ===")
    for ep, ep_urls in by_endpoint.items():
        if len(ep_urls) < 2:
            continue
        all_params = [set(parse_qs(urlparse(u).query).keys()) for u in ep_urls]
        common = all_params[0].intersection(*all_params[1:])
        variable = set().union(*all_params) - common
        print(f"\n  {ep} ({len(ep_urls)} URLs)")
        print(f"    Params fijos:    {sorted(common)}")
        print(f"    Params variables: {sorted(variable)}")


# ---------------------------------------------------------------------------
# Alternativas sin Playwright
# ---------------------------------------------------------------------------

def suggest_alternatives(probe_results: dict) -> None:
    """
    Basado en los resultados del probe, sugiere la mejor estrategia.
    """
    print("\n=== Estrategias alternativas ===\n")

    any_ok = any(
        any(v.get("ok") for v in r["probe"].values())
        for r in probe_results.values()
    )

    signed_endpoints = [
        ep for ep, r in probe_results.items() if r["url_analysis"]["likely_signed"]
    ]
    session_endpoints = [
        ep for ep, r in probe_results.items() if r["url_analysis"]["likely_session"]
    ]
    ip_blocked = [
        ep for ep, r in probe_results.items()
        if any(v.get("deny_reason") == "host_not_allowed" for v in r["probe"].values())
    ]

    if any_ok:
        working = [ep for ep, r in probe_results.items() if any(v.get("ok") for v in r["probe"].values())]
        print(f"✅ HTTPX PURO funciona para: {working}")
        print("   -> Podés reemplazar Playwright con httpx para estos endpoints.")
        print("   -> Mirá qué header set funcionó y usalo directamente.\n")

    if ip_blocked:
        print(f"🔒 IP ALLOWLIST (Sportradar B2B): {ip_blocked}")
        print("   Sportradar tiene a los clientes licenciados (como bet365) en allowlist.")
        print("   Opciones:")
        print("   A) Playwright sigue siendo necesario (el browser pasa como cliente legítimo).")
        print("   B) VPS con IP de Argentina + cookies reales exportadas del browser.")
        print("   C) Buscar si bet365 tiene su propio proxy estadístico.\n")

    if signed_endpoints:
        print(f"🔑 URLs FIRMADAS (tokens en query params): {signed_endpoints}")
        print("   -> Los tokens probablemente se generan en el JS del widget.")
        print("   -> Estrategia: capturar 1 vez con Playwright para obtener el token,")
        print("      luego reusar con httpx mientras el token sea válido.")
        print("   -> Verificar TTL del token con múltiples intentos en el tiempo.\n")

    if session_endpoints:
        print(f"🍪 SESIÓN/COOKIES requeridas: {session_endpoints}")
        print("   -> Necesitás las cookies de una sesión real del widget.")
        print("   -> Con Playwright podés exportar las cookies y reusar con httpx.\n")

    print("📋 RECOMENDACIÓN GENERAL:")
    print("   1. Corré `python probe_http_investigation.py <capture_dir> --list-only`")
    print("      para ver las URLs completas con sus query params.")
    print("   2. Si hay params tipo `_bcid` o `_ck`, revisá el JS del widget para ver")
    print("      cómo se calculan (probablemente son el match_id + timestamp + HMAC).")
    print("   3. Si el bloqueo es puro IP, considerá una sesión híbrida:")
    print("      Playwright solo para obtener la URL firmada inicial,")
    print("      httpx para polling frecuente con esa URL.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Sportradar gismo endpoints via HTTP puro.")
    parser.add_argument("capture_dir", type=Path, help="Directorio con la captura")
    parser.add_argument("--cookies", type=Path, default=None, help="Archivo JSON con cookies")
    parser.add_argument("--list-only", action="store_true", help="Solo listar URLs capturadas sin probar")
    parser.add_argument("--out", type=Path, default=None, help="Guardar resultados en JSON")
    args = parser.parse_args()

    capture_dir = args.capture_dir
    if not capture_dir.exists():
        raise SystemExit(f"No existe el directorio: {capture_dir}")

    # Cargar cookies si las hay
    cookies: dict = {}
    if args.cookies and args.cookies.exists():
        raw = json.loads(args.cookies.read_text(encoding="utf-8"))
        # Soportar formato lista [{name, value}] o dict plano
        if isinstance(raw, list):
            cookies = {c["name"]: c["value"] for c in raw if "name" in c and "value" in c}
        elif isinstance(raw, dict):
            cookies = raw
        print(f"  Cookies cargadas: {len(cookies)} entradas")

    # Cargar URLs de la captura
    print(f"\nCargando URLs desde {capture_dir}...")
    url_records = load_urls_from_capture(capture_dir)
    
    if not url_records:
        print("No se encontraron URLs de Sportradar/gismo en la captura.")
        return

    print(f"  URLs encontradas: {len(url_records)}\n")

    if args.list_only:
        print("=== URLs capturadas ===")
        for rec in url_records:
            params = _classify_params(rec["url"])
            print(f"\n  [{rec['endpoint']}]")
            print(f"  URL: {rec['url']}")
            print(f"  Query params: {params['param_keys']}")
            print(f"  Firmada: {params['likely_signed']} | Sesión: {params['likely_session']}")
        
        analyze_signing_pattern([r["url"] for r in url_records])
        return

    # Probar cada URL única
    seen_urls: set[str] = set()
    all_results: dict[str, dict] = {}

    print("=== Probando URLs con httpx ===")
    for rec in url_records:
        url = rec["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        ep = rec["endpoint"]
        url_analysis = _classify_params(url)
        
        print(f"\n  [{ep}]")
        print(f"  URL: {url[:100]}{'...' if len(url) > 100 else ''}")
        print(f"  Params: {url_analysis['param_keys']} | Firmada: {url_analysis['likely_signed']}")
        
        probe = probe_url(url, cookies=cookies)
        
        for label, result in probe.items():
            status = result.get("status", "?")
            ok = result.get("ok", False)
            deny = result.get("deny_reason", "")
            icon = "✅" if ok else "❌"
            detail = f"deny={deny}" if deny else result.get("body_preview", "")[:80]
            print(f"    {icon} [{label}] status={status} | {detail}")
        
        all_results[ep] = {
            "url": url,
            "url_analysis": url_analysis,
            "probe": probe,
        }

    # Sugerencias de estrategia
    suggest_alternatives(all_results)

    # Guardar resultados
    if args.out:
        out_path = args.out
    else:
        out_path = capture_dir / "http_probe_deep.json"
    
    out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ Resultados guardados en: {out_path}")


if __name__ == "__main__":
    main()