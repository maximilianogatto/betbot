# Betovo (betovo848425.com) — investigación de la API (2026-05-31)

## Qué es

Casino/sportsbook que corre la plataforma **Altenar**. La API es el frontend
compartido de Altenar (`sb2frontend-altenar2.biahosted.com/api/`), scopeado al
operador con el query param **`integration=betovo`**. **HTTP plano, sin token**
(verificado con httpx puro). Los `extId` traen ids de Sportradar
(`fp32_ar:match:554495` → `ar:match:554495`) → linkeo directo con stats.

## Auth / params comunes

Todas las llamadas llevan: `culture=en-GB`, `timezoneOffset=180`,
`integration=betovo`, `deviceType=2`, `numFormat=en-GB`, `countryCode=AR`.
No hace falta token ni cookie. Fútbol = **sportId 66** (id interno de Altenar
para esta integración; `GetSportInfo` mapea id→typeId Betradar).

## Endpoints clave

| Endpoint | Para qué |
|---|---|
| `GET /widget/GetEvents?sportId=66` | **catálogo completo**: events + champs (ligas) + categories (países) + odds titulares, normalizado |
| `GET /widget/GetEvents?sportId=66&champIds=<id>` | eventos de UNA liga (filtro correcto = `champIds`, no `championshipIds`) |
| `GET /widget/GetEventDetails?eventId=<id>` | **mercados completos** de un evento (1x2 + AH + goal line + …) |
| `GET /widget/GetUpcoming?eventCount=0&sportId=66` | alternativa (capa a ~272 eventos) |

Respuesta normalizada: `events[]` (id, name, champId, catId, startDate, extId,
competitorIds), `champs{}` (ligas), `categories{}` (países, con `iso` y
`champIds`), `competitors{}`, `markets[]`, `odds[]`. En GetEventDetails los
markets enlazan odds vía **`desktopOddIds`** (arrays anidados), no `oddIds`.

## Mercados (GetEventDetails, fútbol)

| typeId | nombre | mapeo |
|---|---|---|
| `1` | 1x2 | odds "1"/"X"/"2" (`price`) → `odds_1x2` |
| `16` | Handicap (asiático) | odd name "<equipo> (<linea>)" + `competitorId`; `sv`=línea base → 📐 `asian_handicap` |
| `18` | Goal Line / Totals | odds "Over <l>"/"Under <l>" → 📏 `goal_line` |

Tiene 200+ mercados por evento; usamos los 3 que el bot renderiza
(**1X2 + AH + GL**, igual de completo que BZ).

## Integración (producción, HTTP puro)

`extractors/betovo_http/`: `settings.py` (host/integration/sport overridables por
env), `client.py` (GetEvents + GetEventDetails por evento, concurrencia acotada),
`parser.py` (1X2 + 📐 AH + 📏 GL; guarda `sr_match_id` para stats), `discovery.py`
(ligas por país desde categories.champIds), `extractor.py` (`search_leagues` +
`extract_league`, feed cacheado 90s). Registrado browserless. `/track_league`
end-to-end: país → liga → tracking con nombre real + odds, sin pegar URL.

Verificado en vivo: Brasil (11 ligas, Serie A 12 ev con AH+GL), Argentina
(Copa Argentina, Primera B/C), Japón (J.League 10 ev).
