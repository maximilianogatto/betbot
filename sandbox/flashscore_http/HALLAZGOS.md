# Flashscore (flashscore.com.ar) — investigación stats provider (2026-06-01)

## Resumen

Flashscore (Livesport) es viable como stats provider **HTTP puro** y es la fuente
de **mayor cobertura de ligas** (incluye ligas nicho que no están en Sportradar /
SofaScore). Es además la más fácil de todas: **httpx plano + un header estático**,
sin Cloudflare, sin token bootstrap, sin curl_cffi, sin browser.

## Transporte

- Feed host: `https://global.flashscore.ninja/<project>/x/feed/<code>`
  (también `204.flashscore.ninja`). **project_id = 204** = flashscore.com.ar.
- Header obligatorio (y suficiente): **`x-fsign: SW9D1eZo`** (firma estática).
  Sin él → la API no responde; con él → `200` por httpx directo.
- Respuestas: `text/plain`, formato propietario — registros separados por `~`,
  campos por `¬`, pares `KEY÷value`.

## Feeds clave (sport 1 = fútbol)

| Code | Devuelve |
|---|---|
| `f_1_<dayOffset>_<tz>_<lang>_1` | partidos del día agrupados por liga (0=hoy, 1=mañana, -1=ayer; tz=-3 ARG, lang=es-ar) |
| `df_sui_1_<eventId>` | incidencias / timeline (goles, tarjetas, cambios) |
| `df_st_1_<eventId>` | estadísticas (posesión, remates, **xG**, córners, tarjetas, grandes ocasiones) |
| `df_hh_1_<eventId>` | head-to-head + forma reciente |
| `dc_1_<eventId>` | meta del partido (estado, timestamps, marcador) |
| `r_1_1` | resultados live (sport 1) · `nl_1_59` / `mc_-3` (menús, no usados) |

## Códigos de campo (decodificados)

- **Liga** (header): `ZA` = "PAÍS: Liga" (el país es el prefijo antes de `:`),
  `ZEE` = id de liga, `ZC` = id de tournament-stage, `ZB` = sport/orden.
- **Partido**: `AA` = event id, `AD` = kickoff unix, `AE`/`AF` = local/visitante,
  `AG`/`AH` = marcador local/visitante, `AB` = estado (1=programado, 2=live,
  3=terminado), `CX` = nombre.
- **Estadística** (`df_st`): `SG` = nombre, `SH`/`SI` = valor local/visitante
  (agrupadas por secciones `SE`/`SF`).
- **Incidencia** (`df_sui`): `IB` = minuto, `IE` = tipo, `IOX/IOY` = marcador
  corrido, `IF`/`IK` = jugador.

## Probado en vivo (HTTP puro)

- Hoy: **40 países, 61 ligas, 133 partidos** (incluye Aruba, Bielorrusia, Bolivia,
  Camerún, Irak, Islandia, Estonia… → cobertura nicho).
- Discovery por país (Argentina → Primera B / Primera C / Torneo Promocional
  Amateur).
- Reporte de partido (Marruecos Sub-17 0-2 Egipto Sub-17): xG 1.29/1.06,
  posesión 68%/32%, remates 24/12, grandes ocasiones 3/3, + incidencias con
  minuto y jugador.

## Integración propuesta (siguiente paso)

Mismo patrón que SofaScore (sandbox → `stats_providers/flashscore_http/`):
1. `search_leagues(country)`: filtrar el feed del día (± días) por país; opcional
   feed de menú para el árbol completo.
2. `list_fixtures(league_id)`: filtrar partidos de la liga en los feeds de día,
   o el feed por tournament-stage.
3. `resolve_match` (fuzzy nombre+hora) + `build_match_report` (`df_sui` + `df_st`
   + `df_hh`).
Sin dependencias nuevas (httpx ya está). Valor: **la mayor cobertura de ligas**.

Sandbox: `client.py` (httpx + x-fsign), `parser.py` (formato `~¬÷`). HTTP-only
probado de punta a punta.
