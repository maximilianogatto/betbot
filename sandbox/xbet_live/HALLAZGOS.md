# 1xBet en vivo (LiveFeed) — investigación (2026-06-01)

Dominio investigado: `https://1xbetarge.com/es` (clon 1xBet; mismo backend que
`spinbetter.com`, que ya usa el extractor para prematch).

## El feed live: LiveFeed (gemela de LineFeed)

El prematch usa `…/service-api/LineFeed/…`. El **en vivo** usa
`…/service-api/LiveFeed/…`, mismo host, **HTTP plano sin token**.

Endpoint clave (capturado del live de fútbol):
```
GET /service-api/LiveFeed/Get1x2_VZip
    ?sports=1&count=100&lng=es&gr=2025&cfview=2&mode=4&country=14
    &virtualSports=true&noFilterBlockEvent=true
```
Params que faltaban y hacían devolver `Value:[]`: **`gr=2025`, `country=14`,
`mode=4`** (no `partner`/`country=1`). Con `sports=1` filtra fútbol. Devuelve el
envelope estándar `{Success, Value:[...]}`. (A veces responde con status 406 pero
el cuerpo JSON es válido; normalmente es 200.)

## Estructura del evento (igual que LineFeed)

- `I`=id, `O1`/`O2`=local/visitante, `L`=liga (localizada), `LE`=liga (en),
  `CN`=país.
- `SC` (marcador/reloj): `FS.S1`/`FS.S2`=marcador, `SLS`=etiqueta de minuto
  ("76 minutos"), `CP`=período actual, `I`=texto estado. Si `I=="Apuestas
  prepartido"` o `SLS` empieza con "Comienza", el evento **aún no arrancó** → se
  excluye (no es "salió en vivo").
- `E`=mercados `{T,C,P,G}` → se reusa `_extract_markets` (1X2 G=1 T=1/2/3, +
  hándicap y totales) para traer 1X2 en la alerta.

## Virtuales a filtrar

El feed mezcla fútbol simulado: "Short Football 5x5/4x4/3x3/2x2", "Fútbol corto",
"FIFA 26", "Volta", "LFL", "Student League", "eFootball", "… NxN". Se marcan
`is_soccer=False` por regex sobre el nombre de liga (igual el matcher del
watchlist los descarta porque los equipos no coinciden con el fixture real).

## Integración

`extractors/xbet_http/`: `build_live_1x2_url` (deriva `/LiveFeed` del base
`/LineFeed`), `client.fetch_live_1x2_zip`, `parser.live_events_from_1x2_vzip`,
`extractor.list_live_events` + `supports_live_detection=True`,
`provider_capabilities.supports_live=True`. Params live overridables en settings
(`live_gr`, `live_country`, `live_mode`, `live_cfview`, `live_count`).

Verificado en vivo: 22 partidos en juego (10 reales) con minuto + marcador + 1X2;
12 virtuales filtrados. Ahora son **5 casas** con detección live: 1xbet, betovo,
betwarrior, bz, solcasino.
