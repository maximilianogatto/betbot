# Sportradar Stats Filtered Endpoint Report

- Capture dir: `/Users/maximilianogatto/Library/CloudStorage/OneDrive-Personal/Apuestas/BetBot/sandbox/sportradar_stats/captures/rayo_villareal_full`
- Source usado: `filtered_fetch.ndjson`
- Responses útiles filtradas: 30
- Endpoints limpios detectados: 21

## Resumen Ejecutivo

- `match_markets` expone mercados/odds por HTTP. En esta captura devolvió 11 markets, incluyendo 1X2 y handicaps.
- `match_timeline` / `match_timelinedelta` son los candidatos más fuertes para detectar `live`, score, estado y timeline. Ambos usan `_maxage` corto.
- `event_get` parece un feed live global y no necesariamente del partido abierto: en esta captura apunta a match id(s) 67645070, 67648462, 67904748, 71411252, 71411162, mientras el match principal fue 61624668.
- Hay buen contexto pre-match por HTTP: forma reciente, tabla, streaks, head-to-head y slices de standings.
- También aparecen endpoints útiles para enriquecer análisis: lesiones y leaders de goles, tarjetas y asistencias.

## Endpoints Detectados

| Endpoint | Hits | Polling | Tamaño aprox. | Categorías |
| --- | ---: | :---: | ---: | --- |
| `stats_season_tables` | 2 | Sí | 21.4 KB | Tabla y standings |
| `stats_season_teamscoringconceding` | 2 | Sí | 3.5 KB | Stats pre-match y contexto |
| `stats_season_topassists` | 2 | Sí | 11.4 KB | Jugadores y leaders |
| `stats_season_topcards` | 2 | Sí | 20.5 KB | Jugadores y leaders |
| `stats_season_topgoals` | 2 | Sí | 14.6 KB | Jugadores y leaders |
| `stats_team_lastx` | 2 | Sí | 25.7 KB | Stats pre-match y contexto, Forma reciente |
| `stats_team_nextx` | 2 | Sí | 2.6 KB | Stats pre-match y contexto, Forma reciente |
| `stats_team_streaks` | 2 | Sí | 3.2 KB | Stats pre-match y contexto, Forma reciente |
| `uniqueteam_markets` | 2 | Sí | 371.0 KB | Mercados y odds |
| `event_get` | 1 | Sí | 287.2 KB | Score y estado live, Timeline y eventos live |
| `match_details` | 1 | Sí | 113.0 B | Metadata del partido |
| `match_info_statshub` | 1 | No | 7.1 KB | Metadata del partido |
| `match_markets` | 1 | No | 6.5 KB | Mercados y odds |
| `match_timeline` | 1 | Sí | 2.3 KB | Score y estado live, Timeline y eventos live |
| `match_timelinedelta` | 1 | Sí | 2.4 KB | Score y estado live, Timeline y eventos live |
| `odds_ukformat` | 1 | No | 9.6 KB | Mercados y odds |
| `stats_formtable` | 1 | No | 53.5 KB | Forma reciente, Tabla y standings |
| `stats_h2h_versus` | 1 | Sí | 19.9 KB | Stats pre-match y contexto |
| `stats_match_get` | 1 | No | 5.6 KB | Metadata del partido, Score y estado live |
| `stats_season_injuries` | 1 | No | 58.3 KB | Lesiones |
| `stats_team_versus` | 1 | No | 56.2 KB | Stats pre-match y contexto, Forma reciente |

## Endpoints por Caso de Uso

### Metadata del partido

#### `match_details`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage)
- Tamaño aprox.: min 113.0 B | max 113.0 B | avg 113.0 B
- queryUrl: match_details/61624668
- Qué aporta: Detalle auxiliar del match; en esta muestra vino vacío.
- Estructura resumida:

```json
[]
```

#### `match_info_statshub`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 7.1 KB | max 7.1 KB | avg 7.1 KB
- queryUrl: match_info_statshub/61624668
- Match ids detectados: 61624668
- Campos principales: _doc, match, cities, stadium, tournament, uniquetournament, sport, realcategory, season, referee, manager, jerseys
- Qué aporta: Metadata fuerte del partido: torneo, estadio, ciudades, coverage y contexto del evento.
- Estructura resumida:

```json
{
  "_doc": "match_info",
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624668,
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
      "_id": 194,
      "name": "Madrid"
    },
    "away": {
      "_id": 85,
      "name": "Villarreal"
    }
  },
  "stadium": {
    "_doc": "stadium",
    "_id": "2440",
    "name": "Estadio de Vallecas",
    "description": "",
    "city": "Madrid",
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
    "capacity": "14708",
    "hometeams": [
      {
        "_doc": "uniqueteam",
        "_id": 2818,
        "_rcid": 32,
        "_sid": 1,
        "name": "Vallecano",
        "mediumname": "Rayo Vallecano",
        "suffix": null,
        "abbr": "RVC",
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
    "_id": 92296,
    "name": "De Burgos Bengoechea, Ricardo",
    "birthdate": {
      "_doc": "time",
      "time": "00:00",
      "date": "16/03/86",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 511315200
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
- Tamaño aprox.: min 5.6 KB | max 5.6 KB | avg 5.6 KB
- queryUrl: stats_match_get/61624668
- Match ids detectados: 61624668
- Campos principales: _doc, _doctype, _id, _sid, _rcid, _tid, _utid, round, week, teams, tobeannounced, postponed
- Qué aporta: Snapshot del match con ids, hora, equipos, resultado y señales de live/inlivescore.
- Estructura resumida:

```json
{
  "_doc": "match",
  "_doctype": "generic",
  "_id": 61624668,
  "_sid": 1,
  "_rcid": 32,
  "_tid": 36,
  "_utid": 8,
  "round": 37,
  "week": 20,
  "teams": {
    "home": {
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
    },
    "away": {
      "_doc": "team",
      "_id": 5120,
      "_sid": 1,
      "uid": 2819,
      "virtual": false,
      "name": "Villarreal",
      "mediumname": "Villarreal CF",
      "abbr": "VIL",
      "nickname": null,
      "iscountry": false
    }
  }
}
```

### Score y estado live

#### `event_get`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 287.2 KB | max 287.2 KB | avg 287.2 KB
- queryUrl: event_get/
- Match ids detectados: 67645070, 67648462, 67904748, 71411252, 71411162, 68046520, 71530068, 71528038, 71545486, 71546626
- Campos principales: _doc, _doctype, _id, _scoutid, _sid, _rcid, _tid, _dc, _typeid, uts, updated_uts, type
- Qué aporta: Feed de eventos live que parece más global; hay que validar alcance exacto en más capturas.
- Estructura resumida:

```json
[
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "67645070-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 52,
    "_tid": 182714,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778997743
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "67648462-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 52,
    "_tid": 182728,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778999324
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "67904748-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 34,
    "_tid": 43961,
    "_dc": false,
    "_typeid": "22",
    "uts": 1779000323
  }
]
```

#### `match_timeline`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 2.3 KB | max 2.3 KB | avg 2.3 KB
- queryUrl: match_timeline/61624668
- Match ids detectados: 61624668
- Campos principales: match, events
- Qué aporta: Estado del partido y timeline principal. Es el candidato más claro para live state del fixture abierto.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624668,
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
- queryUrl: match_timelinedelta/61624668
- Match ids detectados: 61624668
- Campos principales: match, events
- Qué aporta: Delta del timeline, ideal para polling liviano cuando el partido está en vivo.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624668,
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
- Tamaño aprox.: min 5.6 KB | max 5.6 KB | avg 5.6 KB
- queryUrl: stats_match_get/61624668
- Match ids detectados: 61624668
- Campos principales: _doc, _doctype, _id, _sid, _rcid, _tid, _utid, round, week, teams, tobeannounced, postponed
- Qué aporta: Snapshot del match con ids, hora, equipos, resultado y señales de live/inlivescore.
- Estructura resumida:

```json
{
  "_doc": "match",
  "_doctype": "generic",
  "_id": 61624668,
  "_sid": 1,
  "_rcid": 32,
  "_tid": 36,
  "_utid": 8,
  "round": 37,
  "week": 20,
  "teams": {
    "home": {
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
    },
    "away": {
      "_doc": "team",
      "_id": 5120,
      "_sid": 1,
      "uid": 2819,
      "virtual": false,
      "name": "Villarreal",
      "mediumname": "Villarreal CF",
      "abbr": "VIL",
      "nickname": null,
      "iscountry": false
    }
  }
}
```

### Timeline y eventos live

#### `event_get`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 287.2 KB | max 287.2 KB | avg 287.2 KB
- queryUrl: event_get/
- Match ids detectados: 67645070, 67648462, 67904748, 71411252, 71411162, 68046520, 71530068, 71528038, 71545486, 71546626
- Campos principales: _doc, _doctype, _id, _scoutid, _sid, _rcid, _tid, _dc, _typeid, uts, updated_uts, type
- Qué aporta: Feed de eventos live que parece más global; hay que validar alcance exacto en más capturas.
- Estructura resumida:

```json
[
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "67645070-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 52,
    "_tid": 182714,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778997743
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "67648462-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 52,
    "_tid": 182728,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778999324
  },
  {
    "_doc": "event",
    "_doctype": "currentperiod",
    "_id": "67904748-22",
    "_scoutid": null,
    "_sid": 1,
    "_rcid": 34,
    "_tid": 43961,
    "_dc": false,
    "_typeid": "22",
    "uts": 1779000323
  }
]
```

#### `match_timeline`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 2.3 KB | max 2.3 KB | avg 2.3 KB
- queryUrl: match_timeline/61624668
- Match ids detectados: 61624668
- Campos principales: match, events
- Qué aporta: Estado del partido y timeline principal. Es el candidato más claro para live state del fixture abierto.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624668,
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
- queryUrl: match_timelinedelta/61624668
- Match ids detectados: 61624668
- Campos principales: match, events
- Qué aporta: Delta del timeline, ideal para polling liviano cuando el partido está en vivo.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624668,
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
- Tamaño aprox.: min 19.9 KB | max 19.9 KB | avg 19.9 KB
- queryUrl: stats_h2h_versus/2818/2819/61624668
- Match ids detectados: 61624668, 414099, 363940, 61624156, 27965882
- Campos principales: match, lastmatchesbetweenteams, lastmatchesbetweenteamsonvenue, versusmatchstats
- Qué aporta: Historial comparativo y versus stats entre ambos equipos.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624668,
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
      "_id": 61624156,
      "result": {
        "home": 4,
        "away": 0,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "13:00",
        "date": "01/11/25",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1762002000
      },
      "homeuniqueteamid": 2819,
      "awayuniqueteamid": 2818,
      "periods": {
        "ft": {
          "home": 4,
          "away": 0
        },
        "p1": {
          "home": 1,
          "away": 0
        }
      },
      "round": 11,
      "roundname": {
        "_doc": "tableround",
        "_id": 11,
        "name": 11
      },
      "_seasonid": 130805
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 50852565,
      "result": {
        "home": 0,
        "away": 1,
        "period": "nt",
        "winner": "away"
      },
      "time": {
        "_doc": "time",
        "time": "15:15",
        "date": "22/02/25",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1740237300
      },
      "homeuniqueteamid": 2818,
      "awayuniqueteamid": 2819,
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
      "round": 25,
      "roundname": {
        "_doc": "tableround",
        "_id": 25,
        "name": 25
      },
      "_seasonid": 118691
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 55396411,
      "result": {
        "home": 1,
        "away": 1,
        "period": "nt",
        "winner": null
      },
      "time": {
        "_doc": "time",
        "time": "20:30",
        "date": "18/12/24",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1734553800
      },
      "homeuniqueteamid": 2819,
      "awayuniqueteamid": 2818,
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
      "round": 12,
      "roundname": {
        "_doc": "tableround",
        "_id": 12,
        "name": 12
      },
      "_seasonid": 118691
    }
  ],
  "lastmatchesbetweenteamsonvenue": [
    {
      "_doc": "match_h2h_simple",
      "_id": 50852565,
      "result": {
        "home": 0,
        "away": 1,
        "period": "nt",
        "winner": "away"
      },
      "time": {
        "_doc": "time",
        "time": "15:15",
        "date": "22/02/25",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1740237300
      },
      "homeuniqueteamid": 2818,
      "awayuniqueteamid": 2819,
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
      "round": 25,
      "roundname": {
        "_doc": "tableround",
        "_id": 25,
        "name": 25
      },
      "_seasonid": 118691
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 41893009,
      "result": {
        "home": 1,
        "away": 1,
        "period": "nt",
        "winner": null
      },
      "time": {
        "_doc": "time",
        "time": "14:15",
        "date": "24/09/23",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1695564900
      },
      "homeuniqueteamid": 2818,
      "awayuniqueteamid": 2819,
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
      "round": 6,
      "roundname": {
        "_doc": "tableround",
        "_id": 6,
        "name": 6
      },
      "_seasonid": 106501
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 34277929,
      "result": {
        "home": 2,
        "away": 1,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "17:00",
        "date": "28/05/23",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1685293200
      },
      "homeuniqueteamid": 2818,
      "awayuniqueteamid": 2819,
      "periods": {
        "ft": {
          "home": 2,
          "away": 1
        },
        "p1": {
          "home": 0,
          "away": 0
        }
      },
      "round": 37,
      "roundname": {
        "_doc": "tableround",
        "_id": 37,
        "name": 37
      },
      "_seasonid": 94215
    }
  ],
  "versusmatchstats": {
    "2818": {
      "highestwin": {
        "total": {
          "home": 5,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 5,
          "matchid": 414099,
          "matchuts": 874252800
        },
        "home": {
          "home": 5,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 5,
          "matchid": 414099,
          "matchuts": 874252800
        },
        "away": {
          "home": 1,
          "away": 5,
          "period": "nt",
          "winner": "away",
          "goaldiff": 4,
          "matchid": 363940,
          "matchuts": 968601600
        }
      },
      "totalmatches": {
        "total": 28,
        "home": 14,
        "away": 14
      },
      "teamwins": {
        "total": 6,
        "home": 4,
        "away": 2
      },
      "teamloses": {
        "total": 17,
        "home": 7,
        "away": 10
      },
      "teamdraws": {
        "total": 5,
        "home": 3,
        "away": 2
      },
      "oldestmatchdate": "1997",
      "totalgoals": {
        "total": 33,
        "home": 20,
        "away": 13
      },
      "averagegoals": {
        "total": 1.1785714285714286,
        "home": 1.4285714285714286,
        "away": 0.9285714285714286
      },
      "leadingathalftime": {
        "total": 5,
        "home": 1,
        "away": 4
      },
      "losingathalftime": {
        "total": 12,
        "home": 5,
        "away": 7
      }
    },
    "2819": {
      "highestwin": {
        "total": {
          "home": 4,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 4,
          "matchid": 61624156,
          "matchuts": 1762002000
        },
        "home": {
          "home": 4,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 4,
          "matchid": 61624156,
          "matchuts": 1762002000
        },
        "away": {
          "home": 1,
          "away": 5,
          "period": "nt",
          "winner": "away",
          "goaldiff": 4,
          "matchid": 27965882,
          "matchuts": 1652378400
        }
      },
      "totalmatches": {
        "total": 28,
        "home": 14,
        "away": 14
      },
      "teamwins": {
        "total": 17,
        "home": 10,
        "away": 7
      },
      "teamloses": {
        "total": 6,
        "home": 2,
        "away": 4
      },
      "teamdraws": {
        "total": 5,
        "home": 2,
        "away": 3
      },
      "oldestmatchdate": "1997",
      "totalgoals": {
        "total": 57,
        "home": 32,
        "away": 25
      },
      "averagegoals": {
        "total": 2.0357142857142856,
        "home": 2.2857142857142856,
        "away": 1.7857142857142858
      },
      "leadingathalftime": {
        "total": 12,
        "home": 7,
        "away": 5
      },
      "losingathalftime": {
        "total": 5,
        "home": 4,
        "away": 1
      }
    }
  }
}
```

#### `stats_season_teamscoringconceding`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 3.5 KB | max 3.5 KB | avg 3.5 KB
- queryUrl: stats_season_teamscoringconceding/130805/2818/-1, stats_season_teamscoringconceding/130805/2819/-1
- Campos principales: team, stats
- Qué aporta: Distribución de goles anotados/recibidos por equipo y temporada.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2818,
    "_rcid": 32,
    "_sid": 1,
    "name": "Vallecano",
    "mediumname": "Rayo Vallecano",
    "suffix": null,
    "abbr": "RVC",
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
      "total": 10,
      "home": 6,
      "away": 4
    },
    "scoring": {
      "goalsscored": {
        "total": 37,
        "home": 22,
        "away": 15
      },
      "atleastonegoal": {
        "total": 33,
        "home": 16,
        "away": 17
      },
      "failedtoscore": {
        "total": 12,
        "home": 3,
        "away": 9
      },
      "scoringathalftime": {
        "total": 13,
        "home": 7,
        "away": 6
      },
      "scoringatfulltime": {
        "total": 24,
        "home": 15,
        "away": 9
      },
      "bothteamsscored": {
        "total": 16,
        "home": 10,
        "away": 6
      },
      "goalsscoredfirsthalf": {
        "total": 18,
        "home": 9,
        "away": 9
      },
      "goalsscoredaverage": {
        "total": 1.0277777777777777,
        "home": 1.2222222222222223,
        "away": 0.8333333333333334
      },
      "atleastonegoalaverage": {
        "total": 0.9166666666666666,
        "home": 0.8888888888888888,
        "away": 0.9444444444444444
      },
      "failedtoscoreaverage": {
        "total": 0.3333333333333333,
        "home": 0.16666666666666666,
        "away": 0.5
      }
    },
    "conceding": {
      "goalsconceded": {
        "total": 43,
        "home": 15,
        "away": 28
      },
      "cleansheets": {
        "total": 11,
        "home": 7,
        "away": 4
      },
      "goalsconcededfirsthalf": {
        "total": 18,
        "home": 5,
        "away": 13
      },
      "goalsconcededaverage": {
        "total": 1.1944444444444444,
        "home": 0.8333333333333334,
        "away": 1.5555555555555556
      },
      "cleansheetsaverage": {
        "total": 0.3055555555555556,
        "home": 0.3888888888888889,
        "away": 0.2222222222222222
      },
      "goalsconcededfirsthalfaverage": {
        "total": 0.5,
        "home": 0.2777777777777778,
        "away": 0.7222222222222222
      },
      "minutespergoalconceded": {
        "total": 79.93023255813954,
        "home": 114.06666666666666,
        "away": 61.642857142857146
      },
      "goalsbyminutes": {
        "0-15": {
          "total": 0.1388888888888889,
          "home": 0,
          "away": 0.2777777777777778
        },
        "16-30": {
          "total": 0.16666666666666666,
          "home": 0.16666666666666666,
          "away": 0.16666666666666666
        },
        "31-45": {
          "total": 0.19444444444444445,
          "home": 0.1111111111111111,
          "away": 0.2777777777777778
        },
        "46-60": {
          "total": 0.16666666666666666,
          "home": 0.1111111111111111,
          "away": 0.2222222222222222
        },
        "61-75": {
          "total": 0.19444444444444445,
          "home": 0.1111111111111111,
          "away": 0.2777777777777778
        },
        "76-90": {
          "total": 0.3333333333333333,
          "home": 0.3333333333333333,
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
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 25.3 KB | max 26.0 KB | avg 25.7 KB
- queryUrl: stats_team_lastx/2818/20, stats_team_lastx/2819/20
- Match ids detectados: 61624652, 61624636, 69340064, 61624606, 69340060, 61624566, 61624594, 69340054, 61624546, 69339976
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Últimos partidos de un equipo, útil para forma reciente.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2818,
    "_rcid": 32,
    "_sid": 1,
    "name": "Vallecano",
    "mediumname": "Rayo Vallecano",
    "suffix": null,
    "abbr": "RVC",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624652,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 36,
      "week": 20,
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
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624636,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 35,
      "week": 20,
      "teams": {
        "home": {
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
        },
        "away": {
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
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 69340064,
      "_sid": 1,
      "_rcid": 393,
      "_tid": 104106,
      "_utid": 34480,
      "round": 2,
      "week": 19,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 26360016,
          "_sid": 1,
          "uid": 1659,
          "virtual": false,
          "name": "Strasbourg Alsace",
          "mediumname": "Strasbourg Alsace",
          "abbr": "RCS",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 18598472,
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
    },
    "104106": {
      "_doc": "tournament",
      "_id": 104106,
      "_sid": 1,
      "_rcid": 393,
      "_isk": 15,
      "_tid": 104106,
      "_utid": 34480,
      "_gender": "men",
      "name": "UEFA Conference League, Knockout stage",
      "abbr": "UECL"
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
    "34480": {
      "_doc": "uniquetournament",
      "_id": 34480,
      "_utid": 34480,
      "_sid": 1,
      "_rcid": 393,
      "name": "UEFA Conference League",
      "currentseason": 131637,
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
    },
    "393": {
      "_doc": "realcategory",
      "_id": 393,
      "_sid": 1,
      "_rcid": 393,
      "name": "International Clubs",
      "cc": null
    }
  }
}
```

#### `stats_team_nextx`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 2.6 KB | max 2.6 KB | avg 2.6 KB
- queryUrl: stats_team_nextx/2819/1, stats_team_nextx/2818/1
- Match ids detectados: 61624668
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Próximos partidos del equipo, útil para congestión de calendario.
- Estructura resumida:

```json
{
  "team": {
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
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624668,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 37,
      "week": 20,
      "teams": {
        "home": {
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
        },
        "away": {
          "_doc": "team",
          "_id": 5120,
          "_sid": 1,
          "uid": 2819,
          "virtual": false,
          "name": "Villarreal",
          "mediumname": "Villarreal CF",
          "abbr": "VIL",
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
- Tamaño aprox.: min 2.8 KB | max 3.5 KB | avg 3.2 KB
- queryUrl: stats_team_streaks/2819, stats_team_streaks/2818
- Match ids detectados: 61624668, 61624692, 61624654, 61624626, 61624614, 61624572, 61624586, 61624538, 61624524, 61624516
- Campos principales: team, nextmatches, lastmatchesform, streaks
- Qué aporta: Rachas y forma condensada del equipo.
- Estructura resumida:

```json
{
  "team": {
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
  },
  "nextmatches": [
    {
      "matchdifficultyrating": 3,
      "matchid": 61624668
    },
    {
      "matchdifficultyrating": 5,
      "matchid": 61624692
    }
  ],
  "lastmatchesform": {
    "total": [
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624654
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624626
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624614
      }
    ],
    "home": [
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624654
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624614
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624572
      }
    ],
    "away": [
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624626
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624586
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624538
      }
    ]
  },
  "streaks": {
    "nodrawing": {
      "home": {
        "value": 10,
        "streak": [
          {
            "result": "L",
            "matchid": 61624654
          },
          {
            "result": "W",
            "matchid": 61624614
          },
          {
            "result": "W",
            "matchid": 61624572
          }
        ]
      }
    },
    "goalsscored": {
      "total": {
        "value": 6,
        "streak": [
          {
            "result": 2,
            "matchid": 61624654
          },
          {
            "result": 1,
            "matchid": 61624626
          },
          {
            "result": 5,
            "matchid": 61624614
          }
        ]
      },
      "home": {
        "value": 7,
        "streak": [
          {
            "result": 2,
            "matchid": 61624654
          },
          {
            "result": 5,
            "matchid": 61624614
          },
          {
            "result": 2,
            "matchid": 61624572
          }
        ]
      }
    },
    "goalsconceded": {
      "total": {
        "value": 10,
        "streak": [
          {
            "result": 3,
            "matchid": 61624654
          },
          {
            "result": 1,
            "matchid": 61624626
          },
          {
            "result": 1,
            "matchid": 61624614
          }
        ]
      },
      "home": {
        "value": 10,
        "streak": [
          {
            "result": 3,
            "matchid": 61624654
          },
          {
            "result": 1,
            "matchid": 61624614
          },
          {
            "result": 1,
            "matchid": 61624572
          }
        ]
      },
      "away": {
        "value": 6,
        "streak": [
          {
            "result": 1,
            "matchid": 61624626
          },
          {
            "result": 1,
            "matchid": 61624586
          },
          {
            "result": 1,
            "matchid": 61624538
          }
        ]
      }
    }
  }
}
```

#### `stats_team_versus`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 56.2 KB | max 56.2 KB | avg 56.2 KB
- queryUrl: stats_team_versus/2818/2819
- Match ids detectados: 61624156, 50852565, 55396411, 41893565, 41893009, 34277929, 34277577, 27965882, 27965500, 21087425
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
      "_id": 61624156,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 11,
      "week": 44,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5120,
          "_sid": 1,
          "uid": 2819,
          "virtual": false,
          "name": "Villarreal",
          "mediumname": "Villarreal CF",
          "abbr": "VIL",
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
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 50852565,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 25,
      "week": 8,
      "teams": {
        "home": {
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
        },
        "away": {
          "_doc": "team",
          "_id": 5120,
          "_sid": 1,
          "uid": 2819,
          "virtual": false,
          "name": "Villarreal",
          "mediumname": "Villarreal CF",
          "abbr": "VIL",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 55396411,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 12,
      "week": 51,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5120,
          "_sid": 1,
          "uid": 2819,
          "virtual": false,
          "name": "Villarreal",
          "mediumname": "Villarreal CF",
          "abbr": "VIL",
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
    }
  },
  "teams": {
    "2818": {
      "_doc": "uniqueteam",
      "_id": 2818,
      "_rcid": 32,
      "_sid": 1,
      "name": "Vallecano",
      "mediumname": "Rayo Vallecano",
      "suffix": null,
      "abbr": "RVC",
      "nickname": null,
      "teamtypeid": 0
    },
    "2819": {
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
  "currentmanagers": {
    "2818": [
      {
        "_doc": "player",
        "_id": 99104,
        "name": "Perez, Inigo",
        "fullname": "Perez Soto, Inigo",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "18/01/88",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 569462400
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
          "date": "14/02/24",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1707868800
        }
      }
    ],
    "2819": [
      {
        "_doc": "player",
        "_id": 52990,
        "name": "Marcelino",
        "fullname": "Toral, Marcelino Garcia",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "14/08/65",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": -138326400
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
          "date": "13/11/23",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1699833600
        }
      }
    ]
  },
  "jersey": {
    "2818": {
      "base": "ffffff",
      "sleeve": "000000",
      "number": "000000",
      "type": "short_sleeves",
      "sleevelong": "ffffff",
      "real": true
    },
    "2819": {
      "base": "ffff00",
      "sleeve": "f0e316",
      "number": "1f4e7a",
      "type": "short_sleeves",
      "sleevelong": "ffff00",
      "real": true
    }
  },
  "next": {
    "_doc": "match",
    "_doctype": "generic",
    "_id": 61624668,
    "_sid": 1,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "round": 37,
    "week": 20,
    "teams": {
      "home": {
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
      },
      "away": {
        "_doc": "team",
        "_id": 5120,
        "_sid": 1,
        "uid": 2819,
        "virtual": false,
        "name": "Villarreal",
        "mediumname": "Villarreal CF",
        "abbr": "VIL",
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
- Tamaño aprox.: min 25.3 KB | max 26.0 KB | avg 25.7 KB
- queryUrl: stats_team_lastx/2818/20, stats_team_lastx/2819/20
- Match ids detectados: 61624652, 61624636, 69340064, 61624606, 69340060, 61624566, 61624594, 69340054, 61624546, 69339976
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Últimos partidos de un equipo, útil para forma reciente.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2818,
    "_rcid": 32,
    "_sid": 1,
    "name": "Vallecano",
    "mediumname": "Rayo Vallecano",
    "suffix": null,
    "abbr": "RVC",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624652,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 36,
      "week": 20,
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
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624636,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 35,
      "week": 20,
      "teams": {
        "home": {
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
        },
        "away": {
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
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 69340064,
      "_sid": 1,
      "_rcid": 393,
      "_tid": 104106,
      "_utid": 34480,
      "round": 2,
      "week": 19,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 26360016,
          "_sid": 1,
          "uid": 1659,
          "virtual": false,
          "name": "Strasbourg Alsace",
          "mediumname": "Strasbourg Alsace",
          "abbr": "RCS",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 18598472,
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
    },
    "104106": {
      "_doc": "tournament",
      "_id": 104106,
      "_sid": 1,
      "_rcid": 393,
      "_isk": 15,
      "_tid": 104106,
      "_utid": 34480,
      "_gender": "men",
      "name": "UEFA Conference League, Knockout stage",
      "abbr": "UECL"
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
    "34480": {
      "_doc": "uniquetournament",
      "_id": 34480,
      "_utid": 34480,
      "_sid": 1,
      "_rcid": 393,
      "name": "UEFA Conference League",
      "currentseason": 131637,
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
    },
    "393": {
      "_doc": "realcategory",
      "_id": 393,
      "_sid": 1,
      "_rcid": 393,
      "name": "International Clubs",
      "cc": null
    }
  }
}
```

#### `stats_team_nextx`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 2.6 KB | max 2.6 KB | avg 2.6 KB
- queryUrl: stats_team_nextx/2819/1, stats_team_nextx/2818/1
- Match ids detectados: 61624668
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Próximos partidos del equipo, útil para congestión de calendario.
- Estructura resumida:

```json
{
  "team": {
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
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624668,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 37,
      "week": 20,
      "teams": {
        "home": {
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
        },
        "away": {
          "_doc": "team",
          "_id": 5120,
          "_sid": 1,
          "uid": 2819,
          "virtual": false,
          "name": "Villarreal",
          "mediumname": "Villarreal CF",
          "abbr": "VIL",
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
- Tamaño aprox.: min 2.8 KB | max 3.5 KB | avg 3.2 KB
- queryUrl: stats_team_streaks/2819, stats_team_streaks/2818
- Match ids detectados: 61624668, 61624692, 61624654, 61624626, 61624614, 61624572, 61624586, 61624538, 61624524, 61624516
- Campos principales: team, nextmatches, lastmatchesform, streaks
- Qué aporta: Rachas y forma condensada del equipo.
- Estructura resumida:

```json
{
  "team": {
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
  },
  "nextmatches": [
    {
      "matchdifficultyrating": 3,
      "matchid": 61624668
    },
    {
      "matchdifficultyrating": 5,
      "matchid": 61624692
    }
  ],
  "lastmatchesform": {
    "total": [
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624654
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624626
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624614
      }
    ],
    "home": [
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624654
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624614
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624572
      }
    ],
    "away": [
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624626
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624586
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624538
      }
    ]
  },
  "streaks": {
    "nodrawing": {
      "home": {
        "value": 10,
        "streak": [
          {
            "result": "L",
            "matchid": 61624654
          },
          {
            "result": "W",
            "matchid": 61624614
          },
          {
            "result": "W",
            "matchid": 61624572
          }
        ]
      }
    },
    "goalsscored": {
      "total": {
        "value": 6,
        "streak": [
          {
            "result": 2,
            "matchid": 61624654
          },
          {
            "result": 1,
            "matchid": 61624626
          },
          {
            "result": 5,
            "matchid": 61624614
          }
        ]
      },
      "home": {
        "value": 7,
        "streak": [
          {
            "result": 2,
            "matchid": 61624654
          },
          {
            "result": 5,
            "matchid": 61624614
          },
          {
            "result": 2,
            "matchid": 61624572
          }
        ]
      }
    },
    "goalsconceded": {
      "total": {
        "value": 10,
        "streak": [
          {
            "result": 3,
            "matchid": 61624654
          },
          {
            "result": 1,
            "matchid": 61624626
          },
          {
            "result": 1,
            "matchid": 61624614
          }
        ]
      },
      "home": {
        "value": 10,
        "streak": [
          {
            "result": 3,
            "matchid": 61624654
          },
          {
            "result": 1,
            "matchid": 61624614
          },
          {
            "result": 1,
            "matchid": 61624572
          }
        ]
      },
      "away": {
        "value": 6,
        "streak": [
          {
            "result": 1,
            "matchid": 61624626
          },
          {
            "result": 1,
            "matchid": 61624586
          },
          {
            "result": 1,
            "matchid": 61624538
          }
        ]
      }
    }
  }
}
```

#### `stats_team_versus`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 56.2 KB | max 56.2 KB | avg 56.2 KB
- queryUrl: stats_team_versus/2818/2819
- Match ids detectados: 61624156, 50852565, 55396411, 41893565, 41893009, 34277929, 34277577, 27965882, 27965500, 21087425
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
      "_id": 61624156,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 11,
      "week": 44,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5120,
          "_sid": 1,
          "uid": 2819,
          "virtual": false,
          "name": "Villarreal",
          "mediumname": "Villarreal CF",
          "abbr": "VIL",
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
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 50852565,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 25,
      "week": 8,
      "teams": {
        "home": {
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
        },
        "away": {
          "_doc": "team",
          "_id": 5120,
          "_sid": 1,
          "uid": 2819,
          "virtual": false,
          "name": "Villarreal",
          "mediumname": "Villarreal CF",
          "abbr": "VIL",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 55396411,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 12,
      "week": 51,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5120,
          "_sid": 1,
          "uid": 2819,
          "virtual": false,
          "name": "Villarreal",
          "mediumname": "Villarreal CF",
          "abbr": "VIL",
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
    }
  },
  "teams": {
    "2818": {
      "_doc": "uniqueteam",
      "_id": 2818,
      "_rcid": 32,
      "_sid": 1,
      "name": "Vallecano",
      "mediumname": "Rayo Vallecano",
      "suffix": null,
      "abbr": "RVC",
      "nickname": null,
      "teamtypeid": 0
    },
    "2819": {
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
  "currentmanagers": {
    "2818": [
      {
        "_doc": "player",
        "_id": 99104,
        "name": "Perez, Inigo",
        "fullname": "Perez Soto, Inigo",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "18/01/88",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 569462400
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
          "date": "14/02/24",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1707868800
        }
      }
    ],
    "2819": [
      {
        "_doc": "player",
        "_id": 52990,
        "name": "Marcelino",
        "fullname": "Toral, Marcelino Garcia",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "14/08/65",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": -138326400
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
          "date": "13/11/23",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1699833600
        }
      }
    ]
  },
  "jersey": {
    "2818": {
      "base": "ffffff",
      "sleeve": "000000",
      "number": "000000",
      "type": "short_sleeves",
      "sleevelong": "ffffff",
      "real": true
    },
    "2819": {
      "base": "ffff00",
      "sleeve": "f0e316",
      "number": "1f4e7a",
      "type": "short_sleeves",
      "sleevelong": "ffff00",
      "real": true
    }
  },
  "next": {
    "_doc": "match",
    "_doctype": "generic",
    "_id": 61624668,
    "_sid": 1,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "round": 37,
    "week": 20,
    "teams": {
      "home": {
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
      },
      "away": {
        "_doc": "team",
        "_id": 5120,
        "_sid": 1,
        "uid": 2819,
        "virtual": false,
        "name": "Villarreal",
        "mediumname": "Villarreal CF",
        "abbr": "VIL",
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
- Tamaño aprox.: min 9.8 KB | max 13.0 KB | avg 11.4 KB
- queryUrl: stats_season_topassists/130805/2819, stats_season_topassists/130805/2818
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
      "_id": 1981109,
      "playerid": 1981109,
      "player": {
        "_doc": "player",
        "_id": 1981109,
        "name": "Mikautadze, Georges",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "31/10/00",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 972950400
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 79,
          "a2": "ge",
          "name": "Georgia",
          "a3": "GEO",
          "ioc": "GEO",
          "continentid": 1,
          "continent": "Europe",
          "population": 3718000
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
        "2819": {
          "active": true,
          "lastevent": "2026-05-13 18:28:52",
          "started": 22,
          "matches": 31,
          "assists": 6,
          "minutes_played": 2029,
          "substituted_in": 9,
          "shirtnumber": "9"
        }
      },
      "total": {
        "matches": 31,
        "assists": 6,
        "minutes_played": 2029,
        "substituted_in": 9
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 593526,
      "playerid": 593526,
      "player": {
        "_doc": "player",
        "_id": 593526,
        "name": "Pepe, Nicolas",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "29/05/95",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 801705600
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 53,
          "a2": "ci",
          "name": "Cote d’Ivoire",
          "a3": "CIV",
          "ioc": "CIV",
          "continentid": 4,
          "continent": "Africa",
          "population": 21100000
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
        "jerseynumber": 19
      },
      "teams": {
        "2819": {
          "active": true,
          "lastevent": "2026-05-13 18:19:26",
          "started": 25,
          "matches": 35,
          "assists": 6,
          "minutes_played": 2306,
          "substituted_in": 10,
          "shirtnumber": "19"
        }
      },
      "total": {
        "matches": 35,
        "assists": 6,
        "minutes_played": 2306,
        "substituted_in": 10
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 1008335,
      "playerid": 1008335,
      "player": {
        "_doc": "player",
        "_id": 1008335,
        "name": "Comesana, Santi",
        "fullname": "Comesana Veiga, Santiago",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "05/10/96",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 844473600
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
        "jerseynumber": 14
      },
      "teams": {
        "2819": {
          "active": true,
          "lastevent": "2026-05-13 18:29:02",
          "started": 27,
          "matches": 33,
          "assists": 6,
          "minutes_played": 2349,
          "substituted_in": 6,
          "shirtnumber": "14"
        }
      },
      "total": {
        "matches": 33,
        "assists": 6,
        "minutes_played": 2349,
        "substituted_in": 6
      }
    }
  ],
  "teams": {
    "2819": {
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
  }
}
```

#### `stats_season_topcards`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 19.1 KB | max 21.9 KB | avg 20.5 KB
- queryUrl: stats_season_topcards/130805/2818, stats_season_topcards/130805/2819
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
      "_id": 1247646,
      "playerid": 1247646,
      "player": {
        "_doc": "player",
        "_id": 1247646,
        "name": "Ciss, Pathe",
        "fullname": "Ciss, Pathe Ismael",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "16/03/94",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 763776000
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 188,
          "a2": "sn",
          "name": "Senegal",
          "a3": "SEN",
          "ioc": "SEN",
          "continentid": 4,
          "continent": "Africa",
          "population": 15416000
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
        "jerseynumber": 6
      },
      "teams": {
        "2818": {
          "active": true,
          "lastevent": "2026-05-14 18:23:15",
          "started": 19,
          "yellow_cards": 8,
          "red_cards": 2,
          "matches": 27,
          "minutes_played": 1876,
          "substituted_in": 8,
          "number_of_cards_1st_half": 1,
          "number_of_cards_2nd_half": 9
        }
      },
      "total": {
        "yellow_cards": 8,
        "red_cards": 2,
        "matches": 27,
        "minutes_played": 1876,
        "substituted_in": 8,
        "number_of_cards_1st_half": 1,
        "number_of_cards_2nd_half": 9
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 2530597,
      "playerid": 2530597,
      "player": {
        "_doc": "player",
        "_id": 2530597,
        "name": "Mendy, Nobel",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "03/09/04",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1094169600
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 188,
          "a2": "sn",
          "name": "Senegal",
          "a3": "SEN",
          "ioc": "SEN",
          "continentid": 4,
          "continent": "Africa",
          "population": 15416000
        },
        "secondarynationality": {
          "_doc": "countrycode",
          "_id": 90,
          "a2": "gw",
          "name": "Guinea-Bissau",
          "a3": "GNB",
          "ioc": "GBS",
          "continentid": 4,
          "continent": "Africa",
          "population": 1815000
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
        "jerseynumber": 0
      },
      "teams": {
        "2818": {
          "active": true,
          "lastevent": "2026-05-14 16:14:55",
          "started": 21,
          "yellow_cards": 7,
          "yellowred_cards": 1,
          "red_cards": 1,
          "matches": 23,
          "minutes_played": 1715,
          "substituted_in": 2,
          "number_of_cards_1st_half": 7
        }
      },
      "total": {
        "yellow_cards": 7,
        "yellowred_cards": 1,
        "red_cards": 1,
        "matches": 23,
        "minutes_played": 1715,
        "substituted_in": 2,
        "number_of_cards_1st_half": 7,
        "number_of_cards_2nd_half": 3
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 891282,
      "playerid": 891282,
      "player": {
        "_doc": "player",
        "_id": 891282,
        "name": "Palazon, Isi",
        "fullname": "Palazon Camacho, Isaac",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "27/12/94",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 788486400
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
        "jerseynumber": 7
      },
      "teams": {
        "2818": {
          "active": true,
          "lastevent": "2026-04-26 14:19:10",
          "started": 27,
          "yellow_cards": 10,
          "red_cards": 1,
          "matches": 31,
          "minutes_played": 2266,
          "substituted_in": 4,
          "number_of_cards_1st_half": 5,
          "number_of_cards_2nd_half": 6
        }
      },
      "total": {
        "yellow_cards": 10,
        "red_cards": 1,
        "matches": 31,
        "minutes_played": 2266,
        "substituted_in": 4,
        "number_of_cards_1st_half": 5,
        "number_of_cards_2nd_half": 6
      }
    }
  ],
  "teams": {
    "2818": {
      "_doc": "uniqueteam",
      "_id": 2818,
      "_rcid": 32,
      "_sid": 1,
      "name": "Vallecano",
      "mediumname": "Rayo Vallecano",
      "suffix": null,
      "abbr": "RVC",
      "nickname": null,
      "teamtypeid": 0
    }
  }
}
```

#### `stats_season_topgoals`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 13.2 KB | max 16.0 KB | avg 14.6 KB
- queryUrl: stats_season_topgoals/130805/2818, stats_season_topgoals/130805/2819
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
      "_id": 1793402,
      "playerid": 1793402,
      "player": {
        "_doc": "player",
        "_id": 1793402,
        "name": "De Frutos, Jorge",
        "fullname": "de Frutos Sebastian, Jorge",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "20/02/97",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 856396800
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
        "jerseynumber": 19
      },
      "teams": {
        "2818": {
          "active": true,
          "lastevent": "2026-05-14 18:22:53",
          "started": 30,
          "goals": 10,
          "matches": 34,
          "penalties": 1,
          "goal_points": 11,
          "minutes_played": 2350,
          "substituted_in": 4,
          "first_goals": 6
        }
      },
      "total": {
        "goals": 10,
        "matches": 34,
        "penalties": 1,
        "goal_points": 11,
        "minutes_played": 2350,
        "substituted_in": 4,
        "first_goals": 6,
        "last_goals": 1
      },
      "home": {
        "goals": 6
      },
      "away": {
        "goals": 4
      },
      "firsthalf": {
        "goals": 7
      },
      "secondhalf": {
        "goals": 3
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 345111,
      "playerid": 345111,
      "player": {
        "_doc": "player",
        "_id": 345111,
        "name": "Garcia, Alvaro",
        "fullname": "Garcia Rivera, Alvaro",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "27/10/92",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 720144000
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
        "jerseynumber": 18
      },
      "teams": {
        "2818": {
          "active": true,
          "lastevent": "2026-04-12 15:52:13",
          "started": 22,
          "goals": 4,
          "matches": 31,
          "goal_points": 9,
          "minutes_played": 2062,
          "substituted_in": 9,
          "last_goals": 2,
          "shirtnumber": "18"
        }
      },
      "total": {
        "goals": 4,
        "matches": 31,
        "goal_points": 9,
        "minutes_played": 2062,
        "substituted_in": 9,
        "last_goals": 2
      },
      "home": {
        "goals": 1
      },
      "away": {
        "goals": 3
      },
      "firsthalf": {
        "goals": 1
      },
      "secondhalf": {
        "goals": 3
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 891282,
      "playerid": 891282,
      "player": {
        "_doc": "player",
        "_id": 891282,
        "name": "Palazon, Isi",
        "fullname": "Palazon Camacho, Isaac",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "27/12/94",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 788486400
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
        "jerseynumber": 7
      },
      "teams": {
        "2818": {
          "active": true,
          "lastevent": "2026-04-26 13:31:20",
          "started": 27,
          "goals": 3,
          "matches": 31,
          "penalties": 2,
          "goal_points": 6,
          "minutes_played": 2266,
          "substituted_in": 4,
          "last_goals": 2
        }
      },
      "total": {
        "goals": 3,
        "matches": 31,
        "penalties": 2,
        "goal_points": 6,
        "minutes_played": 2266,
        "substituted_in": 4,
        "last_goals": 2
      },
      "home": {
        "goals": 1
      },
      "away": {
        "goals": 2
      },
      "firsthalf": {
        "goals": 3
      }
    }
  ],
  "teams": {
    "2818": {
      "_doc": "uniqueteam",
      "_id": 2818,
      "_rcid": 32,
      "_sid": 1,
      "name": "Vallecano",
      "mediumname": "Rayo Vallecano",
      "suffix": null,
      "abbr": "RVC",
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
- queryUrl: match_markets/61624668
- Campos principales: markets
- Qué aporta: Mercados y odds del partido por HTTP; hoy es el hallazgo más fuerte del lado odds.
- Estructura resumida:

```json
{
  "markets": [
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624668,
      "_marketId": 1,
      "_uts": 1778923988,
      "specifiers": null,
      "name": "1x2",
      "nameShort": "1x2",
      "active": true,
      "type": "prematch"
    },
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624668,
      "_marketId": 10,
      "_uts": 1778924082,
      "specifiers": null,
      "name": "Double chance",
      "nameShort": "Double chance",
      "active": true,
      "type": "prematch"
    },
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624668,
      "_marketId": 11,
      "_uts": 1778924082,
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
- Tamaño aprox.: min 352.3 KB | max 389.6 KB | avg 371.0 KB
- queryUrl: uniqueteam_markets/2819, uniqueteam_markets/2818
- Campos principales: matches
- Qué aporta: Mercados por equipo sobre matches relacionados, útil para análisis complementario.
- Estructura resumida:

```json
{
  "matches": {
    "50852803": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 50852803,
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
          "_matchId": 50852803,
          "_marketId": 10,
          "_uts": 1747587009,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 50852803,
          "_marketId": 11,
          "_uts": 1747586649,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "50852839": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 50852839,
          "_marketId": 1,
          "_uts": 1748181046,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 50852839,
          "_marketId": 10,
          "_uts": 1748181009,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 50852839,
          "_marketId": 11,
          "_uts": 1748181009,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "60827317": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 60827317,
          "_marketId": 1,
          "_uts": 1754142083,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 60827317,
          "_marketId": 10,
          "_uts": 1754142249,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 60827317,
          "_marketId": 11,
          "_uts": 1754142009,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61623442": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623442,
          "_marketId": 1,
          "_uts": 1755283331,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623442,
          "_marketId": 10,
          "_uts": 1755283209,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623442,
          "_marketId": 11,
          "_uts": 1755286090,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61623976": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623976,
          "_marketId": 1,
          "_uts": 1756055632,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623976,
          "_marketId": 10,
          "_uts": 1756056129,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623976,
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
    "61623980": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623980,
          "_marketId": 1,
          "_uts": 1756655925,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623980,
          "_marketId": 10,
          "_uts": 1756655925,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623980,
          "_marketId": 11,
          "_uts": 1756655925,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": false,
          "type": "prematch"
        }
      ]
    },
    "61623998": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623998,
          "_marketId": 1,
          "_uts": 1757793551,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623998,
          "_marketId": 10,
          "_uts": 1757793554,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623998,
          "_marketId": 11,
          "_uts": 1757793554,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": false,
          "type": "prematch"
        }
      ]
    },
    "61624036": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624036,
          "_marketId": 1,
          "_uts": 1758383843,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624036,
          "_marketId": 10,
          "_uts": 1758383840,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624036,
          "_marketId": 11,
          "_uts": 1758382522,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "61624046": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624046,
          "_marketId": 1,
          "_uts": 1758659369,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624046,
          "_marketId": 10,
          "_uts": 1758659369,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624046,
          "_marketId": 11,
          "_uts": 1758659369,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": false,
          "type": "prematch"
        }
      ]
    },
    "61624070": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624070,
          "_marketId": 1,
          "_uts": 1758999565,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624070,
          "_marketId": 10,
          "_uts": 1758999554,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624070,
          "_marketId": 11,
          "_uts": 1758999554,
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
