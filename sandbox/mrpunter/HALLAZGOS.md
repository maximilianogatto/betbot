# MrPunter (mrpunter.com) — investigación de la API (2026-06-01)

## Qué es

`mrpunter.com` es un casino cuyo **sportsbook corre sobre FSB** (host
`prod20296-144090624.fssb.io`; `project/info` reporta `integration: "bti"`). El
sportsbook se embebe como iframe desde `…/es/spbk/`. La API de datos es
`prod20296-144090624.fssb.io/api/eventlist/…`.

## Auth: JWT embebidos en el HTML → HTTP puro (sin browser)

Las llamadas a `/api/eventlist/…` dan **403 "token expected"** salvo que se manden
**dos JWT** + un header:
- `authorization: <JWT>` — token anónimo (payload con `customerType:"anon"`, `languageCode`, etc.)
- `session: <JWT>` — token de sesión (payload con `customerId:-1`, `expiredDate`, `iat`)
- `time-area: 01`

Lo clave: **ambos JWT vienen embebidos en el HTML de `…/es/spbk/`**, que se baja
con httpx puro (200). Es decir, el bootstrap es **HTTP puro, sin navegador**:

```
GET https://prod20296-144090624.fssb.io/es/spbk/   (httpx)
  → regex `eyJ…\.eyJ…\.…` → 2 JWT
  → authorization = el que tiene "customerType"; session = el que tiene "expiredDate"
```
Hay un `POST /api/master/auth/signToken {"dataToSign":{"timezoneId":10},...}` que
**refresca** los tokens (lleva auth+session+time-area), pero para empezar alcanza
con los del HTML. (Son anónimos y caducan → re-bajar el HTML cuando expiren.)

## Endpoints (host `…fssb.io/api/eventlist/eu`)

| Endpoint | Para qué |
|---|---|
| `GET /navigation/v2/sports?regionCode=AR` | **árbol completo**: sports → countries → Leagues (`_id` display, `MasterLeagueId`, `LeagueName`, `eventsQuantity`, `liveEventsQuantity`, `fixtureEventsQuantity`…) |
| `GET /leagues/v2/<MasterLeagueId>/gameOdds?marketTypeIds=<codes>&IsLive=false` | **eventos + odds** de una liga (prematch). `IsLive=true` para en vivo. |
| `GET /events/v2/live/initial?regionCode=AR` | **live**: counts por sport + eventos del sport 1 (fútbol) |
| `GET /events/v2/1/live/eventUpdates` | deltas live del sport 1 |

Sport **1 = Fútbol** (real), **234 = V-Fútbol** (virtual). Liga: el `_id` es de
display; **`MasterLeagueId`** es el que usa `gameOdds`.

## Formato (arrays posicionales)

Tanto live como gameOdds devuelven eventos como **listas posicionales**, no objetos:
```
[ eventId, leagueId, leagueName, sportId, sportName, regionId, regionCode, regionName,
  [[compId,{ES:nombre},"Home"],[compId,{ES:nombre},"Away"]],
  num, "Home vs Away", "startISO",
  [score1, score2, null, {firstHalfScore1,...}],   # marcador
  clockRunning(bool), …, {ClockRunning, ClockDirection, …},   # reloj
  …, masterEventId, [ …markets… ] ]                 # markets (último; puede ser null)
```
Cada market: `[marketId, name, name2, [marketTypeCode, name, …], eventId, leagueId, sportId, [ outcomes ]]`.
Cada outcome: `[outcomeId, {ES:label}, {ES:label}, bool, PRECIO_DECIMAL, bool, [formatos…], … , line?]`.

**Mercados** se piden por `marketTypeIds` (códigos tipo `ML1`,`ML39`,`OU249`,`QA158`…).
`ML*`=moneyline/resultado (ML1 = Resultado 1er Tiempo; el de tiempo reglamentario
es otro `ML…` — confirmar con un partido próximo que tenga el mercado abierto),
`OU*`=over/under (totales → 📏), handicap asiático en un `QA…`/`ML…` con `line`.
Precio = decimal (ej. 2.08). Marcador en pos 12, reloj en el dict de pos ~14.

## Estado / próximos pasos

Investigación **completa y HTTP puro confirmado** (token bootstrap desde HTML +
navigation + gameOdds + live, todo con httpx). Falta, para el extractor:
1. Mapear los `marketTypeCode` de **Resultado Final (1X2)**, **Hándicap Asiático**
   y **Total de goles** (leer los names de un partido con mercados completos).
2. Parser de arrays posicionales → `EventSnapshot` (1X2 + 📐 AH + 📏 GL) y
   `LiveEventSnapshot` (equipos, marcador pos12, minuto del reloj).
3. `search_leagues` desde navigation (país→liga, usando MasterLeagueId en source_url).

Harness: `sandbox/mrpunter/capture_traffic.py`. Plataforma FSB → distinta a las 6
anteriores (Betby/Altenar/Kambi/LineFeed/Sportradar-id).
