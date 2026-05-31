# Rainbet — investigación de la API (2026-05-31)

## Rainbet corre sobre Betby (feed sptpub)

Rainbet usa el sportsbook **Betby**, igual que Solcasino. Las odds vienen del
feed **sptpub.com** (snapshot por chunks), todo por **HTTP plano sin token**.

## El dato que faltaba: brand id + api host

`/sports` da 404 y el sitio está tras **Cloudflare "verify you're human"**, así
que el widget Betby no carga en una captura headless normal. Pero el `brand_id`
está en el JS bundle de Rainbet (`assets.rbgcdn.com`), en la config de
`BTRenderer().initialize({...})`. Capturado con Playwright (Chrome headed,
escaneando responses JS — ver `capture_brand.py`):

```
brand_id = "2374656571012681728"
api_host = "api-g-c7818b61-607.sptpub.com"   (gateway sptpub compartido)
language = "en"
```

(El placeholder previo en `sandbox/solca/betby_http.py` copiaba el brand de
solcasino — estaba MAL para Rainbet.)

## Flujo HTTP (verificado headless con httpx puro)

```
GET https://api-g-c7818b61-607.sptpub.com/api/v4/prematch/brand/2374656571012681728/en/0
  -> manifest { version, top_events_versions[], rest_events_versions[] }
GET .../en/<chunk_version>   (por cada versión)
  -> chunk { sports, categories, tournaments, events }
merge(chunks) -> snapshot completo
```

Run de validación: **55 sports, 195 categorías (países), 369 torneos, 1215
eventos**. Incluye ligas nicho (Argentina Primera Nacional / Torneo Federal A,
Venezuela, Costa Rica, Nicaragua…).

## Estructura

- `category` = país (con nombre). `tournament` = liga (con nombre). El sport de
  un torneo se infiere de `event.desc.sport` (fútbol = **sport_id 1**).
- `event.desc`: `type="match"`, `sport`, `tournament`, `competitors=[home,away]`,
  `scheduled` (unix s).
- Mercados de fútbol en el snapshot amplio:
  - `"1"` → 1X2 (outcome 1=local, 2=empate, 3=visitante; `k`=cuota)
  - `"18"` → totals (spec `total=<linea>`, outcome 12=Over, 13=Under) → 📏 GL
  - `"10"` → doble oportunidad (no renderizado por el bot)
- **Asian Handicap (`hcp=`) NO está en el snapshot amplio.** Los endpoints de
  detalle por evento probados dan **403** → AH no disponible por HTTP en Betby.
  Se omite (limitación de datos del proveedor, no del extractor).

## Integración (producción, HTTP puro)

`extractors/rainbet_http/`: `settings.py` (brand/host overridables por env),
`client.py` (snapshot async + merge), `parser.py` (1X2 + 📏 GL en el shape del
bot), `discovery.py` (ligas de fútbol por país), `extractor.py`
(`search_leagues` + `extract_league`, snapshot cacheado 120s). Registrado en
`extractors/__init__.py` (browserless). `/track_league` funciona end-to-end:
elegir país → liga → tracking con nombre real + odds. Sin pegar URL ni nombre.
