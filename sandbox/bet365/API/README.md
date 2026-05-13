# Bet365 API Sandbox

Investigación local limitada a `BetBot/sandbox/bet365/API/`.

Este sandbox ya no persigue replays HTTP directos como línea activa. La estrategia vigente es:

1. capturar responses reales con Playwright;
2. guardar los payloads crudos;
3. parsearlos offline con Python.

## Estado actual

HTTP directo quedó descartado como fuente principal:
- `httpx` -> `403`
- `curl_cffi` -> `200` con body vacío
- `aiohttp` / `tls-client` -> fallos de DNS en este sandbox

Toda esa línea quedó archivada en:
- `archive_http_attempts/`

No se borra por si hace falta revisar evidencia vieja, pero no es el flujo recomendado.

## Estructura activa

- `models.py`
  - dataclasses `Event`, `Market`, `Selection`
- `parser.py`
  - parser genérico de payloads Bet365 tipo `CL`, `EV`, `MG`, `MA`, `PA`, `CO`
  - soporta:
    - `matchmarketscontentapi/markets`
    - `matchbettingcontentapi/coupon`
- `parse_markets_payload.py`
  - CLI compatible para parsear un payload guardado
  - autodetecta `markets` o `coupon`
- `playwright_capture_bet365.py`
  - abre Bet365 con Playwright
  - no scrapea DOM
  - escucha responses de red y guarda payloads útiles
- `playwright_capture_league_events.py`
  - abre una liga
  - captura `matchmarketscontentapi/markets`
  - parsea los eventos detectados
  - navega directo a cada `event_url`
  - captura `coupon` por fixture
- `output_market.txt`
  - fixture real manual de `matchmarketscontentapi/markets`
- `output_coupon.txt`
  - fixture real manual de `matchbettingcontentapi/coupon`
- `output/parsed_league_events.json`
  - lista estructurada de eventos detectados desde `output_market.txt`
- `output/parsed_league_markets.json`
  - mercados básicos por evento detectados desde la liga
- `output/parsed_market.json`
  - última salida válida del parser sobre `output_market.txt`
- `output/parsed_coupon.json`
  - última salida válida del parser sobre `output_coupon.txt`

## Estrategia activa

### 1. Parseo offline

El parser trabaja sobre bodies `.txt` ya capturados desde DevTools o Playwright.

Tipos de registro soportados:
- `CL`
- `EV`
- `MG`
- `MA`
- `PA`
- `CO`

### 2. Captura con Playwright

`playwright_capture_bet365.py`:
- navega a una URL de liga o evento;
- escucha responses de red;
- guarda payloads si la URL contiene:
  - `matchmarketscontentapi/markets`
  - `matchbettingcontentapi/coupon`
  - `changefixture`
  - `splashcontentapi`
  - `Blob`
- después parsea automáticamente payloads `markets` y `coupon`.

No usa scraping visual del DOM. La página solo se navega para disparar las requests.

### 3. Flujo recomendado por liga

1. tomar una URL visual de liga Bet365;
2. derivar `pd` desde el fragmento `#/...`;
3. construir la API `matchmarketscontentapi/markets`;
4. abrir `https://www.bet365.es/` con Playwright para inicializar sesión;
5. pedir explícitamente la API de liga desde Playwright;
6. parsear eventos de liga;
7. usar `event_pd` / `event_it` / `event_url` de cada evento;
8. navegar evento por evento;
9. capturar `matchbettingcontentapi/coupon`;
10. parsear mercados detallados offline.

Regla de derivación:

- visual:
  - `https://www.bet365.es/#/AC/B1/C1/D1002/E120757998/G40/`
- `pd` derivado:
  - `#AC#B1#C1#D1002#E120757998#G40#`
- API:
  - `https://www.bet365.es/matchmarketscontentapi/markets?lid=3&zid=0&pd=<encoded_pd>&cid=171&cgid=4&ctid=171`

## Comandos

### Parsear fixture de liga

```bash
BetBot/betbot/bin/python BetBot/sandbox/bet365/API/parse_markets_payload.py \
  BetBot/sandbox/bet365/API/output_market.txt \
  --host www.bet365.es \
  --out BetBot/sandbox/bet365/API/output/parsed_league.json
```

Eso también genera:
- `output/parsed_league_events.json`
- `output/parsed_league_markets.json`

### Parsear fixture de evento

```bash
BetBot/betbot/bin/python BetBot/sandbox/bet365/API/parse_markets_payload.py \
  BetBot/sandbox/bet365/API/output_coupon.txt \
  --host www.bet365.es \
  --out BetBot/sandbox/bet365/API/output/parsed_coupon.json
```

### Capturar con Playwright e integrar parseo

```bash
BetBot/betbot/bin/python BetBot/sandbox/bet365/API/playwright_capture_bet365.py \
  "https://www.bet365.es/#/AC/B1/C1/D8/E193003384/F3/I1/" \
  --host www.bet365.es \
  --channel chrome
```

Salida:
- `playwright_captures/<timestamp>/payloads/`
- `playwright_captures/<timestamp>/responses.json`
- `playwright_captures/<timestamp>/parsed_payloads/`
- `playwright_captures/<timestamp>/parsed_events.json`
- `playwright_captures/<timestamp>/parsed_markets.json`
- `playwright_captures/<timestamp>/summary.json`

### Capturar liga completa e iterar eventos

```bash
BetBot/betbot/bin/python BetBot/sandbox/bet365/API/playwright_capture_league_events.py \
  "https://www.bet365.es/#/AC/B1/C1/D1002/E120757998/G40/" \
  --host www.bet365.es \
  --channel chrome \
  --max-events 1
```

Salida:
- `playwright_captures/<timestamp>/league/parsed_league.json`
- `playwright_captures/<timestamp>/league/parsed_league_events.json`
- `playwright_captures/<timestamp>/league/parsed_league_markets.json`
- `playwright_captures/<timestamp>/events/<fixture_id>/parsed_coupon.json`
- `playwright_captures/<timestamp>/events/<fixture_id>/parsed_markets.json`
- `playwright_captures/<timestamp>/events/<fixture_id>/summary.json`

Logs clave del summary:
- `input_league_url`
- `derived_pd`
- `resolved_league_api_url`
- `league_api_status`
- `league_api_body_size`
- `league_api_body_preview`
- `league_events_discovered`
- `league_events_processed`

### Tests

```bash
BetBot/betbot/bin/python -m unittest discover BetBot/sandbox/bet365/API -p 'test_parse_markets_payload.py'
```

### Compile

```bash
BetBot/betbot/bin/python -m compileall BetBot/sandbox/bet365/API
```

## Qué extrae hoy el parser

### Desde `markets`

Para cada fixture:
- `fixture_id`
- `event_token`
- `home`
- `away`
- `name`
- `start_raw`
- `event_it`
- `event_pd`
- `event_url`
- `sportradar_url`
- `stats_identifier`
- `source_meta`
- odds `1/X/2`

### Desde `coupon`

Para cada evento:
- competencia
- `event_id` / `fixture_id`
- `event_token`
- `home`
- `away`
- `event_it`
- `event_url`
- mercados
- selecciones
- odds fraccionales y decimales

## Caso validado: `E193003384`

El fixture real `output_coupon.txt` ya parsea correctamente:

- `Full Time Result`
  - `Elche` -> `23/20`
  - `Draw` -> `2/1`
  - `CD Alaves` -> `11/5`
- `Goals Over/Under`
  - `Over 2.5` -> `10/11`
  - `Under 2.5` -> `10/11`
- `Both Teams to Score`
  - `Yes` -> `7/10`
  - `No` -> `21/20`

## Caso validado desde liga

El fixture real `output_market.txt` ya detecta `193003384`:
- `event_token`: `E193003384`
- `name`: `Elche v CD Alaves`
- `event_it`: `ACB1D8E193003384F3I0`
- `event_pd`: `#AC#B1#C1#D8#E193003384#F3#I1#`
- `event_url`: `https://www.bet365.es/#/AC/B1/C1/D8/E193003384/F3/I1/`
- `sportradar_url`: `https://s5.sir.sportradar.com/bet365/en/match/61624628`

## Notas

- El parser offline ya está resuelto para los fixtures guardados.
- Lo que sigue dependiendo de navegador es la obtención confiable del payload real.
- Si después se quiere llevar esto a código productivo, la base correcta hoy es:
  - Playwright solo para network interception;
  - descubrimiento de eventos desde la liga;
  - parser offline reusable sobre `markets` y `coupon`.
