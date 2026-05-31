# BetWarrior (caba.betwarrior.bet.ar) — investigación de la API (2026-05-31)

## Qué es

Sportsbook argentino que corre la plataforma **Kambi**. Kambi expone una API
pública de "offering" reachable por **HTTP plano sin token**. El `offering` (id
del operador) y el host estaban embebidos en el HTML de la página:

```
API:      https://eu-offering-api.kambicdn.com/offering/v2018/bwargbac
offering: bwargbac   (BetWarrior Argentina CABA)
```

Params comunes: `lang=es_AR`, `market=AR`, `client_id=2`, `channel_id=1`.

## Endpoints clave

| Endpoint | Para qué |
|---|---|
| `GET /listView/football.json` | eventos prematch con su `path` (deporte→país→liga) → **discovery** |
| `GET /betoffer/group/<groupId>.json` | **todos los eventos + todas las odds de una liga en UNA llamada** |
| `GET /betoffer/event/<id>.json` | odds de un evento (alternativa) |
| `GET /group.json` | árbol top-level (shallow, no se usa) |

`listView` event → `event.path[]` (cada nivel con id/name/termKey), `group`
(liga), `groupId`. `betoffer/group` → `events[]` (homeName/awayName/start/path) +
`betOffers[]` (cada uno con `eventId`).

## Mercados (Kambi)

**odds y line son enteros ×1000** (1660 = 1.66, -250 = -0.25). El mercado se
identifica por `betOfferType.id` + `criterion.englishLabel`:

| selección | mapeo |
|---|---|
| `betOfferType.id==2` + `englishLabel=="Full Time"` | 1X2 (outcome type OT_ONE=local, OT_CROSS=empate, OT_TWO=visitante) |
| `betOfferType.id==7` + `englishLabel=="Asian Handicap"` | 📐 AH (1 offer por línea; outcomes[0]=local, [1]=visitante; cada uno con su `line`) |
| `betOfferType.id==6` + `englishLabel=="Total Goals"` | 📏 GL (OT_OVER/OT_UNDER, `line`=total) |

El tag `MAIN` marca el 1X2 principal; hay que excluir variantes ("- 1st Half",
"Total Goals by <team>", etc.) filtrando por el `englishLabel` exacto.

## Integración (producción, HTTP puro)

`extractors/betwarrior_http/`: `settings.py` (host/offering overridables por env),
`client.py` (listView + betoffer/group), `parser.py` (1X2 + 📐 AH + 📏 GL,
×1000), `discovery.py` (ligas por país desde path), `extractor.py`
(`search_leagues` + `extract_league`, listView cacheado 90s). Registrado
browserless. `/track_league` end-to-end: país → liga → tracking con nombre real
+ odds (verificado: Uruguay Campeonato 9 ev, Argentina Primera B/C, Brasil
Brasileirao A–D). 1 sola llamada por liga (betoffer/group).
