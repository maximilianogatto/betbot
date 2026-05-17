# Sportradar / Bet365Stats Research Sandbox

Este sandbox sirve para investigar el feed de estadísticas que Bet365 incrusta a través de Bet365Stats / Sportradar, sin tocar todavía el extractor productivo ni la DB principal del bot.

## Flujo recomendado

```text
capture_everything.py -> filter_capture.py -> analyze_filtered_capture.py -> build_match_snapshot.py -> build_match_features.py
```

`capture_everything.py` guarda todo lo que ve el navegador. Después el filtro deja solo lo útil para research (`fetch` / `xhr` y rutas `/gismo/`), y el análisis genera un reporte enfocado en endpoints accionables para BetBot.

## Archivos principales

- `capture_everything.py`
  Captura responses crudas del widget con Playwright.
- `filtering.py`
  Helpers puros de filtrado, normalización y agrupación por endpoint.
- `filter_capture.py`
  Filtra `responses.ndjson` y genera artefactos útiles de análisis.
- `analysis.py`
  Helpers puros de clasificación y render de reportes.
- `analyze_filtered_capture.py`
  Lee el filtrado y genera un `endpoint_report.md`.
- `snapshot_builder.py`
  Normaliza los endpoints útiles en un snapshot compacto por partido.
- `build_match_snapshot.py`
  CLI para construir `match_snapshot.json` desde `filtered_fetch.ndjson`.
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

## Conclusiones iniciales

- `match_markets` es un hallazgo fuerte: expone mercados/odds del partido por HTTP.
- `match_timeline` y `match_timelinedelta` son los mejores candidatos para detectar `live`, score y estado del partido.
- `match_info_statshub` y `stats_match_get` dan metadata útil del match.
- `stats_formtable`, `stats_season_tables`, `stats_team_lastx`, `stats_team_streaks` y relacionados aportan contexto pre-match interesante.
- `stats_season_injuries`, `stats_season_topgoals`, `stats_season_topcards` y `stats_season_topassists` sirven para enriquecer análisis.
- `event_get` parece especialmente prometedor, pero hay que validar si es del partido abierto o un feed live más global.

## Próximos pasos recomendados

1. Correr varias capturas con partidos pre-match y también con partidos en vivo.
2. Confirmar si `event_get` es fixture-specific o un feed global.
3. Ver si en capturas live aparecen corners, shots, possession, cards y clock de forma estable.
4. Recién después evaluar una integración aislada con el extractor productivo.
