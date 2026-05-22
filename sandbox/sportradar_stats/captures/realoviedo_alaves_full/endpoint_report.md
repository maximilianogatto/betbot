# Sportradar Stats Filtered Endpoint Report

- Capture dir: `/Users/maximilianogatto/Library/CloudStorage/OneDrive-Personal/Apuestas/BetBot/sandbox/sportradar_stats/captures/realoviedo_alaves_full`
- Source usado: `filtered_fetch.ndjson`
- Responses útiles filtradas: 30
- Endpoints limpios detectados: 21

## Resumen Ejecutivo

- `match_markets` expone mercados/odds por HTTP. En esta captura devolvió 11 markets, incluyendo 1X2 y handicaps.
- `match_timeline` / `match_timelinedelta` son los candidatos más fuertes para detectar `live`, score, estado y timeline. Ambos usan `_maxage` corto.
- `event_get` parece un feed live global y no necesariamente del partido abierto: en esta captura apunta a match id(s) 71001364, 66777416, 67648462, 67904438, 67694248, mientras el match principal fue 61624672.
- Hay buen contexto pre-match por HTTP: forma reciente, tabla, streaks, head-to-head y slices de standings.
- También aparecen endpoints útiles para enriquecer análisis: lesiones y leaders de goles, tarjetas y asistencias.

## Endpoints Detectados

| Endpoint | Hits | Polling | Tamaño aprox. | Categorías |
| --- | ---: | :---: | ---: | --- |
| `stats_season_tables` | 2 | Sí | 21.4 KB | Tabla y standings |
| `stats_season_teamscoringconceding` | 2 | Sí | 3.5 KB | Stats pre-match y contexto |
| `stats_season_topassists` | 2 | Sí | 10.3 KB | Jugadores y leaders |
| `stats_season_topcards` | 2 | Sí | 22.8 KB | Jugadores y leaders |
| `stats_season_topgoals` | 2 | Sí | 10.3 KB | Jugadores y leaders |
| `stats_team_lastx` | 2 | Sí | 22.5 KB | Stats pre-match y contexto, Forma reciente |
| `stats_team_nextx` | 2 | Sí | 2.5 KB | Stats pre-match y contexto, Forma reciente |
| `stats_team_streaks` | 2 | Sí | 2.4 KB | Stats pre-match y contexto, Forma reciente |
| `uniqueteam_markets` | 2 | Sí | 298.0 KB | Mercados y odds |
| `event_get` | 1 | Sí | 326.0 KB | Score y estado live, Timeline y eventos live |
| `match_details` | 1 | Sí | 113.0 B | Metadata del partido |
| `match_info_statshub` | 1 | No | 7.2 KB | Metadata del partido |
| `match_markets` | 1 | No | 6.5 KB | Mercados y odds |
| `match_timeline` | 1 | Sí | 2.3 KB | Score y estado live, Timeline y eventos live |
| `match_timelinedelta` | 1 | Sí | 2.4 KB | Score y estado live, Timeline y eventos live |
| `odds_ukformat` | 1 | No | 9.6 KB | Mercados y odds |
| `stats_formtable` | 1 | No | 53.5 KB | Forma reciente, Tabla y standings |
| `stats_h2h_versus` | 1 | Sí | 14.7 KB | Stats pre-match y contexto |
| `stats_match_get` | 1 | No | 5.6 KB | Metadata del partido, Score y estado live |
| `stats_season_injuries` | 1 | No | 58.3 KB | Lesiones |
| `stats_team_versus` | 1 | No | 26.5 KB | Stats pre-match y contexto, Forma reciente |

## Endpoints por Caso de Uso

### Metadata del partido

#### `match_details`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage)
- Tamaño aprox.: min 113.0 B | max 113.0 B | avg 113.0 B
- queryUrl: match_details/61624672
- Qué aporta: Detalle auxiliar del match; en esta muestra vino vacío.
- Estructura resumida:

```json
[]
```

#### `match_info_statshub`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 7.2 KB | max 7.2 KB | avg 7.2 KB
- queryUrl: match_info_statshub/61624672
- Match ids detectados: 61624672
- Campos principales: _doc, match, cities, stadium, tournament, uniquetournament, sport, realcategory, season, referee, manager, jerseys
- Qué aporta: Metadata fuerte del partido: torneo, estadio, ciudades, coverage y contexto del evento.
- Estructura resumida:

```json
{
  "_doc": "match_info",
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624672,
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
      "_id": 892,
      "name": "Oviedo"
    },
    "away": {
      "_id": 4586,
      "name": "Vitoria-Gasteiz"
    }
  },
  "stadium": {
    "_doc": "stadium",
    "_id": "2842",
    "name": "Carlos Tartiere",
    "description": "",
    "city": "Oviedo",
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
    "capacity": "30500",
    "hometeams": [
      {
        "_doc": "uniqueteam",
        "_id": 2851,
        "_rcid": 32,
        "_sid": 1,
        "name": "Oviedo",
        "mediumname": "Real Oviedo",
        "suffix": null,
        "abbr": "OVI",
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
    "_id": 129521,
    "name": "Munuera Montero, Jose Luis",
    "birthdate": {
      "_doc": "time",
      "time": "00:00",
      "date": "19/05/83",
      "tz": "UTC",
      "tzoffset": 0,
      "uts": 422150400
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
- queryUrl: stats_match_get/61624672
- Match ids detectados: 61624672
- Campos principales: _doc, _doctype, _id, _sid, _rcid, _tid, _utid, round, week, teams, tobeannounced, postponed
- Qué aporta: Snapshot del match con ids, hora, equipos, resultado y señales de live/inlivescore.
- Estructura resumida:

```json
{
  "_doc": "match",
  "_doctype": "generic",
  "_id": 61624672,
  "_sid": 1,
  "_rcid": 32,
  "_tid": 36,
  "_utid": 8,
  "round": 37,
  "week": 20,
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
      "_id": 5123,
      "_sid": 1,
      "uid": 2885,
      "virtual": false,
      "name": "Alaves",
      "mediumname": "Deportivo Alaves",
      "abbr": "ALA",
      "nickname": null,
      "iscountry": false
    }
  }
}
```

### Score y estado live

#### `event_get`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 326.0 KB | max 326.0 KB | avg 326.0 KB
- queryUrl: event_get/
- Match ids detectados: 71001364, 66777416, 67648462, 67904438, 67694248, 67904152, 67817706, 71530068, 71529870, 71527796
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
    "_id": 2361796534,
    "_scoutid": null,
    "_sid": 3,
    "_rcid": 211,
    "_tid": 2099,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778990403
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
  }
]
```

#### `match_timeline`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 2.3 KB | max 2.3 KB | avg 2.3 KB
- queryUrl: match_timeline/61624672
- Match ids detectados: 61624672
- Campos principales: match, events
- Qué aporta: Estado del partido y timeline principal. Es el candidato más claro para live state del fixture abierto.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624672,
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
- queryUrl: match_timelinedelta/61624672
- Match ids detectados: 61624672
- Campos principales: match, events
- Qué aporta: Delta del timeline, ideal para polling liviano cuando el partido está en vivo.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624672,
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
- queryUrl: stats_match_get/61624672
- Match ids detectados: 61624672
- Campos principales: _doc, _doctype, _id, _sid, _rcid, _tid, _utid, round, week, teams, tobeannounced, postponed
- Qué aporta: Snapshot del match con ids, hora, equipos, resultado y señales de live/inlivescore.
- Estructura resumida:

```json
{
  "_doc": "match",
  "_doctype": "generic",
  "_id": 61624672,
  "_sid": 1,
  "_rcid": 32,
  "_tid": 36,
  "_utid": 8,
  "round": 37,
  "week": 20,
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
      "_id": 5123,
      "_sid": 1,
      "uid": 2885,
      "virtual": false,
      "name": "Alaves",
      "mediumname": "Deportivo Alaves",
      "abbr": "ALA",
      "nickname": null,
      "iscountry": false
    }
  }
}
```

### Timeline y eventos live

#### `event_get`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 326.0 KB | max 326.0 KB | avg 326.0 KB
- queryUrl: event_get/
- Match ids detectados: 71001364, 66777416, 67648462, 67904438, 67694248, 67904152, 67817706, 71530068, 71529870, 71527796
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
    "_id": 2361796534,
    "_scoutid": null,
    "_sid": 3,
    "_rcid": 211,
    "_tid": 2099,
    "_dc": false,
    "_typeid": "22",
    "uts": 1778990403
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
  }
]
```

#### `match_timeline`
- Hits: 1 | Status: 200:1 | Polling: sí (short_maxage+live_endpoint_name)
- Tamaño aprox.: min 2.3 KB | max 2.3 KB | avg 2.3 KB
- queryUrl: match_timeline/61624672
- Match ids detectados: 61624672
- Campos principales: match, events
- Qué aporta: Estado del partido y timeline principal. Es el candidato más claro para live state del fixture abierto.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624672,
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
- queryUrl: match_timelinedelta/61624672
- Match ids detectados: 61624672
- Campos principales: match, events
- Qué aporta: Delta del timeline, ideal para polling liviano cuando el partido está en vivo.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624672,
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
- Tamaño aprox.: min 14.7 KB | max 14.7 KB | avg 14.7 KB
- queryUrl: stats_h2h_versus/2851/2885/61624672
- Match ids detectados: 61624672, 1442987, 364016
- Campos principales: match, lastmatchesbetweenteams, lastmatchesbetweenteamsonvenue, versusmatchstats
- Qué aporta: Historial comparativo y versus stats entre ambos equipos.
- Estructura resumida:

```json
{
  "match": {
    "_doc": "match",
    "_doctype": "soccer",
    "_id": 61624672,
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
      "_id": 61624278,
      "result": {
        "home": 1,
        "away": 1,
        "period": "nt",
        "winner": null
      },
      "time": {
        "_doc": "time",
        "time": "17:30",
        "date": "04/01/26",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1767547800
      },
      "homeuniqueteamid": 2885,
      "awayuniqueteamid": 2851,
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
      "round": 18,
      "roundname": {
        "_doc": "tableround",
        "_id": 18,
        "name": 18
      },
      "_seasonid": 130805
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 34278899,
      "result": {
        "home": 1,
        "away": 0,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "20:00",
        "date": "13/01/23",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1673640000
      },
      "homeuniqueteamid": 2851,
      "awayuniqueteamid": 2885,
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
      "round": 23,
      "roundname": {
        "_doc": "tableround",
        "_id": 23,
        "name": 23
      },
      "_seasonid": 94827
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 34278667,
      "result": {
        "home": 2,
        "away": 1,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "16:30",
        "date": "29/10/22",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1667061000
      },
      "homeuniqueteamid": 2885,
      "awayuniqueteamid": 2851,
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
      "round": 13,
      "roundname": {
        "_doc": "tableround",
        "_id": 13,
        "name": 13
      },
      "_seasonid": 94827
    }
  ],
  "lastmatchesbetweenteamsonvenue": [
    {
      "_doc": "match_h2h_simple",
      "_id": 34278899,
      "result": {
        "home": 1,
        "away": 0,
        "period": "nt",
        "winner": "home"
      },
      "time": {
        "_doc": "time",
        "time": "20:00",
        "date": "13/01/23",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1673640000
      },
      "homeuniqueteamid": 2851,
      "awayuniqueteamid": 2885,
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
      "round": 23,
      "roundname": {
        "_doc": "tableround",
        "_id": 23,
        "name": 23
      },
      "_seasonid": 94827
    },
    {
      "_doc": "match_h2h_simple",
      "_id": 7616552,
      "result": {
        "home": 1,
        "away": 1,
        "period": "nt",
        "winner": null
      },
      "time": {
        "_doc": "time",
        "time": "19:15",
        "date": "30/01/16",
        "tz": "UTC",
        "tzoffset": 0,
        "uts": 1454181300
      },
      "homeuniqueteamid": 2851,
      "awayuniqueteamid": 2885,
      "periods": {
        "ft": {
          "home": 1,
          "away": 1
        },
        "p1": {
          "home": 1,
          "away": 0
        }
      },
      "round": 23,
      "roundname": {
        "_doc": "tableround",
        "_id": 23,
        "name": 23
      },
      "_seasonid": 10702
    }
  ],
  "versusmatchstats": {
    "2851": {
      "highestwin": {
        "total": {
          "home": 2,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 2,
          "matchid": 1442987,
          "matchuts": 1300642200
        },
        "home": {
          "home": 2,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 2,
          "matchid": 1442987,
          "matchuts": 1300642200
        },
        "away": null
      },
      "totalmatches": {
        "total": 15,
        "home": 6,
        "away": 7
      },
      "teamwins": {
        "total": 4,
        "home": 4,
        "away": 0
      },
      "teamloses": {
        "total": 7,
        "home": 0,
        "away": 5
      },
      "teamdraws": {
        "total": 4,
        "home": 2,
        "away": 2
      },
      "oldestmatchdate": "1998",
      "totalgoals": {
        "total": 15,
        "home": 9,
        "away": 5
      },
      "averagegoals": {
        "total": 1,
        "home": 1.5,
        "away": 0.7142857142857143
      },
      "leadingathalftime": {
        "total": 4,
        "home": 4,
        "away": 0
      },
      "losingathalftime": {
        "total": 5,
        "home": 0,
        "away": 5
      }
    },
    "2885": {
      "highestwin": {
        "total": {
          "home": 4,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 4,
          "matchid": 364016,
          "matchuts": 973443600
        },
        "home": {
          "home": 4,
          "away": 0,
          "period": "nt",
          "winner": "home",
          "goaldiff": 4,
          "matchid": 364016,
          "matchuts": 973443600
        },
        "away": null
      },
      "totalmatches": {
        "total": 15,
        "home": 7,
        "away": 6
      },
      "teamwins": {
        "total": 7,
        "home": 5,
        "away": 0
      },
      "teamloses": {
        "total": 4,
        "home": 0,
        "away": 4
      },
      "teamdraws": {
        "total": 4,
        "home": 2,
        "away": 2
      },
      "oldestmatchdate": "1998",
      "totalgoals": {
        "total": 21,
        "home": 14,
        "away": 4
      },
      "averagegoals": {
        "total": 1.4,
        "home": 2,
        "away": 0.6666666666666666
      },
      "leadingathalftime": {
        "total": 5,
        "home": 5,
        "away": 0
      },
      "losingathalftime": {
        "total": 4,
        "home": 0,
        "away": 4
      }
    }
  }
}
```

#### `stats_season_teamscoringconceding`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 3.4 KB | max 3.5 KB | avg 3.5 KB
- queryUrl: stats_season_teamscoringconceding/130805/2851/-1, stats_season_teamscoringconceding/130805/2885/-1
- Campos principales: team, stats
- Qué aporta: Distribución de goles anotados/recibidos por equipo y temporada.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2851,
    "_rcid": 32,
    "_sid": 1,
    "name": "Oviedo",
    "mediumname": "Real Oviedo",
    "suffix": null,
    "abbr": "OVI",
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
      "total": 6,
      "home": 4,
      "away": 2
    },
    "scoring": {
      "goalsscored": {
        "total": 26,
        "home": 9,
        "away": 17
      },
      "atleastonegoal": {
        "total": 31,
        "home": 13,
        "away": 18
      },
      "failedtoscore": {
        "total": 19,
        "home": 9,
        "away": 10
      },
      "scoringathalftime": {
        "total": 10,
        "home": 5,
        "away": 5
      },
      "scoringatfulltime": {
        "total": 17,
        "home": 9,
        "away": 8
      },
      "bothteamsscored": {
        "total": 12,
        "home": 5,
        "away": 7
      },
      "goalsscoredfirsthalf": {
        "total": 12,
        "home": 5,
        "away": 7
      },
      "goalsscoredaverage": {
        "total": 0.7222222222222222,
        "home": 0.5,
        "away": 0.9444444444444444
      },
      "atleastonegoalaverage": {
        "total": 0.8611111111111112,
        "home": 0.7222222222222222,
        "away": 1
      },
      "failedtoscoreaverage": {
        "total": 0.5277777777777778,
        "home": 0.5,
        "away": 0.5555555555555556
      }
    },
    "conceding": {
      "goalsconceded": {
        "total": 56,
        "home": 17,
        "away": 39
      },
      "cleansheets": {
        "total": 10,
        "home": 9,
        "away": 1
      },
      "goalsconcededfirsthalf": {
        "total": 24,
        "home": 5,
        "away": 19
      },
      "goalsconcededaverage": {
        "total": 1.5555555555555556,
        "home": 0.9444444444444444,
        "away": 2.1666666666666665
      },
      "cleansheetsaverage": {
        "total": 0.2777777777777778,
        "home": 0.5,
        "away": 0.05555555555555555
      },
      "goalsconcededfirsthalfaverage": {
        "total": 0.6666666666666666,
        "home": 0.2777777777777778,
        "away": 1.0555555555555556
      },
      "minutespergoalconceded": {
        "total": 61.25,
        "home": 100.76470588235294,
        "away": 44.02564102564103
      },
      "goalsbyminutes": {
        "0-15": {
          "total": 0.16666666666666666,
          "home": 0.1111111111111111,
          "away": 0.2222222222222222
        },
        "16-30": {
          "total": 0.25,
          "home": 0.1111111111111111,
          "away": 0.3888888888888889
        },
        "31-45": {
          "total": 0.25,
          "home": 0.05555555555555555,
          "away": 0.4444444444444444
        },
        "46-60": {
          "total": 0.2222222222222222,
          "home": 0.1111111111111111,
          "away": 0.3333333333333333
        },
        "61-75": {
          "total": 0.2777777777777778,
          "home": 0.2222222222222222,
          "away": 0.3333333333333333
        },
        "76-90": {
          "total": 0.3888888888888889,
          "home": 0.3333333333333333,
          "away": 0.4444444444444444
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
- Tamaño aprox.: min 21.6 KB | max 23.3 KB | avg 22.5 KB
- queryUrl: stats_team_lastx/2885/20, stats_team_lastx/2851/20
- Match ids detectados: 61624638, 61624628, 61624598, 61624558, 61624588, 61624548, 61624518, 61624510, 61624478, 61624466
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Últimos partidos de un equipo, útil para forma reciente.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2885,
    "_rcid": 32,
    "_sid": 1,
    "name": "Alaves",
    "mediumname": "Deportivo Alaves",
    "suffix": null,
    "abbr": "ALA",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624638,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 36,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5123,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        },
        "away": {
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
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624628,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 35,
      "week": 19,
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
          "_id": 5123,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624598,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 34,
      "week": 18,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5123,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5133,
          "_sid": 1,
          "uid": 2825,
          "virtual": false,
          "name": "Bilbao",
          "mediumname": "Athletic Bilbao",
          "abbr": "ATH",
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
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 2.5 KB | max 2.5 KB | avg 2.5 KB
- queryUrl: stats_team_nextx/2885/1, stats_team_nextx/2851/1
- Match ids detectados: 61624672
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Próximos partidos del equipo, útil para congestión de calendario.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2885,
    "_rcid": 32,
    "_sid": 1,
    "name": "Alaves",
    "mediumname": "Deportivo Alaves",
    "suffix": null,
    "abbr": "ALA",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624672,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 37,
      "week": 20,
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
          "_id": 5123,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
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
- Tamaño aprox.: min 1.9 KB | max 2.9 KB | avg 2.4 KB
- queryUrl: stats_team_streaks/2885, stats_team_streaks/2851
- Match ids detectados: 61624672, 61624678, 61624638, 61624628, 61624598, 61624558, 61624588, 61624548, 61624518, 61624510
- Campos principales: team, nextmatches, lastmatchesform, streaks
- Qué aporta: Rachas y forma condensada del equipo.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2885,
    "_rcid": 32,
    "_sid": 1,
    "name": "Alaves",
    "mediumname": "Deportivo Alaves",
    "suffix": null,
    "abbr": "ALA",
    "nickname": null,
    "teamtypeid": 0
  },
  "nextmatches": [
    {
      "matchdifficultyrating": 2,
      "matchid": 61624672
    },
    {
      "matchdifficultyrating": 1,
      "matchid": 61624678
    }
  ],
  "lastmatchesform": {
    "total": [
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624638
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624628
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624598
      }
    ],
    "home": [
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624638
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624598
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624558
      }
    ],
    "away": [
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624628
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624588
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624548
      }
    ]
  },
  "streaks": {
    "goalsscored": {
      "total": {
        "value": 10,
        "streak": [
          {
            "result": 1,
            "matchid": 61624638
          },
          {
            "result": 1,
            "matchid": 61624628
          },
          {
            "result": 2,
            "matchid": 61624598
          }
        ]
      },
      "home": {
        "value": 6,
        "streak": [
          {
            "result": 1,
            "matchid": 61624638
          },
          {
            "result": 2,
            "matchid": 61624598
          },
          {
            "result": 2,
            "matchid": 61624558
          }
        ]
      },
      "away": {
        "value": 5,
        "streak": [
          {
            "result": 1,
            "matchid": 61624628
          },
          {
            "result": 1,
            "matchid": 61624588
          },
          {
            "result": 3,
            "matchid": 61624548
          }
        ]
      }
    },
    "goalsconceded": {
      "away": {
        "value": 10,
        "streak": [
          {
            "result": 1,
            "matchid": 61624628
          },
          {
            "result": 2,
            "matchid": 61624588
          },
          {
            "result": 3,
            "matchid": 61624548
          }
        ]
      }
    }
  }
}
```

#### `stats_team_versus`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 26.5 KB | max 26.5 KB | avg 26.5 KB
- queryUrl: stats_team_versus/2851/2885
- Match ids detectados: 61624278, 34278899, 34278667, 18714516, 15222451, 7616552, 7616080, 1442987, 1442797, 364208
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
      "_id": 61624278,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 18,
      "week": 1,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5123,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        },
        "away": {
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
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 34278899,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 37,
      "_utid": 54,
      "round": 23,
      "week": 2,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 59687,
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
          "_id": 239030,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 34278667,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 37,
      "_utid": 54,
      "round": 13,
      "week": 43,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 239030,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 59687,
          "_sid": 1,
          "uid": 2851,
          "virtual": false,
          "name": "Oviedo",
          "mediumname": "Real Oviedo",
          "abbr": "OVI",
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
    "1695": {
      "_doc": "tournament",
      "_id": 1695,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 11,
      "_tid": 1695,
      "_utid": 544,
      "_gender": "men",
      "name": "Segunda B Group II",
      "abbr": "SBGI"
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
    "2851": {
      "_doc": "uniqueteam",
      "_id": 2851,
      "_rcid": 32,
      "_sid": 1,
      "name": "Oviedo",
      "mediumname": "Real Oviedo",
      "suffix": null,
      "abbr": "OVI",
      "nickname": null,
      "teamtypeid": 0
    },
    "2885": {
      "_doc": "uniqueteam",
      "_id": 2885,
      "_rcid": 32,
      "_sid": 1,
      "name": "Alaves",
      "mediumname": "Deportivo Alaves",
      "suffix": null,
      "abbr": "ALA",
      "nickname": null,
      "teamtypeid": 0
    }
  },
  "currentmanagers": {
    "2885": [
      {
        "_doc": "player",
        "_id": 53603,
        "name": "Sanchez, Quique",
        "fullname": "Flores, Enrique Sanchez",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "02/02/65",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": -155001600
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
          "date": "03/03/26",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1772496000
        }
      }
    ],
    "2851": [
      {
        "_doc": "player",
        "_id": 150321,
        "name": "Almada, Guillermo",
        "fullname": "Almada Alves, Jorge Guillermo",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "18/06/69",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": -17020800
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
        "primarypositiontype": null,
        "haslogo": false,
        "membersince": {
          "_doc": "time",
          "time": "00:00",
          "date": "16/12/25",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1765843200
        }
      }
    ]
  },
  "jersey": {
    "2851": {
      "base": "0c6cc0",
      "sleeve": "dbb76d",
      "number": "dbb76d",
      "type": "short_sleeves",
      "real": true
    },
    "2885": {
      "base": "fdfdfc",
      "sleeve": "063877",
      "number": "023f7e",
      "type": "short_sleeves",
      "real": true
    }
  },
  "next": {
    "_doc": "match",
    "_doctype": "generic",
    "_id": 61624672,
    "_sid": 1,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "round": 37,
    "week": 20,
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
        "_id": 5123,
        "_sid": 1,
        "uid": 2885,
        "virtual": false,
        "name": "Alaves",
        "mediumname": "Deportivo Alaves",
        "abbr": "ALA",
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
- Tamaño aprox.: min 21.6 KB | max 23.3 KB | avg 22.5 KB
- queryUrl: stats_team_lastx/2885/20, stats_team_lastx/2851/20
- Match ids detectados: 61624638, 61624628, 61624598, 61624558, 61624588, 61624548, 61624518, 61624510, 61624478, 61624466
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Últimos partidos de un equipo, útil para forma reciente.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2885,
    "_rcid": 32,
    "_sid": 1,
    "name": "Alaves",
    "mediumname": "Deportivo Alaves",
    "suffix": null,
    "abbr": "ALA",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624638,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 36,
      "week": 20,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5123,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        },
        "away": {
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
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624628,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 35,
      "week": 19,
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
          "_id": 5123,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624598,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 34,
      "week": 18,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5123,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 5133,
          "_sid": 1,
          "uid": 2825,
          "virtual": false,
          "name": "Bilbao",
          "mediumname": "Athletic Bilbao",
          "abbr": "ATH",
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
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 2.5 KB | max 2.5 KB | avg 2.5 KB
- queryUrl: stats_team_nextx/2885/1, stats_team_nextx/2851/1
- Match ids detectados: 61624672
- Campos principales: team, matches, tournaments, uniquetournaments, realcategories
- Qué aporta: Próximos partidos del equipo, útil para congestión de calendario.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2885,
    "_rcid": 32,
    "_sid": 1,
    "name": "Alaves",
    "mediumname": "Deportivo Alaves",
    "suffix": null,
    "abbr": "ALA",
    "nickname": null,
    "teamtypeid": 0
  },
  "matches": [
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 61624672,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 37,
      "week": 20,
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
          "_id": 5123,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
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
- Tamaño aprox.: min 1.9 KB | max 2.9 KB | avg 2.4 KB
- queryUrl: stats_team_streaks/2885, stats_team_streaks/2851
- Match ids detectados: 61624672, 61624678, 61624638, 61624628, 61624598, 61624558, 61624588, 61624548, 61624518, 61624510
- Campos principales: team, nextmatches, lastmatchesform, streaks
- Qué aporta: Rachas y forma condensada del equipo.
- Estructura resumida:

```json
{
  "team": {
    "_doc": "uniqueteam",
    "_id": 2885,
    "_rcid": 32,
    "_sid": 1,
    "name": "Alaves",
    "mediumname": "Deportivo Alaves",
    "suffix": null,
    "abbr": "ALA",
    "nickname": null,
    "teamtypeid": 0
  },
  "nextmatches": [
    {
      "matchdifficultyrating": 2,
      "matchid": 61624672
    },
    {
      "matchdifficultyrating": 1,
      "matchid": 61624678
    }
  ],
  "lastmatchesform": {
    "total": [
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624638
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624628
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624598
      }
    ],
    "home": [
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624638
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624598
      },
      {
        "typeid": "W",
        "value": "W",
        "matchid": 61624558
      }
    ],
    "away": [
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624628
      },
      {
        "typeid": "L",
        "value": "L",
        "matchid": 61624588
      },
      {
        "typeid": "D",
        "value": "D",
        "matchid": 61624548
      }
    ]
  },
  "streaks": {
    "goalsscored": {
      "total": {
        "value": 10,
        "streak": [
          {
            "result": 1,
            "matchid": 61624638
          },
          {
            "result": 1,
            "matchid": 61624628
          },
          {
            "result": 2,
            "matchid": 61624598
          }
        ]
      },
      "home": {
        "value": 6,
        "streak": [
          {
            "result": 1,
            "matchid": 61624638
          },
          {
            "result": 2,
            "matchid": 61624598
          },
          {
            "result": 2,
            "matchid": 61624558
          }
        ]
      },
      "away": {
        "value": 5,
        "streak": [
          {
            "result": 1,
            "matchid": 61624628
          },
          {
            "result": 1,
            "matchid": 61624588
          },
          {
            "result": 3,
            "matchid": 61624548
          }
        ]
      }
    },
    "goalsconceded": {
      "away": {
        "value": 10,
        "streak": [
          {
            "result": 1,
            "matchid": 61624628
          },
          {
            "result": 2,
            "matchid": 61624588
          },
          {
            "result": 3,
            "matchid": 61624548
          }
        ]
      }
    }
  }
}
```

#### `stats_team_versus`
- Hits: 1 | Status: 200:1 | Polling: no (single_request)
- Tamaño aprox.: min 26.5 KB | max 26.5 KB | avg 26.5 KB
- queryUrl: stats_team_versus/2851/2885
- Match ids detectados: 61624278, 34278899, 34278667, 18714516, 15222451, 7616552, 7616080, 1442987, 1442797, 364208
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
      "_id": 61624278,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 36,
      "_utid": 8,
      "round": 18,
      "week": 1,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 5123,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        },
        "away": {
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
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 34278899,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 37,
      "_utid": 54,
      "round": 23,
      "week": 2,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 59687,
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
          "_id": 239030,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        }
      }
    },
    {
      "_doc": "match",
      "_doctype": "generic",
      "_id": 34278667,
      "_sid": 1,
      "_rcid": 32,
      "_tid": 37,
      "_utid": 54,
      "round": 13,
      "week": 43,
      "teams": {
        "home": {
          "_doc": "team",
          "_id": 239030,
          "_sid": 1,
          "uid": 2885,
          "virtual": false,
          "name": "Alaves",
          "mediumname": "Deportivo Alaves",
          "abbr": "ALA",
          "nickname": null,
          "iscountry": false
        },
        "away": {
          "_doc": "team",
          "_id": 59687,
          "_sid": 1,
          "uid": 2851,
          "virtual": false,
          "name": "Oviedo",
          "mediumname": "Real Oviedo",
          "abbr": "OVI",
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
    "1695": {
      "_doc": "tournament",
      "_id": 1695,
      "_sid": 1,
      "_rcid": 32,
      "_isk": 11,
      "_tid": 1695,
      "_utid": 544,
      "_gender": "men",
      "name": "Segunda B Group II",
      "abbr": "SBGI"
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
    "2851": {
      "_doc": "uniqueteam",
      "_id": 2851,
      "_rcid": 32,
      "_sid": 1,
      "name": "Oviedo",
      "mediumname": "Real Oviedo",
      "suffix": null,
      "abbr": "OVI",
      "nickname": null,
      "teamtypeid": 0
    },
    "2885": {
      "_doc": "uniqueteam",
      "_id": 2885,
      "_rcid": 32,
      "_sid": 1,
      "name": "Alaves",
      "mediumname": "Deportivo Alaves",
      "suffix": null,
      "abbr": "ALA",
      "nickname": null,
      "teamtypeid": 0
    }
  },
  "currentmanagers": {
    "2885": [
      {
        "_doc": "player",
        "_id": 53603,
        "name": "Sanchez, Quique",
        "fullname": "Flores, Enrique Sanchez",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "02/02/65",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": -155001600
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
          "date": "03/03/26",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1772496000
        }
      }
    ],
    "2851": [
      {
        "_doc": "player",
        "_id": 150321,
        "name": "Almada, Guillermo",
        "fullname": "Almada Alves, Jorge Guillermo",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "18/06/69",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": -17020800
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
        "primarypositiontype": null,
        "haslogo": false,
        "membersince": {
          "_doc": "time",
          "time": "00:00",
          "date": "16/12/25",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1765843200
        }
      }
    ]
  },
  "jersey": {
    "2851": {
      "base": "0c6cc0",
      "sleeve": "dbb76d",
      "number": "dbb76d",
      "type": "short_sleeves",
      "real": true
    },
    "2885": {
      "base": "fdfdfc",
      "sleeve": "063877",
      "number": "023f7e",
      "type": "short_sleeves",
      "real": true
    }
  },
  "next": {
    "_doc": "match",
    "_doctype": "generic",
    "_id": 61624672,
    "_sid": 1,
    "_rcid": 32,
    "_tid": 36,
    "_utid": 8,
    "round": 37,
    "week": 20,
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
        "_id": 5123,
        "_sid": 1,
        "uid": 2885,
        "virtual": false,
        "name": "Alaves",
        "mediumname": "Deportivo Alaves",
        "abbr": "ALA",
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
- Tamaño aprox.: min 10.1 KB | max 10.6 KB | avg 10.3 KB
- queryUrl: stats_season_topassists/130805/2851, stats_season_topassists/130805/2885
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
      "_id": 2329181,
      "playerid": 2329181,
      "player": {
        "_doc": "player",
        "_id": 2329181,
        "name": "Fernandez, Thiago",
        "fullname": "Fernandez, Thiago Cruz",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "03/04/04",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1080950400
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 10,
          "a2": "ar",
          "name": "Argentina",
          "a3": "ARG",
          "ioc": "ARG",
          "continentid": 3,
          "continent": "South America",
          "population": 44293000
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
        "jerseynumber": 0
      },
      "teams": {
        "2851": {
          "active": true,
          "lastevent": "2026-05-14 20:59:02",
          "started": 9,
          "matches": 15,
          "assists": 4,
          "minutes_played": 775,
          "substituted_in": 6,
          "shirtnumber": "15"
        }
      },
      "total": {
        "matches": 15,
        "assists": 4,
        "minutes_played": 775,
        "substituted_in": 6
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 1627210,
      "playerid": 1627210,
      "player": {
        "_doc": "player",
        "_id": 1627210,
        "name": "Hassan, Haissem",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "08/02/02",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1013126400
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 63,
          "a2": "eg",
          "name": "Egypt",
          "a3": "EGY",
          "ioc": "EGY",
          "continentid": 4,
          "continent": "Africa",
          "population": 94666000
        },
        "secondarynationality": {
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
        "2851": {
          "active": true,
          "lastevent": "2026-05-14 20:59:02",
          "started": 19,
          "matches": 35,
          "assists": 3,
          "minutes_played": 1825,
          "substituted_in": 16,
          "shirtnumber": "10"
        }
      },
      "total": {
        "matches": 35,
        "assists": 3,
        "minutes_played": 1825,
        "substituted_in": 16
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 2052927,
      "playerid": 2052927,
      "player": {
        "_doc": "player",
        "_id": 2052927,
        "name": "Chaira, Ilyas",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "02/02/01",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 981072000
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
          "_id": "8",
          "_type": "F",
          "name": "Forward",
          "shortname": "FWD",
          "abbr": "F"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 7
      },
      "teams": {
        "2851": {
          "active": true,
          "lastevent": "2026-05-14 20:44:51",
          "started": 29,
          "matches": 34,
          "assists": 2,
          "minutes_played": 2346,
          "substituted_in": 5,
          "shirtnumber": "7"
        }
      },
      "total": {
        "matches": 34,
        "assists": 2,
        "minutes_played": 2346,
        "substituted_in": 5
      }
    }
  ],
  "teams": {
    "2851": {
      "_doc": "uniqueteam",
      "_id": 2851,
      "_rcid": 32,
      "_sid": 1,
      "name": "Oviedo",
      "mediumname": "Real Oviedo",
      "suffix": null,
      "abbr": "OVI",
      "nickname": null,
      "teamtypeid": 0
    }
  }
}
```

#### `stats_season_topcards`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 21.9 KB | max 23.6 KB | avg 22.8 KB
- queryUrl: stats_season_topcards/130805/2851, stats_season_topcards/130805/2885
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
      "_id": 1706803,
      "playerid": 1706803,
      "player": {
        "_doc": "player",
        "_id": 1706803,
        "name": "Vinas, Federico",
        "fullname": "Vinas Barboza, Federico Sebastian",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "30/06/98",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 899164800
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
        "jerseynumber": 9
      },
      "teams": {
        "2851": {
          "active": true,
          "lastevent": "2026-05-14 18:56:55",
          "started": 27,
          "yellow_cards": 4,
          "yellowred_cards": 1,
          "red_cards": 2,
          "matches": 32,
          "minutes_played": 2373,
          "substituted_in": 5,
          "number_of_cards_1st_half": 3
        }
      },
      "total": {
        "yellow_cards": 4,
        "yellowred_cards": 1,
        "red_cards": 2,
        "matches": 32,
        "minutes_played": 2373,
        "substituted_in": 5,
        "number_of_cards_1st_half": 3,
        "number_of_cards_2nd_half": 5
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 1561854,
      "playerid": 1561854,
      "player": {
        "_doc": "player",
        "_id": 1561854,
        "name": "Lopez, Javi",
        "fullname": "Lopez Carballo, Javier",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "25/03/02",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 1017014400
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
        "jerseynumber": 12
      },
      "teams": {
        "2851": {
          "active": true,
          "lastevent": "2026-05-10 17:45:25",
          "started": 19,
          "yellow_cards": 3,
          "red_cards": 1,
          "matches": 23,
          "minutes_played": 1609,
          "substituted_in": 4,
          "number_of_cards_2nd_half": 4,
          "shirtnumber": "25"
        }
      },
      "total": {
        "yellow_cards": 3,
        "red_cards": 1,
        "matches": 23,
        "minutes_played": 1609,
        "substituted_in": 4,
        "number_of_cards_2nd_half": 4
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 1324118,
      "playerid": 1324118,
      "player": {
        "_doc": "player",
        "_id": 1324118,
        "name": "Sibo, Kwasi",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "24/06/98",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 898646400
        },
        "nationality": {
          "_doc": "countrycode",
          "_id": 81,
          "a2": "gh",
          "name": "Ghana",
          "a3": "GHA",
          "ioc": "GHA",
          "continentid": 4,
          "continent": "Africa",
          "population": 22800000
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
        "2851": {
          "active": true,
          "lastevent": "2026-05-10 18:09:19",
          "started": 21,
          "yellow_cards": 3,
          "red_cards": 1,
          "matches": 26,
          "minutes_played": 1685,
          "substituted_in": 5,
          "number_of_cards_1st_half": 2,
          "number_of_cards_2nd_half": 2
        }
      },
      "total": {
        "yellow_cards": 3,
        "red_cards": 1,
        "matches": 26,
        "minutes_played": 1685,
        "substituted_in": 5,
        "number_of_cards_1st_half": 2,
        "number_of_cards_2nd_half": 2
      }
    }
  ],
  "teams": {
    "2851": {
      "_doc": "uniqueteam",
      "_id": 2851,
      "_rcid": 32,
      "_sid": 1,
      "name": "Oviedo",
      "mediumname": "Real Oviedo",
      "suffix": null,
      "abbr": "OVI",
      "nickname": null,
      "teamtypeid": 0
    }
  }
}
```

#### `stats_season_topgoals`
- Hits: 2 | Status: 200:2 | Polling: sí (repeated_requests)
- Tamaño aprox.: min 9.3 KB | max 11.3 KB | avg 10.3 KB
- queryUrl: stats_season_topgoals/130805/2851, stats_season_topgoals/130805/2885
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
      "_id": 1706803,
      "playerid": 1706803,
      "player": {
        "_doc": "player",
        "_id": 1706803,
        "name": "Vinas, Federico",
        "fullname": "Vinas Barboza, Federico Sebastian",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "30/06/98",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 899164800
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
        "jerseynumber": 9
      },
      "teams": {
        "2851": {
          "active": true,
          "lastevent": "2026-05-14 18:56:55",
          "started": 27,
          "goals": 9,
          "matches": 32,
          "penalties": 2,
          "goal_points": 10,
          "minutes_played": 2373,
          "substituted_in": 5,
          "first_goals": 5
        }
      },
      "total": {
        "goals": 9,
        "matches": 32,
        "penalties": 2,
        "goal_points": 10,
        "minutes_played": 2373,
        "substituted_in": 5,
        "first_goals": 5,
        "last_goals": 2
      },
      "home": {
        "goals": 1
      },
      "away": {
        "goals": 8
      },
      "firsthalf": {
        "goals": 5
      },
      "secondhalf": {
        "goals": 4
      }
    },
    {
      "_doc": "toplistentry",
      "_id": 2052927,
      "playerid": 2052927,
      "player": {
        "_doc": "player",
        "_id": 2052927,
        "name": "Chaira, Ilyas",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "02/02/01",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 981072000
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
          "_id": "8",
          "_type": "F",
          "name": "Forward",
          "shortname": "FWD",
          "abbr": "F"
        },
        "primarypositiontype": null,
        "haslogo": false,
        "jerseynumber": 7
      },
      "teams": {
        "2851": {
          "active": true,
          "lastevent": "2026-05-14 20:44:51",
          "started": 29,
          "goals": 6,
          "matches": 34,
          "goal_points": 8,
          "minutes_played": 2346,
          "substituted_in": 5,
          "first_goals": 3,
          "last_goals": 3
        }
      },
      "total": {
        "goals": 6,
        "matches": 34,
        "goal_points": 8,
        "minutes_played": 2346,
        "substituted_in": 5,
        "first_goals": 3,
        "last_goals": 3
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
    },
    {
      "_doc": "toplistentry",
      "_id": 1137631,
      "playerid": 1137631,
      "player": {
        "_doc": "player",
        "_id": 1137631,
        "name": "Reina Campos, Alberto",
        "fullname": "Reina Campos, Alberto",
        "birthdate": {
          "_doc": "time",
          "time": "00:00",
          "date": "09/09/97",
          "tz": "UTC",
          "tzoffset": 0,
          "uts": 873763200
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
        "jerseynumber": 5
      },
      "teams": {
        "2851": {
          "active": true,
          "lastevent": "2026-05-14 18:56:57",
          "started": 29,
          "goals": 4,
          "matches": 35,
          "goal_points": 5,
          "minutes_played": 2301,
          "substituted_in": 6,
          "first_goals": 3,
          "shirtnumber": "5"
        }
      },
      "total": {
        "goals": 4,
        "matches": 35,
        "goal_points": 5,
        "minutes_played": 2301,
        "substituted_in": 6,
        "first_goals": 3
      },
      "home": {
        "goals": 1
      },
      "away": {
        "goals": 3
      },
      "firsthalf": {
        "goals": 3
      },
      "secondhalf": {
        "goals": 1
      }
    }
  ],
  "teams": {
    "2851": {
      "_doc": "uniqueteam",
      "_id": 2851,
      "_rcid": 32,
      "_sid": 1,
      "name": "Oviedo",
      "mediumname": "Real Oviedo",
      "suffix": null,
      "abbr": "OVI",
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
- queryUrl: match_markets/61624672
- Campos principales: markets
- Qué aporta: Mercados y odds del partido por HTTP; hoy es el hallazgo más fuerte del lado odds.
- Estructura resumida:

```json
{
  "markets": [
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624672,
      "_marketId": 1,
      "_uts": 1779000468,
      "specifiers": null,
      "name": "1x2",
      "nameShort": "1x2",
      "active": true,
      "type": "prematch"
    },
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624672,
      "_marketId": 10,
      "_uts": 1778998339,
      "specifiers": null,
      "name": "Double chance",
      "nameShort": "Double chance",
      "active": true,
      "type": "prematch"
    },
    {
      "_doc": "oddsapi_market",
      "_bookmakerId": 74,
      "_matchId": 61624672,
      "_marketId": 11,
      "_uts": 1778998339,
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
- Tamaño aprox.: min 295.4 KB | max 300.6 KB | avg 298.0 KB
- queryUrl: uniqueteam_markets/2851, uniqueteam_markets/2885
- Campos principales: matches
- Qué aporta: Mercados por equipo sobre matches relacionados, útil para análisis complementario.
- Estructura resumida:

```json
{
  "matches": {
    "51103785": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103785,
          "_marketId": 1,
          "_uts": 1747575046,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103785,
          "_marketId": 10,
          "_uts": 1747575009,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103785,
          "_marketId": 11,
          "_uts": 1747575129,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "51103815": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103815,
          "_marketId": 1,
          "_uts": 1748189684,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103815,
          "_marketId": 10,
          "_uts": 1748189649,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103815,
          "_marketId": 11,
          "_uts": 1748189649,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "51103831": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103831,
          "_marketId": 1,
          "_uts": 1748795097,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103831,
          "_marketId": 10,
          "_uts": 1748794809,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 51103831,
          "_marketId": 11,
          "_uts": 1748793849,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
          "type": "prematch"
        }
      ]
    },
    "60969997": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 60969997,
          "_marketId": 1,
          "_uts": 1749049674,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 60969997,
          "_marketId": 10,
          "_uts": 1749049702,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": false,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 60969997,
          "_marketId": 11,
          "_uts": 1749049702,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": false,
          "type": "prematch"
        }
      ]
    },
    "60969999": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 60969999,
          "_marketId": 1,
          "_uts": 1750529463,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 60969999,
          "_marketId": 10,
          "_uts": 1750531929,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 60969999,
          "_marketId": 11,
          "_uts": 1750529409,
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
    "61623964": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623964,
          "_marketId": 1,
          "_uts": 1756061754,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623964,
          "_marketId": 10,
          "_uts": 1756063329,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61623964,
          "_marketId": 11,
          "_uts": 1756059489,
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
    "61624006": {
      "markets": [
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624006,
          "_marketId": 1,
          "_uts": 1757763112,
          "specifiers": null,
          "name": "1x2",
          "nameShort": "1x2",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624006,
          "_marketId": 10,
          "_uts": 1757763103,
          "specifiers": null,
          "name": "Double chance",
          "nameShort": "Double chance",
          "active": true,
          "type": "prematch"
        },
        {
          "_doc": "oddsapi_market",
          "_bookmakerId": 74,
          "_matchId": 61624006,
          "_marketId": 11,
          "_uts": 1757763103,
          "specifiers": null,
          "name": "Draw no bet",
          "nameShort": "Draw no bet",
          "active": true,
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
