# Sportradar / Bet365Stats Endpoint Report

- Capture dir: `/Users/maximilianogatto/Library/CloudStorage/OneDrive-Personal/Apuestas/BetBot/sandbox/sportradar_stats/captures/bootstrap_test`
- Responses captured: 1
- Logical endpoints: 1

## Endpoints Detectados

| Endpoint | Hits | Polling | Tamaño med. | Señales |
| --- | ---: | :---: | ---: | --- |
| `/bet365/en/match/:id` | 1 | No | 415.0 B | match_id |

## Endpoints Útiles para BetBot

No se detectaron endpoints claramente útiles con la captura actual.

## Restricciones de Acceso

### `/bet365/en/match/:id`
- Status observado(s): 403
- Resultado: la página o feed quedó bloqueado por control de acceso antes de exponer JSON útil.
- Ejemplo resumido:

```json
{
  "status": 403,
  "content_type": "text/html",
  "preview": "<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>\n<H1>Access Denied</H1>\n \nYou don't have permission to access \"http&#58;&#47;&#47;s5&#46;sir&#46;sportradar&#46;com&#47;bet365&#47;en&#47;match&#47;61624656\" on this server.<P>\nReference&#32;&#35;18&#46;b4f71202&#46;1778876018&#46;4cce08a1\n<P>ht"
}
```

## Datos Disponibles

- `match_id`: visto en 1 endpoint(s)

## Datos que No Aparecieron Claramente

- `attacks` no apareció claramente
- `cards` no apareció claramente
- `corners` no apareció claramente
- `current_period` no apareció claramente
- `dangerous_attacks` no apareció claramente
- `injuries` no apareció claramente
- `lineups` no apareció claramente
- `live_state` no apareció claramente
- `odds` no apareció claramente
- `player_stats` no apareció claramente
- `possession` no apareció claramente
- `recent_form` no apareció claramente
- `score` no apareció claramente
- `shots` no apareció claramente
- `shots_on_target` no apareció claramente
- `standings` no apareció claramente
- `team_stats` no apareció claramente
- `time_played` no apareció claramente
- `timeline` no apareció claramente
- `win_probability` no apareció claramente

## Estructura Mínima Recomendada

```json
{
  "bet365_event_id": "string",
  "sportradar_match_id": "string",
  "stats_url": "string",
  "home_team": "string | null",
  "away_team": "string | null",
  "start_time_utc": "ISO-8601 | null",
  "coverage_flags": {
    "timeline": true,
    "lineups": false,
    "standings": false,
    "player_stats": false,
    "live_metrics": true
  },
  "available_stats": [
    "timeline",
    "score",
    "cards"
  ],
  "latest_live_state": {
    "status": "string | null",
    "score_home": "number | null",
    "score_away": "number | null",
    "period": "string | null",
    "clock": "string | null"
  }
}
```

## Conclusión

- Hallazgo principal: desde Playwright puro, la stats URL respondió `403 Access Denied`, incluso probando bootstrap previo desde Bet365. Eso sugiere una protección adicional de Akamai / first-party session.
- La captura actual no mostró suficientes señales live para justificar una integración inmediata desde este entorno aislado.
- Las métricas avanzadas de partido todavía no quedaron confirmadas con esta muestra.
- Standings, forma reciente o probabilidades no quedaron suficientemente expuestos en esta captura.
- Recomendación práctica: mantener esta investigación aislada y, si se quiere profundizar, probar una captura desde una sesión real de navegador con contexto/cookies del usuario antes de integrar `bet365_event_id -> sportradar_match_id -> latest_live_state`.
