# Sportradar / Bet365Stats Research Sandbox

Este sandbox sirve para investigar el feed de estadísticas que Bet365 incrusta a través de Bet365Stats / Sportradar, sin tocar todavía el extractor productivo ni la DB principal del bot.

## Flujo recomendado

```text
capture_everything.py -> filter_capture.py -> analyze_filtered_capture.py -> build_match_snapshot.py -> build_match_features.py
```

Flujo alternativo para investigación más liviana:

```text
capture_useful.py -> probe_useful_http.py
```

`capture_everything.py` guarda todo lo que ve el navegador. Después el filtro deja solo lo útil para research (`fetch` / `xhr` y rutas `/gismo/`), y el análisis genera un reporte enfocado en endpoints accionables para BetBot. `capture_useful.py` ataca el mismo problema desde el inicio, guardando solo endpoints útiles ya filtrados.

## Archivos principales

- `capture_everything.py`
  Captura responses crudas del widget con Playwright.
- `filtering.py`
  Helpers puros de filtrado, normalización y agrupación por endpoint.
- `filter_capture.py`
  Filtra `responses.ndjson` y genera artefactos útiles de análisis.
- `capture_useful.py`
  Captura directamente solo endpoints útiles de `/gismo/` y algunos documentos relevantes de StatsHub.
- `analysis.py`
  Helpers puros de clasificación y render de reportes.
- `analyze_filtered_capture.py`
  Lee el filtrado y genera un `endpoint_report.md`.
- `probe_useful_http.py`
  Intenta repetir por HTTP puro las URLs firmadas de la captura útil para ver si son reutilizables sin navegador.
- `snapshot_builder.py`
  Normaliza los endpoints útiles en un snapshot compacto por partido.
- `build_match_snapshot.py`
  CLI para construir `match_snapshot.json` desde `filtered_fetch.ndjson` o `useful_fetch.ndjson`.
- `features_builder.py`
  Deriva features compactas y robustas desde `match_snapshot.json`.
- `build_match_features.py`
  CLI para construir `match_features.json` desde `match_snapshot.json`.
- `run_full_stats_pipeline.py`
  Orquestador único para correr el pipeline completo desde un `stats_url`.
- `endpoint_report.md`
  Último reporte espejado automáticamente desde una captura bajo `captures/`.

## Cómo correr el capturador

Desde la raíz del repo:

```bash
./betbot/bin/python sandbox/sportradar_stats/capture_everything.py "<stats_url>" \
  --seconds 30 \
  --out-dir sandbox/sportradar_stats/captures/test
```

Ejemplo real de `stats_url`:

```text
https://s5.sir.sportradar.com/bet365/en/match/61624664
```

### Nota sobre perfiles reales

En varias pruebas, StatsHub respondió mejor cuando Chromium reutilizó un perfil persistente real.

El pipeline y el wrapper headless ahora intentan resolver el perfil así:

- `--user-data-dir` si lo pasás explícitamente
- `SPORTRADAR_USER_DATA_DIR` o `BETBOT_SPORTRADAR_USER_DATA_DIR`
- `/tmp/chrome-sportradar-profile` si existe

## Cómo capturar sin ventana visible

Sin tocar `capture_everything.py`, podés usar este wrapper:

```bash
./betbot/bin/python sandbox/sportradar_stats/capture_everything_headless.py \
  "https://s5.sir.sportradar.com/bet365/en/match/61624664" \
  --seconds 30 \
  --out-dir sandbox/sportradar_stats/captures/headless_test
```

Esto sigue usando Playwright/Chromium, pero en `headless`, así que no abre una ventana visible.

## Cómo correr la captura útil

```bash
./betbot/bin/python sandbox/sportradar_stats/capture_useful.py "<stats_url>" \
  --seconds 30 \
  --out-dir sandbox/sportradar_stats/captures/useful_test
```

Esta variante:

- reutiliza el perfil persistente igual que `capture_everything.py`
- guarda solo `fetch` / `xhr` / `document` relevantes
- prioriza endpoints allowlist bajo `/gismo/`
- produce artefactos más compactos y directos para inspección

### Qué produce la captura útil

Dentro del directorio de captura:

- `useful_fetch.ndjson`
- `useful_fetch.json`
- `useful_endpoints_index.json`
- `useful_capture_metadata.json`

## Cómo probar si las URLs útiles se pueden repetir por HTTP puro

```bash
./betbot/bin/python sandbox/sportradar_stats/probe_useful_http.py \
  sandbox/sportradar_stats/captures/useful_test
```

Si querés sumar cookies exportadas:

```bash
./betbot/bin/python sandbox/sportradar_stats/probe_useful_http.py \
  sandbox/sportradar_stats/captures/useful_test \
  --cookies-json sandbox/sportradar_stats/captures/useful_test/cookies.json
```

O un `storage_state.json` compatible con Playwright:

```bash
./betbot/bin/python sandbox/sportradar_stats/probe_useful_http.py \
  sandbox/sportradar_stats/captures/useful_test \
  --storage-state /tmp/storage_state.json
```

### Qué produce el probe HTTP

- `http_probe_results.json`
- `http_probe_report.md`

La idea es responder rápido:

- si una URL firmada sirve por `httpx`
- si requiere cookies
- si la firma venció
- si devuelve HTML / empty body / 403
- si el endpoint sigue siendo el mismo útil o redirige a otra cosa

## Cómo correr el filtrado

```bash
./betbot/bin/python sandbox/sportradar_stats/filter_capture.py \
  sandbox/sportradar_stats/captures/test
```

Si querés además un JSON agrupado con todos los registros filtrados:

```bash
./betbot/bin/python sandbox/sportradar_stats/filter_capture.py \
  sandbox/sportradar_stats/captures/test \
  --json
```

### Qué produce el filtrado

Dentro del directorio de captura:

- `filtered_fetch.ndjson`
- `filtered_fetch.json` solo si usás `--json`
- `endpoints_index.json`

## Cómo correr el análisis

```bash
./betbot/bin/python sandbox/sportradar_stats/analyze_filtered_capture.py \
  sandbox/sportradar_stats/captures/test
```

El script usa `filtered_fetch.ndjson` si existe. Si no, cae a `responses.ndjson` y aplica el mismo filtro en streaming.

### Qué produce el análisis

Dentro del directorio de captura:

- `endpoint_report.md`

Además, si la captura vive bajo `sandbox/sportradar_stats/captures/...`, el script espeja el reporte más reciente a:

- `sandbox/sportradar_stats/endpoint_report.md`

## Qué archivos guarda cada etapa

- `responses.ndjson`
  Captura cruda, con mucho ruido: scripts, css, fuentes, assets, fetches útiles, etc.
- `useful_fetch.ndjson`
  Captura ya filtrada en origen, con endpoints útiles de StatsHub / Sportradar.
- `useful_endpoints_index.json`
  Índice agrupado solo para la captura útil.
- `filtered_fetch.ndjson`
  Solo responses útiles para research.
- `endpoints_index.json`
  Índice agrupado por endpoint limpio (`match_timeline`, `match_markets`, etc.).
- `endpoint_report.md`
  Reporte Markdown con hallazgos y recomendaciones.
- `match_snapshot.json`
  Snapshot compacto por partido, listo para alimentar análisis pre-match, live o futuros agentes.
- `match_features.json`
  Features derivadas compactas, separadas de la evidencia cruda.

## Qué busca el análisis

El reporte intenta responder:

- qué endpoints sirven para metadata del partido
- cuáles parecen live / polling
- dónde aparecen score, estado, timeline o live state
- si hay odds o mercados por HTTP
- qué endpoints sirven para forma, tabla, lesiones o player leaders
- qué endpoints valdría la pena integrar primero en BetBot

## Cómo construir el snapshot del partido

```bash
./betbot/bin/python sandbox/sportradar_stats/build_match_snapshot.py \
  sandbox/sportradar_stats/captures/test \
  --pretty
```

Si en la carpeta existe `useful_fetch.ndjson`, el builder lo usa antes que `filtered_fetch.ndjson`.

Opciones útiles:

```bash
./betbot/bin/python sandbox/sportradar_stats/build_match_snapshot.py \
  sandbox/sportradar_stats/captures/test \
  --pretty \
  --include-debug-raw \
  --out /tmp/match_snapshot.json
```

### Qué guarda

- `match_snapshot.json`

El snapshot:

- no duplica responses completas gigantes
- sí conserva referencias compactas a los records usados
- sigue generándose aunque falten endpoints
- está pensado como base para:
  - análisis pre-match
  - detección de value / anomalías
  - análisis live
  - futuros mensajes resumidos de Telegram

### Metadatos del snapshot v1

El snapshot ahora agrega `snapshot_metadata` con:

- `snapshot_version`
- `generated_at`
- `capture_type` (`prematch`, `live`, `ended`, `unknown`)
- `data_completeness`
- `endpoints_used`
- `missing_important_endpoints`

La idea es que el snapshot siga siendo evidencia estructurada, mientras que la interpretación compacta viva aparte en `match_features.json`.

## Cómo construir features derivadas

```bash
./betbot/bin/python sandbox/sportradar_stats/build_match_features.py \
  sandbox/sportradar_stats/captures/test \
  --pretty
```

Opciones útiles:

```bash
./betbot/bin/python sandbox/sportradar_stats/build_match_features.py \
  sandbox/sportradar_stats/captures/test \
  --pretty \
  --out /tmp/match_features.json
```

Si `match_snapshot.json` no existe, la CLI lo reconstruye automáticamente desde `filtered_fetch.ndjson`.
Si hay `useful_fetch.ndjson`, también lo acepta como fuente.

## Cómo correr todo el pipeline de una vez

```bash
./betbot/bin/python sandbox/sportradar_stats/run_full_stats_pipeline.py \
  "https://s5.sir.sportradar.com/bet365/en/match/61624664" \
  --seconds 30 \
  --out-dir sandbox/sportradar_stats/captures/test_full \
  --pretty
```

Opciones útiles:

```bash
./betbot/bin/python sandbox/sportradar_stats/run_full_stats_pipeline.py \
  "https://s5.sir.sportradar.com/bet365/en/match/61624664" \
  --out-dir sandbox/sportradar_stats/captures/test_full \
  --skip-capture \
  --json \
  --include-debug-raw \
  --pretty
```

El runner ejecuta, en orden:

1. `capture_everything.py`
2. `filter_capture.py`
3. `analyze_filtered_capture.py`
4. `build_match_snapshot.py`
5. `build_match_features.py`

Y al final imprime las rutas generadas para:

- `responses.ndjson`
- `filtered_fetch.ndjson`
- `filtered_fetch.json` si pedís `--json`
- `endpoints_index.json`
- `endpoint_report.md`
- `match_snapshot.json`
- `match_features.json`

Si ya tenés una captura cruda con `responses.ndjson`, el flujo recomendado es usar `--skip-capture`.

## Conclusiones iniciales

- `match_markets` es un hallazgo fuerte: expone mercados/odds del partido por HTTP.
- `match_timeline` y `match_timelinedelta` son los mejores candidatos para detectar `live`, score y estado del partido.
- `match_info_statshub` y `stats_match_get` dan metadata útil del match.
- `stats_formtable`, `stats_season_tables`, `stats_team_lastx`, `stats_team_streaks` y relacionados aportan contexto pre-match interesante.
- `stats_season_injuries`, `stats_season_topgoals`, `stats_season_topcards` y `stats_season_topassists` sirven para enriquecer análisis.
- `event_get` parece especialmente prometedor, pero hay que validar si es del partido abierto o un feed live más global.
- `capture_useful.py` sirve como atajo para quedarse solo con endpoints importantes sin arrastrar todos los assets del widget.
- `probe_useful_http.py` sirve para separar qué endpoints podrían reciclarse con HTTP puro de cuáles siguen dependiendo del navegador o de cookies/sesión.

## Próximos pasos recomendados

1. Correr varias capturas con partidos pre-match y también con partidos en vivo.
2. Confirmar si `event_get` es fixture-specific o un feed global.
3. Ver si en capturas live aparecen corners, shots, possession, cards y clock de forma estable.
4. Recién después evaluar una integración aislada con el extractor productivo.
