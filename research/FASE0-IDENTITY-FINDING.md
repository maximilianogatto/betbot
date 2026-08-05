# Hallazgo — resolución de identidad: id-join vs nombre

**Investigación (2026-08-04)**: ¿conviene reusar la resolución stats-match del bot
para obtener los team_ids de federación, en vez de matchear por nombre?

## Respuesta: es complementario, no un reemplazo. Depende del provider.

El modelo usa, como `team_id`, la clave con la que se construyó el dataset — y esa
clave **difiere por país**:

| País | Provider | `team_id` del modelo | ¿id-join exacto disponible? |
|---|---|---|---|
| FIN | palloliitto | **`team_A_id`/`team_B_id` numérico** de la API (`build_dataset.py:76`) | **Sí, exacto** |
| SWE | svenskfotboll | **slug del nombre** (`build_dataset_nordics.py::_slug`) | No — la clave ES el nombre |
| NOR | fotball.no | **slug del nombre** | No — la clave ES el nombre |

### FIN: el id-join es exacto y robusto
El provider del bot pone `raw_payload=m` en el `StatsFixture`
(`stats_providers/palloliitto/provider.py:212`), y el modelo usó `m["team_A_id"]`
como `home_team_id`. Entonces, para un fixture ya resuelto a su `StatsFixture`:
`raw_payload["team_A_id"]` **== el id del modelo**, sin fuzzy. La resolución a
`StatsFixture` (nombre + kickoff) ya la hace el bot y es más robusta que el fuzzy
de nombres suelto (la hora de inicio desambigua).

### SWE/NOR: el nombre ES la clave
El dataset nórdico se construyó sin id numérico estable (las federaciones no lo
exponían en los endpoints usados), así que el `team_id` del modelo es el slug del
nombre. Ahí la resolución por nombre (alias → fuzzy) no es un rodeo: es la clave
natural. El alias sigue siendo necesario para el hueco nombre-de-casa vs
nombre-de-federación.

## Consecuencia de diseño (ya soportada por la arquitectura)

`PredictionService` acepta **ambos** caminos sin cambios:
- **Caller con ids de federación** (los sacó del `raw_payload` vía la resolución
  stats del bot) → `predict(league_code, home_id, away_id)` — exacto, sin fuzzy.
  Es el camino preferido para FIN.
- **Caller con sólo nombres** → `predict_for_fixture` / `predict_by_names`
  (alias → fuzzy) — el camino natural para SWE/NOR y el fallback general.

**Recomendación**: la orquestación que maneje fixtures reales debería, cuando el
provider sea palloliitto, extraer `team_A_id/team_B_id` del `raw_payload` y usar
`predict(...)` con ids; para SWE/NOR usar `predict_for_fixture` con nombres. Esa
lógica vive en la capa de orquestación (que llama a los providers), NO en
`PredictionService` (que es puro, sin llamadas a red ni async). No requiere tocar
el esquema.

**Pendiente para cuando se cablee el detector a fixtures reales**: el mapping
`unified_competition` (por el que llegan los fixtures del bot) → `league_code` de
research. `resolve_league` ya matchea por nombre/país/género; falta enganchar el
`unified_competition_id` del fixture a ese `resolve_league` (o guardar el
`league_code` en el registro de ligas).
