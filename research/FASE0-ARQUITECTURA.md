# Fase 0 — Arquitectura del archivado y del puente modelo→bot

**Estado**: PLAN. No modifica producción. Ancla el diseño en el código greenfield
real (verificado 2026-07-27), no en la memoria previa (que describía el esquema
legacy). La ejecución es una sesión dedicada del bot con autorización explícita.

---

## 1. Objetivo

Construir una herramienta que compare **la línea que el modelo considera justa**
contra **la línea que ofrecen las casas**, y avise cuando la diferencia es
aprovechable.

Todo el sistema es una sola comparación, alimentada por dos lados:

```
providers (fixtures, forma, resultados) ─┐
                                          ├→ MODELO → lam_h/lam_a → línea justa ─┐
histórico (odds_history, event_results) ─┘                                        ├→ discrepancia
9 extractores (odds de las casas) ──────────────────→ línea de la casa ──────────┘
```

De ahí salen **dos productos con requisitos opuestos**, y separarlos es la
decisión de diseño central:

### Producto A — Screening pre-match
Lista diaria de partidos potables con su línea estimada, exportable a Excel.
Márgenes chicos, la precisión manda, se puede calcular con calma.
**Depende de que el modelo esté confirmado (EXP-005).**

### Producto B — Detector de error grosero en vivo
El caso que motiva el proyecto: el análisis dice que la línea va en -4.5 y la
casa la publica en -1, o directamente invierte el favorito. Es un error de la
casa, dura poco y se aprovecha.

**No necesita un modelo calibrado.** Si el modelo dice -4.5 y la casa -1, no hace
falta calibración para saber que algo no cierra. Lo que manda es la velocidad.
**Por eso B puede salir antes que A, sin esperar la confirmación de EXP-005.**

### Lo que el usuario ve
- Fixtures del día con forma y línea estimada.
- En cuánto salió cada partido y cómo se movió la línea desde entonces.
- Si hubo peak o no, y el análisis que lo respalda.
- Si no hubo valor pre-match, el partido queda cargado para el seguimiento en vivo.
- Excel diario de partidos potables con la línea estimada.

---

## 2. Corrección de entendimiento (se mantiene del plan original)

La memoria y el primer chip de Fase 0 asumían que `event_odds_snapshots` existía
con el esquema correcto y sólo había que "dejar de pisarlo". **Eso ya no es
cierto**: el cutover greenfield la puso en `FORBIDDEN_LEGACY_TABLES`
(`adapters/storage/schema.py:27`). El esquema nuevo es deliberadamente
**current-state, sin historial**. Por lo tanto Fase 0 **agrega tablas de archivo
nuevas**, no revive la vieja.

---

## 3. Lo que YA existe (no reinventar)

| Pieza | Dónde | Qué da |
|---|---|---|
| Tabla `events` (current-state) | `adapters/storage/schema.py:105` | Registro vivo por `(platform, external_event_id)`: `odds_home/draw/away`, `markets_json`, `status`, `scheduled_at`, `first_seen_at`, `last_seen_at`. Es el calendario / tracking pre-match. |
| Pollers de odds | `services/tracking.py`, `services/live_watch.py` → `EventsStore.upsert_active_events` | Punto de entrada de cuotas. El archivado debe ser una operación explícita de servicio/puerto, no un efecto lateral del adapter current-state. |
| 9 extractores de odds | `extractors/` | La fuente. Ya normalizan a `odds_home/draw/away` + `markets_json`. |
| **Modelo de goles** | `research/peak_models/models.py:84` | `predict_probs()` devuelve **`lam_home`, `lam_away`**, `p_home/draw/away`, `p_over25`, `p_btts`. Versión jerárquica multi-liga en `HierPoissonFit` (EXP-003). **De `lam_h`/`lam_a` sale la línea de goles y el hándicap justo.** |
| Ratings atk/def | idem, dentro del fit | Son "la forma" en versión estadística: no hace falta una métrica de forma aparte para empezar. |
| Estado en vivo | `core/models.py:190` (`LiveEventSnapshot`) | Marcador, minuto, **rojas y amarillas**, cuotas 1X2, `markets_payload`, `live_stats` (posesión, ataques, ataques peligrosos, tiros al arco, corners). |
| Scoring diario | `services/special_peak.py` | Ya produce una lista diaria 1-10 para Fin/Swe con detector de rotación/equipo B y ventana de alineaciones. **Es el germen del Producto A, pero hoy es heurístico y no usa el modelo.** |
| Interfaz de stats providers | `stats_providers/*/provider.py` | Los 6 implementan `search_leagues / list_fixtures / resolve_match / build_match_report`. La unificación pendiente es de *contenido*, no de interfaz. |
| Captura de token sportradar | `stats_providers/.../session_manager.py` | Captura y reusa un token firmado; **no genera la firma**. Es refresco/captura, no minteo. |

---

## 4. Los gaps

1. **El modelo está desconectado del bot.** Vive en `research/` y nada del
   runtime lo importa (verificado). Hoy no hay forma de que una pantalla muestre
   una "línea estimada". **Es el cuello de botella: sin esto no hay producto.**
2. **No se guarda qué se predijo.** Para saber "cómo salió" hay que haber
   registrado la predicción **antes** del partido y de forma inmutable. Sin eso
   se evalúa contra números ajustados a posteriori, que es engañarse solo.
3. **No hay historial de cuotas**: cada poll pisa `events`. Falta un append-only
   con apertura → intermedios → cierre.
4. **No hay captura de "cierre"**: nada marca el último snapshot estrictamente
   pre-kickoff (la cuota que importa para CLV).
5. **No hay resultado final archivado** para etiquetar sin re-scrapear.
6. **Falta identidad canónica cross-plataforma**: `events` sólo es único por
   `(platform, external_event_id)`. Hace falta `canonical_events` con aliases
   antes de comparar casas entre sí.
7. **Paridad de providers incompleta** (§8).

---

## 5. Puente modelo → bot (NUEVO — es lo que desbloquea todo)

### `PredictionService`

Un service que traduce la salida del modelo a las magnitudes con las que se
apuesta:

- Entrada: fixture (equipos, liga, fecha).
- Usa el fit del modelo para obtener `lam_home`, `lam_away`.
- Deriva: **línea de goles justa** (total esperado), **hándicap justo**
  (de la distribución de diferencia de goles), y probabilidades 1X2 / over-under.
- Salida: un DTO, sin nada de Telegram.

**Restricción de capas** (la valida `tests/test_architecture_layers.py`): el
código de `research/` no puede importarse desde `core/`. El puente se implementa
como un service que carga el fit desde un artefacto versionado (parámetros
serializados), **no importando `research/` desde el runtime**. El entrenamiento
sigue viviendo en `research/`; el bot sólo consume el resultado.

### Tabla `predictions` (append-only, inmutable)

```
predictions(
  id INTEGER PK,
  canonical_event_id INTEGER,          -- nullable hasta resolver identidad
  platform TEXT, external_event_id TEXT,
  unified_competition_id INTEGER,
  model_version TEXT NOT NULL,         -- qué fit produjo esto (reproducibilidad)
  predicted_at TEXT NOT NULL,          -- UTC; SIEMPRE anterior al kickoff
  lam_home REAL, lam_away REAL,
  fair_goal_line REAL,                 -- línea de goles derivada
  fair_handicap REAL,                  -- hándicap derivado
  p_home REAL, p_draw REAL, p_away REAL,
  p_over25 REAL, p_btts REAL,
  inputs_hash TEXT,                    -- con qué datos se calculó
  notes TEXT
)
índices: (canonical_event_id, predicted_at), (unified_competition_id, predicted_at)
```

**`model_version` no es opcional.** Sin él, cuando el modelo cambie, el archivo
histórico deja de ser comparable y se pierde la capacidad de evaluar.

---

## 6. Archivado de odds (se mantiene del plan original)

### Tabla `odds_history` (append-only)

```
odds_history(
  id INTEGER PK,
  source_event_pk INTEGER,                   -- referencia lógica
  canonical_event_id INTEGER,                -- nullable hasta resolver identidad
  platform TEXT, external_event_id TEXT,
  unified_competition_id INTEGER,
  captured_at TEXT NOT NULL,                 -- timestamp UTC del snapshot
  provider_observed_at TEXT,
  status TEXT,                               -- PREMATCH/LIVE/FINISHED al momento
  odds_home REAL, odds_draw REAL, odds_away REAL,
  markets_json TEXT,                         -- comprimido (zlib) si supera N bytes
  is_suspended INTEGER DEFAULT 0
)
idempotencia: (platform, external_event_id, captured_at, hash_payload)
lectura: (source_event_pk, captured_at), (canonical_event_id, captured_at),
         (unified_competition_id, captured_at)
```

### Lógica de captura

Definir un `OddsArchivePort` y llamarlo explícitamente desde la orquestación de
tracking. Evitar que el adapter current-state escriba en silencio en otra base.

- **Semántica honesta**: el primer registro es `first_observed`, no la apertura
  real. El cierre disponible es `last_observed_prematch`, no la closing line
  oficial. Decirlo en el nombre de las columnas y en los reportes.
- **Intermedios**: append sólo si las cuotas 1X2 (o el hash de `markets_json`)
  cambiaron respecto del último snapshot. No archivar polls idénticos.
- **Cierre observado**: conservar los snapshots crudos y derivar por consulta el
  último con `captured_at < actual_start_at`.
- **Roles derivados**: no escribir `opening/closing` al ingerir; se calculan
  desde la serie. El archivo se mantiene verdaderamente append-only.
- **Suspendidas**: si el extractor devuelve odds nulas/parciales, archivar con
  `is_suspended=1` en vez de descartar (auditable).

---

## 7. Resultado final: `event_results`

`upsert_active_events` no actualiza `status` ni resultados. Hace falta un flujo
explícito de transición y una tabla separada (no ensuciar el current-state).

**Indicadores a guardar**, en tres niveles según lo que aportan:

**Nivel 1 — sin esto no se puede evaluar nada**
- `final_home_score`, `final_away_score`
- `ht_home_score`, `ht_away_score` — separa 1ª/2ª parte, sale gratis
- `status` real: FINISHED / suspendido / postergado. **Crítico**: un partido
  suspendido guardado como 0-0 envenena el dataset.
- `actual_start_at` — necesario para definir el cierre (§6)

**Nivel 2 — los que explican el resultado**
- **xG local/visitante**: el mejor predictor individual post-partido. SofaScore
  lo entrega.
- **Tiros al arco**: fallback donde no haya xG.
- **Rojas con el minuto**: sin el minuto, un resultado raro parece ruido; con él
  es explicable.
- **Minutos de los goles**: conecta directo con la línea de investigación abierta
  (déficit de ceros a baja intensidad, EXP-004.9); permite modelar la tasa de gol
  en el tiempo y no sólo el total.

**Nivel 3 — vienen gratis pero valen poco**
- Posesión, corners, ataques peligrosos. Guardar en el **JSON crudo, no como
  columnas**. La posesión es notoriamente mal predictor; no justifica ensuciar el
  esquema.

**Regla**: guardar el payload crudo del provider (comprimido) **además** de las
columnas normalizadas. Normalizar entre 6 providers es la parte difícil (§8) y el
crudo evita perder datos que hoy no se sabe que se van a querer.

---

## 8. Paridad de stats providers (habilitador)

Que sofascore/footystats/flashscore/especiales entreguen la misma información que
sportradar (fixtures, resultados, tablas), cada uno por sus endpoints. La interfaz
común ya existe; falta cerrar el **contenido**:

1. **Token sportradar**: arreglar el refresco/captura del token firmado (se
   bloquea/expira). Es el cuello de botella de sportradar como referencia.
2. **Matriz de paridad**: por provider, verificar que devuelve {fixtures con
   fecha, resultado final, tabla as-of, xG si aplica}. Primer entregable.
3. **Criterio de listo**: para cada liga del dataset, al menos un provider
   entrega el resultado final de cada partido de forma programática.

---

## 9. Producto B — Detector de error grosero en vivo

El de mayor valor inmediato y el que menos depende del modelo confirmado.

### El ajuste que decide si sirve

Comparar una línea **pre-match** contra una línea **en vivo** sin condicionar al
estado del partido produce basura: si va 0-3 al minuto 60, el -1 de la casa está
bien y el -4.5 pre-match no significa nada.

El detector necesita recalcular la expectativa **restante**:

```
lam_restante = f(lam_prematch, minutos restantes, marcador actual, rojas)
```

El estado ya se captura (`LiveEventSnapshot`: marcador, minuto, rojas). Sin este
ajuste la alarma dispara falsos positivos constantemente y se vuelve ruido que se
termina ignorando.

### Salvaguardas

- **Una discrepancia grande muchas veces NO es un error de la casa**: es que la
  casa sabe algo que el modelo no (lesión, expulsión no capturada, feed atrasado).
  Exigir que el estado que ve el modelo esté **fresco** antes de alertar.
- **Umbral alto**: esto busca errores groseros, no ventajas de 2%. Un umbral bajo
  lo convierte en un generador de ruido.
- **Registrar cada alerta** (disparó / no disparó, y cómo terminó) para poder
  medir la tasa de falsos positivos en vez de estimarla de memoria.

---

## 10. Alcance de ligas

- **Hoy**: el modelo jerárquico está entrenado sobre **nórdicas**, que es donde
  la línea estimada se apoya en datos reales.
- **Objetivo**: todas las ligas trackeadas.
- **La ampliación se investiga en una sesión aparte** (otro chat). Este plan no
  la incluye; sólo la toma como dependencia del Producto A.
- **Regla mientras tanto**: si una liga no está en el fit, la línea estimada se
  marca como *no disponible*, **nunca se extrapola en silencio**. Una línea
  inventada donde más se la va a mirar es peor que no tenerla.

---

## 11. Presupuesto de disco

VM GCP de 10GB que **ya tuvo un incidente de disco lleno** (hoy 61% usado, con
121 MB todavía ocupados por `tracking.legacy.sqlite3`).

- `markets_json` es lo pesado → comprimir.
- Estimar tamaño en local antes de activar en prod; definir retención/rotación.
- **DB separada** para el archivo (append-only), con WAL, métricas de tamaño y
  backup. No rotar ni borrar datos de investigación sin exportación verificada.

---

## 12. Secuencia

1. **Puente modelo → bot** (`PredictionService` + tabla `predictions`).
   *Desbloquea todo lo demás; no depende de las otras tablas.*
2. **Archivado**: `odds_history` + `event_results` + paridad de providers.
3. **Producto B** (detector en vivo). Valor rápido, no espera a EXP-005.
4. **Producto A** (lista diaria + Excel) cuando EXP-005 confirme el modelo.

**Excluido de Fase 0**: el cálculo de métricas de mercado (q_r, CLV, z_r) y el
modelo de value. Vienen después, cuando el archivo tenga datos.

---

## 13. Métricas que esto habilita (dejar el dato, no calcularlas todavía)

Probabilidad implícita sin margen $q_r=(1/o_r)/\sum_s (1/o_s)$; log-loss y RPS del
modelo vs mercado; **CLV** (cuota tomada vs cierre); calibración modelo–mercado;
residual de mercado $z_r=\log(p_r/p_A)-\log(q_r/q_A)$. El test de ventaja usa
**interacción preespecificada por segmento** (ligas chicas, inicio de temporada,
ascendidos), nunca selección retrospectiva.

---

## 14. Preguntas abiertas

- δ de la ventana de "cierre": ¿minutos fijos o adaptativo por liga?
- ¿Cómo se modelan `canonical_events` y sus aliases por plataforma para evitar
  falsos matches entre partidos de la misma liga y fecha?
- ¿En qué formato se serializa el fit del modelo para que el bot lo consuma sin
  importar `research/`, y cómo se versiona (`model_version`)?
- Umbral del detector en vivo: ¿fijo, o por liga según el error histórico del
  modelo en esa liga?
- ¿El Excel diario se genera desde el bot o desde un job aparte?
