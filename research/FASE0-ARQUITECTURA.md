# Fase 0 — Arquitectura del archivado de cuotas (plan para la sesión dedicada)

**Estado**: PLAN. No modifica producción. Ancla el diseño en el código greenfield
real (verificado 2026-07-23), no en la memoria previa (que describía el esquema
legacy). La ejecución es una sesión dedicada del bot con autorización explícita.

## 0. Corrección de entendimiento (importante)

La memoria y el primer chip de Fase 0 asumían que `event_odds_snapshots` existía
con el esquema correcto y solo había que "dejar de pisarlo". **Eso ya no es
cierto**: el cutover greenfield la puso en `FORBIDDEN_LEGACY_TABLES`
(`adapters/storage/schema.py:27`). El esquema nuevo es deliberadamente
**current-state, sin historial**. Por lo tanto Fase 0 **agrega una tabla de
archivo nueva**, no revive la vieja.

## 1. Lo que YA existe (no reinventar)

| Pieza | Dónde | Qué da para Fase 0 |
|---|---|---|
| Tabla `events` (current-state) | `adapters/storage/schema.py:105` | Registro vivo por `(platform, external_event_id)`: `odds_home/draw/away`, `markets_json`, `status` (PREMATCH/LIVE/FINISHED), `scheduled_at`, `first_seen_at`, `last_seen_at`. **Es el "calendario / tracking pre-match" que preguntabas — ya está.** |
| Pollers de odds | `services/tracking.py`, `services/live_watch.py` → `EventsStore.upsert_active_events` (`adapters/storage/events.py:56`) | El punto único donde entran las cuotas nuevas: el hook de archivado va acá. |
| 9 extractores de odds | `extractors/` | La fuente. Ya normalizan a `odds_home/draw/away` + `markets_json`. |
| `unified_competitions` + registro de ligas | `adapters/storage/competitions.py` | La **correspondencia inequívoca partido↔mercado** cross-plataforma que exige el spec — ya resuelve el entity matching. |
| Interfaz común de stats providers | `stats_providers/*/provider.py` | Los 6 providers YA implementan `search_leagues / list_fixtures / resolve_match / build_match_report`. La unificación es de *contenido de datos*, no de interfaz. |
| Captura de token sportradar | `stats_providers/sportradar_http/engine/session_manager.py` | Captura y reusa un token `T` firmado desde respuestas de red; **no genera la firma** (línea 23). Este es el "ajustar la generación del token" — es refresco/captura, no minteo. |

## 2. El gap real (lo que Fase 0 agrega)

1. **No hay historial de cuotas**: cada poll pisa `events`. Falta una tabla
   append-only que acumule apertura → snapshots intermedios → cierre.
2. **No hay captura de "cierre"**: nada marca el último snapshot estrictamente
   pre-kickoff (la cuota que importa para CLV).
3. **No hay resultado final archivado junto al evento** para etiquetar sin
   re-scrapear (depende de la paridad de providers, §4).
4. **Paridad de providers incompleta**: para etiquetar el archivo de odds con
   resultados de TODAS las ligas hace falta que sofascore/footystats/flashscore/
   especiales entreguen la misma superficie (fixtures + resultados + tablas) que
   sportradar, cada uno por sus endpoints.

## 3. Diseño del archivado de odds (parte A)

### Tabla nueva (append-only, nombre a definir, p.ej. `odds_history`)

```
odds_history(
  id INTEGER PK,
  event_pk INTEGER REFERENCES events(id),   -- linkea al current-state (correspondencia inequívoca)
  platform TEXT, external_event_id TEXT,     -- redundante pero robusto ante borrado de events
  unified_competition_id INTEGER,            -- para joins por liga
  captured_at TEXT NOT NULL,                 -- timestamp UTC del snapshot
  snapshot_kind TEXT,                        -- 'opening' | 'intermediate' | 'closing'
  status TEXT,                               -- PREMATCH/LIVE/FINISHED al momento
  odds_home REAL, odds_draw REAL, odds_away REAL,
  markets_json TEXT,                         -- comprimido (zlib) si supera N bytes
  is_suspended INTEGER DEFAULT 0             -- registrar cuotas suspendidas/incompletas
)
índice: (event_pk, captured_at), (unified_competition_id, captured_at)
```

### Lógica de captura (en `upsert_active_events`)

- **Apertura**: primer snapshot que se ve del evento (`first_seen_at` == ahora) →
  `snapshot_kind='opening'`.
- **Intermedios**: append solo si las cuotas 1X2 (o el hash de `markets_json`)
  **cambiaron** respecto del último snapshot archivado (dedup / idempotencia —
  requisito del spec). No archivar polls idénticos.
- **Cierre**: cuando `now ≥ scheduled_at − δ` (δ ~ pocos minutos) y el evento aún
  PREMATCH, forzar un snapshot `snapshot_kind='closing'` — el último estricto
  pre-kickoff. El poller de `live_watch` ya conoce los kickoffs.
- **Suspendidas/incompletas**: si el extractor devuelve odds nulas/parciales,
  archivar con `is_suspended=1` en vez de descartar (auditable).

### Resultado final

- Cuando `status` pasa a FINISHED, escribir el marcador final en el evento (o en
  una tabla `event_results`), tomándolo del stats provider (§4). Etiqueta el
  archivo sin re-scrapear.

### Presupuesto de disco (VM GCP 10GB, ya tuvo disk-full — ver memoria)

- ~partidos/día × plataformas × snapshots/partido. Con dedup por cambio, un
  partido nórdico típico son pocos snapshots. `markets_json` es lo pesado →
  comprimir. Estimar antes de activar en prod y poner retención/rotación si hace
  falta. Medir en local primero.

## 4. Paridad de stats providers (parte B, habilitador)

Objetivo del director: que sofascore/footystats/flashscore/especiales entreguen
la MISMA información que sportradar (fixtures, resultados, tablas), cada uno por
sus endpoints. La interfaz común ya existe; falta cerrar el **contenido**:

1. **Token sportradar** (`session_manager.py`): arreglar el refresco/captura del
   token `T` firmado (hoy captura de red y reusa; se bloquea/expira). Es el
   cuello de botella de sportradar como referencia.
2. **Matriz de paridad**: por provider, verificar que devuelve {fixtures con
   fecha, resultado final, tabla as-of}. Donde falte, completar el endpoint.
   Esta matriz es el primer entregable de la sesión (una tabla provider × dato).
3. Criterio de "listo": para cada liga del dataset de investigación, al menos un
   provider entrega el resultado final de cada partido de forma programática.

## 5. Métricas que esto habilita (NO implementar en Fase 0, solo dejar el dato)

Probabilidad implícita sin margen $q_r=(1/o_r)/\sum_s (1/o_s)$; log-loss y RPS
del modelo vs mercado; **CLV** (cuota tomada vs cierre); calibración modelo–
mercado; residual de mercado $z_r=\log(p_r/p_A)-\log(q_r/q_A)$. El test de
ventaja usa **interacción preespecificada por segmento** (ligas chicas, inicio de
temporada, ascendidos), nunca selección retrospectiva de segmentos.

## 6. Alcance de la sesión dedicada (acotado)

Incluye: tabla `odds_history` + hook de captura (apertura/intermedio/cierre/
dedup/suspendidas) + resultado final + arreglo del token sportradar + matriz de
paridad de providers y cierre de los faltantes. Tests bajo `tests/`
(`./run_tests.sh`). Commits chicos. Migración de esquema con el patrón greenfield
(no tocar `FORBIDDEN_LEGACY_TABLES`).

Excluye: el cálculo de métricas de mercado (q_r, CLV, z_r) y el modelo de value —
esos vienen después, cuando el archivo tenga datos.

## 7. Preguntas abiertas para el arranque de la sesión

- ¿Archivo en la misma DB (`data/tracking.sqlite3`) o base separada para no
  inflar la operativa? (recomendación inicial: tabla en la misma DB con rotación,
  revisar tras estimar volumen).
- δ de la ventana de "cierre": ¿minutos fijos o adaptativo por liga?
- ¿El resultado final va en `events` (nueva columna) o en `event_results`
  separada? (separada es más limpia y no ensucia el current-state).
