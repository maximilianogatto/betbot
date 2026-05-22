# Sportradar Stats Filtered Endpoint Report

- Capture dir: `/Users/maximilianogatto/Library/CloudStorage/OneDrive-Personal/Apuestas/BetBot/sandbox/sportradar_stats/captures/realsociedad_valencia_full`
- Source usado: `filtered_fetch.ndjson`
- Responses útiles filtradas: 32
- Endpoints limpios detectados: 21

## Resumen Ejecutivo

- `match_markets` expone mercados/odds por HTTP. En esta captura devolvió 11 markets, incluyendo 1X2 y handicaps.
- `match_timeline` / `match_timelinedelta` son los candidatos más fuertes para detectar `live`, score, estado y timeline. Ambos usan `_maxage` corto.
- `event_get` parece un feed live global y no necesariamente del partido abierto: en esta captura apunta a match id(s) 71001364, 70813618, 71411170, 69767366, 71411252, mientras el match principal fue 61624670.
- Hay buen contexto pre-match por HTTP: forma reciente, tabla, streaks, head-to-head y slices de standings.
- También aparecen endpoints útiles para enriquecer análisis: lesiones y leaders de goles, tarjetas y asistencias.

## Endpoints Detectados

| Endpoint | Hits | Polling | Tamaño aprox. | Categorías |
| --- | ---: | :---: | ---: | --- |
| `stats_team_lastx` | 3 | Sí | 20.7 KB | Stats pre-match y contexto, Forma reciente |
| `stats_team_nextx` | 3 | Sí | 2.6 KB | Stats pre-match y contexto, Forma reciente |
| `stats_season_tables` | 2 | Sí | 21.4 KB | Tabla y standings |
| `stats_season_teamscoringconceding` | 2 | Sí | 3.5 KB | Stats pre-match y contexto |
| `stats_season_topassists` | 2 | Sí | 10.5 KB | Jugadores y leaders |
| `stats_season_topcards` | 2 | Sí | 20.7 KB | Jugadores y leaders |
| `stats_season_topgoals` | 2 | Sí | 13.5 KB | Jugadores y leaders |
| `stats_team_streaks` | 2 | Sí | 2.2 KB | Stats pre-match y contexto, Forma reciente |
| `uniqueteam_markets` | 2 | Sí | 313.3 KB | Mercados y odds |
| `event_get` | 1 | Sí | 391.0 KB | Score y estado live, Timeline y eventos live |
| `match_details` | 1 | Sí | 113.0 B | Metadata del partido |
| `match_info_statshub` | 1 | No | 7.2 KB | Metadata del partido |
| `match_markets` | 1 | No | 6.5 KB | Mercados y odds |
| `match_timeline` | 1 | Sí | 2.4 KB | Score y estado live, Timeline y eventos live |
| `match_timelinedelta` | 1 | Sí | 2.4 KB | Score y estado live, Timeline y eventos live |
| `odds_ukformat` | 1 | No | 9.6 KB | Mercados y odds |
| `stats_formtable` | 1 | No | 53.5 KB | Forma reciente, Tabla y standings |
| `stats_h2h_versus` | 1 | Sí | 20.0 KB | Stats pre-match y contexto |
| `stats_match_get` | 1 | No | 5.9 KB | Metadata del partido, Score y estado live |
| `stats_season_injuries` | 1 | No | 58.3 KB | Lesiones |
| `stats_team_versus` | 1 | No | 100.5 KB | Stats pre-match y contexto, Forma reciente |

## Endpoints por Caso de Uso

### Metadata del partido

#### `match_details`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage)
- Tamaño aprox.: min 113.0 B | max 113.0 B | avg 113.0 B
- queryUrl: match_details/61624670
- Qué aporta: Detalle auxiliar del match; en esta muestra vino vacío.
- Estructura resumida:

```json
[]
```

#### `match_info_statshub`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 7.2 KB | max 7.2 KB | avg 7.2 KB
- queryUrl: match_info_statshub/61624670
- Match ids detectados: 61624670
- Campos principales: _doc, match, cities, stadium, tournament, uniquetournament, sport, realcategory, season, referee, manager, jerseys
- Qué aporta: Metadata fuerte del partido: torneo, estadio, ciudades, coverage y contexto del evento.
- Estructura resumida:

```json
{
  "_doc": "match_info",
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624670,
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
      "_id": 51,
      "name": "San Sebastian"
    },
    "away": {
      "_id": 74,
      "name": "Valencia"
    }
  },
  "stadium": {
    "_doc": "stadium",
    "_id": "581",
    "name": "Reale Arena",
    "description": "",
    "city": "San Sebastian",
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
    "capacity": "32000",
    "hometeams": [
      {
        "_doc": "uniqueteam",
        "_id": 2824,
        "_rcid": 32,
        "_sid": 1,
        "name": "Real Sociedad",
        "mediumname": "Real Sociedad San Sebastian",
        "suffix": null,
        "abbr": "RSO",
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
  "referee": {
    "_doc": "player",
    "_id": 179011,
    "name": "Galech Apezteguia, Iosu",
    "birthdate": {
      "_doc": "time",
      "time": "00:00",
      "date": "12/12/90",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 660960000
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
    "haslogo": false
  }
}
```

#### `stats_match_get`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 5.9 KB | max 5.9 KB | avg 5.9 KB
- queryUrl: stats_match_get/61624670
- Match ids detectados: 61624670
- Campos principales: _doc, _doctype, _id, _sid, _rcid, _tid, _utid, round, week, teams, tobeannounced, postponed
- Qué aporta: Snapshot del match con ids, hora, equipos, resultado y señales de live/inlivescore.
- Estructura resumida:

```json
{
  "_doc": "match",
  "_doctype": "generic",
  "_id": 61624670,
  "_sid": 1,
  "_rcid": 32,
  "_tid": 36,
  "_utid": 8,
  "round": 37,
  "week": 20,
  "teams": {
    "home": {
      "_doc": "team",
      "_id": 5134,
      "_sid": 1,
      "uid": 2824,
      "virtual": false,
      "name": "Real Sociedad",
      "mediumname": "Real Sociedad San Sebastian",
      "abbr": "RSO",
      "nickname": null,
      "iscountry": false
    },
    "away": {
      "_doc": "team",
      "_id": 5197,
      "_sid": 1,
      "uid": 2828,
      "virtual": false,
      "name": "Valencia",
      "mediumname": "Valencia CF",
      "abbr": "VCF",
      "nickname": null,
      "iscountry": false
    }
  }
}
```

### Score y estado live

#### `event_get`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 391.0 KB | max 391.0 KB | avg 391.0 KB
- queryUrl: event_get/
- Match ids detectados: 71001364, 70813618, 71411170, 69767366, 71411252, 71411258, 71411178, 71411162, 67694248, 71411804
- Campos principales: _doc, _doctype, _id, _scoutid, _sid, _rcid, _tid, _dc, _typeid, uts, updated_uts, type
- Qué aporta: Feed de eventos live que parece más global; hay que validar alcance exacto en más capturas.
- Estructura resumida:

```json
[
  {
    "_doc": "event",
    "_doctype": "cricketcurrentstatusevent",
    "_id": 2360424892,
    "_scoutid": null,
    "_sid": 21,
    "_rcid": 105,
    "_tid": 107534,
    "_dc": false,
    "_typeid": "1705",
    "uts": 1778904027
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "70813618-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 339,
    "_tid": 174781,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778999464
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "71411170-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 2123,
    "_tid": 93577,
    "_dc": false,
    "_typeid": "22",
    "uts": 1779000268
  }
]
```

#### `match_timeline`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 2.4 KB | max 2.4 KB | avg 2.4 KB
- queryUrl: match_timeline/61624670
- Match ids detectados: 61624670
- Campos principales: match, events
- Qué aporta: Estado del partido y timeline principal. Es el candidato más claro para live state del fixture abierto.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624670,
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
- queryUrl: match_timelinedelta/61624670
- Match ids detectados: 61624670
- Campos principales: match, events
- Qué aporta: Delta del timeline, ideal para polling liviano cuando el partido está en vivo.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624670,
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
- Tamaño aprox.: min 5.9 KB | max 5.9 KB | avg 5.9 KB
- queryUrl: stats_match_get/61624670
- Match ids detectados: 61624670
- Campos principales: _doc, _doctype, _id, _sid, _rcid, _tid, _utid, round, week, teams, tobeannounced, postponed
- Qué aporta: Snapshot del match con ids, hora, equipos, resultado y señales de live/inlivescore.
- Estructura resumida:

```json
{
  "_doc": "match",
  "_doctype": "generic",
  "_id": 61624670,
  "_sid": 1,
  "_rcid": 32,
  "_tid": 36,
  "_utid": 8,
  "round": 37,
  "week": 20,
  "teams": {
    "home": {
      "_doc": "team",
      "_id": 5134,
      "_sid": 1,
      "uid": 2824,
      "virtual": false,
      "name": "Real Sociedad",
      "mediumname": "Real Sociedad San Sebastian",
      "abbr": "RSO",
      "nickname": null,
      "iscountry": false
    },
    "away": {
      "_doc": "team",
      "_id": 5197,
      "_sid": 1,
      "uid": 2828,
      "virtual": false,
      "name": "Valencia",
      "mediumname": "Valencia CF",
      "abbr": "VCF",
      "nickname": null,
      "iscountry": false
    }
  }
}
```

### Timeline y eventos live

#### `event_get`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 391.0 KB | max 391.0 KB | avg 391.0 KB
- queryUrl: event_get/
- Match ids detectados: 71001364, 70813618, 71411170, 69767366, 71411252, 71411258, 71411178, 71411162, 67694248, 71411804
- Campos principales: _doc, _doctype, _id, _scoutid, _sid, _rcid, _tid, _dc, _typeid, uts, updated_uts, type
- Qué aporta: Feed de eventos live que parece más global; hay que validar alcance exacto en más capturas.
- Estructura resumida:

```json
[
  {
    "_doc": "event",
    "_doctype": "cricketcurrentstatusevent",
    "_id": 2360424892,
    "_scoutid": null,
    "_sid": 21,
    "_rcid": 105,
    "_tid": 107534,
    "_dc": false,
    "_typeid": "1705",
    "uts": 1778904027
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "70813618-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 339,
    "_tid": 174781,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778999464
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "71411170-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 2123,
    "_tid": 93577,
    "_dc": false,
    "_typeid": "22",
    "uts": 1779000268
  }
]
```

#### `match_timeline`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 2.4 KB | max 2.4 KB | avg 2.4 KB
- queryUrl: match_timeline/61624670
- Match ids detectados: 61624670
- Campos principales: match, events
- Qué aporta: Estado del partido y timeline principal. Es el candidato más claro para live state del fixture abierto.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624670,
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
- queryUrl: match_timelinedelta/61624670
- Match ids detectados: 61624670
- Campos principales: match, events
- Qué aporta: Delta del timeline, ideal para polling liviano cuando el partido está en vivo.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624670,
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
- Tamaño aprox.: min 20.0 KB | max 20.0 KB | avg 20.0 KB
- queryUrl: stats_h2h_versus/2824/2828/61624670
- Match ids detectados: 61624670, 50852227, 2834599, 363879, 366287
- Campos principales: match, lastmatchesbetweenteams, lastmatchesbetweenteamsonvenue, versusmatchstats
- Qué aporta: Historial comparativo y versus stats entre ambos equipos.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624670,
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
      "_id": 61623440,
      "result": {
        "home": 1,
        "away": 1,
        "period": "nt",
        "winner": null
      },
      "time": {
        "_doc": "time",
        "time": "19:30",
        "date": "16/08/25",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1755372600
      },
      "homeuniqueteamid": 2828,
      "awayuniqueteamid": 2824,
      "periods": {
        "ft": {
          "home": 1,
          "away": 1
        },
        "p1": {
          "home": 0,
          "away": 0
        }
      },
      "round": 1,
      "roundname": {
        "_doc": "tableround",
        "_id": 1,
        "name": 1
      },
      "_seasonid": 130805
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 50852475,
      "result": {
        "home": 1,
        "away": 0,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "20:00",
        "date": "19/01/25",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1737316800
      },
      "homeuniqueteamid": 2828,
      "awayuniqueteamid": 2824,
      "periods": {
        "ft": {
          "home": 1,
          "away": 0
        },
        "p1": {
          "home": 1,
          "away": 0
        }
      },
      "round": 20,
      "roundname": {
        "_doc": "tableround",
        "_id": 20,
        "name": 20
      },
      "_seasonid": 118691
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 50852227,
      "result": {
        "home": 3,
        "away": 0,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "16:30",
        "date": "28/09/24",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1727541000
      },
      "homeuniqueteamid": 2824,
      "awayuniqueteamid": 2828,
      "periods": {
        "ft": {
          "home": 3,
          "away": 0
        },
        "p1": {
          "home": 1,
          "away": 0
        }
      },
      "round": 8,
      "roundname": {
        "_doc": "tableround",
        "_id": 8,
        "name": 8
      },
      "_seasonid": 118691
    }
  ],
  "lastmatchesbetweenteamsonvenue": [
    {
      "_doc": "match_h2h_simple",
      "_id": 50852227,
      "result": {
        "home": 3,
        "away": 0,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "16:30",
        "date": "28/09/24",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1727541000
      },
      "homeuniqueteamid": 2824,
      "awayuniqueteamid": 2828,
      "periods": {
        "ft": {
          "home": 3,
          "away": 0
        },
        "p1": {
          "home": 1,
          "away": 0
        }
      },
      "round": 8,
      "roundname": {
        "_doc": "tableround",
        "_id": 8,
        "name": 8
      },
      "_seasonid": 118691
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 41893613,
      "result": {
        "home": 1,
        "away": 0,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "20:00",
        "date": "16/05/24",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1715889600
      },
      "homeuniqueteamid": 2824,
      "awayuniqueteamid": 2828,
      "periods": {
        "ft": {
          "home": 1,
          "away": 0
        },
        "p1": {
          "home": 1,
          "away": 0
        }
      },
      "round": 36,
      "roundname": {
        "_doc": "tableround",
        "_id": 36,
        "name": 36
      },
      "_seasonid": 106501
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 34277445,
      "result": {
        "home": 1,
        "away": 1,
        "period": "nt",
        "winner": null
      },
      "time": {
        "_doc": "time",
        "time": "15:15",
        "date": "06/11/22",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1667747700
      },
      "homeuniqueteamid": 2824,
      "awayuniqueteamid": 2828,
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
      "round": 13,
      "roundname": {
        "_doc": "tableround",
        "_id": 13,
        "name": 13
      },
      "_seasonid": 94215
    }
  ],
  "versusmatchstats": {
    "2824": {
      "highestwin": {
        "total": {
          "home": 3,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 3,
          "matchid": 50852227,
          "matchuts": 1727541000
        },
        "home": {
          "home": 3,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 3,
          "matchid": 50852227,
          "matchuts": 1727541000
        },
        "away": {
          "home": 2,
          "away": 5,
          "period": "nt",
          "winner": "away",
          "goaldiff": 3,
          "matchid": 2834599,
          "matchuts": 1354381200
        }
      },
      "totalmatches": {
        "total": 59,
        "home": 29,
        "away": 30
      },
      "teamwins": {
        "total": 18,
        "home": 10,
        "away": 8
      },
      "teamloses": {
        "total": 22,
        "home": 9,
        "away": 13
      },
      "teamdraws": {
        "total": 19,
        "home": 10,
        "away": 9
      },
      "oldestmatchdate": "1993",
      "totalgoals": {
        "total": 71,
        "home": 38,
        "away": 33
      },
      "averagegoals": {
        "total": 1.2033898305084745,
        "home": 1.3103448275862069,
        "away": 1.1
      },
      "leadingathalftime": {
        "total": 12,
        "home": 7,
        "away": 5
      },
      "losingathalftime": {
        "total": 13,
        "home": 3,
        "away": 10
      }
    },
    "2828": {
      "highestwin": {
        "total": {
          "home": 4,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 4,
          "matchid": 363879,
          "matchuts": 1018195200
        },
        "home": {
          "home": 4,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 4,
          "matchid": 363879,
          "matchuts": 1018195200
        },
        "away": {
          "home": 0,
          "away": 2,
          "period": "nt",
          "winner": "away",
          "goaldiff": 2,
          "matchid": 366287,
          "matchuts": 780512400
        }
      },
      "totalmatches": {
        "total": 59,
        "home": 30,
        "away": 29
      },
      "teamwins": {
        "total": 22,
        "home": 13,
        "away": 9
      },
      "teamloses": {
        "total": 18,
        "home": 8,
        "away": 10
      },
      "teamdraws": {
        "total": 19,
        "home": 9,
        "away": 10
      },
      "oldestmatchdate": "1993",
      "totalgoals": {
        "total": 78,
        "home": 49,
        "away": 29
      },
      "averagegoals": {
        "total": 1.3220338983050848,
        "home": 1.6333333333333333,
        "away": 1
      },
      "leadingathalftime": {
        "total": 13,
        "home": 10,
        "away": 3
      },
      "losingathalftime": {
        "total": 12,
        "home": 5,
        "away": 7
      }
    }
  }
}
```

#### `stats_season_teamscoringconceding`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 3.5 KB | max 3.5 KB | avg 3.5 KB
- queryUrl: stats_season_teamscoringconceding/130805/2824/-1, stats_season_teamscoringconceding/130805/2828/-1
- Campos principales: team, stats
- Qué aporta: Distribución de goles anotados/recibidos por equipo y temporada.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2824,
    "_rcid": 32,
    "_sid": 1,
    "name": "Real Sociedad",
    "mediumname": "Real Sociedad San Sebastian",
    "suffix": null,
    "abbr": "RSO",
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
      "total": 11,
      "home": 8,
      "away": 3
    },
    "scoring": {
      "goalsscored": {
        "total": 55,
        "home": 34,
        "away": 21
      },
      "atleastonegoal": {
        "total": 36,
        "home": 18,
        "away": 18
      },
      "failedtoscore": {
        "total": 5,
        "home": 2,
        "away": 3
      },
      "scoringathalftime": {
        "total": 19,
        "home": 9,
        "away": 10
      },
      "scoringatfulltime": {
        "total": 31,
        "home": 16,
        "away": 15
      },
      "bothteamsscored": {
        "total": 28,
        "home": 14,
        "away": 14
      },
      "goalsscoredfirsthalf": {
        "total": 23,
        "home": 13,
        "away": 10
      },
      "goalsscoredaverage": {
        "total": 1.5277777777777777,
        "home": 1.8888888888888888,
        "away": 1.1666666666666667
      },
      "atleastonegoalaverage": {
        "total": 1,
        "home": 1,
        "away": 1
      },
      "failedtoscoreaverage": {
        "total": 0.1388888888888889,
        "home": 0.1111111111111111,
        "away": 0.16666666666666666
      }
    },
    "conceding": {
      "goalsconceded": {
        "total": 56,
        "home": 27,
        "away": 29
      },
      "cleansheets": {
        "total": 3,
        "home": 2,
        "away": 1
      },
      "goalsconcededfirsthalf": {
        "total": 26,
        "home": 12,
        "away": 14
      },
      "goalsconcededaverage": {
        "total": 1.5555555555555556,
        "home": 1.5,
        "away": 1.6111111111111112
      },
      "cleansheetsaverage": {
        "total": 0.08333333333333333,
        "home": 0.1111111111111111,
        "away": 0.05555555555555555
      },
      "goalsconcededfirsthalfaverage": {
        "total": 0.7222222222222222,
        "home": 0.6666666666666666,
        "away": 0.7777777777777778
      },
      "minutespergoalconceded": {
        "total": 61.357142857142854,
        "home": 63.666666666666664,
        "away": 59.206896551724135
      },
      "goalsbyminutes": {
        "0-15": {
          "total": 0.2222222222222222,
          "home": 0.16666666666666666,
          "away": 0.2777777777777778
        },
        "16-30": {
          "total": 0.19444444444444445,
          "home": 0.16666666666666666,
          "away": 0.2222222222222222
        },
        "31-45": {
          "total": 0.3055555555555556,
          "home": 0.3333333333333333,
          "away": 0.2777777777777778
        },
        "46-60": {
          "total": 0.3055555555555556,
          "home": 0.2777777777777778,
          "away": 0.3333333333333333
        },
        "61-75": {
          "total": 0.1388888888888889,
          "home": 0.1111111111111111,
          "away": 0.16666666666666666
        },
        "76-90": {
          "total": 0.3888888888888889,
          "home": 0.4444444444444444,
          "away": 0.3333333333333333
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
- Hits: 3 | Status: 200:3 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 8.4 KB | max 27.8 KB | avg 20.7 KB
- queryUrl: stats_team_lastx/2824/20, stats_team_lastx/2828/20, stats_team_lastx/2824/5
- Match ids detectados: 61624646, 61624630, 61624616, 61624566, 61624596, 69589774, 61624548, 61624536, 61624516, 61624496
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Últimos partidos de un equipo, útil para forma reciente.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2824,
    "_rcid": 32,
    "_sid": 1,
    "name": "Real Sociedad",
    "mediumname": "Real Sociedad San Sebastian",
    "suffix": null,
    "abbr": "RSO",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624646,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 36,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 7320247,
          "_sid": 1,
          "uid": 24264,
          "virtual": false,
          "name": "Girona",
          "mediumname": "Girona FC",
          "abbr": "GIR",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624630,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 35,
      "week": 19,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        },
        "away": {
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
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624616,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 34,
      "week": 19,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 70660,
          "_sid": 1,
          "uid": 2833,
          "virtual": false,
          "name": "Sevilla",
          "mediumname": "Sevilla FC",
          "abbr": "SEV",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
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
    "150": {
      "_doc": "tournament",
      "_id": 150,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 500,
      "_tid": 150,
      "_utid": 329,
      "_gender": "men",
      "name": "Copa del Rey",
      "abbr": "CDR"
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
    },
    "329": {
      "_doc": "uniquetournament",
      "_id": 329,
      "_utid": 329,
      "_sid": 1,
      "_rcid": 32,
      "name": "Copa del Rey",
      "currentseason": 131970,
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
- Hits: 3 | Status: 200:3 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 2.6 KB | max 2.6 KB | avg 2.6 KB
- queryUrl: stats_team_nextx/2824/1, stats_team_nextx/2828/1
- Match ids detectados: 61624670
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Próximos partidos del equipo, útil para congestión de calendario.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2824,
    "_rcid": 32,
    "_sid": 1,
    "name": "Real Sociedad",
    "mediumname": "Real Sociedad San Sebastian",
    "suffix": null,
    "abbr": "RSO",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624670,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 37,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5197,
          "_sid": 1,
          "uid": 2828,
          "virtual": false,
          "name": "Valencia",
          "mediumname": "Valencia CF",
          "abbr": "VCF",
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
- Tamaño aprox.: min 2.0 KB | max 2.5 KB | avg 2.2 KB
- queryUrl: stats_team_streaks/2828, stats_team_streaks/2824
- Match ids detectados: 11370727, 61624670, 61624694, 61624652, 61624618, 61624610, 61624576, 61624584, 61624544, 61624532
- Campos principales: team, nextmatches, lastmatchesform, streaks
- Qué aporta: Rachas y forma condensada del equipo.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2828,
    "_rcid": 32,
    "_sid": 1,
    "name": "Valencia",
    "mediumname": "Valencia CF",
    "suffix": null,
    "abbr": "VCF",
    "nickname": null,
    "teamtypeid": 0
  },
  "nextmatches": [
    {
      "matchdifficultyrating": 1,
      "matchid": 11370727
    },
    {
      "matchdifficultyrating": 4,
      "matchid": 61624670
    },
    {
      "matchdifficultyrating": 5,
      "matchid": 61624694
    }
  ],
  "lastmatchesform": {
    "total": [
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624652
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624618
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624610
      }
    ],
    "home": [
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624652
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624610
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624576
      }
    ],
    "away": [
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624618
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624584
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624544
      }
    ]
  },
  "streaks": {
    "goalsconceded": {
      "home": {
        "value": 5,
        "streak": [
          {
            "result": 1,
            "matchid": 61624652
          },
          {
            "result": 2,
            "matchid": 61624610
          },
          {
            "result": 1,
            "matchid": 61624576
          }
        ]
      }
    }
  }
}
```

#### `stats_team_versus`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 100.5 KB | max 100.5 KB | avg 100.5 KB
- queryUrl: stats_team_versus/2824/2828
- Match ids detectados: 61623440, 50852475, 50852227, 41893613, 41893033, 34277657, 34277445, 27965620, 27965434, 23360915
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
      "_id": 61623440,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 1,
      "week": 33,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5197,
          "_sid": 1,
          "uid": 2828,
          "virtual": false,
          "name": "Valencia",
          "mediumname": "Valencia CF",
          "abbr": "VCF",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 50852475,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 20,
      "week": 3,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5197,
          "_sid": 1,
          "uid": 2828,
          "virtual": false,
          "name": "Valencia",
          "mediumname": "Valencia CF",
          "abbr": "VCF",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 50852227,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 8,
      "week": 39,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5197,
          "_sid": 1,
          "uid": 2828,
          "virtual": false,
          "name": "Valencia",
          "mediumname": "Valencia CF",
          "abbr": "VCF",
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
  },
  "teams": {
    "2824": {
      "_doc": "uniqueteam",
      "_id": 2824,
      "_rcid": 32,
      "_sid": 1,
      "name": "Real Sociedad",
      "mediumname": "Real Sociedad San Sebastian",
      "suffix": null,
      "abbr": "RSO",
      "nickname": null,
      "teamtypeid": 0
    },
    "2828": {
      "_doc": "uniqueteam",
      "_id": 2828,
      "_rcid": 32,
      "_sid": 1,
      "name": "Valencia",
      "mediumname": "Valencia CF",
      "suffix": null,
      "abbr": "VCF",
      "nickname": null,
      "teamtypeid": 0
    }
  },
  "currentmanagers": {
    "2824": [
      {
        "_doc": "player",
        "_id": 4556,
        "name": "Matarazzo, Pellegrino",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "28/11/77",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 249523200
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 105,
          "a2": "it",
          "name": "Italy",
          "a3": "ITA",
          "ioc": "ITA",
          "continentid": 1,
          "continent": "Europe",
          "population": 60300000
        },
        "primarypositiontype": null,
        "haslogo": false,
        "membersince": {
          "_doc": "time",
          "time": "00:00",
          "date": "20/12/25",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1766188800
        }
      }
    ],
    "2828": [
      {
        "_doc": "player",
        "_id": 1083700,
        "name": "Corberan, Carlos",
        "fullname": "Corberan Vallet, Carlos",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "07/04/83",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 418521600
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
          "date": "24/12/24",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1734998400
        }
      }
    ]
  },
  "jersey": {
    "2824": {
      "base": "ffffff",
      "sleeve": "1e68bf",
      "number": "000000",
      "stripes": "4f619f",
      "type": "short_sleeves",
      "sleevelong": "ffffff",
      "real": true
    },
    "2828": {
      "base": "ab2139",
      "sleeve": "ad233d",
      "number": "e87250",
      "type": "short_sleeves",
      "real": true
    }
  },
  "next": {
    "_doc": "match",
    "_doctype": "generic",
    "_id": 61624670,
    "_sid": 1,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "round": 37,
    "week": 20,
    "teams": {
      "home": {
        "_doc": "team",
        "_id": 5134,
        "_sid": 1,
        "uid": 2824,
        "virtual": false,
        "name": "Real Sociedad",
        "mediumname": "Real Sociedad San Sebastian",
        "abbr": "RSO",
        "nickname": null,
        "iscountry": false
      },
      "away": {
        "_doc": "team",
        "_id": 5197,
        "_sid": 1,
        "uid": 2828,
        "virtual": false,
        "name": "Valencia",
        "mediumname": "Valencia CF",
        "abbr": "VCF",
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
- Hits: 3 | Status: 200:3 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 8.4 KB | max 27.8 KB | avg 20.7 KB
- queryUrl: stats_team_lastx/2824/20, stats_team_lastx/2828/20, stats_team_lastx/2824/5
- Match ids detectados: 61624646, 61624630, 61624616, 61624566, 61624596, 69589774, 61624548, 61624536, 61624516, 61624496
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Últimos partidos de un equipo, útil para forma reciente.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2824,
    "_rcid": 32,
    "_sid": 1,
    "name": "Real Sociedad",
    "mediumname": "Real Sociedad San Sebastian",
    "suffix": null,
    "abbr": "RSO",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624646,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 36,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 7320247,
          "_sid": 1,
          "uid": 24264,
          "virtual": false,
          "name": "Girona",
          "mediumname": "Girona FC",
          "abbr": "GIR",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624630,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 35,
      "week": 19,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        },
        "away": {
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
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624616,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 34,
      "week": 19,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 70660,
          "_sid": 1,
          "uid": 2833,
          "virtual": false,
          "name": "Sevilla",
          "mediumname": "Sevilla FC",
          "abbr": "SEV",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
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
    "150": {
      "_doc": "tournament",
      "_id": 150,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 500,
      "_tid": 150,
      "_utid": 329,
      "_gender": "men",
      "name": "Copa del Rey",
      "abbr": "CDR"
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
    },
    "329": {
      "_doc": "uniquetournament",
      "_id": 329,
      "_utid": 329,
      "_sid": 1,
      "_rcid": 32,
      "name": "Copa del Rey",
      "currentseason": 131970,
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
- Hits: 3 | Status: 200:3 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 2.6 KB | max 2.6 KB | avg 2.6 KB
- queryUrl: stats_team_nextx/2824/1, stats_team_nextx/2828/1
- Match ids detectados: 61624670
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Próximos partidos del equipo, útil para congestión de calendario.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2824,
    "_rcid": 32,
    "_sid": 1,
    "name": "Real Sociedad",
    "mediumname": "Real Sociedad San Sebastian",
    "suffix": null,
    "abbr": "RSO",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624670,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 37,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5197,
          "_sid": 1,
          "uid": 2828,
          "virtual": false,
          "name": "Valencia",
          "mediumname": "Valencia CF",
          "abbr": "VCF",
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
- Tamaño aprox.: min 2.0 KB | max 2.5 KB | avg 2.2 KB
- queryUrl: stats_team_streaks/2828, stats_team_streaks/2824
- Match ids detectados: 11370727, 61624670, 61624694, 61624652, 61624618, 61624610, 61624576, 61624584, 61624544, 61624532
- Campos principales: team, nextmatches, lastmatchesform, streaks
- Qué aporta: Rachas y forma condensada del equipo.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2828,
    "_rcid": 32,
    "_sid": 1,
    "name": "Valencia",
    "mediumname": "Valencia CF",
    "suffix": null,
    "abbr": "VCF",
    "nickname": null,
    "teamtypeid": 0
  },
  "nextmatches": [
    {
      "matchdifficultyrating": 1,
      "matchid": 11370727
    },
    {
      "matchdifficultyrating": 4,
      "matchid": 61624670
    },
    {
      "matchdifficultyrating": 5,
      "matchid": 61624694
    }
  ],
  "lastmatchesform": {
    "total": [
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624652
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624618
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624610
      }
    ],
    "home": [
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624652
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624610
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624576
      }
    ],
    "away": [
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624618
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624584
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624544
      }
    ]
  },
  "streaks": {
    "goalsconceded": {
      "home": {
        "value": 5,
        "streak": [
          {
            "result": 1,
            "matchid": 61624652
          },
          {
            "result": 2,
            "matchid": 61624610
          },
          {
            "result": 1,
            "matchid": 61624576
          }
        ]
      }
    }
  }
}
```

#### `stats_team_versus`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 100.5 KB | max 100.5 KB | avg 100.5 KB
- queryUrl: stats_team_versus/2824/2828
- Match ids detectados: 61623440, 50852475, 50852227, 41893613, 41893033, 34277657, 34277445, 27965620, 27965434, 23360915
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
      "_id": 61623440,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 1,
      "week": 33,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5197,
          "_sid": 1,
          "uid": 2828,
          "virtual": false,
          "name": "Valencia",
          "mediumname": "Valencia CF",
          "abbr": "VCF",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 50852475,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 20,
      "week": 3,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5197,
          "_sid": 1,
          "uid": 2828,
          "virtual": false,
          "name": "Valencia",
          "mediumname": "Valencia CF",
          "abbr": "VCF",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 50852227,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 8,
      "week": 39,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5134,
          "_sid": 1,
          "uid": 2824,
          "virtual": false,
          "name": "Real Sociedad",
          "mediumname": "Real Sociedad San Sebastian",
          "abbr": "RSO",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5197,
          "_sid": 1,
          "uid": 2828,
          "virtual": false,
          "name": "Valencia",
          "mediumname": "Valencia CF",
          "abbr": "VCF",
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
  },
  "teams": {
    "2824": {
      "_doc": "uniqueteam",
      "_id": 2824,
      "_rcid": 32,
      "_sid": 1,
      "name": "Real Sociedad",
      "mediumname": "Real Sociedad San Sebastian",
      "suffix": null,
      "abbr": "RSO",
      "nickname": null,
      "teamtypeid": 0
    },
    "2828": {
      "_doc": "uniqueteam",
      "_id": 2828,
      "_rcid": 32,
      "_sid": 1,
      "name": "Valencia",
      "mediumname": "Valencia CF",
      "suffix": null,
      "abbr": "VCF",
      "nickname": null,
      "teamtypeid": 0
    }
  },
  "currentmanagers": {
    "2824": [
      {
        "_doc": "player",
        "_id": 4556,
        "name": "Matarazzo, Pellegrino",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "28/11/77",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 249523200
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 105,
          "a2": "it",
          "name": "Italy",
          "a3": "ITA",
          "ioc": "ITA",
          "continentid": 1,
          "continent": "Europe",
          "population": 60300000
        },
        "primarypositiontype": null,
        "haslogo": false,
        "membersince": {
          "_doc": "time",
          "time": "00:00",
          "date": "20/12/25",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1766188800
        }
      }
    ],
    "2828": [
      {
        "_doc": "player",
        "_id": 1083700,
        "name": "Corberan, Carlos",
        "fullname": "Corberan Vallet, Carlos",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "07/04/83",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 418521600
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
          "date": "24/12/24",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1734998400
        }
      }
    ]
  },
  "jersey": {
    "2824": {
      "base": "ffffff",
      "sleeve": "1e68bf",
      "number": "000000",
      "stripes": "4f619f",
      "type": "short_sleeves",
      "sleevelong": "ffffff",
      "real": true
    },
    "2828": {
      "base": "ab2139",
      "sleeve": "ad233d",
      "number": "e87250",
      "type": "short_sleeves",
      "real": true
    }
  },
  "next": {
    "_doc": "match",
    "_doctype": "generic",
    "_id": 61624670,
    "_sid": 1,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "round": 37,
    "week": 20,
    "teams": {
      "home": {
        "_doc": "team",
        "_id": 5134,
        "_sid": 1,
        "uid": 2824,
        "virtual": false,
        "name": "Real Sociedad",
        "mediumname": "Real Sociedad San Sebastian",
        "abbr": "RSO",
        "nickname": null,
        "iscountry": false
      },
      "away": {
        "_doc": "team",
        "_id": 5197,
        "_sid": 1,
        "uid": 2828,
        "virtual": false,
        "name": "Valencia",
        "mediumname": "Valencia CF",
        "abbr": "VCF",
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
- Tamaño aprox.: min 10.5 KB | max 10.6 KB | avg 10.5 KB
- queryUrl: stats_season_topassists/130805/2828, stats_season_topassists/130805/2824
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
      "_id": 2287743,
      "playerid": 2287743,
      "player": {
        "_doc": "player",
        "_id": 2287743,
        "name": "Guerra Moreno, Javier",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "13/05/03",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1052784000
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
        "jerseynumber": 8
      },
      "teams": {
        "2828": {
          "active": true,
          "lastevent": "2026-05-14 18:23:35",
          "started": 23,
          "matches": 34,
          "assists": 6,
          "minutes_played": 1888,
          "substituted_in": 11,
          "shirtnumber": "8"
        }
      },
      "total": {
        "matches": 34,
        "assists": 6,
        "minutes_played": 1888,
        "substituted_in": 11
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 1278078,
      "playerid": 1278078,
      "player": {
        "_doc": "player",
        "_id": 1278078,
        "name": "Rioja, Luis",
        "fullname": "Rioja Gonzalez, Luis Jesus",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "16/10/93",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 750729600
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
        "jerseynumber": 11
      },
      "teams": {
        "2828": {
          "active": true,
          "lastevent": "2026-05-14 16:14:55",
          "started": 29,
          "matches": 35,
          "assists": 6,
          "minutes_played": 2475,
          "substituted_in": 6,
          "shirtnumber": "11"
        }
      },
      "total": {
        "matches": 35,
        "assists": 6,
        "minutes_played": 2475,
        "substituted_in": 6
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 1069048,
      "playerid": 1069048,
      "player": {
        "_doc": "player",
        "_id": 1069048,
        "name": "Ugrinic, Filip",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "05/01/99",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 915494400
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 206,
          "a2": "ch",
          "name": "Switzerland",
          "a3": "CHE",
          "ioc": "SUI",
          "continentid": 1,
          "continent": "Europe",
          "population": 7800000
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
        "jerseynumber": 23
      },
      "teams": {
        "2828": {
          "active": true,
          "lastevent": "2026-05-14 18:23:44",
          "started": 15,
          "matches": 25,
          "assists": 3,
          "minutes_played": 1345,
          "substituted_in": 10,
          "shirtnumber": "23"
        }
      },
      "total": {
        "matches": 25,
        "assists": 3,
        "minutes_played": 1345,
        "substituted_in": 10
      }
    }
  ],
  "teams": {
    "2828": {
      "_doc": "uniqueteam",
      "_id": 2828,
      "_rcid": 32,
      "_sid": 1,
      "name": "Valencia",
      "mediumname": "Valencia CF",
      "suffix": null,
      "abbr": "VCF",
      "nickname": null,
      "teamtypeid": 0
    }
  }
}
```

#### `stats_season_topcards`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 20.4 KB | max 21.1 KB | avg 20.7 KB
- queryUrl: stats_season_topcards/130805/2828, stats_season_topcards/130805/2824
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
      "_id": 227922,
      "playerid": 227922,
      "player": {
        "_doc": "player",
        "_id": 227922,
        "name": "Gaya, Jose",
        "fullname": "Gaya Pena, Jose Luis",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "25/05/95",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 801360000
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
          "_id": "4",
          "_type": "D",
          "name": "Defender",
          "shortname": "DEF",
          "abbr": "D"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 14
      },
      "teams": {
        "2828": {
          "active": true,
          "lastevent": "2026-05-14 18:25:55",
          "started": 31,
          "yellow_cards": 6,
          "red_cards": 1,
          "matches": 32,
          "minutes_played": 2463,
          "substituted_in": 1,
          "number_of_cards_1st_half": 4,
          "number_of_cards_2nd_half": 3
        }
      },
      "total": {
        "yellow_cards": 6,
        "red_cards": 1,
        "matches": 32,
        "minutes_played": 2463,
        "substituted_in": 1,
        "number_of_cards_1st_half": 4,
        "number_of_cards_2nd_half": 3
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 2253033,
      "playerid": 2253033,
      "player": {
        "_doc": "player",
        "_id": 2253033,
        "name": "Tarrega, Cesar",
        "fullname": "Tarrega Requeni, Cesar",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "26/02/02",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1014681600
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
          "_id": "4",
          "_type": "D",
          "name": "Defender",
          "shortname": "DEF",
          "abbr": "D"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 5
      },
      "teams": {
        "2828": {
          "active": true,
          "lastevent": "2026-05-14 16:14:55",
          "started": 27,
          "yellow_cards": 7,
          "matches": 30,
          "minutes_played": 2417,
          "substituted_in": 3,
          "number_of_cards_1st_half": 2,
          "number_of_cards_2nd_half": 5,
          "shirtnumber": "5"
        }
      },
      "total": {
        "yellow_cards": 7,
        "matches": 30,
        "minutes_played": 2417,
        "substituted_in": 3,
        "number_of_cards_1st_half": 2,
        "number_of_cards_2nd_half": 5
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 1342500,
      "playerid": 1342500,
      "player": {
        "_doc": "player",
        "_id": 1342500,
        "name": "Duro, Hugo",
        "fullname": "Duro Perales, Hugo",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "10/11/99",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 942192000
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
        "2828": {
          "active": true,
          "lastevent": "2026-05-14 18:23:33",
          "started": 20,
          "yellow_cards": 6,
          "matches": 34,
          "minutes_played": 1827,
          "substituted_in": 14,
          "number_of_cards_1st_half": 3,
          "number_of_cards_2nd_half": 3,
          "shirtnumber": "9"
        }
      },
      "total": {
        "yellow_cards": 6,
        "matches": 34,
        "minutes_played": 1827,
        "substituted_in": 14,
        "number_of_cards_1st_half": 3,
        "number_of_cards_2nd_half": 3
      }
    }
  ],
  "teams": {
    "2828": {
      "_doc": "uniqueteam",
      "_id": 2828,
      "_rcid": 32,
      "_sid": 1,
      "name": "Valencia",
      "mediumname": "Valencia CF",
      "suffix": null,
      "abbr": "VCF",
      "nickname": null,
      "teamtypeid": 0
    }
  }
}
```

#### `stats_season_topgoals`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 13.1 KB | max 14.0 KB | avg 13.5 KB
- queryUrl: stats_season_topgoals/130805/2824, stats_season_topgoals/130805/2828
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
      "_id": 924002,
      "playerid": 924002,
      "player": {
        "_doc": "player",
        "_id": 924002,
        "name": "Oyarzabal, Mikel",
        "fullname": "Oyarzabal Ugarte, Mikel",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "21/04/97",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 861580800
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
        "jerseynumber": 10
      },
      "teams": {
        "2824": {
          "active": true,
          "lastevent": "2026-05-14 17:12:53",
          "started": 30,
          "goals": 15,
          "matches": 32,
          "penalties": 7,
          "goal_points": 18,
          "minutes_played": 2665,
          "substituted_in": 2,
          "first_goals": 6
        }
      },
      "total": {
        "goals": 15,
        "matches": 32,
        "penalties": 7,
        "goal_points": 18,
        "minutes_played": 2665,
        "substituted_in": 2,
        "first_goals": 6,
        "last_goals": 5
      },
      "home": {
        "goals": 10
      },
      "away": {
        "goals": 5
      },
      "firsthalf": {
        "goals": 8
      },
      "secondhalf": {
        "goals": 7
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 280979,
      "playerid": 280979,
      "player": {
        "_doc": "player",
        "_id": 280979,
        "name": "Guedes, Goncalo",
        "fullname": "Ganchinho Guedes, Goncalo Manuel",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "29/11/96",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 849225600
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
          "_id": "6",
          "_type": "M",
          "name": "Midfielder",
          "shortname": "MID",
          "abbr": "M"
        },
        "primarypositiontype": null,
        "haslogo": true,
        "jerseynumber": 11
      },
      "teams": {
        "2824": {
          "active": true,
          "lastevent": "2026-04-11 13:07:59",
          "started": 22,
          "goals": 8,
          "matches": 31,
          "goal_points": 12,
          "minutes_played": 1820,
          "substituted_in": 9,
          "first_goals": 2,
          "last_goals": 2
        }
      },
      "total": {
        "goals": 8,
        "matches": 31,
        "goal_points": 12,
        "minutes_played": 1820,
        "substituted_in": 9,
        "first_goals": 2,
        "last_goals": 2
      },
      "home": {
        "goals": 6
      },
      "away": {
        "goals": 2
      },
      "firsthalf": {
        "goals": 3
      },
      "secondhalf": {
        "goals": 5
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 1748491,
      "playerid": 1748491,
      "player": {
        "_doc": "player",
        "_id": 1748491,
        "name": "Oskarsson, Orri",
        "fullname": "Oskarsson, Orri Steinn",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "29/08/04",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1093737600
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 98,
          "a2": "is",
          "name": "Iceland",
          "a3": "ISL",
          "ioc": "ISL",
          "continentid": 1,
          "continent": "Europe",
          "population": 346000
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
        "2824": {
          "active": true,
          "lastevent": "2026-05-09 20:39:23",
          "started": 6,
          "goals": 7,
          "matches": 18,
          "goal_points": 7,
          "minutes_played": 676,
          "substituted_in": 12,
          "last_goals": 2,
          "shirtnumber": "9"
        }
      },
      "total": {
        "goals": 7,
        "matches": 18,
        "goal_points": 7,
        "minutes_played": 676,
        "substituted_in": 12,
        "last_goals": 2
      },
      "home": {
        "goals": 6
      },
      "away": {
        "goals": 1
      },
      "secondhalf": {
        "goals": 7
      }
    }
  ],
  "teams": {
    "2824": {
      "_doc": "uniqueteam",
      "_id": 2824,
      "_rcid": 32,
      "_sid": 1,
      "name": "Real Sociedad",
      "mediumname": "Real Sociedad San Sebastian",
      "suffix": null,
      "abbr": "RSO",
      "nickname": null,
      "teamtypeid": 0
    }
  }
}
```

### Lesiones

#### `stats_season_injuries`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 58.3 KB | max 58.3 KB | avg 58.3 KB
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
- queryUrl: match_markets/61624670
- Campos principales: markets
- Qué aporta: Mercados y odds del partido por HTTP; hoy es el hallazgo más fuerte del lado odds.
- Estructura resumida:

```json
{
  "markets": [
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624670,
      "_marketId": 1,
      "_uts": 1778983672,
      "specifiers": null,
      "name": "1x2",
      "nameShort": "1x2",
      "active": true,
      "type": "prematch"
    },
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624670,
      "_marketId": 10,
      "_uts": 1778983698,
      "specifiers": null,
      "name": "Double chance",
      "nameShort": "Double chance",
      "active": true,
      "type": "prematch"
    },
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624670,
      "_marketId": 11,
      "_uts": 1778983698,
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
- Tamaño aprox.: min 299.9 KB | max 326.6 KB | avg 313.3 KB
- queryUrl: uniqueteam_markets/2824, uniqueteam_markets/2828
- Campos principales: matches
- Qué aporta: Mercados por equipo sobre matches relacionados, útil para análisis complementario.
- Estructura resumida:

```json
{
  "matches": {
    "50852811": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 50852811,
          "_marketId": 1,
          "_uts": 1747587527,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 50852811,
          "_marketId": 10,
          "_uts": 1747587489,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 50852811,
          "_marketId": 11,
          "_uts": 1747587489,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "50852825": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 50852825,
          "_marketId": 1,
          "_uts": 1748095131,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 50852825,
          "_marketId": 10,
          "_uts": 1748095809,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 50852825,
          "_marketId": 11,
          "_uts": 1748095809,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61175115": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61175115,
          "_marketId": 1,
          "_uts": 1754755300,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61175115,
          "_marketId": 10,
          "_uts": 1754755329,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61175115,
          "_marketId": 11,
          "_uts": 1754755329,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61264019": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61264019,
          "_marketId": 1,
          "_uts": 1753893590,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61264019,
          "_marketId": 10,
          "_uts": 1753893490,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61264019,
          "_marketId": 11,
          "_uts": 1753893490,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61265727": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61265727,
          "_marketId": 1,
          "_uts": 1754120361,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61265727,
          "_marketId": 10,
          "_uts": 1754120409,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61265727,
          "_marketId": 11,
          "_uts": 1754120409,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61623440": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623440,
          "_marketId": 1,
          "_uts": 1755371520,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623440,
          "_marketId": 10,
          "_uts": 1755371529,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623440,
          "_marketId": 11,
          "_uts": 1755371529,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61623972": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623972,
          "_marketId": 1,
          "_uts": 1756055394,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623972,
          "_marketId": 10,
          "_uts": 1756055889,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623972,
          "_marketId": 11,
          "_uts": 1756056010,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61623988": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623988,
          "_marketId": 1,
          "_uts": 1756573012,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623988,
          "_marketId": 10,
          "_uts": 1756573010,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623988,
          "_marketId": 11,
          "_uts": 1756573010,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61624016": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624016,
          "_marketId": 1,
          "_uts": 1757772809,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624016,
          "_marketId": 10,
          "_uts": 1757772807,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624016,
          "_marketId": 11,
          "_uts": 1757772446,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61624022": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624022,
          "_marketId": 1,
          "_uts": 1758306338,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624022,
          "_marketId": 10,
          "_uts": 1758305640,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624022,
          "_marketId": 11,
          "_uts": 1758306343,
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
