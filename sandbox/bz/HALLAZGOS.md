# BZ (m.bz.com) — investigación de la API (2026-05-31)

## Qué es

Sportsbook propio (no Betby/sptpub) con API JSON en `m.bz.com/api/`. **Usa
identificadores de Sportradar en todo** (`sr:sport:1`, `sr:tournament:231`,
`sr:match:...`, `sr:competitor:...`, `sr:season:...`) → los eventos linkean
directo con el proveedor de stats de Sportradar del bot.

## Auth: solo headers (sin token)

Las llamadas dan **403 "Client type undefined"** salvo que se manden:

```
x-client-type: BZ-H5
x-channel-type: 0
x-browser-language: en-US
```

Con esos headers, todo funciona por **HTTP plano sin token ni cookie**
(verificado con httpx puro). Capturado con Playwright (`capture_traffic.py`,
mobile UA) leyendo los request headers reales.

## Endpoints clave

| Endpoint | Para qué |
|---|---|
| `GET /api/sports/sport/recommend?statusList=1` | lista de deportes (sr:sport:N) |
| `GET /api/sports/match/search?statusList=0&sportId=sr:sport:1&pageSize=200&marketMode=0` | **torneos agrupados con sus partidos** (prematch) |
| `GET /api/odds/v2/bz/all?sportId=sr:sport:1&matchId=sr:match:N` | **mercados completos** de un partido |
| `POST /api/odds/v2/bz/recommend/batch` `{"batch":[{matchId,sportId,phase}]}` | solo mercado titular (1X2) por lote |
| `POST /api/sports/match/getTournamentMatchByIds` `{"matchIds":[...]}` | partidos por id (agrupados) |

**`statusList`**: `0` = "Not started" (PREMATCH, lo que usamos), `1` = en vivo.
`scheduledTime` = unix **ms**.

`match/search` devuelve cada torneo con: `id` (sr:tournament), `name`,
`categoryName` (país), `categoryId`, `currentSeasonId`, `matchCount`, y
`matches[]` (con `id` sr:match, `homeName`/`awayName`, `homeId`/`awayId`,
`scheduledTime`, `seasonId`). Las odds NO vienen acá → se piden por partido.

## Mercados (odds/v2/bz/all, tab MAIN, fútbol)

| marketId | nombre | mapeo |
|---|---|---|
| `1` | 1X2 | outcome 1=local, 2=Draw, 3=visitante; `odds`=cuota → `odds_1x2` |
| `16` | Handicap (asiático) | spec `hcp=<linea>`; outcome 1714=local, 1715=visitante; `displayName`=línea por lado → 📐 `asian_handicap` |
| `18` | Total | spec `total=<linea>`; outcome 12=Over, 13=Under → 📏 `goal_line` |
| 11/29/45/8 | DNB / BTTS / correct score / nth goal | (no usados) |

**Es el extractor más completo: 1X2 + AH + GL, todo por HTTP** (a diferencia de
Rainbet, que no expone AH).

## Integración (producción, HTTP puro)

`extractors/bz_http/`: `settings.py` (base/headers overridables por env),
`client.py` (match/search + odds por partido con concurrencia acotada),
`parser.py` (1X2 + 📐 AH + 📏 GL; guarda `sr_match_id`/`sr_season_id` en
metadata para stats), `discovery.py` (ligas por país), `extractor.py`
(`search_leagues` + `extract_league`, search cacheado 90s). Registrado
browserless. `/track_league` end-to-end: país → liga → tracking con nombre real
+ odds, sin pegar URL ni nombre.
