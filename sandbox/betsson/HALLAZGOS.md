# Betsson (cba.betsson.bet.ar) — investigación de la API (2026-06-17)

## Qué es

Sportsbook argentino (Córdoba) que corre la plataforma **OBG / Betsson Group**.
Expone una API JSON pública bajo `https://cba.betsson.bet.ar/api/sb/v1/...` por
**HTTP plano**, gateada sólo por un set de **headers de marca estáticos** (no hay
bootstrap por sesión):

```
brandid:      46df28af-e0f4-48d6-a3b3-3183b2586c44   (estático; aparece también en /dist/prod/config/<brandid>/...)
marketcode:   ag                                      (Argentina)
sessiontoken: <JWT anónimo estático>                  (userId = 11111111-...-1111, sin expiración)
```

Headers adicionales estáticos que la API valida (todos constantes de marca):
`x-obg-channel: Web`, `x-sb-channel: Mobile`, `x-sb-type: b2b`,
`x-sb-jurisdiction: Lpcse`, `x-sb-content-id: <brandid>`, `x-sb-currency-code: ARS`,
`x-sb-language-code: ag`, `x-sb-country-code: AR`. (Individualmente sólo `brandid` y
`marketcode` son imprescindibles, pero hay redundancia entre los `x-sb-*`; mandamos
el set completo, que es robusto.) Los `x-sb-static-context-id` / `x-sb-segment-id`
dinámicos NO hacen falta.

Playwright se usó **sólo para investigar** (capturar tráfico); el flujo final
(odds + live) es **HTTP puro** con `httpx`.

## Endpoints clave

| Endpoint | Para qué |
|---|---|
| `GET /api/sb/v1/widgets/categories/v2` | árbol completo deporte→región→competición; cada competición trae su mapa `events` (label "Local - Visita", `eventType`, `phase`, `startDate`) → **discovery + listado prematch** (763 eventos en 1 sola llamada cacheada, sin paginar) |
| `GET /api/sb/v1/widgets/events-table/v2?categoryIds=1&competitionIds=<id>` | **todos los eventos + mercados principales de una liga** (paginado: `pageNumber`/`totalPages`) |
| `GET /api/sb/v1/widgets/events-table/v2?categoryIds=1&eventPhase=Live` | **todos los partidos en vivo** del deporte (con `scoreboards`: marcador, reloj, tarjetas) |

`categories/v2` → `data.items.categories["1"]` es Fútbol; `regions[<id>]` con
`label` (ES) + `trackingLabel` (EN) + `competitions[<id>]` (`label`/`slug`/`events`).
La región `0` ("Partidos Top") y la competición `0` ("Todos <país>") se saltan.
`indexBySlug` mapea `futbol/alemania/alemania-bundesliga` → `["1","14","15"]` (último
id = competición), usado para resolver una URL del sitio a un competition id.

`events-table/v2` → `data.{events, markets, selections, scoreboards}`:
- `events[]`: `id` (`f-...`), `label`, `participants` (`side` 1=local, 2=visita),
  `startDate`, `competitionId/Name`, `regionName` (país), `eventType` (`Fixture`
  vs `Outright` → se filtran outrights), `phase`.
- `markets[]`: `id` (`m-...`, determinístico `m-f-<fixture>-<TEMPLATE>`), `eventId`,
  `marketTemplateId`, `lineValue`.
- `selections[]`: `marketId`, `odds` (**decimal directo, sin escalar**),
  `selectionTemplateId`, `label`, `sortOrder`.

## Mercados (fútbol)

| selección | template | mapeo |
|---|---|---|
| 1X2 | `MW3W` | selectionTemplateId HOME/DRAW/AWAY → `odds_1x2` |
| Hándicap europeo 3-vías | `M3WHCP` | `lineValue`="`<local> - <visita>`", outcomes HANDICAPHOME/DRAW/AWAY → 📐 (ver abajo) |
| Total de goles O/U | `MTG2W*` | OVER/UNDER, `lineValue`=total (multi-línea) → 📏 `goal_line` |
| Ambos anotan | `BTTS` | YES/NO → `both_teams_to_score` |

Excluir `1HTG` (total 1er tiempo) y player-props (`PLYPROP*`, `OVERSHOTS`…). El book
**no ofrece Asian Handicap de 2 vías**, sólo el **hándicap europeo de 3 vías**
(`M3WHCP`) y DNB (`MW2W`). El handicap firmado sale de `lineValue` ("1 - 0" → local
+1) o del `label` ("1 (+1)"). Para que fluya por la maquinaria de handicap del bot
(render 📐, change-detection, tracking), se mapean las patas **local/visita** al slot
`asian_handicap` (line firmada), guardando la pata **empate** aparte en `draw`.

Live (`scoreboards[]`): `scorePerParticipant` (por id de participante),
`statistics[<pid>].{redCards,yellowCards,...}.value`, `matchClock.minutes` +
`currentPhase.label` ("2da mitad") para el minuto.

## Integración (producción, HTTP puro)

`extractors/betsson_http/`: `settings.py` (headers de marca; `brandid`/`marketcode`/
`sessiontoken`/`site_origin` overridables por env `BETSSON_*`), `client.py`
(`categories/v2` + `events-table/v2` con paginación), `parser.py` (1X2 + 📏 totales +
BTTS; live con marcador/tarjetas/minuto), `discovery.py` (ligas por país desde el
árbol + resolución por slug), `extractor.py` (`search_leagues` + `extract_league` +
`list_live_events` + `list_prematch_events`, árbol cacheado 90s). Registrado
browserless por defecto. **Prematch (`list_prematch_events`)**: se arma desde el
árbol `categories/v2` (1 sola llamada cacheada, ~610 fixtures) en vez del barrido
events-table `eventPhase=Prematch` (525 ev / 27 páginas / ~17 MB, descartado).
Detección live vía events-table `eventPhase=Live` (liviana).

**Integración en el bot:** registrado en `extractors/__init__.py`; agregado a
`bot/canonical_leagues.py` (`PLATFORM_ORDER` + display "Betsson") y al parseo de
esquema en `monitors/live_watch.py` (`betsson:competition:` → auto-track). El
hándicap europeo se renderiza con la maquinaria 📐 existente (verificado vía
`bot/alerts._format_asian_handicap_line`).

URLs aceptadas: `betsson:competition:<id>` (canónica) y URLs
`cba.betsson.bet.ar/apuestas-deportivas/<slug>` (resueltas vía `indexBySlug`).
Tests: `tests/extractors/test_betsson_http.py`.
