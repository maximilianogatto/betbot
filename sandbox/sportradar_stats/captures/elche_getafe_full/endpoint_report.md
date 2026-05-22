# Sportradar Stats Filtered Endpoint Report

- Capture dir: `/Users/maximilianogatto/Library/CloudStorage/OneDrive-Personal/Apuestas/BetBot/sandbox/sportradar_stats/captures/elche_getafe_full`
- Source usado: `filtered_fetch.ndjson`
- Responses útiles filtradas: 32
- Endpoints limpios detectados: 23

## Resumen Ejecutivo

- `match_markets` expone mercados/odds por HTTP. En esta captura devolvió 11 markets, incluyendo 1X2 y handicaps.
- `match_timeline` / `match_timelinedelta` son los candidatos más fuertes para detectar `live`, score, estado y timeline. Ambos usan `_maxage` corto.
- `event_get` parece un feed live global y no necesariamente del partido abierto: en esta captura apunta a match id(s) 68042480, 70881658, 71490166, 71490628, 71507762, mientras el match principal fue 61624664.
- Hay buen contexto pre-match por HTTP: forma reciente, tabla, streaks, head-to-head y slices de standings.
- También aparecen endpoints útiles para enriquecer análisis: lesiones y leaders de goles, tarjetas y asistencias.

## Endpoints Detectados

| Endpoint | Hits | Polling | Tamaño aprox. | Categorías |
| --- | ---: | :---: | ---: | --- |
| `stats_season_tables` | 2 | Sí | 21.4 KB | Tabla y standings |
| `stats_season_teamscoringconceding` | 2 | Sí | 3.5 KB | Stats pre-match y contexto |
| `stats_season_topassists` | 2 | Sí | 11.2 KB | Jugadores y leaders |
| `stats_season_topcards` | 2 | Sí | 22.6 KB | Jugadores y leaders |
| `stats_season_topgoals` | 2 | Sí | 14.7 KB | Jugadores y leaders |
| `stats_team_lastx` | 2 | Sí | 25.3 KB | Stats pre-match y contexto, Forma reciente |
| `stats_team_nextx` | 2 | Sí | 2.6 KB | Stats pre-match y contexto, Forma reciente |
| `stats_team_streaks` | 2 | Sí | 2.7 KB | Stats pre-match y contexto, Forma reciente |
| `uniqueteam_markets` | 2 | Sí | 300.2 KB | Mercados y odds |
| `event_get` | 1 | Sí | 143.8 KB | Score y estado live, Timeline y eventos live |
| `match_details` | 1 | Sí | 113.0 B | Metadata del partido |
| `match_info_statshub` | 1 | No | 6.8 KB | Metadata del partido |
| `match_markets` | 1 | No | 6.5 KB | Mercados y odds |
| `match_timeline` | 1 | Sí | 2.3 KB | Score y estado live, Timeline y eventos live |
| `match_timelinedelta` | 1 | Sí | 2.4 KB | Score y estado live, Timeline y eventos live |
| `odds_ukformat` | 1 | No | 9.6 KB | Mercados y odds |
| `stats_formtable` | 1 | No | 53.5 KB | Forma reciente, Tabla y standings |
| `stats_h2h_versus` | 1 | Sí | 18.0 KB | Stats pre-match y contexto |
| `stats_match_get` | 1 | No | 5.2 KB | Metadata del partido, Score y estado live |
| `stats_match_head2head` | 1 | No | 505.0 B | Stats pre-match y contexto |
| `stats_match_tableslice` | 1 | No | 2.9 KB | Stats pre-match y contexto, Tabla y standings |
| `stats_season_injuries` | 1 | No | 59.4 KB | Lesiones |
| `stats_team_versus` | 1 | No | 45.4 KB | Stats pre-match y contexto, Forma reciente |

## Endpoints por Caso de Uso

### Metadata del partido

#### `match_details`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage)
- Tamaño aprox.: min 113.0 B | max 113.0 B | avg 113.0 B
- queryUrl: match_details/61624664
- Qué aporta: Detalle auxiliar del match; en esta muestra vino vacío.
- Estructura resumida:

```json
[]
```

#### `match_info_statshub`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 6.8 KB | max 6.8 KB | avg 6.8 KB
- queryUrl: match_info_statshub/61624664
- Match ids detectados: 61624664
- Campos principales: _doc, match, cities, stadium, tournament, uniquetournament, sport, realcategory, season, manager, jerseys, statscoverage
- Qué aporta: Metadata fuerte del partido: torneo, estadio, ciudades, coverage y contexto del evento.
- Estructura resumida:

```json
{
  "_doc": "match_info",
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624664,
    "_sid": 1,
    "_seasonid": 130805,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "_dt": {
      "_doc": "time",
      "time": "17:00",
      "date": "17/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779037200
    },
    "round": 37
  },
  "cities": {
    "home": {
      "_id": 485,
      "name": "Elche"
    },
    "away": {
      "_id": 75,
      "name": "Getafe"
    }
  },
  "stadium": {
    "_doc": "stadium",
    "_id": "1042",
    "name": "Estadio Martínez Valero",
    "description": "",
    "city": "Elche",
    "country": "Spain",
    "state": null,
    "cc": {
      "_doc": "countrycode",
      "_id": 199,
      "a2": "es",
      "name": "Spain",
      "a3": "ESP",
      "ioc": "ESP",
      "continentid": 1,
      "continent": "Europe",
      "population": 46000000
    },
    "capacity": "31388",
    "hometeams": [
      {
        "_doc": "uniqueteam",
        "_id": 2846,
        "_rcid": 32,
        "_sid": 1,
        "name": "Elche",
        "mediumname": "Elche CF",
        "suffix": null,
        "abbr": "ELC",
        "nickname": null,
        "teamtypeid": 0
      }
    ]
  },
  "tournament": {
    "_doc": "tournament",
    "_id": 36,
    "_sid": 1,
    "_rcid": 32,
    "_isk": 1,
    "_tid": 36,
    "_utid": 8,
    "_gender": "men",
    "name": "LaLiga",
    "abbr": "LL"
  },
  "uniquetournament": {
    "_doc": "uniquetournament",
    "_id": 8,
    "_utid": 8,
    "_sid": 1,
    "_rcid": 32,
    "name": "LaLiga",
    "currentseason": 130805,
    "friendly": false
  },
  "sport": {
    "_doc": "sport",
    "_id": 1,
    "_sid": 1,
    "name": "Soccer"
  },
  "realcategory": {
    "_doc": "realcategory",
    "_id": 32,
    "_sid": 1,
    "_rcid": 32,
    "name": "Spain",
    "cc": {
      "_doc": "countrycode",
      "_id": 199,
      "a2": "es",
      "name": "Spain",
      "a3": "ESP",
      "ioc": "ESP",
      "continentid": 1,
      "continent": "Europe",
      "population": 46000000
    }
  },
  "season": {
    "_id": "130805",
    "_doc": "season",
    "_utid": 8,
    "_sid": 1,
    "name": "LaLiga 25/26",
    "abbr": "L 25/26",
    "start": {
      "_doc": "time",
      "time": "00:00",
      "date": "15/08/25",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1755216000
    },
    "end": {
      "_doc": "time",
      "time": "23:59",
      "date": "24/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779667199
    },
    "neutralground": false,
    "friendly": false
  },
  "manager": {
    "home": {
      "_doc": "player",
      "_id": 2118312,
      "name": "Sarabia, Eder",
      "fullname": "Sarabia Armesto, Eder",
      "birthdate": {
        "_doc": "time",
        "time": "00:00",
        "date": "12/01/81",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 348105600
      },
      "nationality": {
        "_doc": "countrycode",
        "_id": 199,
        "a2": "es",
        "name": "Spain",
        "a3": "ESP",
        "ioc": "ESP",
        "continentid": 1,
        "continent": "Europe",
        "population": 46000000
      },
      "primarypositiontype": null,
      "haslogo": false
    },
    "away": {
      "_doc": "player",
      "_id": 94696,
      "name": "Bordalas, Pepe",
      "fullname": "Bordalas Jimenez, Jose",
      "birthdate": {
        "_doc": "time",
        "time": "00:00",
        "date": "05/03/64",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": -183859200
      },
      "nationality": {
        "_doc": "countrycode",
        "_id": 199,
        "a2": "es",
        "name": "Spain",
        "a3": "ESP",
        "ioc": "ESP",
        "continentid": 1,
        "continent": "Europe",
        "population": 46000000
      },
      "primarypositiontype": null,
      "haslogo": false
    }
  }
}
```

#### `stats_match_get`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 5.2 KB | max 5.2 KB | avg 5.2 KB
- queryUrl: stats_match_get/61624664
- Match ids detectados: 61624664
- Campos principales: _doc, _doctype, _id, _sid, _rcid, _tid, _utid, round, week, teams, tobeannounced, postponed
- Qué aporta: Snapshot del match con ids, hora, equipos, resultado y señales de live/inlivescore.
- Estructura resumida:

```json
{
  "_doc": "match",
  "_doctype": "generic",
  "_id": 61624664,
  "_sid": 1,
  "_rcid": 32,
  "_tid": 36,
  "_utid": 8,
  "round": 37,
  "week": 20,
  "teams": {
    "home": {
      "_doc": "team",
      "_id": 6669997,
      "_sid": 1,
      "uid": 2846,
      "virtual": false,
      "name": "Elche",
      "mediumname": "Elche CF",
      "abbr": "ELC",
      "nickname": null,
      "iscountry": false
    },
    "away": {
      "_doc": "team",
      "_id": 368362,
      "_sid": 1,
      "uid": 2859,
      "virtual": false,
      "name": "Getafe",
      "mediumname": "Getafe CF",
      "abbr": "GET",
      "nickname": null,
      "iscountry": false
    }
  }
}
```

### Score y estado live

#### `event_get`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 143.8 KB | max 143.8 KB | avg 143.8 KB
- queryUrl: event_get/
- Match ids detectados: 68042480, 70881658, 71490166, 71490628, 71507762, 71508116, 71506104, 71531244, 71506106, 71506108
- Campos principales: _doc, _doctype, _id, _scoutid, _sid, _rcid, _tid, _dc, _typeid, uts, updated_uts, type
- Qué aporta: Feed de eventos live que parece más global; hay que validar alcance exacto en más capturas.
- Estructura resumida:

```json
[
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "68042480-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 280,
    "_tid": 3133,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778875123
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "70881658-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 20,
    "_tid": 34467,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778875165
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": 2360140358,
    "_scoutid": null,
    "_sid": 137,
    "_rcid": 2265,
    "_tid": 119625,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778879713
  }
]
```

#### `match_timeline`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 2.3 KB | max 2.3 KB | avg 2.3 KB
- queryUrl: match_timeline/61624664
- Match ids detectados: 61624664
- Campos principales: match, events
- Qué aporta: Estado del partido y timeline principal. Es el candidato más claro para live state del fixture abierto.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624664,
    "_sid": 1,
    "_seasonid": 130805,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "_dt": {
      "_doc": "time",
      "time": "17:00",
      "date": "17/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779037200
    },
    "round": 37
  },
  "events": []
}
```

#### `match_timelinedelta`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 2.4 KB | max 2.4 KB | avg 2.4 KB
- queryUrl: match_timelinedelta/61624664
- Match ids detectados: 61624664
- Campos principales: match, events
- Qué aporta: Delta del timeline, ideal para polling liviano cuando el partido está en vivo.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624664,
    "_sid": 1,
    "_seasonid": 130805,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "_dt": {
      "_doc": "time",
      "time": "17:00",
      "date": "17/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779037200
    },
    "round": 37
  },
  "events": []
}
```

#### `stats_match_get`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 5.2 KB | max 5.2 KB | avg 5.2 KB
- queryUrl: stats_match_get/61624664
- Match ids detectados: 61624664
- Campos principales: _doc, _doctype, _id, _sid, _rcid, _tid, _utid, round, week, teams, tobeannounced, postponed
- Qué aporta: Snapshot del match con ids, hora, equipos, resultado y señales de live/inlivescore.
- Estructura resumida:

```json
{
  "_doc": "match",
  "_doctype": "generic",
  "_id": 61624664,
  "_sid": 1,
  "_rcid": 32,
  "_tid": 36,
  "_utid": 8,
  "round": 37,
  "week": 20,
  "teams": {
    "home": {
      "_doc": "team",
      "_id": 6669997,
      "_sid": 1,
      "uid": 2846,
      "virtual": false,
      "name": "Elche",
      "mediumname": "Elche CF",
      "abbr": "ELC",
      "nickname": null,
      "iscountry": false
    },
    "away": {
      "_doc": "team",
      "_id": 368362,
      "_sid": 1,
      "uid": 2859,
      "virtual": false,
      "name": "Getafe",
      "mediumname": "Getafe CF",
      "abbr": "GET",
      "nickname": null,
      "iscountry": false
    }
  }
}
```

### Timeline y eventos live

#### `event_get`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 143.8 KB | max 143.8 KB | avg 143.8 KB
- queryUrl: event_get/
- Match ids detectados: 68042480, 70881658, 71490166, 71490628, 71507762, 71508116, 71506104, 71531244, 71506106, 71506108
- Campos principales: _doc, _doctype, _id, _scoutid, _sid, _rcid, _tid, _dc, _typeid, uts, updated_uts, type
- Qué aporta: Feed de eventos live que parece más global; hay que validar alcance exacto en más capturas.
- Estructura resumida:

```json
[
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "68042480-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 280,
    "_tid": 3133,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778875123
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "70881658-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 20,
    "_tid": 34467,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778875165
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": 2360140358,
    "_scoutid": null,
    "_sid": 137,
    "_rcid": 2265,
    "_tid": 119625,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778879713
  }
]
```

#### `match_timeline`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 2.3 KB | max 2.3 KB | avg 2.3 KB
- queryUrl: match_timeline/61624664
- Match ids detectados: 61624664
- Campos principales: match, events
- Qué aporta: Estado del partido y timeline principal. Es el candidato más claro para live state del fixture abierto.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624664,
    "_sid": 1,
    "_seasonid": 130805,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "_dt": {
      "_doc": "time",
      "time": "17:00",
      "date": "17/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779037200
    },
    "round": 37
  },
  "events": []
}
```

#### `match_timelinedelta`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 2.4 KB | max 2.4 KB | avg 2.4 KB
- queryUrl: match_timelinedelta/61624664
- Match ids detectados: 61624664
- Campos principales: match, events
- Qué aporta: Delta del timeline, ideal para polling liviano cuando el partido está en vivo.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624664,
    "_sid": 1,
    "_seasonid": 130805,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "_dt": {
      "_doc": "time",
      "time": "17:00",
      "date": "17/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779037200
    },
    "round": 37
  },
  "events": []
}
```

### Stats pre-match y contexto

#### `stats_h2h_versus`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage)
- Tamaño aprox.: min 18.0 KB | max 18.0 KB | avg 18.0 KB
- queryUrl: stats_h2h_versus/2846/2859/61624664
- Match ids detectados: 61624664, 27965924, 27965224, 412818, 9775105
- Campos principales: match, lastmatchesbetweenteams, lastmatchesbetweenteamsonvenue, versusmatchstats
- Qué aporta: Historial comparativo y versus stats entre ambos equipos.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624664,
    "_sid": 1,
    "_seasonid": 130805,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "_dt": {
      "_doc": "time",
      "time": "17:00",
      "date": "17/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779037200
    },
    "round": 37
  },
  "lastmatchesbetweenteams": [
    {
      "_doc": "match_h2h_simple",
      "_id": 61624216,
      "result": {
        "home": 1,
        "away": 0,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "20:00",
        "date": "28/11/25",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1764360000
      },
      "homeuniqueteamid": 2859,
      "awayuniqueteamid": 2846,
      "periods": {
        "ft": {
          "home": 1,
          "away": 0
        },
        "p1": {
          "home": 0,
          "away": 0
        }
      },
      "round": 14,
      "roundname": {
        "_doc": "tableround",
        "_id": 14,
        "name": 14
      },
      "_seasonid": 130805
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 61976986,
      "result": {
        "home": 2,
        "away": 1,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "08:00",
        "date": "30/07/25",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1753862400
      },
      "homeuniqueteamid": 2846,
      "awayuniqueteamid": 2859,
      "periods": {
        "ft": {
          "home": 2,
          "away": 1
        },
        "p1": {
          "home": 1,
          "away": 0
        }
      },
      "round": null,
      "_seasonid": 126853,
      "tournament": {
        "_doc": "tournament",
        "_id": 86,
        "_sid": 1,
        "_rcid": 393,
        "_isk": 1000,
        "_tid": 86,
        "_utid": 853,
        "_gender": "men",
        "name": "Club Friendly Games",
        "abbr": "CFG"
      }
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 34277893,
      "result": {
        "home": 1,
        "away": 1,
        "period": "nt",
        "winner": null
      },
      "time": {
        "_doc": "time",
        "time": "16:30",
        "date": "20/05/23",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1684600200
      },
      "homeuniqueteamid": 2859,
      "awayuniqueteamid": 2846,
      "periods": {
        "ft": {
          "home": 1,
          "away": 1
        },
        "p1": {
          "home": 1,
          "away": 1
        }
      },
      "round": 35,
      "roundname": {
        "_doc": "tableround",
        "_id": 35,
        "name": 35
      },
      "_seasonid": 94215
    }
  ],
  "lastmatchesbetweenteamsonvenue": [
    {
      "_doc": "match_h2h_simple",
      "_id": 61976986,
      "result": {
        "home": 2,
        "away": 1,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "08:00",
        "date": "30/07/25",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1753862400
      },
      "homeuniqueteamid": 2846,
      "awayuniqueteamid": 2859,
      "periods": {
        "ft": {
          "home": 2,
          "away": 1
        },
        "p1": {
          "home": 1,
          "away": 0
        }
      },
      "round": null,
      "_seasonid": 126853,
      "tournament": {
        "_doc": "tournament",
        "_id": 86,
        "_sid": 1,
        "_rcid": 393,
        "_isk": 1000,
        "_tid": 86,
        "_utid": 853,
        "_gender": "men",
        "name": "Club Friendly Games",
        "abbr": "CFG"
      }
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 34277421,
      "result": {
        "home": 0,
        "away": 1,
        "period": "nt",
        "winner": "away"
      },
      "time": {
        "_doc": "time",
        "time": "20:00",
        "date": "31/10/22",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1667246400
      },
      "homeuniqueteamid": 2846,
      "awayuniqueteamid": 2859,
      "periods": {
        "ft": {
          "home": 0,
          "away": 1
        },
        "p1": {
          "home": 0,
          "away": 0
        }
      },
      "round": 12,
      "roundname": {
        "_doc": "tableround",
        "_id": 12,
        "name": 12
      },
      "_seasonid": 94215
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 27965924,
      "result": {
        "home": 3,
        "away": 1,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "15:30",
        "date": "22/05/22",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1653233400
      },
      "homeuniqueteamid": 2846,
      "awayuniqueteamid": 2859,
      "periods": {
        "ft": {
          "home": 3,
          "away": 1
        },
        "p1": {
          "home": 1,
          "away": 1
        }
      },
      "round": 38,
      "roundname": {
        "_doc": "tableround",
        "_id": 38,
        "name": 38
      },
      "_seasonid": 84048
    }
  ],
  "versusmatchstats": {
    "2846": {
      "highestwin": {
        "total": {
          "home": 3,
          "away": 1,
          "period": "nt",
          "winner": "home",
          "goaldiff": 2,
          "matchid": 27965924,
          "matchuts": 1653233400
        },
        "home": {
          "home": 3,
          "away": 1,
          "period": "nt",
          "winner": "home",
          "goaldiff": 2,
          "matchid": 27965924,
          "matchuts": 1653233400
        },
        "away": {
          "home": 0,
          "away": 1,
          "period": "nt",
          "winner": "away",
          "goaldiff": 1,
          "matchid": 27965224,
          "matchuts": 1631556000
        }
      },
      "totalmatches": {
        "total": 24,
        "home": 13,
        "away": 11
      },
      "teamwins": {
        "total": 6,
        "home": 4,
        "away": 2
      },
      "teamloses": {
        "total": 7,
        "home": 4,
        "away": 3
      },
      "teamdraws": {
        "total": 11,
        "home": 5,
        "away": 6
      },
      "oldestmatchdate": "1999",
      "totalgoals": {
        "total": 24,
        "home": 15,
        "away": 9
      },
      "averagegoals": {
        "total": 1,
        "home": 1.1538461538461537,
        "away": 0.8181818181818182
      },
      "leadingathalftime": {
        "total": 6,
        "home": 4,
        "away": 2
      },
      "losingathalftime": {
        "total": 4,
        "home": 2,
        "away": 2
      }
    },
    "2859": {
      "highestwin": {
        "total": {
          "home": 1,
          "away": 4,
          "period": "nt",
          "winner": "away",
          "goaldiff": 3,
          "matchid": 412818,
          "matchuts": 974653200
        },
        "home": {
          "home": 2,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 2,
          "matchid": 9775105,
          "matchuts": 1495220400
        },
        "away": {
          "home": 1,
          "away": 4,
          "period": "nt",
          "winner": "away",
          "goaldiff": 3,
          "matchid": 412818,
          "matchuts": 974653200
        }
      },
      "totalmatches": {
        "total": 24,
        "home": 11,
        "away": 13
      },
      "teamwins": {
        "total": 7,
        "home": 3,
        "away": 4
      },
      "teamloses": {
        "total": 6,
        "home": 2,
        "away": 4
      },
      "teamdraws": {
        "total": 11,
        "home": 6,
        "away": 5
      },
      "oldestmatchdate": "1999",
      "totalgoals": {
        "total": 29,
        "home": 12,
        "away": 17
      },
      "averagegoals": {
        "total": 1.2083333333333333,
        "home": 1.0909090909090908,
        "away": 1.3076923076923077
      },
      "leadingathalftime": {
        "total": 4,
        "home": 2,
        "away": 2
      },
      "losingathalftime": {
        "total": 6,
        "home": 2,
        "away": 4
      }
    }
  }
}
```

#### `stats_match_head2head`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 505.0 B | max 505.0 B | avg 505.0 B
- queryUrl: stats_match_head2head/61624664
- Campos principales: _id, teams
- Qué aporta: Head-to-head compacto entre los equipos.
- Estructura resumida:

```json
{
  "_id": 61624664,
  "teams": {
    "home": {
      "_doc": "team",
      "_id": 6669997,
      "_sid": 1,
      "uid": 2846,
      "virtual": false,
      "name": "Elche",
      "mediumname": "Elche CF",
      "abbr": "ELC",
      "nickname": null,
      "iscountry": false
    },
    "away": {
      "_doc": "team",
      "_id": 368362,
      "_sid": 1,
      "uid": 2859,
      "virtual": false,
      "name": "Getafe",
      "mediumname": "Getafe CF",
      "abbr": "GET",
      "nickname": null,
      "iscountry": false
    }
  }
}
```

#### `stats_match_tableslice`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 2.9 KB | max 2.9 KB | avg 2.9 KB
- queryUrl: stats_match_tableslice/61624664
- Match ids detectados: 61624664
- Campos principales: _doc, _id, parenttableid, leaguetypeid, parenttableids, seasonid, maxrounds, currentround, presentationid, name, abbr, groupname
- Qué aporta: Slice de tabla alrededor del partido, útil para contexto competitivo.
- Estructura resumida:

```json
{
  "_doc": "statistics_leaguetable",
  "_id": "95812",
  "parenttableid": null,
  "leaguetypeid": null,
  "parenttableids": {},
  "seasonid": "130805",
  "maxrounds": 38,
  "currentround": 36,
  "presentationid": 0,
  "name": "LaLiga 25/26"
}
```

#### `stats_season_teamscoringconceding`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 3.5 KB | max 3.6 KB | avg 3.5 KB
- queryUrl: stats_season_teamscoringconceding/130805/2859/-1, stats_season_teamscoringconceding/130805/2846/-1
- Campos principales: team, stats
- Qué aporta: Distribución de goles anotados/recibidos por equipo y temporada.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2859,
    "_rcid": 32,
    "_sid": 1,
    "name": "Getafe",
    "mediumname": "Getafe CF",
    "suffix": null,
    "abbr": "GET",
    "nickname": null,
    "teamtypeid": 0
  },
  "stats": {
    "totalmatches": {
      "total": 36,
      "home": 18,
      "away": 18
    },
    "totalwins": {
      "total": 14,
      "home": 7,
      "away": 7
    },
    "scoring": {
      "goalsscored": {
        "total": 31,
        "home": 17,
        "away": 14
      },
      "atleastonegoal": {
        "total": 34,
        "home": 17,
        "away": 17
      },
      "failedtoscore": {
        "total": 16,
        "home": 8,
        "away": 8
      },
      "scoringathalftime": {
        "total": 10,
        "home": 5,
        "away": 5
      },
      "scoringatfulltime": {
        "total": 20,
        "home": 10,
        "away": 10
      },
      "bothteamsscored": {
        "total": 11,
        "home": 6,
        "away": 5
      },
      "goalsscoredfirsthalf": {
        "total": 14,
        "home": 8,
        "away": 6
      },
      "goalsscoredaverage": {
        "total": 0.8611111111111112,
        "home": 0.9444444444444444,
        "away": 0.7777777777777778
      },
      "atleastonegoalaverage": {
        "total": 0.9444444444444444,
        "home": 0.9444444444444444,
        "away": 0.9444444444444444
      },
      "failedtoscoreaverage": {
        "total": 0.4444444444444444,
        "home": 0.4444444444444444,
        "away": 0.4444444444444444
      }
    },
    "conceding": {
      "goalsconceded": {
        "total": 37,
        "home": 16,
        "away": 21
      },
      "cleansheets": {
        "total": 11,
        "home": 5,
        "away": 6
      },
      "goalsconcededfirsthalf": {
        "total": 14,
        "home": 4,
        "away": 10
      },
      "goalsconcededaverage": {
        "total": 1.0277777777777777,
        "home": 0.8888888888888888,
        "away": 1.1666666666666667
      },
      "cleansheetsaverage": {
        "total": 0.3055555555555556,
        "home": 0.2777777777777778,
        "away": 0.3333333333333333
      },
      "goalsconcededfirsthalfaverage": {
        "total": 0.3888888888888889,
        "home": 0.2222222222222222,
        "away": 0.5555555555555556
      },
      "minutespergoalconceded": {
        "total": 92.94594594594595,
        "home": 107.25,
        "away": 82.04761904761905
      },
      "goalsbyminutes": {
        "0-15": {
          "total": 0.08333333333333333,
          "home": 0,
          "away": 0.16666666666666666
        },
        "16-30": {
          "total": 0.08333333333333333,
          "home": 0.05555555555555555,
          "away": 0.1111111111111111
        },
        "31-45": {
          "total": 0.2222222222222222,
          "home": 0.16666666666666666,
          "away": 0.2777777777777778
        },
        "46-60": {
          "total": 0.1388888888888889,
          "home": 0.05555555555555555,
          "away": 0.2222222222222222
        },
        "61-75": {
          "total": 0.2222222222222222,
          "home": 0.2777777777777778,
          "away": 0.16666666666666666
        },
        "76-90": {
          "total": 0.2777777777777778,
          "home": 0.3333333333333333,
          "away": 0.2222222222222222
        }
      }
    },
    "averagegoalsbyminutes": {
      "0-15": 0.3085399449035813,
      "16-30": 0.31955922865013775,
      "31-45": 0.5041322314049587,
      "46-60": 0.4297520661157025,
      "61-75": 0.4380165289256198,
      "76-90": 0.6694214876033058
    }
  }
}
```

#### `stats_team_lastx`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 23.9 KB | max 26.7 KB | avg 25.3 KB
- queryUrl: stats_team_lastx/2859/20, stats_team_lastx/2846/20
- Match ids detectados: 61624644, 61624634, 61624606, 61624570, 61624596, 61624554, 61624530, 61624504, 61624480, 61624468
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Últimos partidos de un equipo, útil para forma reciente.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2859,
    "_rcid": 32,
    "_sid": 1,
    "name": "Getafe",
    "mediumname": "Getafe CF",
    "suffix": null,
    "abbr": "GET",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624644,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 36,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5206,
          "_sid": 1,
          "uid": 2826,
          "virtual": false,
          "name": "Mallorca",
          "mediumname": "RCD Mallorca",
          "abbr": "MAL",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624634,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 35,
      "week": 19,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5205,
          "_sid": 1,
          "uid": 2851,
          "virtual": false,
          "name": "Oviedo",
          "mediumname": "Real Oviedo",
          "abbr": "OVI",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624606,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 34,
      "week": 18,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5121,
          "_sid": 1,
          "uid": 2818,
          "virtual": false,
          "name": "Vallecano",
          "mediumname": "Rayo Vallecano",
          "abbr": "RVC",
          "nickname": null,
          "iscountry": false
        }
      }
    }
  ],
  "tournaments": {
    "36": {
      "_doc": "tournament",
      "_id": 36,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 1,
      "_tid": 36,
      "_utid": 8,
      "_gender": "men",
      "name": "LaLiga",
      "abbr": "LL"
    }
  },
  "uniquetournaments": {
    "8": {
      "_doc": "uniquetournament",
      "_id": 8,
      "_utid": 8,
      "_sid": 1,
      "_rcid": 32,
      "name": "LaLiga",
      "currentseason": 130805,
      "friendly": false
    }
  },
  "realcategories": {
    "32": {
      "_doc": "realcategory",
      "_id": 32,
      "_sid": 1,
      "_rcid": 32,
      "name": "Spain",
      "cc": {
        "_doc": "countrycode",
        "_id": 199,
        "a2": "es",
        "name": "Spain",
        "a3": "ESP",
        "ioc": "ESP",
        "continentid": 1,
        "continent": "Europe",
        "population": 46000000
      }
    }
  }
}
```

#### `stats_team_nextx`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 2.6 KB | max 2.6 KB | avg 2.6 KB
- queryUrl: stats_team_nextx/2846/1, stats_team_nextx/2859/1
- Match ids detectados: 61624664
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Próximos partidos del equipo, útil para congestión de calendario.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2846,
    "_rcid": 32,
    "_sid": 1,
    "name": "Elche",
    "mediumname": "Elche CF",
    "suffix": null,
    "abbr": "ELC",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624664,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 37,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 6669997,
          "_sid": 1,
          "uid": 2846,
          "virtual": false,
          "name": "Elche",
          "mediumname": "Elche CF",
          "abbr": "ELC",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        }
      }
    }
  ],
  "tournaments": {
    "36": {
      "_doc": "tournament",
      "_id": 36,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 1,
      "_tid": 36,
      "_utid": 8,
      "_gender": "men",
      "name": "LaLiga",
      "abbr": "LL"
    }
  },
  "uniquetournaments": {
    "8": {
      "_doc": "uniquetournament",
      "_id": 8,
      "_utid": 8,
      "_sid": 1,
      "_rcid": 32,
      "name": "LaLiga",
      "currentseason": 130805,
      "friendly": false
    }
  },
  "realcategories": {
    "32": {
      "_doc": "realcategory",
      "_id": 32,
      "_sid": 1,
      "_rcid": 32,
      "name": "Spain",
      "cc": {
        "_doc": "countrycode",
        "_id": 199,
        "a2": "es",
        "name": "Spain",
        "a3": "ESP",
        "ioc": "ESP",
        "continentid": 1,
        "continent": "Europe",
        "population": 46000000
      }
    }
  }
}
```

#### `stats_team_streaks`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 2.1 KB | max 3.4 KB | avg 2.7 KB
- queryUrl: stats_team_streaks/2859, stats_team_streaks/2846
- Match ids detectados: 61624664, 61624686, 61624644, 61624634, 61624606, 61624570, 61624596, 61624554, 61624530, 61624504
- Campos principales: team, nextmatches, lastmatchesform, streaks
- Qué aporta: Rachas y forma condensada del equipo.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2859,
    "_rcid": 32,
    "_sid": 1,
    "name": "Getafe",
    "mediumname": "Getafe CF",
    "suffix": null,
    "abbr": "GET",
    "nickname": null,
    "teamtypeid": 0
  },
  "nextmatches": [
    {
      "matchdifficultyrating": 3,
      "matchid": 61624664
    },
    {
      "matchdifficultyrating": 1,
      "matchid": 61624686
    }
  ],
  "lastmatchesform": {
    "total": [
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624644
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624634
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624606
      }
    ],
    "home": [
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624644
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624606
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624570
      }
    ],
    "away": [
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624634
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624596
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624554
      }
    ]
  },
  "streaks": {
    "nodrawing": {
      "home": {
        "value": 7,
        "streak": [
          {
            "result": "W",
            "matchid": 61624644
          },
          {
            "result": "L",
            "matchid": 61624606
          },
          {
            "result": "L",
            "matchid": 61624570
          }
        ]
      }
    },
    "nogoalsconceded": {
      "away": {
        "value": 2,
        "streak": [
          {
            "result": 0,
            "matchid": 61624634
          },
          {
            "result": 0,
            "matchid": 61624596
          }
        ]
      }
    }
  }
}
```

#### `stats_team_versus`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 45.4 KB | max 45.4 KB | avg 45.4 KB
- queryUrl: stats_team_versus/2846/2859
- Match ids detectados: 61624216, 61976986, 34277893, 34277421, 34651551, 27965924, 27965224, 23360869, 23360677, 9775105
- Campos principales: livematchid, matches, tournaments, realcategories, teams, currentmanagers, jersey, next
- Qué aporta: Cruces entre equipos con contexto extra.
- Estructura resumida:

```json
{
  "livematchid": null,
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624216,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 14,
      "week": 48,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 6669997,
          "_sid": 1,
          "uid": 2846,
          "virtual": false,
          "name": "Elche",
          "mediumname": "Elche CF",
          "abbr": "ELC",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61976986,
      "_sid": 1,
      "_rcid": 393,
      "_tid": 86,
      "_utid": 853,
      "round": null,
      "week": 31,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 585694,
          "_sid": 1,
          "uid": 2846,
          "virtual": false,
          "name": "Elche",
          "mediumname": "Elche CF",
          "abbr": "ELC",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 580540,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 34277893,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 35,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 6669997,
          "_sid": 1,
          "uid": 2846,
          "virtual": false,
          "name": "Elche",
          "mediumname": "Elche CF",
          "abbr": "ELC",
          "nickname": null,
          "iscountry": false
        }
      }
    }
  ],
  "tournaments": {
    "36": {
      "_doc": "tournament",
      "_id": 36,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 1,
      "_tid": 36,
      "_utid": 8,
      "_gender": "men",
      "name": "LaLiga",
      "abbr": "LL"
    },
    "86": {
      "_doc": "tournament",
      "_id": 86,
      "_sid": 1,
      "_rcid": 393,
      "_isk": 1000,
      "_tid": 86,
      "_utid": 853,
      "_gender": "men",
      "name": "Club Friendly Games",
      "abbr": "CFG"
    },
    "37": {
      "_doc": "tournament",
      "_id": 37,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 5,
      "_tid": 37,
      "_utid": 54,
      "_gender": "men",
      "name": "LaLiga 2",
      "abbr": "SD"
    }
  },
  "realcategories": {
    "32": {
      "_doc": "realcategory",
      "_id": 32,
      "_sid": 1,
      "_rcid": 32,
      "name": "Spain",
      "cc": {
        "_doc": "countrycode",
        "_id": 199,
        "a2": "es",
        "name": "Spain",
        "a3": "ESP",
        "ioc": "ESP",
        "continentid": 1,
        "continent": "Europe",
        "population": 46000000
      }
    },
    "393": {
      "_doc": "realcategory",
      "_id": 393,
      "_sid": 1,
      "_rcid": 393,
      "name": "International Clubs",
      "cc": null
    }
  },
  "teams": {
    "2846": {
      "_doc": "uniqueteam",
      "_id": 2846,
      "_rcid": 32,
      "_sid": 1,
      "name": "Elche",
      "mediumname": "Elche CF",
      "suffix": null,
      "abbr": "ELC",
      "nickname": null,
      "teamtypeid": 0
    },
    "2859": {
      "_doc": "uniqueteam",
      "_id": 2859,
      "_rcid": 32,
      "_sid": 1,
      "name": "Getafe",
      "mediumname": "Getafe CF",
      "suffix": null,
      "abbr": "GET",
      "nickname": null,
      "teamtypeid": 0
    }
  },
  "currentmanagers": {
    "2846": [
      {
        "_doc": "player",
        "_id": 2118312,
        "name": "Sarabia, Eder",
        "fullname": "Sarabia Armesto, Eder",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "12/01/81",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 348105600
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 199,
          "a2": "es",
          "name": "Spain",
          "a3": "ESP",
          "ioc": "ESP",
          "continentid": 1,
          "continent": "Europe",
          "population": 46000000
        },
        "primarypositiontype": null,
        "haslogo": false,
        "membersince": {
          "_doc": "time",
          "time": "00:00",
          "date": "01/07/24",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1719792000
        }
      }
    ],
    "2859": [
      {
        "_doc": "player",
        "_id": 94696,
        "name": "Bordalas, Pepe",
        "fullname": "Bordalas Jimenez, Jose",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "05/03/64",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": -183859200
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 199,
          "a2": "es",
          "name": "Spain",
          "a3": "ESP",
          "ioc": "ESP",
          "continentid": 1,
          "continent": "Europe",
          "population": 46000000
        },
        "primarypositiontype": null,
        "haslogo": false,
        "membersince": {
          "_doc": "time",
          "time": "00:00",
          "date": "29/04/23",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1682726400
        }
      }
    ]
  },
  "jersey": {
    "2846": {
      "base": "ffffff",
      "sleeve": "008000",
      "number": "0d0e06",
      "type": "short_sleeves",
      "sleevelong": "ffffff",
      "real": true
    },
    "2859": {
      "base": "063ba1",
      "sleeve": "ffd505",
      "number": "ffffff",
      "type": "short_sleeves",
      "sleevelong": "063ba1",
      "real": true
    }
  },
  "next": {
    "_doc": "match",
    "_doctype": "generic",
    "_id": 61624664,
    "_sid": 1,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "round": 37,
    "week": 20,
    "teams": {
      "home": {
        "_doc": "team",
        "_id": 6669997,
        "_sid": 1,
        "uid": 2846,
        "virtual": false,
        "name": "Elche",
        "mediumname": "Elche CF",
        "abbr": "ELC",
        "nickname": null,
        "iscountry": false
      },
      "away": {
        "_doc": "team",
        "_id": 368362,
        "_sid": 1,
        "uid": 2859,
        "virtual": false,
        "name": "Getafe",
        "mediumname": "Getafe CF",
        "abbr": "GET",
        "nickname": null,
        "iscountry": false
      }
    }
  }
}
```

### Forma reciente

#### `stats_formtable`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 53.5 KB | max 53.5 KB | avg 53.5 KB
- queryUrl: stats_formtable/130805
- Match ids detectados: 61624638, 61624622, 61624612, 61624570, 61624580, 61624540, 61624500, 61624482, 61624438, 61624520
- Campos principales: matchtype, tabletype, season, winpoints, losspoints, currentround, teams
- Qué aporta: Tabla de forma reciente, muy útil para filtros pre-match.
- Estructura resumida:

```json
{
  "matchtype": [
    {
      "_doc": "matchtype",
      "_id": 1,
      "settypeid": 2,
      "column": "All matches"
    },
    {
      "_doc": "matchtype",
      "_id": 2,
      "settypeid": 4,
      "column": "Home matches"
    },
    {
      "_doc": "matchtype",
      "_id": 3,
      "settypeid": 6,
      "column": "Away matches"
    }
  ],
  "tabletype": [
    {
      "_doc": "tabletype",
      "_id": 1,
      "column": "Full Time"
    },
    {
      "_doc": "tabletype",
      "_id": 2,
      "column": "1st half"
    }
  ],
  "season": {
    "_id": "130805",
    "_doc": "season",
    "_utid": 8,
    "_sid": 1,
    "name": "LaLiga 25/26",
    "abbr": "L 25/26",
    "start": {
      "_doc": "time",
      "time": "00:00",
      "date": "15/08/25",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1755216000
    },
    "end": {
      "_doc": "time",
      "time": "23:59",
      "date": "24/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779667199
    },
    "neutralground": false,
    "friendly": false
  },
  "winpoints": 3,
  "losspoints": 0,
  "currentround": 36,
  "teams": [
    {
      "team": {
        "_doc": "team",
        "_id": 5198,
        "_sid": 1,
        "uid": 2817,
        "virtual": false,
        "name": "Barcelona",
        "mediumname": "FC Barcelona",
        "abbr": "BAR",
        "nickname": null,
        "iscountry": false
      },
      "position": {
        "total": 1,
        "home": 1,
        "away": 1
      },
      "played": {
        "total": 6,
        "totalhome": 3,
        "totalaway": 3,
        "home": 6,
        "away": 6
      },
      "win": {
        "total": 5,
        "totalhome": 3,
        "totalaway": 2,
        "home": 6,
        "away": 4
      },
      "draw": {
        "total": 0,
        "totalhome": 0,
        "totalaway": 0,
        "home": 0,
        "away": 0
      },
      "loss": {
        "total": 1,
        "totalhome": 0,
        "totalaway": 1,
        "home": 0,
        "away": 2
      },
      "goalsfor": {
        "total": 11,
        "totalhome": 7,
        "totalaway": 4,
        "home": 17,
        "away": 8
      },
      "goalsagainst": {
        "total": 3,
        "totalhome": 1,
        "totalaway": 2,
        "home": 4,
        "away": 5
      },
      "goaldifference": {
        "total": 8,
        "totalhome": 6,
        "totalaway": 2,
        "home": 13,
        "away": 3
      },
      "points": {
        "total": 15,
        "totalhome": 9,
        "totalaway": 6,
        "home": 18,
        "away": 12
      }
    },
    {
      "team": {
        "_doc": "team",
        "_id": 368361,
        "_sid": 1,
        "uid": 2849,
        "virtual": false,
        "name": "Levante",
        "mediumname": "Levante UD",
        "abbr": "LEV",
        "nickname": null,
        "iscountry": false
      },
      "position": {
        "total": 2,
        "home": 2,
        "away": 12
      },
      "played": {
        "total": 6,
        "totalhome": 3,
        "totalaway": 3,
        "home": 6,
        "away": 6
      },
      "win": {
        "total": 4,
        "totalhome": 3,
        "totalaway": 1,
        "home": 5,
        "away": 1
      },
      "draw": {
        "total": 1,
        "totalhome": 0,
        "totalaway": 1,
        "home": 1,
        "away": 2
      },
      "loss": {
        "total": 1,
        "totalhome": 0,
        "totalaway": 1,
        "home": 0,
        "away": 3
      },
      "goalsfor": {
        "total": 10,
        "totalhome": 6,
        "totalaway": 4,
        "home": 13,
        "away": 5
      },
      "goalsagainst": {
        "total": 9,
        "totalhome": 2,
        "totalaway": 7,
        "home": 5,
        "away": 13
      },
      "goaldifference": {
        "total": 1,
        "totalhome": 4,
        "totalaway": -3,
        "home": 8,
        "away": -8
      },
      "points": {
        "total": 13,
        "totalhome": 9,
        "totalaway": 4,
        "home": 16,
        "away": 5
      }
    },
    {
      "team": {
        "_doc": "team",
        "_id": 32608,
        "_sid": 1,
        "uid": 2816,
        "virtual": false,
        "name": "Real Betis",
        "mediumname": "Real Betis Seville",
        "abbr": "RBB",
        "nickname": null,
        "iscountry": false
      },
      "position": {
        "total": 3,
        "home": 10,
        "away": 5
      },
      "played": {
        "total": 6,
        "totalhome": 3,
        "totalaway": 3,
        "home": 6,
        "away": 6
      },
      "win": {
        "total": 3,
        "totalhome": 2,
        "totalaway": 1,
        "home": 2,
        "away": 2
      },
      "draw": {
        "total": 3,
        "totalhome": 1,
        "totalaway": 2,
        "home": 4,
        "away": 2
      },
      "loss": {
        "total": 0,
        "totalhome": 0,
        "totalaway": 0,
        "home": 0,
        "away": 2
      },
      "goalsfor": {
        "total": 12,
        "totalhome": 6,
        "totalaway": 6,
        "home": 9,
        "away": 9
      },
      "goalsagainst": {
        "total": 7,
        "totalhome": 2,
        "totalaway": 5,
        "home": 5,
        "away": 10
      },
      "goaldifference": {
        "total": 5,
        "totalhome": 4,
        "totalaway": 1,
        "home": 4,
        "away": -1
      },
      "points": {
        "total": 12,
        "totalhome": 7,
        "totalaway": 5,
        "home": 10,
        "away": 8
      }
    }
  ]
}
```

#### `stats_team_lastx`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 23.9 KB | max 26.7 KB | avg 25.3 KB
- queryUrl: stats_team_lastx/2859/20, stats_team_lastx/2846/20
- Match ids detectados: 61624644, 61624634, 61624606, 61624570, 61624596, 61624554, 61624530, 61624504, 61624480, 61624468
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Últimos partidos de un equipo, útil para forma reciente.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2859,
    "_rcid": 32,
    "_sid": 1,
    "name": "Getafe",
    "mediumname": "Getafe CF",
    "suffix": null,
    "abbr": "GET",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624644,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 36,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5206,
          "_sid": 1,
          "uid": 2826,
          "virtual": false,
          "name": "Mallorca",
          "mediumname": "RCD Mallorca",
          "abbr": "MAL",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624634,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 35,
      "week": 19,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5205,
          "_sid": 1,
          "uid": 2851,
          "virtual": false,
          "name": "Oviedo",
          "mediumname": "Real Oviedo",
          "abbr": "OVI",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624606,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 34,
      "week": 18,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5121,
          "_sid": 1,
          "uid": 2818,
          "virtual": false,
          "name": "Vallecano",
          "mediumname": "Rayo Vallecano",
          "abbr": "RVC",
          "nickname": null,
          "iscountry": false
        }
      }
    }
  ],
  "tournaments": {
    "36": {
      "_doc": "tournament",
      "_id": 36,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 1,
      "_tid": 36,
      "_utid": 8,
      "_gender": "men",
      "name": "LaLiga",
      "abbr": "LL"
    }
  },
  "uniquetournaments": {
    "8": {
      "_doc": "uniquetournament",
      "_id": 8,
      "_utid": 8,
      "_sid": 1,
      "_rcid": 32,
      "name": "LaLiga",
      "currentseason": 130805,
      "friendly": false
    }
  },
  "realcategories": {
    "32": {
      "_doc": "realcategory",
      "_id": 32,
      "_sid": 1,
      "_rcid": 32,
      "name": "Spain",
      "cc": {
        "_doc": "countrycode",
        "_id": 199,
        "a2": "es",
        "name": "Spain",
        "a3": "ESP",
        "ioc": "ESP",
        "continentid": 1,
        "continent": "Europe",
        "population": 46000000
      }
    }
  }
}
```

#### `stats_team_nextx`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 2.6 KB | max 2.6 KB | avg 2.6 KB
- queryUrl: stats_team_nextx/2846/1, stats_team_nextx/2859/1
- Match ids detectados: 61624664
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Próximos partidos del equipo, útil para congestión de calendario.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2846,
    "_rcid": 32,
    "_sid": 1,
    "name": "Elche",
    "mediumname": "Elche CF",
    "suffix": null,
    "abbr": "ELC",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624664,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 37,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 6669997,
          "_sid": 1,
          "uid": 2846,
          "virtual": false,
          "name": "Elche",
          "mediumname": "Elche CF",
          "abbr": "ELC",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        }
      }
    }
  ],
  "tournaments": {
    "36": {
      "_doc": "tournament",
      "_id": 36,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 1,
      "_tid": 36,
      "_utid": 8,
      "_gender": "men",
      "name": "LaLiga",
      "abbr": "LL"
    }
  },
  "uniquetournaments": {
    "8": {
      "_doc": "uniquetournament",
      "_id": 8,
      "_utid": 8,
      "_sid": 1,
      "_rcid": 32,
      "name": "LaLiga",
      "currentseason": 130805,
      "friendly": false
    }
  },
  "realcategories": {
    "32": {
      "_doc": "realcategory",
      "_id": 32,
      "_sid": 1,
      "_rcid": 32,
      "name": "Spain",
      "cc": {
        "_doc": "countrycode",
        "_id": 199,
        "a2": "es",
        "name": "Spain",
        "a3": "ESP",
        "ioc": "ESP",
        "continentid": 1,
        "continent": "Europe",
        "population": 46000000
      }
    }
  }
}
```

#### `stats_team_streaks`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 2.1 KB | max 3.4 KB | avg 2.7 KB
- queryUrl: stats_team_streaks/2859, stats_team_streaks/2846
- Match ids detectados: 61624664, 61624686, 61624644, 61624634, 61624606, 61624570, 61624596, 61624554, 61624530, 61624504
- Campos principales: team, nextmatches, lastmatchesform, streaks
- Qué aporta: Rachas y forma condensada del equipo.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2859,
    "_rcid": 32,
    "_sid": 1,
    "name": "Getafe",
    "mediumname": "Getafe CF",
    "suffix": null,
    "abbr": "GET",
    "nickname": null,
    "teamtypeid": 0
  },
  "nextmatches": [
    {
      "matchdifficultyrating": 3,
      "matchid": 61624664
    },
    {
      "matchdifficultyrating": 1,
      "matchid": 61624686
    }
  ],
  "lastmatchesform": {
    "total": [
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624644
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624634
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624606
      }
    ],
    "home": [
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624644
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624606
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624570
      }
    ],
    "away": [
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624634
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624596
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624554
      }
    ]
  },
  "streaks": {
    "nodrawing": {
      "home": {
        "value": 7,
        "streak": [
          {
            "result": "W",
            "matchid": 61624644
          },
          {
            "result": "L",
            "matchid": 61624606
          },
          {
            "result": "L",
            "matchid": 61624570
          }
        ]
      }
    },
    "nogoalsconceded": {
      "away": {
        "value": 2,
        "streak": [
          {
            "result": 0,
            "matchid": 61624634
          },
          {
            "result": 0,
            "matchid": 61624596
          }
        ]
      }
    }
  }
}
```

#### `stats_team_versus`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 45.4 KB | max 45.4 KB | avg 45.4 KB
- queryUrl: stats_team_versus/2846/2859
- Match ids detectados: 61624216, 61976986, 34277893, 34277421, 34651551, 27965924, 27965224, 23360869, 23360677, 9775105
- Campos principales: livematchid, matches, tournaments, realcategories, teams, currentmanagers, jersey, next
- Qué aporta: Cruces entre equipos con contexto extra.
- Estructura resumida:

```json
{
  "livematchid": null,
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624216,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 14,
      "week": 48,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 6669997,
          "_sid": 1,
          "uid": 2846,
          "virtual": false,
          "name": "Elche",
          "mediumname": "Elche CF",
          "abbr": "ELC",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61976986,
      "_sid": 1,
      "_rcid": 393,
      "_tid": 86,
      "_utid": 853,
      "round": null,
      "week": 31,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 585694,
          "_sid": 1,
          "uid": 2846,
          "virtual": false,
          "name": "Elche",
          "mediumname": "Elche CF",
          "abbr": "ELC",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 580540,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 34277893,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 35,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 368362,
          "_sid": 1,
          "uid": 2859,
          "virtual": false,
          "name": "Getafe",
          "mediumname": "Getafe CF",
          "abbr": "GET",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 6669997,
          "_sid": 1,
          "uid": 2846,
          "virtual": false,
          "name": "Elche",
          "mediumname": "Elche CF",
          "abbr": "ELC",
          "nickname": null,
          "iscountry": false
        }
      }
    }
  ],
  "tournaments": {
    "36": {
      "_doc": "tournament",
      "_id": 36,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 1,
      "_tid": 36,
      "_utid": 8,
      "_gender": "men",
      "name": "LaLiga",
      "abbr": "LL"
    },
    "86": {
      "_doc": "tournament",
      "_id": 86,
      "_sid": 1,
      "_rcid": 393,
      "_isk": 1000,
      "_tid": 86,
      "_utid": 853,
      "_gender": "men",
      "name": "Club Friendly Games",
      "abbr": "CFG"
    },
    "37": {
      "_doc": "tournament",
      "_id": 37,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 5,
      "_tid": 37,
      "_utid": 54,
      "_gender": "men",
      "name": "LaLiga 2",
      "abbr": "SD"
    }
  },
  "realcategories": {
    "32": {
      "_doc": "realcategory",
      "_id": 32,
      "_sid": 1,
      "_rcid": 32,
      "name": "Spain",
      "cc": {
        "_doc": "countrycode",
        "_id": 199,
        "a2": "es",
        "name": "Spain",
        "a3": "ESP",
        "ioc": "ESP",
        "continentid": 1,
        "continent": "Europe",
        "population": 46000000
      }
    },
    "393": {
      "_doc": "realcategory",
      "_id": 393,
      "_sid": 1,
      "_rcid": 393,
      "name": "International Clubs",
      "cc": null
    }
  },
  "teams": {
    "2846": {
      "_doc": "uniqueteam",
      "_id": 2846,
      "_rcid": 32,
      "_sid": 1,
      "name": "Elche",
      "mediumname": "Elche CF",
      "suffix": null,
      "abbr": "ELC",
      "nickname": null,
      "teamtypeid": 0
    },
    "2859": {
      "_doc": "uniqueteam",
      "_id": 2859,
      "_rcid": 32,
      "_sid": 1,
      "name": "Getafe",
      "mediumname": "Getafe CF",
      "suffix": null,
      "abbr": "GET",
      "nickname": null,
      "teamtypeid": 0
    }
  },
  "currentmanagers": {
    "2846": [
      {
        "_doc": "player",
        "_id": 2118312,
        "name": "Sarabia, Eder",
        "fullname": "Sarabia Armesto, Eder",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "12/01/81",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 348105600
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 199,
          "a2": "es",
          "name": "Spain",
          "a3": "ESP",
          "ioc": "ESP",
          "continentid": 1,
          "continent": "Europe",
          "population": 46000000
        },
        "primarypositiontype": null,
        "haslogo": false,
        "membersince": {
          "_doc": "time",
          "time": "00:00",
          "date": "01/07/24",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1719792000
        }
      }
    ],
    "2859": [
      {
        "_doc": "player",
        "_id": 94696,
        "name": "Bordalas, Pepe",
        "fullname": "Bordalas Jimenez, Jose",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "05/03/64",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": -183859200
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 199,
          "a2": "es",
          "name": "Spain",
          "a3": "ESP",
          "ioc": "ESP",
          "continentid": 1,
          "continent": "Europe",
          "population": 46000000
        },
        "primarypositiontype": null,
        "haslogo": false,
        "membersince": {
          "_doc": "time",
          "time": "00:00",
          "date": "29/04/23",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1682726400
        }
      }
    ]
  },
  "jersey": {
    "2846": {
      "base": "ffffff",
      "sleeve": "008000",
      "number": "0d0e06",
      "type": "short_sleeves",
      "sleevelong": "ffffff",
      "real": true
    },
    "2859": {
      "base": "063ba1",
      "sleeve": "ffd505",
      "number": "ffffff",
      "type": "short_sleeves",
      "sleevelong": "063ba1",
      "real": true
    }
  },
  "next": {
    "_doc": "match",
    "_doctype": "generic",
    "_id": 61624664,
    "_sid": 1,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "round": 37,
    "week": 20,
    "teams": {
      "home": {
        "_doc": "team",
        "_id": 6669997,
        "_sid": 1,
        "uid": 2846,
        "virtual": false,
        "name": "Elche",
        "mediumname": "Elche CF",
        "abbr": "ELC",
        "nickname": null,
        "iscountry": false
      },
      "away": {
        "_doc": "team",
        "_id": 368362,
        "_sid": 1,
        "uid": 2859,
        "virtual": false,
        "name": "Getafe",
        "mediumname": "Getafe CF",
        "abbr": "GET",
        "nickname": null,
        "iscountry": false
      }
    }
  }
}
```

### Tabla y standings

#### `stats_formtable`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 53.5 KB | max 53.5 KB | avg 53.5 KB
- queryUrl: stats_formtable/130805
- Match ids detectados: 61624638, 61624622, 61624612, 61624570, 61624580, 61624540, 61624500, 61624482, 61624438, 61624520
- Campos principales: matchtype, tabletype, season, winpoints, losspoints, currentround, teams
- Qué aporta: Tabla de forma reciente, muy útil para filtros pre-match.
- Estructura resumida:

```json
{
  "matchtype": [
    {
      "_doc": "matchtype",
      "_id": 1,
      "settypeid": 2,
      "column": "All matches"
    },
    {
      "_doc": "matchtype",
      "_id": 2,
      "settypeid": 4,
      "column": "Home matches"
    },
    {
      "_doc": "matchtype",
      "_id": 3,
      "settypeid": 6,
      "column": "Away matches"
    }
  ],
  "tabletype": [
    {
      "_doc": "tabletype",
      "_id": 1,
      "column": "Full Time"
    },
    {
      "_doc": "tabletype",
      "_id": 2,
      "column": "1st half"
    }
  ],
  "season": {
    "_id": "130805",
    "_doc": "season",
    "_utid": 8,
    "_sid": 1,
    "name": "LaLiga 25/26",
    "abbr": "L 25/26",
    "start": {
      "_doc": "time",
      "time": "00:00",
      "date": "15/08/25",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1755216000
    },
    "end": {
      "_doc": "time",
      "time": "23:59",
      "date": "24/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779667199
    },
    "neutralground": false,
    "friendly": false
  },
  "winpoints": 3,
  "losspoints": 0,
  "currentround": 36,
  "teams": [
    {
      "team": {
        "_doc": "team",
        "_id": 5198,
        "_sid": 1,
        "uid": 2817,
        "virtual": false,
        "name": "Barcelona",
        "mediumname": "FC Barcelona",
        "abbr": "BAR",
        "nickname": null,
        "iscountry": false
      },
      "position": {
        "total": 1,
        "home": 1,
        "away": 1
      },
      "played": {
        "total": 6,
        "totalhome": 3,
        "totalaway": 3,
        "home": 6,
        "away": 6
      },
      "win": {
        "total": 5,
        "totalhome": 3,
        "totalaway": 2,
        "home": 6,
        "away": 4
      },
      "draw": {
        "total": 0,
        "totalhome": 0,
        "totalaway": 0,
        "home": 0,
        "away": 0
      },
      "loss": {
        "total": 1,
        "totalhome": 0,
        "totalaway": 1,
        "home": 0,
        "away": 2
      },
      "goalsfor": {
        "total": 11,
        "totalhome": 7,
        "totalaway": 4,
        "home": 17,
        "away": 8
      },
      "goalsagainst": {
        "total": 3,
        "totalhome": 1,
        "totalaway": 2,
        "home": 4,
        "away": 5
      },
      "goaldifference": {
        "total": 8,
        "totalhome": 6,
        "totalaway": 2,
        "home": 13,
        "away": 3
      },
      "points": {
        "total": 15,
        "totalhome": 9,
        "totalaway": 6,
        "home": 18,
        "away": 12
      }
    },
    {
      "team": {
        "_doc": "team",
        "_id": 368361,
        "_sid": 1,
        "uid": 2849,
        "virtual": false,
        "name": "Levante",
        "mediumname": "Levante UD",
        "abbr": "LEV",
        "nickname": null,
        "iscountry": false
      },
      "position": {
        "total": 2,
        "home": 2,
        "away": 12
      },
      "played": {
        "total": 6,
        "totalhome": 3,
        "totalaway": 3,
        "home": 6,
        "away": 6
      },
      "win": {
        "total": 4,
        "totalhome": 3,
        "totalaway": 1,
        "home": 5,
        "away": 1
      },
      "draw": {
        "total": 1,
        "totalhome": 0,
        "totalaway": 1,
        "home": 1,
        "away": 2
      },
      "loss": {
        "total": 1,
        "totalhome": 0,
        "totalaway": 1,
        "home": 0,
        "away": 3
      },
      "goalsfor": {
        "total": 10,
        "totalhome": 6,
        "totalaway": 4,
        "home": 13,
        "away": 5
      },
      "goalsagainst": {
        "total": 9,
        "totalhome": 2,
        "totalaway": 7,
        "home": 5,
        "away": 13
      },
      "goaldifference": {
        "total": 1,
        "totalhome": 4,
        "totalaway": -3,
        "home": 8,
        "away": -8
      },
      "points": {
        "total": 13,
        "totalhome": 9,
        "totalaway": 4,
        "home": 16,
        "away": 5
      }
    },
    {
      "team": {
        "_doc": "team",
        "_id": 32608,
        "_sid": 1,
        "uid": 2816,
        "virtual": false,
        "name": "Real Betis",
        "mediumname": "Real Betis Seville",
        "abbr": "RBB",
        "nickname": null,
        "iscountry": false
      },
      "position": {
        "total": 3,
        "home": 10,
        "away": 5
      },
      "played": {
        "total": 6,
        "totalhome": 3,
        "totalaway": 3,
        "home": 6,
        "away": 6
      },
      "win": {
        "total": 3,
        "totalhome": 2,
        "totalaway": 1,
        "home": 2,
        "away": 2
      },
      "draw": {
        "total": 3,
        "totalhome": 1,
        "totalaway": 2,
        "home": 4,
        "away": 2
      },
      "loss": {
        "total": 0,
        "totalhome": 0,
        "totalaway": 0,
        "home": 0,
        "away": 2
      },
      "goalsfor": {
        "total": 12,
        "totalhome": 6,
        "totalaway": 6,
        "home": 9,
        "away": 9
      },
      "goalsagainst": {
        "total": 7,
        "totalhome": 2,
        "totalaway": 5,
        "home": 5,
        "away": 10
      },
      "goaldifference": {
        "total": 5,
        "totalhome": 4,
        "totalaway": 1,
        "home": 4,
        "away": -1
      },
      "points": {
        "total": 12,
        "totalhome": 7,
        "totalaway": 5,
        "home": 10,
        "away": 8
      }
    }
  ]
}
```

#### `stats_match_tableslice`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 2.9 KB | max 2.9 KB | avg 2.9 KB
- queryUrl: stats_match_tableslice/61624664
- Match ids detectados: 61624664
- Campos principales: _doc, _id, parenttableid, leaguetypeid, parenttableids, seasonid, maxrounds, currentround, presentationid, name, abbr, groupname
- Qué aporta: Slice de tabla alrededor del partido, útil para contexto competitivo.
- Estructura resumida:

```json
{
  "_doc": "statistics_leaguetable",
  "_id": "95812",
  "parenttableid": null,
  "leaguetypeid": null,
  "parenttableids": {},
  "seasonid": "130805",
  "maxrounds": 38,
  "currentround": 36,
  "presentationid": 0,
  "name": "LaLiga 25/26"
}
```

#### `stats_season_tables`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 21.4 KB | max 21.4 KB | avg 21.4 KB
- queryUrl: stats_season_tables/130805, stats_season_tables/130805/1
- Campos principales: _id, _doc, _utid, _sid, name, abbr, start, end, neutralground, friendly, currentseasonid, year
- Qué aporta: Tabla/standings completa de la temporada.
- Estructura resumida:

```json
{
  "_id": "130805",
  "_doc": "season",
  "_utid": 8,
  "_sid": 1,
  "name": "LaLiga 25/26",
  "abbr": "L 25/26",
  "start": {
    "_doc": "time",
    "time": "00:00",
    "date": "15/08/25",
    "tz": "UTC",
    "tzoffset": 0,
    "uts": 1755216000
  },
  "end": {
    "_doc": "time",
    "time": "23:59",
    "date": "24/05/26",
    "tz": "UTC",
    "tzoffset": 0,
    "uts": 1779667199
  },
  "neutralground": false,
  "friendly": false
}
```

### Jugadores y leaders

#### `stats_season_topassists`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 11.2 KB | max 11.3 KB | avg 11.2 KB
- queryUrl: stats_season_topassists/130805/2859, stats_season_topassists/130805/2846
- Campos principales: season, players, teams
- Qué aporta: Leaders de asistencias.
- Estructura resumida:

```json
{
  "season": {
    "_id": "130805",
    "_doc": "season",
    "_utid": 8,
    "_sid": 1,
    "name": "LaLiga 25/26",
    "abbr": "L 25/26",
    "start": {
      "_doc": "time",
      "time": "00:00",
      "date": "15/08/25",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1755216000
    },
    "end": {
      "_doc": "time",
      "time": "23:59",
      "date": "24/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779667199
    },
    "neutralground": false,
    "friendly": false
  },
  "players": [
    {
      "_doc": "toplistentry",
      "_id": 891594,
      "playerid": 891594,
      "player": {
        "_doc": "player",
        "_id": 891594,
        "name": "Milla, Luis",
        "fullname": "Milla Manzanares, Luis",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "07/10/94",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 781488000
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 199,
          "a2": "es",
          "name": "Spain",
          "a3": "ESP",
          "ioc": "ESP",
          "continentid": 1,
          "continent": "Europe",
          "population": 46000000
        },
        "position": {
          "_id": "6",
          "_type": "M",
          "name": "Midfielder",
          "shortname": "MID",
          "abbr": "M"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 5
      },
      "teams": {
        "2859": {
          "active": true,
          "lastevent": "2026-05-13 20:54:59",
          "started": 35,
          "matches": 35,
          "assists": 10,
          "minutes_played": 3097,
          "shirtnumber": "5"
        }
      },
      "total": {
        "matches": 35,
        "assists": 10,
        "minutes_played": 3097
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 1567050,
      "playerid": 1567050,
      "player": {
        "_doc": "player",
        "_id": 1567050,
        "name": "Abqar, Abdel",
        "fullname": "Abqar, Abdelkabir",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "10/03/99",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 921024000
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 144,
          "a2": "ma",
          "name": "Morocco",
          "a3": "MAR",
          "ioc": "MAR",
          "continentid": 4,
          "continent": "Africa",
          "population": 35740000
        },
        "position": {
          "_id": "4",
          "_type": "D",
          "name": "Defender",
          "shortname": "DEF",
          "abbr": "D"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 3
      },
      "teams": {
        "2859": {
          "active": true,
          "lastevent": "2026-05-10 18:04:48",
          "started": 16,
          "matches": 21,
          "assists": 2,
          "minutes_played": 1332,
          "substituted_in": 5,
          "shirtnumber": "3"
        }
      },
      "total": {
        "matches": 21,
        "assists": 2,
        "minutes_played": 1332,
        "substituted_in": 5
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 385888,
      "playerid": 385888,
      "player": {
        "_doc": "player",
        "_id": 385888,
        "name": "Arambarri, Mauro",
        "fullname": "Arambarri Rosa, Mauro Wilney",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "30/09/95",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 812419200
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 228,
          "a2": "uy",
          "name": "Uruguay",
          "a3": "URY",
          "ioc": "URU",
          "continentid": 3,
          "continent": "South America",
          "population": 3300000
        },
        "position": {
          "_id": "6",
          "_type": "M",
          "name": "Midfielder",
          "shortname": "MID",
          "abbr": "M"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 8
      },
      "teams": {
        "2859": {
          "active": true,
          "lastevent": "2026-05-13 19:07:32",
          "started": 35,
          "matches": 35,
          "assists": 2,
          "minutes_played": 3076,
          "shirtnumber": "8"
        }
      },
      "total": {
        "matches": 35,
        "assists": 2,
        "minutes_played": 3076
      }
    }
  ],
  "teams": {
    "2859": {
      "_doc": "uniqueteam",
      "_id": 2859,
      "_rcid": 32,
      "_sid": 1,
      "name": "Getafe",
      "mediumname": "Getafe CF",
      "suffix": null,
      "abbr": "GET",
      "nickname": null,
      "teamtypeid": 0
    }
  }
}
```

#### `stats_season_topcards`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 21.4 KB | max 23.8 KB | avg 22.6 KB
- queryUrl: stats_season_topcards/130805/2846, stats_season_topcards/130805/2859
- Campos principales: season, players, teams
- Qué aporta: Leaders de tarjetas.
- Estructura resumida:

```json
{
  "season": {
    "_id": "130805",
    "_doc": "season",
    "_utid": 8,
    "_sid": 1,
    "name": "LaLiga 25/26",
    "abbr": "L 25/26",
    "start": {
      "_doc": "time",
      "time": "00:00",
      "date": "15/08/25",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1755216000
    },
    "end": {
      "_doc": "time",
      "time": "23:59",
      "date": "24/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779667199
    },
    "neutralground": false,
    "friendly": false
  },
  "players": [
    {
      "_doc": "toplistentry",
      "_id": 1829298,
      "playerid": 1829298,
      "player": {
        "_doc": "player",
        "_id": 1829298,
        "name": "Affengruber, David",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "19/03/01",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 984960000
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 14,
          "a2": "at",
          "name": "Austria",
          "a3": "AUT",
          "ioc": "AUT",
          "continentid": 1,
          "continent": "Europe",
          "population": 8772000
        },
        "position": {
          "_id": "4",
          "_type": "D",
          "name": "Defender",
          "shortname": "DEF",
          "abbr": "D"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 22
      },
      "teams": {
        "2846": {
          "active": true,
          "lastevent": "2026-05-12 17:00:56",
          "started": 31,
          "yellow_cards": 6,
          "red_cards": 1,
          "matches": 34,
          "minutes_played": 2774,
          "substituted_in": 3,
          "number_of_cards_1st_half": 2,
          "number_of_cards_2nd_half": 5
        }
      },
      "total": {
        "yellow_cards": 6,
        "red_cards": 1,
        "matches": 34,
        "minutes_played": 2774,
        "substituted_in": 3,
        "number_of_cards_1st_half": 2,
        "number_of_cards_2nd_half": 5
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 1340428,
      "playerid": 1340428,
      "player": {
        "_doc": "player",
        "_id": 1340428,
        "name": "Valera, German",
        "fullname": "Valera Karabinaite, German",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "16/03/02",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1016236800
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 199,
          "a2": "es",
          "name": "Spain",
          "a3": "ESP",
          "ioc": "ESP",
          "continentid": 1,
          "continent": "Europe",
          "population": 46000000
        },
        "position": {
          "_id": "8",
          "_type": "F",
          "name": "Forward",
          "shortname": "FWD",
          "abbr": "F"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 11
      },
      "teams": {
        "2846": {
          "active": true,
          "lastevent": "2026-05-12 17:00:56",
          "started": 31,
          "yellow_cards": 3,
          "red_cards": 1,
          "matches": 34,
          "minutes_played": 2691,
          "substituted_in": 3,
          "number_of_cards_1st_half": 1,
          "number_of_cards_2nd_half": 3
        }
      },
      "total": {
        "yellow_cards": 3,
        "red_cards": 1,
        "matches": 34,
        "minutes_played": 2691,
        "substituted_in": 3,
        "number_of_cards_1st_half": 1,
        "number_of_cards_2nd_half": 3
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 941560,
      "playerid": 941560,
      "player": {
        "_doc": "player",
        "_id": 941560,
        "name": "Petrot, Leo",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "15/04/97",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 861062400
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 73,
          "a2": "fr",
          "name": "France",
          "a3": "FRA",
          "ioc": "FRA",
          "continentid": 1,
          "continent": "Europe",
          "population": 66000000
        },
        "position": {
          "_id": "4",
          "_type": "D",
          "name": "Defender",
          "shortname": "DEF",
          "abbr": "D"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 21
      },
      "teams": {
        "2846": {
          "active": true,
          "lastevent": "2026-05-12 19:13:24",
          "started": 18,
          "yellow_cards": 2,
          "red_cards": 1,
          "matches": 31,
          "minutes_played": 1566,
          "substituted_in": 13,
          "number_of_cards_2nd_half": 3,
          "shirtnumber": "21"
        }
      },
      "total": {
        "yellow_cards": 2,
        "red_cards": 1,
        "matches": 31,
        "minutes_played": 1566,
        "substituted_in": 13,
        "number_of_cards_2nd_half": 3
      }
    }
  ],
  "teams": {
    "2846": {
      "_doc": "uniqueteam",
      "_id": 2846,
      "_rcid": 32,
      "_sid": 1,
      "name": "Elche",
      "mediumname": "Elche CF",
      "suffix": null,
      "abbr": "ELC",
      "nickname": null,
      "teamtypeid": 0
    }
  }
}
```

#### `stats_season_topgoals`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 12.0 KB | max 17.4 KB | avg 14.7 KB
- queryUrl: stats_season_topgoals/130805/2846, stats_season_topgoals/130805/2859
- Campos principales: season, players, teams
- Qué aporta: Top scorers de la temporada.
- Estructura resumida:

```json
{
  "season": {
    "_id": "130805",
    "_doc": "season",
    "_utid": 8,
    "_sid": 1,
    "name": "LaLiga 25/26",
    "abbr": "L 25/26",
    "start": {
      "_doc": "time",
      "time": "00:00",
      "date": "15/08/25",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1755216000
    },
    "end": {
      "_doc": "time",
      "time": "23:59",
      "date": "24/05/26",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 1779667199
    },
    "neutralground": false,
    "friendly": false
  },
  "players": [
    {
      "_doc": "toplistentry",
      "_id": 190159,
      "playerid": 190159,
      "player": {
        "_doc": "player",
        "_id": 190159,
        "name": "Silva, Andre",
        "fullname": "Valente Silva, Andre Miguel",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "06/11/95",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 815616000
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 172,
          "a2": "pt",
          "name": "Portugal",
          "a3": "PRT",
          "ioc": "POR",
          "continentid": 1,
          "continent": "Europe",
          "population": 10600000
        },
        "position": {
          "_id": "8",
          "_type": "F",
          "name": "Forward",
          "shortname": "FWD",
          "abbr": "F"
        },
        "primarypositiontype": null,
        "haslogo": true,
        "jerseynumber": 9
      },
      "teams": {
        "2846": {
          "active": true,
          "lastevent": "2026-05-12 19:27:30",
          "started": 21,
          "goals": 10,
          "matches": 29,
          "penalties": 3,
          "goal_points": 10,
          "minutes_played": 1774,
          "substituted_in": 8,
          "first_goals": 2
        }
      },
      "total": {
        "goals": 10,
        "matches": 29,
        "penalties": 3,
        "goal_points": 10,
        "minutes_played": 1774,
        "substituted_in": 8,
        "first_goals": 2,
        "last_goals": 3
      },
      "home": {
        "goals": 4
      },
      "away": {
        "goals": 6
      },
      "firsthalf": {
        "goals": 4
      },
      "secondhalf": {
        "goals": 6
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 933416,
      "playerid": 933416,
      "player": {
        "_doc": "player",
        "_id": 933416,
        "name": "Mir, Rafa",
        "fullname": "Mir Vicente, Rafael",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "18/06/97",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 866592000
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 199,
          "a2": "es",
          "name": "Spain",
          "a3": "ESP",
          "ioc": "ESP",
          "continentid": 1,
          "continent": "Europe",
          "population": 46000000
        },
        "position": {
          "_id": "8",
          "_type": "F",
          "name": "Forward",
          "shortname": "FWD",
          "abbr": "F"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 9
      },
      "teams": {
        "2846": {
          "active": true,
          "lastevent": "2026-04-22 18:32:41",
          "started": 21,
          "goals": 8,
          "matches": 27,
          "penalties": 1,
          "goal_points": 8,
          "minutes_played": 1810,
          "substituted_in": 6,
          "first_goals": 1
        }
      },
      "total": {
        "goals": 8,
        "matches": 27,
        "penalties": 1,
        "goal_points": 8,
        "minutes_played": 1810,
        "substituted_in": 6,
        "first_goals": 1,
        "last_goals": 3
      },
      "home": {
        "goals": 5
      },
      "away": {
        "goals": 3
      },
      "firsthalf": {
        "goals": 2
      },
      "secondhalf": {
        "goals": 6
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 2266525,
      "playerid": 2266525,
      "player": {
        "_doc": "player",
        "_id": 2266525,
        "name": "Rodriguez, Alvaro",
        "fullname": "Rodriguez Munoz, Alvaro Daniel",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "14/07/04",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1089763200
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 228,
          "a2": "uy",
          "name": "Uruguay",
          "a3": "URY",
          "ioc": "URU",
          "continentid": 3,
          "continent": "South America",
          "population": 3300000
        },
        "position": {
          "_id": "8",
          "_type": "F",
          "name": "Forward",
          "shortname": "FWD",
          "abbr": "F"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 20
      },
      "teams": {
        "2846": {
          "active": true,
          "lastevent": "2026-05-12 19:27:30",
          "started": 22,
          "goals": 6,
          "matches": 32,
          "goal_points": 11,
          "minutes_played": 2037,
          "substituted_in": 10,
          "first_goals": 2,
          "last_goals": 1
        }
      },
      "total": {
        "goals": 6,
        "matches": 32,
        "goal_points": 11,
        "minutes_played": 2037,
        "substituted_in": 10,
        "first_goals": 2,
        "last_goals": 1
      },
      "home": {
        "goals": 5
      },
      "away": {
        "goals": 1
      },
      "firsthalf": {
        "goals": 2
      },
      "secondhalf": {
        "goals": 4
      }
    }
  ],
  "teams": {
    "2846": {
      "_doc": "uniqueteam",
      "_id": 2846,
      "_rcid": 32,
      "_sid": 1,
      "name": "Elche",
      "mediumname": "Elche CF",
      "suffix": null,
      "abbr": "ELC",
      "nickname": null,
      "teamtypeid": 0
    }
  }
}
```

### Lesiones

#### `stats_season_injuries`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 59.4 KB | max 59.4 KB | avg 59.4 KB
- queryUrl: stats_season_injuries/130805
- Campos principales: _doc, _id, _tid, _playerid, status, player, uniqueteam
- Qué aporta: Listado de lesionados / ausentes por equipo y jugador.
- Estructura resumida:

```json
[
  {
    "_doc": "playerstatus",
    "_id": 589361,
    "_tid": 0,
    "_playerid": 83708,
    "status": {
      "_id": 1,
      "_statusid": 1,
      "status": "Missing",
      "name": "Injured",
      "comment": "",
      "missing": 1,
      "doubtful": 0,
      "start": {
        "_doc": "time",
        "time": "00:00",
        "date": "20/09/25",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1758326400
      },
      "end": null
    },
    "player": {
      "_doc": "player",
      "_id": 83708,
      "name": "Carlos, Juan",
      "fullname": "Martin Corral, Juan Carlos",
      "birthdate": {
        "_doc": "time",
        "time": "00:00",
        "date": "20/01/88",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 569635200
      },
      "nationality": {
        "_doc": "countrycode",
        "_id": 199,
        "a2": "es",
        "name": "Spain",
        "a3": "ESP",
        "ioc": "ESP",
        "continentid": 1,
        "continent": "Europe",
        "population": 46000000
      },
      "position": {
        "_id": "2",
        "_type": "G",
        "name": "Goalkeeper",
        "shortname": "GK",
        "abbr": "G"
      },
      "primarypositiontype": null,
      "haslogo": false,
      "shirtnumber": "0"
    },
    "uniqueteam": {
      "_doc": "uniqueteam",
      "_id": 24264,
      "_rcid": 32,
      "_sid": 1,
      "name": "Girona",
      "mediumname": "Girona FC",
      "suffix": null,
      "abbr": "GIR",
      "nickname": null,
      "teamtypeid": 0
    }
  },
  {
    "_doc": "playerstatus",
    "_id": 591269,
    "_tid": 18,
    "_playerid": 2303541,
    "status": {
      "_id": 0,
      "_statusid": 1,
      "status": "Missing",
      "name": "Other",
      "comment": "",
      "missing": 1,
      "doubtful": 0,
      "start": {
        "_doc": "time",
        "time": "00:00",
        "date": "12/10/25",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1760227200
      },
      "end": null
    },
    "player": {
      "_doc": "player",
      "_id": 2303541,
      "name": "Freeman, Alex",
      "fullname": "Freeman, Alexander Michael",
      "birthdate": {
        "_doc": "time",
        "time": "00:00",
        "date": "09/08/04",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1092009600
      },
      "nationality": {
        "_doc": "countrycode",
        "_id": 226,
        "a2": "us",
        "name": "USA",
        "a3": "USA",
        "ioc": "USA",
        "continentid": 2,
        "continent": "North America",
        "population": 320000000
      },
      "position": {
        "_id": "4",
        "_type": "D",
        "name": "Defender",
        "shortname": "DEF",
        "abbr": "D"
      },
      "primarypositiontype": null,
      "haslogo": false,
      "shirtnumber": "3"
    },
    "uniqueteam": {
      "_doc": "uniqueteam",
      "_id": 2819,
      "_rcid": 32,
      "_sid": 1,
      "name": "Villarreal",
      "mediumname": "Villarreal CF",
      "suffix": null,
      "abbr": "VIL",
      "nickname": null,
      "teamtypeid": 0
    }
  },
  {
    "_doc": "playerstatus",
    "_id": 591365,
    "_tid": 18,
    "_playerid": 2187596,
    "status": {
      "_id": 0,
      "_statusid": 1,
      "status": "Missing",
      "name": "Other",
      "comment": "",
      "missing": 1,
      "doubtful": 0,
      "start": {
        "_doc": "time",
        "time": "00:00",
        "date": "12/10/25",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1760227200
      },
      "end": null
    },
    "player": {
      "_doc": "player",
      "_id": 2187596,
      "name": "Vargas, Obed",
      "fullname": "Vargas, Obed Gomez",
      "birthdate": {
        "_doc": "time",
        "time": "00:00",
        "date": "05/08/05",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1123200000
      },
      "nationality": {
        "_doc": "countrycode",
        "_id": 138,
        "a2": "mx",
        "name": "Mexico",
        "a3": "MEX",
        "ioc": "MEX",
        "continentid": 2,
        "continent": "North America",
        "population": 107500000
      },
      "position": {
        "_id": "6",
        "_type": "M",
        "name": "Midfielder",
        "shortname": "MID",
        "abbr": "M"
      },
      "primarypositiontype": null,
      "haslogo": false,
      "shirtnumber": "21"
    },
    "uniqueteam": {
      "_doc": "uniqueteam",
      "_id": 2836,
      "_rcid": 32,
      "_sid": 1,
      "name": "Atletico",
      "mediumname": "Atletico Madrid",
      "suffix": null,
      "abbr": "ATM",
      "nickname": null,
      "teamtypeid": 0
    }
  }
]
```

### Mercados y odds

#### `match_markets`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 6.5 KB | max 6.5 KB | avg 6.5 KB
- queryUrl: match_markets/61624664
- Campos principales: markets
- Qué aporta: Mercados y odds del partido por HTTP; hoy es el hallazgo más fuerte del lado odds.
- Estructura resumida:

```json
{
  "markets": [
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624664,
      "_marketId": 1,
      "_uts": 1778783392,
      "specifiers": null,
      "name": "1x2",
      "nameShort": "1x2",
      "active": true,
      "type": "prematch"
    },
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624664,
      "_marketId": 10,
      "_uts": 1778783420,
      "specifiers": null,
      "name": "Double chance",
      "nameShort": "Double chance",
      "active": true,
      "type": "prematch"
    },
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624664,
      "_marketId": 11,
      "_uts": 1778854936,
      "specifiers": null,
      "name": "Draw no bet",
      "nameShort": "Draw no bet",
      "active": true,
      "type": "prematch"
    }
  ]
}
```

#### `odds_ukformat`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 9.6 KB | max 9.6 KB | avg 9.6 KB
- queryUrl: odds_ukformat/
- Campos principales: dec, frac
- Qué aporta: Tabla auxiliar de formatos de cuotas; parece soporte más que feed principal.
- Estructura resumida:

```json
[
  {
    "dec": 1.00001,
    "frac": "1/100000"
  },
  {
    "dec": 1.000013,
    "frac": "1/80000"
  },
  {
    "dec": 1.000015,
    "frac": "1/66000"
  }
]
```

#### `uniqueteam_markets`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 299.5 KB | max 301.0 KB | avg 300.2 KB
- queryUrl: uniqueteam_markets/2846, uniqueteam_markets/2859
- Campos principales: matches
- Qué aporta: Mercados por equipo sobre matches relacionados, útil para análisis complementario.
- Estructura resumida:

```json
{
  "matches": {
    "51103793": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103793,
          "_marketId": 1,
          "_uts": 1747498491,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103793,
          "_marketId": 10,
          "_uts": 1747498449,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103793,
          "_marketId": 11,
          "_uts": 1747498449,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "51103801": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103801,
          "_marketId": 1,
          "_uts": 1748185008,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103801,
          "_marketId": 10,
          "_uts": 1748185089,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103801,
          "_marketId": 11,
          "_uts": 1748185089,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "51103823": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103823,
          "_marketId": 1,
          "_uts": 1748795340,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103823,
          "_marketId": 10,
          "_uts": 1748795049,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103823,
          "_marketId": 11,
          "_uts": 1748795169,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61623430": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623430,
          "_marketId": 1,
          "_uts": 1755528730,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623430,
          "_marketId": 10,
          "_uts": 1755534369,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623430,
          "_marketId": 11,
          "_uts": 1755535209,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61623960": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623960,
          "_marketId": 1,
          "_uts": 1755967199,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623960,
          "_marketId": 10,
          "_uts": 1755967089,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623960,
          "_marketId": 11,
          "_uts": 1755967089,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61623982": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623982,
          "_marketId": 1,
          "_uts": 1756488299,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623982,
          "_marketId": 10,
          "_uts": 1756488299,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623982,
          "_marketId": 11,
          "_uts": 1756485308,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61624014": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624014,
          "_marketId": 1,
          "_uts": 1757707182,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624014,
          "_marketId": 10,
          "_uts": 1757707185,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624014,
          "_marketId": 11,
          "_uts": 1757707185,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": false,
          "type": "prematch"
        }
      ]
    },
    "61624024": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624024,
          "_marketId": 1,
          "_uts": 1758470694,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624024,
          "_marketId": 10,
          "_uts": 1758460251,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624024,
          "_marketId": 11,
          "_uts": 1758460251,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": false,
          "type": "prematch"
        }
      ]
    },
    "61624054": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624054,
          "_marketId": 1,
          "_uts": 1758821362,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624054,
          "_marketId": 10,
          "_uts": 1758821262,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624054,
          "_marketId": 11,
          "_uts": 1758821364,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61624072": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624072,
          "_marketId": 1,
          "_uts": 1759036624,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624072,
          "_marketId": 10,
          "_uts": 1759068429,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624072,
          "_marketId": 11,
          "_uts": 1759067826,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    }
  }
}
```

## Endpoints de Baja Prioridad

- `odds_ukformat` aparece en la captura, pero por ahora parece más un helper o tabla auxiliar que un feed principal para BetBot.

## Datos Útiles Detectados

- Metadata del partido: sí.
- Señales live / status / timeline: sí.
- Odds / mercados por HTTP: sí, con `match_markets`.
- Tabla / standings / forma: sí.
- Leaders de jugadores: sí.
- Lesiones: sí.

## Datos que No Aparecieron Claramente

- No apareció un endpoint dedicado de lineups detalladas en esta muestra.
- No apareció win probability explícita.
- Corners, shots, possession y cards live no quedaron confirmados en el match abierto; probablemente haga falta una captura con el partido realmente en vivo.

## Recomendación para BetBot

- Sí conviene seguir por este camino: `match_markets` ya demuestra que hay odds/markets útiles por HTTP sin scraping DOM.
- Para un futuro tracker `in live`, los mejores candidatos son `match_timeline` y `match_timelinedelta`, idealmente validados en un partido efectivamente en juego.
- `event_get` merece investigación aparte: podría ser un feed live global complementario, pero no conviene integrarlo sin validar su scope.
- Los endpoints de contexto (tabla, forma, lesiones, leaders) son buenos candidatos para enriquecer un futuro agente de análisis o filtros de partidos interesantes.
- Próximo paso recomendado: repetir el mismo pipeline con una captura de partido en vivo para confirmar score, clock, timeline real, cards/corners/shots y estabilidad de polling.
