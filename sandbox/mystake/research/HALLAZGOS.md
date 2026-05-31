# Mystake — investigación profunda de la API (2026-05-31)

Captura con Playwright (`capture_traffic.py`): se cargó
`https://mystake.bet/as/sportsbook/prematch#/prematch/selection`, se escucharon
TODAS las responses y se volcaron a `captures/` (gitignored por tamaño).

## El hallazgo clave: `getheader`

```
GET https://analytics-sp.googleserv.tech/api/sport/getheader/as
```

Es el **árbol de navegación completo** (~380KB), JSON doble-codificado, servido
por **HTTP plano sin token, sin cookies, sin MQTT** (verificado con httpx puro).
Esto invalida la creencia previa de que el árbol solo vivía en un cache MQTT con
deltas. Forma:

```
{ "AS": { "Sports": { "1": {            # 1 = Fútbol
    "Name": "Fútbol",
    "Regions": { "<rid>": {              # región == país (nombre traducido)
        "Name": "Australia",
        "Champs": { "<cid>": {           # champ == liga (nombre traducido)
            "Name": "NSW League Two",
            "GameSmallItems": { "<gid>": {"ID","Champ","StartTime","t1"} }
        }}
    }}
}}}}
```

- Nombres de liga **ya traducidos** al español.
- Los ids de `GameSmallItems` **negativos** = mercados outright/especiales;
  **positivos** = partidos 1X2 reales (se filtra a positivos).
- Fútbol: ~47 países, ~121 ligas, ~709 partidos en la captura.

## Resto de endpoints (referencia)

| Endpoint | Para qué |
|---|---|
| `sport/getheader/{region}` | **árbol completo** (sports→países→ligas→games) |
| `prematch/getprematchgameall/{region}/{lang}/?games=,<ids>` | odds + `teams` (1X2/AH/GL) |
| `prematch/getprematchtopgames/{region}` | games destacados (fallback) |
| `sport/getmarketcategories/{region}` | nombres de mercados |
| `wss-eu-uk1.ws-amazon.com/api/cache/get?key=prematch/games` | solo deltas base64 `{UpdateList,DeleteList}` — NO sirve para el snapshot |

## Conclusión / integración

`/track_league` ahora funciona end-to-end sin pasar nombres:
1. `search_leagues(country_name)` → filtra `getheader` por nombre de región.
2. elegir liga → `extract_league("mystake:champ:<id>")` → `getheader` resuelve
   nombre real + game ids → `getprematchgameall` trae odds (1X2 + 📐 AH + 📏 GL).

Código: `extractors/mystake_http/header.py` (parsing) + `extractor.py`
(`search_leagues`, cache de header 300s). El `/track_url` con URL gameall sigue
funcionando y ahora también resuelve el nombre real de la liga.
