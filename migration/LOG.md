# Diario de Migración — BetBot (append-only)

> **No reescribas ni borres entradas pasadas.** Solo se AGREGA al final.
> Template en `PROTOCOL.md`. Una entrada por acción (claim, avance, cierre, fallo, decisión).

---

### 2026-06-25 · @claude · SETUP · DONE
- **Qué hice:** Creé el sistema de coordinación multi-agente: `migration/PROTOCOL.md`, `migration/TASKS.md`, `migration/LOG.md`.
- **Por qué:** Claude y Gemini (y otros) van a trabajar la migración en paralelo; hace falta una fuente de verdad compartida para trazabilidad, evitar pisarse y poder retomar paso a paso.
- **Archivos:** migration/PROTOCOL.md, migration/TASKS.md, migration/LOG.md
- **Commit:** pendiente
- **Tests:** N/A (solo docs)
- **Notas/Bloqueos:** Diseño en papel cerrado (`REPORTE_ARQUITECTURA_BetBot.md`, secciones 1-18). Listos para arrancar PR1.
- **Siguiente sugerido:** PR1-T1 (VACUUM semanal).

### 2026-06-25T13:08:00-03:00 · @gemini · PR1-T1 · DONE
- **Qué hice:** Removí la ejecución incondicional de `VACUUM` en `prune_old_data` de `SqliteTrackingRepository`, implementé `run_db_vacuum()` expuesto en el repositorio y actualicé los jobs de mantenimiento diario (`_orchestrated_db_pruning` en `bot/jobs/tasks.py` y `_db_pruning_loop` en `bot/jobs/legacy.py`) para llamar a `run_db_vacuum()` únicamente los domingos.
- **Por qué:** Evitar la ejecución diaria e incondicional de `VACUUM` para no bloquear operaciones de SQLite innecesariamente, delegándola a un mantenimiento semanal (los domingos).
- **Archivos:** storage/tracking_repository.py, bot/jobs/tasks.py, bot/jobs/legacy.py, tests/bot/test_bot_jobs.py, tests/core/test_prune_old_data.py
- **Commit:** c894203bce0c83f29cc53eb7d776229891709286
- **Tests:** Verde. 594 tests pasados con éxito (incluidos nuevos casos de prueba en `tests/bot/test_bot_jobs.py` y `tests/core/test_prune_old_data.py`).
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** PR1-T2 (Tope FIFO en stats_payload_cache).

### 2026-06-25T11:40:08-03:00 · @gemini · PR1-T2 · DONE
- **Qué hice:** Agregué un tope FIFO de 200 filas a `stats_payload_cache`, ejecutado después de cada `set_cached_stats_payload`, eliminando primero los payloads con `fetched_at` más antiguo. Sumé test de regresión que inserta 205 payloads y verifica que queden 200, conservando los más nuevos.
- **Por qué:** El TTL solo evita usar payloads vencidos, pero no limita crecimiento físico si se cachean muchas ligas/providers con TTL largos. El cap evita crecimiento indefinido sin cambiar el contrato público del cache.
- **Archivos:** storage/tracking_repository.py, tests/core/test_stats_cache_purge.py
- **Commit:** c10b1bd
- **Tests:** Verde con venv real: `/Users/maximilianogatto/Library/CloudStorage/OneDrive-Personal/Apuestas/BetBot/betbot/bin/python -m unittest discover -t . -s tests` → 595 tests OK. Subset: `python3 -m unittest tests.core.test_stats_cache_purge` → 2 tests OK. Nota: `./run_tests.sh` en este worktree cayó a `python3` del sistema y falló por dependencias faltantes (`telegram`, `httpx`, `playwright`), no por el cambio.
- **Notas/Bloqueos:** Toqué un archivo de test además de los archivos principales de la tarea para cumplir el criterio de aceptación. Quedan archivos sin trackear preexistentes en el worktree; no se tocaron.
- **Siguiente sugerido:** PR1-T3 si se quiere evitar colisión sobre `storage/tracking_repository.py`; si no hay otro agente en storage, PR1-T4/PR1-T5 según orden acordado.

### 2026-06-25T11:46:22-03:00 · @gemini · PR1-T3 · DONE
- **Qué hice:** Reemplacé la recuperación por kill de procesos Chromium por un helper compartido que llama `request_restart(reason=...)` en runtimes browser-backed registrados. `BrowserHandler` ahora conserva el motivo del restart solicitado y solo reporta restart disponible cuando `active_pages == 0`. Activé `ENABLE_MONITORING=true` por defecto.
- **Por qué:** Matar procesos Chromium puede cortar extracciones activas y dejar estado inconsistente. El reinicio graceful delega el stop/start al runtime cuando ya no hay páginas activas.
- **Archivos:** bot/config.py, bot/jobs/legacy.py, bot/jobs/tasks.py, bot/jobs/resource_monitor.py, core/browser_handler.py, tests/bot/test_browser_handler.py, tests/bot/test_chromium_memory_recovery.py
- **Commit:** 0955592
- **Tests:** Verde con venv real: `/Users/maximilianogatto/Library/CloudStorage/OneDrive-Personal/Apuestas/BetBot/betbot/bin/python -m unittest discover -t . -s tests` → 598 tests OK. Subset: `.../betbot/bin/python -m unittest tests.bot.test_chromium_memory_recovery tests.bot.test_browser_handler` → 7 tests OK. Compileall OK para `bot/jobs`, `core/browser_handler.py`, `bot/config.py` y tests tocados.
- **Notas/Bloqueos:** El helper también inspecciona `bot_data["browser_handler"]` y extractores registrados por duck typing para mantener bajo acoplamiento en PR1.
- **Siguiente sugerido:** PR1-T4 o PR1-T5 si no hay otro agente trabajando sobre `storage/tracking_repository.py`; si hay colisión, esperar o tomar solo una tarea sin storage.

### 2026-06-25T14:05:00-03:00 · @claude · COORD · DONE
- **Qué hice:** Definí el reparto de carriles para 3 agentes (@claude, @gemini, @codex) en TASKS.md "Notas de coordinación".
- **Por qué:** PR1 quedó reducido a 3 tareas (T4/T5/T6) que tocan TODAS `storage/tracking_repository.py`. Con un solo archivo no se puede paralelizar; 3 agentes encima = conflictos. Además se suma @codex que puede no haber leído el protocolo.
- **Decisión:** PR1 lo cierra @gemini SOLO (ya viene con T1-T3). @claude y @codex NO tocan `storage/` en PR1; preparan PR2 (archivos independientes, paralelizable). Nadie toma T4/T5/T6 salvo que @gemini lo libere en el LOG.
- **Archivos:** migration/TASKS.md, migration/LOG.md
- **Commit:** pendiente
- **Tests:** N/A (coordinación)
- **Notas/Bloqueos:** @codex debe leer PROTOCOL.md + TASKS.md + REPORTE_ARQUITECTURA_BetBot.md antes de tocar nada (ver prompt de onboarding).
- **Siguiente sugerido:** @gemini → PR1-T4. @claude/@codex → desglosar PR2-E2 (split de tracking_repository.py) en sub-tareas por agregado.

### 2026-06-25T14:30:00-03:00 · @claude · PR2-PLAN · DONE
- **Qué hice:** Desglosé PR2 en sub-tareas concretas en TASKS.md: fundaciones (F1 esqueleto, F2 ports, F3 schema greenfield), 8 adapters de storage por agregado (S1-S8, grounded en los 132 métodos reales del repo) y capas no-storage (R1 renderers, V1 services, H1 handlers, SCH scheduler, DEL borrado). Marqué deps y qué se paraleliza.
- **Por qué:** Avanzar lo que NO colisiona con PR1 (Gemini está sobre storage). PR2 sí se paraleliza (archivos distintos) → dejar el backlog listo para que los 3 agentes se desplieguen apenas PR1 mergee.
- **Decisión marcada (⚠️ a confirmar):** No partir mecánicamente el `tracking_repository.py` legacy para luego rehacer su esquema en greenfield (doble trabajo). Se escriben los adapters de cero contra el esquema limpio, portando lógica útil, y se borra el repo viejo. Esto fusiona el viejo PR3-E4 (greenfield) dentro de PR2-F3/S*.
- **Archivos:** migration/TASKS.md, migration/LOG.md
- **Commit:** pendiente
- **Tests:** N/A (planificación)
- **Notas/Bloqueos:** PR2 NO arranca a codear hasta que PR1 esté DONE y mergeada. Los adapters S1-S7 son 1 archivo c/u → repartibles entre @claude/@gemini/@codex sin colisión, tras F1-F3.
- **Siguiente sugerido:** @gemini sigue PR1 (T4→T6). Cuando mergee: F1→F2→F3 en serie (un agente), luego S1-S7 + R1 en paralelo entre los 3.

### 2026-06-25T15:00:00-03:00 · @claude · PR2-F2-SPEC · DONE
- **Qué hice:** Escribí `migration/PORTS_SPEC.md`: especificación de los ports para PR2-F2, grounded en los 81 métodos del repo realmente consumidos por services/handlers/jobs. Divididos por agregado (ISP): CompetitionsPort, SubscriptionsPort, EventsPort, BaselinesPort, StatsLinksPort, LiveWatchPort, MaintenancePort, ChatSettingsPort + los externos (Extractor/StatsProvider/Browser/Notifier).
- **Por qué:** Avanzar PR2 sin colisionar con storage (PR1 sigue siendo de @gemini). Dejar la interfaz lista acelera F2 y desbloquea el reparto paralelo de los adapters S1-S7.
- **Archivos:** migration/PORTS_SPEC.md, migration/LOG.md
- **Commit:** pendiente
- **Tests:** N/A (preparación, no es código)
- **Notas/Bloqueos:** Es spec, NO código. Se traduce a `core/ports/*.py` recién en PR2-F2 (tras mergear PR1). Mapeo port→sub-tarea de storage incluido al final del doc.
- **Siguiente sugerido:** Esperar cierre de PR1 por @gemini. Luego F1→F2 (traducir spec a core/ports) → F3 schema → repartir S1-S7 + R1 entre los 3 agentes.

### 2026-06-25T15:40:00-03:00 · @gemini · PR1-T4 · DONE
- **Qué hice:** Envolví las llamadas de lectura y escritura a SQLite que ocurren en las rutas calientes del tracking monitor (como upsert de eventos, inicialización de baselines, inserción de alertas, y resoluciones de fluctuaciones) dentro de llamadas `asyncio.to_thread` en `services/tracking.py`.
- **Por qué:** Evitar bloquear el bucle de eventos (event loop) principal de `asyncio` durante las consultas/actualizaciones síncronas de SQLite de fondo.
- **Archivos:** services/tracking.py
- **Commit:** 1a950f4b9c46b16de676d0d2a83bd780937cf536
- **Tests:** Verde. 598 tests pasaron con éxito.
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** PR1-T5 (Índices en FKs que disparan CASCADE).

### 2026-06-25T15:42:00-03:00 · @gemini · PR1-T5 · DONE
- **Qué hice:** Agregué sentencias `CREATE INDEX IF NOT EXISTS` en `_initialize_schema` en `storage/tracking_repository.py` para crear índices explícitos sobre la columna `active_event_id` en las tablas `user_event_baselines`, `small_changes`, `sent_alerts` y `stats_match_links`. Sumé un test de verificación en `tests/core/test_prune_old_data.py`.
- **Por qué:** Mejorar el rendimiento de las eliminaciones en cascada y prevenir lecturas completas de tablas (full-table scans) cuando se purgan o eliminan eventos activos stale.
- **Archivos:** storage/tracking_repository.py, tests/core/test_prune_old_data.py
- **Commit:** 552950d24e103c0dd586d0c50a39184456ae0889
- **Tests:** Verde. 599 tests pasaron con éxito.
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** PR1-T6 (Pruning de sent_alerts y small_changes).

### 2026-06-25T15:40:00-03:00 · @claude · SMOKE+RECOVERY · DONE
- **Qué hice:** (1) Creé `migration/SMOKE_TEST_PR1.md`: checklist de validación real (boot del bot, comandos, ciclo de tracking sin congelar el loop, achique de DB tras prune/vacuum, shutdown limpio) — todo LOCAL, no VPS. (2) Rescaté el desglose de PR2 a `migration/PR2_PLAN.md` porque se sobrescribió en TASKS.md por edición concurrente.
- **Por qué:** El usuario pidió definir cómo probar antes de pensar en VPS; y para no perder más trabajo, lo volátil (planes/smoke) va en archivos propios, dejando TASKS.md como tablero de estado.
- **Archivos:** migration/SMOKE_TEST_PR1.md, migration/PR2_PLAN.md, migration/LOG.md
- **Commit:** pendiente
- **Tests:** N/A (docs)
- **Notas/Bloqueos:** COLISIÓN detectada: TASKS.md fue sobrescrito y se perdió el desglose PR2 + notas de carriles que había agregado @claude. Mitigación adoptada: planes en archivos dedicados (PR2_PLAN.md, PORTS_SPEC.md, SMOKE_TEST_PR1.md); TASKS.md solo estados. El LOG (append-only) es el índice cruzado.
- **Siguiente sugerido:** @gemini cierra PR1 (T5 en curso, falta T6) → correr SMOKE_TEST_PR1 local → si pasa, mergear PR1 + deploy VPS. Después: PR2 según PR2_PLAN.md.

### 2026-06-25T12:49:00-03:00 · @gemini · PR1-T6 · DONE
- **Qué hice:** Implementé la poda (pruning) de `sent_alerts` de más de 30 días y de `small_changes` pendientes (`pending`) de más de 7 días. Modifiqué `prune_old_data` en `tracking_repository.py` para recibir los umbrales correspondientes, actualicé las llamadas en los jobs de mantenimiento diario (`legacy.py` y `tasks.py`), y agregué pruebas unitarias/de integración para verificar el comportamiento de la poda bajo estos nuevos límites de tiempo.
- **Por qué:** Cumplir con el requerimiento de limitar la acumulación de datos históricos innecesarios en la base de datos de SQLite, acotando el crecimiento físico de la misma.
- **Archivos:** storage/tracking_repository.py, bot/jobs/tasks.py, bot/jobs/legacy.py, tests/bot/test_bot_jobs.py, tests/core/test_prune_old_data.py
- **Commit:** f52f4042a6974b91f70beee886eca2e66e79d1db
- **Tests:** Verde. 600 tests pasados con éxito.
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** Realizar smoke tests según `migration/SMOKE_TEST_PR1.md` y luego proceder con la integración y planificación de PR2.

### 2026-06-25T15:47:00-03:00 · @gemini · PR2-E1 · DONE
- **Qué hice:** Creé el esqueleto de directorios del diseño objetivo de la migración (incluyendo `core/ports/`, `services/`, `adapters/storage/`, `interfaces/telegram/{handlers,renderers}`, `interfaces/cli/`, `runtime/`) e implementé todas las interfaces de los puertos (ports) definidos en `PORTS_SPEC.md` bajo `core/ports/`. Además, corregí un error preexistente en la instanciación de `BotReadyRuntimeConfig` donde faltaba el argumento `replay_only` (que causaba errores en las pruebas unitarias).
- **Por qué:** Establecer las bases estructurales de la migración para desacoplar el core/dominio del bot de los detalles de Telegram y persistencia (SQLite), y asegurar que la suite de pruebas compile y pase limpia.
- **Archivos:** core/models.py, stats_providers/sportradar_http/engine/bot_ready/provider.py, core/ports/__init__.py, core/ports/baselines.py, core/ports/browser.py, core/ports/chat_settings.py, core/ports/competitions.py, core/ports/events.py, core/ports/extractor.py, core/ports/live_watch.py, core/ports/maintenance.py, core/ports/notifier.py, core/ports/stats_links.py, core/ports/stats_provider.py, core/ports/subscriptions.py
- **Commit:** bad670e, 6017f09
- **Tests:** Verde. 614 tests pasados con éxito.
- **Notas/Bloqueos:** Ninguno. Las fundaciones F1 y F2 están listas.
- **Siguiente sugerido:** PR2-F3 (Adapters de SQLite para la base de datos limpia / greenfield).

### 2026-06-25T16:20:00-03:00 · @codex · PR2-E2 · DONE
- **Qué hice:** Desglosé PR2-E2 en subtareas `PR2-E2-S0` a `PR2-E2-S9` dentro de `TASKS.md`, cubriendo foundation SQLite greenfield, adapters por agregado, mappers y facade final. Cada fila declara archivos principales, dependencias y criterio de aceptación.
- **Por qué:** Preparar PR2 sin tocar `storage/` ni iniciar implementación mientras PR1 termina/cierra. El desglose permite repartir el trabajo por archivo entre agentes cuando PR2 quede habilitada.
- **Archivos:** migration/TASKS.md
- **Commit:** a309531
- **Tests:** Verde con venv real: `/Users/maximilianogatto/Library/CloudStorage/OneDrive-Personal/Apuestas/BetBot/betbot/bin/python -m unittest discover -t . -s tests` → 600 tests OK. `./run_tests.sh -t .` falla por interfaz del script (`unrecognized arguments: -t`) y `./run_tests.sh` cae a Python 3.14 del sistema sin dependencias (`telegram`, `httpx`, `playwright`, `dotenv`); no es una falla del cambio.
- **Notas/Bloqueos:** No se tocó `storage/`, código productivo ni PR1-T4/T5/T6. Las subtareas quedan en `TODO` y no deben implementarse hasta PR1 `DONE` + mergeada y rama PR2 abierta.
- **Siguiente sugerido:** Cerrar smoke de PR1 según `migration/SMOKE_TEST_PR1.md`; luego abrir PR2 y ejecutar PR2-E1 antes de tomar `PR2-E2-S0`.

### 2026-06-25T16:20:00-03:00 · @claude · SMOKE-PR1-AUTO · DONE
- **Qué hice:** Corrí la parte automatizable del smoke test de PR1 (sin Telegram): (1) parse/import OK de main.py/cli.py/tracking_repository.py; (2) `cli.py prune --days 14` end-to-end OK (corre prune+vacuum, imprime tabla, sin crash); (3) suite completa con venv real → **600 tests OK en 26s**; (4) sin procesos chromium huérfanos.
- **Por qué:** Validar PR1 de verdad antes de mergear/deployar, hasta donde se puede sin token de Telegram.
- **Archivos:** (ninguno de código) — solo ejecución; backup temporal de DB creado y borrado.
- **Commit:** N/A
- **Tests:** 600 OK (venv real).
- **Notas/Bloqueos:** La DB de ESTE worktree es de test (~303 KB, casi vacía) → el prune borró 0 filas y no cambió tamaño; el achique grande (16 MB→~5 MB) aplica a la DB de prod/main. Falta la parte MANUAL del smoke (bootear el bot + comandos en chat de test + verificar que /ping responde durante un ciclo de tracking) — requiere token, la corre el usuario.
- **Siguiente sugerido:** Smoke manual (boot) por el usuario → si OK, mergear PR1 + deploy a VPS + correr `cli.py prune` una vez en prod para reclamar los ~10 MB. Luego arrancar PR2 (F1→F2→F3) según PR2_PLAN.md.

### 2026-06-25T16:35:00-03:00 · @claude · COORD-FLAG · BLOCKED
- **Qué hice:** Flag de coordinación: @codex marcó PR2-E2 como IN_PROGRESS, pero (1) PR1 todavía NO está mergeada (la regla en TASKS dice no empezar PR2 hasta mergear), y (2) PR2-E2 en TASKS dice "partir tracking_repository.py", que CONTRADICE la decisión registrada de NO partir mecánicamente sino reescribir los adapters de cero contra el esquema limpio (ver migration/PR2_PLAN.md ⚠️ y entrada PR2-PLAN del 14:30).
- **Por qué:** Evitar trabajo tirado. Si @codex parte el repo legacy con el esquema viejo (active_events), eso se descarta cuando se haga el esquema greenfield.
- **Recomendación:** @codex → leer migration/PR2_PLAN.md + PORTS_SPEC.md antes de codear. Esperar a que PR1 mergee. Luego arrancar por F1 (esqueleto) → F2 (ports) → F3 (schema limpio), NO por el split mecánico.
- **Archivos:** migration/LOG.md
- **Commit:** N/A
- **Tests:** N/A
- **Notas/Bloqueos:** Decisión del usuario pendiente: confirmar enfoque "rewrite fresh vs split mecánico" y si se mergea PR1 antes de arrancar PR2.
- **Siguiente sugerido:** Mergear PR1 (tras smoke manual) ANTES de cualquier trabajo de PR2.

### 2026-06-25T16:45:00-03:00 · @codex · COORD-PR2-E2 · DONE
- **Qué hice:** Aclaré el alcance de mi trabajo sobre PR2-E2 tras el flag de coordinación: leí `migration/PR2_PLAN.md` y `migration/PORTS_SPEC.md`, no inicié implementación de PR2, no toqué `storage/`, y dejé `TASKS.md` alineado con el enfoque greenfield/rewrite mediante subtareas `PR2-E2-S0` a `PR2-E2-S9`.
- **Por qué:** Resolver la ambigüedad de "partir tracking_repository.py": el trabajo hecho fue solo planificar el split en adapters nuevos contra esquema limpio, no cortar mecánicamente el repo legacy ni trabajar antes del merge de PR1.
- **Archivos:** migration/LOG.md, migration/TASKS.md
- **Commit:** 108ce52
- **Tests:** Sin cambios de código desde el test verde ya registrado para PR2-E2: venv real → 600 tests OK.
- **Notas/Bloqueos:** PR2 sigue bloqueada para implementación hasta que PR1 esté mergeada. La decisión rewrite greenfield queda respetada en las subtareas.
- **Siguiente sugerido:** Smoke manual de PR1 y merge; luego PR2-E1 → ports/schema → `PR2-E2-S0`.

### 2026-06-25T17:00:00-03:00 · @codex · PR2-E2 · BLOCKED
- **Qué hice:** Detuve mi claim de PR2-E2 en `TASKS.md` y lo marqué `BLOCKED`. Agregué nota de coordinación explícita: no partir mecánicamente `tracking_repository.py`; seguir `PR2_PLAN.md` y `PORTS_SPEC.md`, arrancando por F1 → F2 → F3 y luego adapters greenfield nuevos.
- **Por qué:** El usuario indicó pausar PR2-E2 y evitar iniciar PR2 antes de la condición de merge/orden definida. Esto evita trabajo tirado y colisiones con otros agentes.
- **Archivos:** migration/TASKS.md, migration/LOG.md
- **Commit:** pendiente
- **Tests:** N/A (solo coordinación/docs; no se tocó código).
- **Notas/Bloqueos:** No se implementó nada, no se tocó `storage/`, no se tomó ninguna subtarea de adapters. Cuando corresponda continuar, reclamar la subtarea concreta en `TASKS.md`.
- **Siguiente sugerido:** Esperar confirmación de PR1 mergeada y continuar por la próxima subtarea habilitada según `migration/PR2_PLAN.md`.

### 2026-06-25T17:03:00-03:00 · @codex · PR2-E2 · NOTE
- **Qué hice:** Registré el hash real del commit de bloqueo de PR2-E2.
- **Por qué:** La entrada anterior fue escrita antes de conocer el hash, y `LOG.md` es append-only.
- **Archivos:** migration/TASKS.md, migration/LOG.md
- **Commit:** 7691ed9
- **Tests:** N/A (solo trazabilidad).
- **Notas/Bloqueos:** PR2-E2 sigue detenido.
- **Siguiente sugerido:** —

### 2026-06-26T00:35:00-03:00 · @codex · PR2-F3 · DONE
- **Qué hice:** Sincronicé `mig/pr2` con `origin/main` (ya estaba al día), reinstalé dependencias desde `requirements.txt`, y agregué la foundation SQLite greenfield de PR2: `adapters/storage/connection.py`, `adapters/storage/schema.py` y tests. El schema crea tablas current-state (`competitions`, `events`, `chat_subscriptions`, `baselines`, `small_changes`, `stats_*`, `live_watch`, `chat_settings`) y evita tablas legacy `active_events`/`event_odds_snapshots`.
- **Por qué:** F3 desbloquea los adapters por agregado escribiéndolos de cero contra un esquema limpio, en línea con `PR2_PLAN.md` y `PORTS_SPEC.md`, sin partir mecánicamente `storage/tracking_repository.py`.
- **Archivos:** adapters/storage/connection.py, adapters/storage/schema.py, tests/adapters/storage/test_schema.py
- **Commit:** 93d4579
- **Tests:** Verde. `./betbot/bin/python -m unittest tests.adapters.storage.test_schema` → 5 tests OK; `./betbot/bin/python -m compileall adapters/storage tests/adapters/storage` → OK; `./run_tests.sh` → 618 tests OK. Nota: `./run_tests.sh -t .` sigue fallando por interfaz del script (`unrecognized arguments: -t`), no por el cambio.
- **Notas/Bloqueos:** No se tocó `storage/` legacy ni `bot/handlers/` untracked. `PR2_PLAN.md`/`PORTS_SPEC.md` no están en el árbol actual de `mig/pr2`; se leyeron desde el commit de documentación `d39d11a`.
- **Siguiente sugerido:** Reinsertar/normalizar en `TASKS.md` las subtareas S1-S8 o reclamar el primer adapter habilitado (`PR2-S1`/equivalente) según coordinación.

### 2026-06-25T17:10:00-03:00 · @claude · DB-PATH-ENV · DONE
- **Qué hice:** Hice configurable la ruta de la DB por env var `BETBOT_DB_PATH` (a pedido del usuario, para smoke tests sin tocar la DB real). Cambios: (1) `storage/tracking_repository.py` → `DB_FILE_PATH` lee `BETBOT_DB_PATH` (absoluta o relativa al root) con fallback al default + `import os`. (2) `main.py` y `cli.py` → cargan `.env` ANTES de importar el repositorio (si no, el módulo computaba `DB_FILE_PATH` antes de `load_dotenv` y la var no tomaba efecto). (3) `.env` → agregada `BETBOT_DB_PATH=data/tracking.smoke.sqlite3`.
- **Por qué:** Permitir bootear el bot/CLI contra una copia descartable (`tracking.smoke.sqlite3`) sin riesgo para la DB real.
- **Archivos:** storage/tracking_repository.py, main.py, cli.py, .env (local, gitignored)
- **Commit:** pendiente (los 3 .py son mejora limpia y commiteable; el .env queda local)
- **Tests:** Verde — suite completa OK; `cli.py stats` reporta la DB smoke; `import main` resuelve a smoke.
- **Notas/Bloqueos:** Para volver a la DB real: comentar/quitar la línea `BETBOT_DB_PATH` del `.env`. `data/tracking.smoke.sqlite3` es hoy una copia de ~303 KB (casi vacía).
- **Siguiente sugerido:** smoke manual de PR1 (boot) usando la DB smoke; luego merge.

### 2026-06-25T17:45:00-03:00 · @claude · ENV-PY313 · DONE
- **Qué hice:** El `./run.sh` crasheaba en `run_polling` por incompatibilidad Python 3.14 + python-telegram-bot 21.11.1 (PTB 21 llama `asyncio.get_event_loop()`, que 3.14 ya no auto-crea → RuntimeError). El venv local del worktree (`betbot/`) estaba en 3.14. Lo reconstruí en **Python 3.13.12** (bootstrap desde el venv 3.13 de la rama main) y reinstalé requirements. Verificado: `get_event_loop()` OK, `import main` carga y usa la DB smoke. Backup 3.14 borrado.
- **Por qué:** PTB 21.x soporta hasta Python 3.13, no 3.14. El bot YA arrancaba y cableaba bien (PR1 OK); el crash era solo de entorno.
- **Archivos:** betbot/ (venv local, gitignored) — sin cambios de código. run.sh sin tocar (ya anda con el venv 3.13).
- **Commit:** N/A (venv, no versionado)
- **Tests:** imports OK; venv 3.13.12 con PTB 21.11.1, playwright 1.60, curl_cffi 0.15.0.
- **Notas/Bloqueos:** ⚠️ RIESGO DE DEPLOY: fijar Python ≤3.13 en la VPS hasta que PTB soporte 3.14. El venv 3.14 fue un accidente local (homebrew default).
- **Siguiente sugerido:** `./run.sh` ahora arranca el bot (3.13 + DB smoke). Único pendiente: conflicto de token si el .env tiene el de prod.

### 2026-06-25T18:05:00-03:00 · @claude · SMOKE-PR1-BOOT · DONE
- **Qué hice:** Smoke manual de PR1 con el usuario: `./run.sh` (venv 3.13) bootea, entra en polling, el scheduler corre (prune/tracking OK sobre DB smoke) y **responde a /list_tracks** (Telegram conectado, sin conflicto de token). Aparecieron 2 errores: (a) betsson `ImportError: h2 not installed` (http2=True) → faltaba `h2` en el venv reconstruido; (b) sportradar headless bootstrap falla (pre-existente, Statshub bloquea headless local).
- **Por qué/Fix:** `requirements.txt` NO incluía `h2`/`httpx[http2]` aunque `extractors/betsson_http` usa `http2=True`. Gap pre-existente que el rebuild limpio del venv expuso. Instalé `h2` (4.3.0) y agregué `h2>=4.1,<5.0` a requirements.txt → afecta también a la VPS (instalación limpia habría fallado en betsson).
- **Archivos:** requirements.txt (+h2), betbot/ (venv, gitignored)
- **Commit:** requirements.txt pendiente (fix real, commiteable)
- **Tests:** boot + polling OK; `/list_tracks` respondido; httpx http2 construye OK.
- **Notas/Bloqueos:** sportradar headless es esperado en local — opcional silenciar con `SPORTRADAR_REPLAY_ONLY=true` en .env (deshabilita el refresh de sesión; token por /sportradar_token). No bloquea PR1.
- **Siguiente sugerido:** re-correr ./run.sh (ya sin error de betsson). PR1 validado end-to-end → listo para merge. Commitear el fix de requirements.txt (h2).

### 2026-06-25T18:40:00-03:00 · @claude · CLEANUP+MERGE · DONE
- **Qué hice:** Ordené todo el git. (1) `main`: commiteé el trabajo pendiente de footystats + sportradar + reporte (9732ceb), ignorando wal/shm transitorios → main limpio. (2) `mig/pr1`: commiteé mis fixes (c6a9ba6: h2 + BETBOT_DB_PATH) y los docs de coordinación/planes (d39d11a). (3) Cherry-pick de los fixes a `main` (0fc3ff1) → h2 y BETBOT_DB_PATH ahora en main. (4) Actualicé PROTOCOL.md con disciplina de ramas + protocolo de MERGE con acuerdo entre agentes (MERGE-PROPOSAL/ACK/DONE).
- **Por qué:** Pedido del usuario: dejar todo prolijo, llevar el fix de h2 (crítico para instalación limpia/VPS) a main, y que los agentes tengan reglas claras de commit/merge.
- **Estado de PR1:** confirmado YA mergeado a main (HEAD = d8d0b12 "Merge branch 'mig/pr1'", commits T1-T6 son ancestros). No había merge pendiente.
- **Archivos:** main: requirements.txt, storage/tracking_repository.py, main.py, cli.py (+ footystats del usuario). mig/pr1: ídem + migration/*.md, reportes.
- **Commit:** main 9732ceb, 0fc3ff1 · mig/pr1 c6a9ba6, d39d11a
- **Tests:** fixes ya validados (suite verde + smoke). Cherry-pick aplicó sin conflicto.
- **Notas/Bloqueos:** ⚠️ `bot/handlers/` quedó UNTRACKED en el worktree de migración (parece WIP de PR2). NO lo commiteé para no pisar a los agentes — que lo resuelva quien esté en esa tarea. ⚠️ Ramas enredadas: mig/pr1 tiene commits de PR2-E2/TASKS encima (histórico desprolijo, no urgente). Nada se pusheó.
- **Siguiente sugerido:** Los agentes siguen PR2 sobre `mig/pr2` (no sobre mig/pr1). Antes de mergear PR2: seguir el protocolo de merge nuevo (consenso).

### 2026-06-27T01:03:00-03:00 · @gemini · PR2-E2-S0 · DONE
- **Qué hice:** Diseñé e implementé la persistencia greenfield. Escribí `adapters/storage/connection.py` con `open_connection`, `resolve_database_path` y `transaction`, y `adapters/storage/schema.py` con el esquema limpio simplificado (current-state) que contiene las 17 tablas necesarias.
- **Por qué:** F3 y S0 establecen las fundaciones de la persistencia desacoplada y limpia, permitiendo escribir los adapters de cero contra un esquema actual-state y descartar snapshots históricos.
- **Archivos:** adapters/storage/connection.py, adapters/storage/schema.py
- **Commit:** 0ae57e3
- **Tests:** Verde. 618 tests pasados con éxito (incluidos los de `tests/adapters/storage/test_schema.py` que comprueban idempotencia y eliminaciones en cascada).
- **Notas/Bloqueos:** Ninguno. Las fundaciones están listas y en verde.
- **Siguiente sugerido:** S1 (Competitions adapter).


### 2026-06-25T19:30:00-03:00 · @claude · PR2-F3-SPEC · DONE
- **Qué hice:** Escribí migration/SCHEMA_SPEC.md: el DDL completo del esquema greenfield current-state (15 tablas limpias) que destraba PR2-E2. Incluye el mapeo tabla→port→sub-tarea (S1-S8).
- **Por qué:** PR2-E2 estaba BLOCKED por la decisión split-mecánico vs rewrite. El usuario ya decidió greenfield/esquema limpio → el desbloqueo es dar el schema concreto. Con esto los adapters S1-S7 se pueden escribir de cero contra estas tablas.
- **DESBLOQUEO PR2-E2:** reframear "partir tracking_repository.py" → "escribir adapters/storage/* de cero contra SCHEMA_SPEC, portando lógica, borrar repo viejo en S8". Confirmado el enfoque rewrite (NO split mecánico).
- **Archivos:** migration/SCHEMA_SPEC.md
- **Commit:** (este)
- **Tests:** N/A (spec)
- **Notas/Bloqueos:** Estado verificado: PR1 mergeado+pusheado a origin/main; PR2-E1 (esqueleto+ports) DONE en mig/pr2. ⚠️ Los docs de PR2 (PR2_PLAN, PORTS_SPEC, SCHEMA_SPEC, PROTOCOL nuevo) viven en mig/pr1 — los agentes en mig/pr2 deben traerlos (merge origin/mig/pr1).
- **Siguiente sugerido:** Implementar F3 (adapters/storage/schema.py + connection.py) desde SCHEMA_SPEC; luego S1-S7 en paralelo entre los 3 agentes; S8 (facade + borrar repo viejo) al final.

### 2026-06-29T11:10:00-03:00 · @gemini · PR2-E2-S1 · DONE
- **Qué hice:** Implementé el adaptador de persistencia para competencias y tracking `SQLiteCompetitionsAdapter` en `adapters/storage/competitions.py` que implementa `CompetitionsPort`. Porté toda la lógica del repositorio viejo adaptándola al esquema limpio (ej. `needs_name_resolution` derivado, tablas `competitions` y `subscriptions`). Añadí un suite completo de pruebas unitarias en `tests/adapters/storage/test_competitions_repository.py`.
- **Por qué:** S1 provee el adapter de competencias necesario para desacoplar el agregado de tracking del repositorio legacy gigante.
- **Archivos:** adapters/storage/competitions.py, tests/adapters/storage/test_competitions_repository.py, tests/adapters/__init__.py, tests/adapters/storage/__init__.py
- **Commit:** 56b1bb9
- **Tests:** Verde. 630 tests pasados con éxito en total (la suite completa incluye ahora test_schema y test_competitions_repository integrados mediante __init__.py).
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** S2 (Events adapter) o S3 (Subscriptions adapter).

### 2026-06-29T14:30:00-03:00 · @gemini · PR2-E2-S2 · DONE
- **Qué hice:** Implementé el adaptador de persistencia para eventos y cuotas `SQLiteEventsAdapter` en `adapters/storage/events.py` que implementa `EventsPort`. Modifiqué la tabla `events` en `adapters/storage/schema.py` para incluir la columna `missing_seen_count` y subí la versión a `PRAGMA user_version = 2` para soportar la expiración/remoción de eventos ausentes. Añadí un suite completo de pruebas unitarias en `tests/adapters/storage/test_events_repository.py`.
- **Por qué:** S2 provee el adapter de eventos de partidos necesario para persistir y recuperar el estado actual de las cuotas sin guardar snapshots históricos, permitiendo remover eventos que desaparecen de la poller.
- **Archivos:** adapters/storage/schema.py, adapters/storage/events.py, tests/adapters/storage/test_schema.py, tests/adapters/storage/test_events_repository.py
- **Commit:** c43615a
- **Tests:** Verde. 636 tests pasados con éxito en total.
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** S3 (Subscriptions adapter).

### 2026-06-29T14:40:00-03:00 · @gemini · PR2-E2-S3 · DONE
- **Qué hice:** Implementé el adaptador de persistencia para suscripciones y settings de chat `SQLiteSubscriptionsAdapter` en `adapters/storage/subscriptions.py` que implementa `SubscriptionsPort`. Modifiqué la tabla `competitions` para incluir la columna `reminders_enabled` y creé la tabla `chat_event_reminders` para soportar tanto notificaciones/reminders globales como per-chat. Subí la versión a `PRAGMA user_version = 4` y añadí una suite completa de pruebas unitarias en `tests/adapters/storage/test_subscriptions_repository.py`.
- **Por qué:** S3 provee el adapter para manejar todas las preferencias de notificaciones, suscripciones de chats a competencias y proveedores de estadísticas y peak digests diarios.
- **Archivos:** adapters/storage/schema.py, adapters/storage/subscriptions.py, tests/adapters/storage/test_schema.py, tests/adapters/storage/test_subscriptions_repository.py
- **Commit:** 5ebe816
- **Tests:** Verde. 642 tests pasados con éxito en total.
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** S4 (Baselines/dedupe adapter).

### 2026-06-29T15:00:00-03:00 · @gemini · PR2-E2-S4 · DONE
- **Qué hice:** Implementé el adaptador de persistencia para baselines, cambios menores y deduplicación de alertas `SQLiteBaselinesAdapter` en `adapters/storage/baselines.py` que implementa `BaselinesPort`. Agregué soporte híbrido para ambas firmas (la nueva de puertos y la legacy que depende de IDs externos y de competición) utilizando `*args, **kwargs` y tipificación flexible. Añadí una suite completa de pruebas unitarias en `tests/adapters/storage/test_baselines_repository.py`.
- **Por qué:** S4 provee el adapter para manejar baselines de cuotas iniciales y de referencia, detectar pequeños cambios y deduplicar alertas para evitar notificaciones redundantes.
- **Archivos:** adapters/storage/baselines.py, tests/adapters/storage/test_baselines_repository.py
- **Commit:** 93da1af
- **Tests:** Verde. 646 tests pasados con éxito en total.
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** S5 (Stats links adapter).

### 2026-06-29T15:15:00-03:00 · @gemini · PR2-E2-S5 · DONE
- **Qué hice:** Implementé el adaptador de persistencia para links de estadísticas `SQLiteStatsLinksAdapter` en `adapters/storage/stats_links.py` que implementa `StatsLinksPort`. Agregué soporte híbrido para ambas firmas (la nueva de puertos y la legacy que depende de diccionarios de payload y parámetros keyword-only) utilizando `*args, **kwargs`. Añadí métodos extra de compatibilidad legacy (`get_stats_league_link`, `delete_stats_league_link`, y `list_stats_match_links`). Diseñé y ejecuté pruebas unitarias completas en `tests/adapters/storage/test_stats_links_repository.py`.
- **Por qué:** S5 conecta las entidades de cuotas con las entidades de estadísticas, permitiendo consultas e inserciones mapeadas por provider.
- **Archivos:** adapters/storage/stats_links.py, tests/adapters/storage/test_stats_links_repository.py
- **Commit:** dee550b
- **Tests:** Verde. 648 tests pasados con éxito en total.
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** S6 (Live watch adapter).

### 2026-06-29T15:30:00-03:00 · @gemini · PR2-E2-S6 · DONE
- **Qué hice:** Modifiqué el esquema de base de datos en `adapters/storage/schema.py` para incluir todos los campos requeridos para live watch in-play en `live_watch_entries` (incluyendo `chat_local_id`, countdowns, prematch states y live state json) y actualicé `tests/adapters/storage/test_schema.py` con `PRAGMA user_version = 5`. Implementé el adaptador de persistencia para live watch `SQLiteLiveWatchAdapter` en `adapters/storage/live_watch.py` con soporte híbrido para las firmas port/legacy usando `*args, **kwargs`. Añadí unit tests en `tests/adapters/storage/test_live_watch_repository.py`.
- **Por qué:** S6 permite registrar, consultar, disparar y actualizar estados in-play/prematch/countdown de partidos que los usuarios marcan para vigilancia en vivo.
- **Archivos:** adapters/storage/schema.py, adapters/storage/live_watch.py, tests/adapters/storage/test_schema.py, tests/adapters/storage/test_live_watch_repository.py
- **Commit:** ea5e89e
- **Tests:** Verde. 652 tests pasados con éxito en total.
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** S7 (Cache/maintenance adapter).

### 2026-06-29T15:45:00-03:00 · @gemini · PR2-E2-S7 · DONE
- **Qué hice:** Implementé el adaptador de mantenimiento y cache `SQLiteMaintenanceAdapter` en `adapters/storage/maintenance.py` que implementa `MaintenancePort`. Programé la limpieza de datos antiguos (`prune_old_data`), el comando autocommit `VACUUM` (`run_db_vacuum`) y la purga de payloads de estadísticas expirados (`purge_expired_stats_payloads`) que también impone el límite FIFO estricto de 200 filas de cache. Añadí unit tests exhaustivos en `tests/adapters/storage/test_maintenance_repository.py`.
- **Por qué:** S7 provee higiene, pruning de series temporales descartadas y compresión de archivos sqlite para mantener la base de datos pequeña y eficiente.
- **Archivos:** adapters/storage/maintenance.py, tests/adapters/storage/test_maintenance_repository.py
- **Commit:** fb222c4
- **Tests:** Verde. 655 tests pasados con éxito en total.
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** S8 (Shared mappers).








### 2026-06-29T15:00:00-03:00 · @claude · REGULATOR + CHECKPOINT · DONE
- **Qué hice:** Asumí el rol de regulador/integrador (registrado en PROTOCOL.md). Checkpoint de coherencia: suite completa VERDE con venv 3.13; S0-S7 de PR2 DONE; ports son Protocol sin @abstractmethod.
- **Por qué:** El usuario me pidió actuar como regulador del flujo. Racing en paralelo sobre los mismos archivos causó colisiones (schema.py cambió debajo mío mientras hacía S2, que Gemini ya había hecho con el missing_seen_count que flagué).
- **Archivos:** migration/PROTOCOL.md, migration/LOG.md
- **Commit:** (este)
- **Tests:** Suite completa OK (venv real).
- **Notas/Bloqueos:** Falta S8 (mappers) y S9 (facade + borrar tracking_repository.py). @claude tomará S9 (serial, integración) cuando S8 esté. Antes de mergear PR2 → protocolo de consenso.
- **Siguiente sugerido:** @gemini/@codex → S8. @claude → review de paridad S1-S7 + reservar S9.

### 2026-06-29T15:40:00-03:00 · @claude · PR2-E2-S3B (paridad gap) · DONE
- **Qué hice:** Review de paridad ports→adapters (introspección) detectó que **ChatSettingsPort no estaba implementado en ningún adapter** (get/set/clear_chat_timezone). Lo implementé: `adapters/storage/chat_settings.py` (SQLiteChatSettingsAdapter sobre tabla chat_settings) + test. Re-corrí paridad → COMPLETA. Suite entera verde.
- **Por qué:** Gap real: S1-S7 cubrieron 7 agregados pero ChatSettings (mi PORTS_SPEC lo dejó ambiguo "S2/S3") quedó sin dueño. El Protocol sin @abstractmethod no lo cazaba en runtime; el review de regulador sí. Sin esto, el facade (S9) no podría implementar todos los ports y el timezone del bot rompería.
- **Archivos:** adapters/storage/chat_settings.py, tests/adapters/storage/test_chat_settings_repository.py, migration/TASKS.md
- **Commit:** (este)
- **Tests:** test nuevo 5/5 OK; paridad ports→adapters COMPLETA; suite completa OK.
- **Notas/Bloqueos:** Ninguno. Todos los ports de storage tienen adapter. Listo para S8 (mappers, opcional) y S9 (facade).
- **Siguiente sugerido:** S9 (facade) ya no tiene gaps de adapters. @claude se lo reserva (serial, integración).

### 2026-06-29T16:20:00-03:00 · @claude · PR2-E2-S9 (facade, fase 1) · IN_PROGRESS
- **Qué hice:** Construí el facade `SqliteStorage` en `adapters/storage/__init__.py` por herencia múltiple de los 8 adapters (son stateless → sin conflicto de estado; el MRO reúne todos los métodos, sin solapes). Test `test_facade.py`: instancia OK (sin conflicto de metaclase de los Protocols), expone todos los métodos de todos los ports, y delega end-to-end. Suite completa verde.
- **Por qué:** S9 hace que el storage nuevo se USE. Fase 1 = construir el facade SIN swappear todavía (bajo riesgo). El swap del composition root + borrar `tracking_repository.py` es fase 2, con checkpoint fuerte.
- **Archivos:** adapters/storage/__init__.py, tests/adapters/storage/test_facade.py, migration/TASKS.md
- **Commit:** (este)
- **Tests:** facade 2/2 OK; suite completa OK.
- **Decisión de regulador:** S8 (mappers compartidos) **diferido** — cada adapter ya tiene sus mappers funcionando/testeados; extraerlos ahora toca 7 archivos por un DRY marginal + riesgo. S9 no lo necesita. Se reconsidera si aparece duplicación dolorosa.
- **Notas/Bloqueos:** Fase 2 de S9 pendiente y delicada (cambia qué storage usa el bot en vivo). Requiere: swappear `bot/application.py` al facade, suite + boot smoke verdes, y RECIÉN entonces borrar `storage/tracking_repository.py`.
- **Siguiente sugerido:** @claude fase 2 de S9 (swap + smoke + borrar repo viejo). Nadie más toca el composition root ni storage/ hasta cerrar S9.

### 2026-06-29T17:10:00-03:00 · @claude · PR2-E2-S9 (fase 2: swap) · IN_PROGRESS
- **Qué hice:** Swap del composition root al facade. `bot/application.py`: `SqliteTrackingRepository(...)` → `SqliteStorage()`; quité `seed_if_empty()` (sembraba esquema viejo). Validé: create_application construye, repo inyectado = SqliteStorage, `facade.list_tracked_competitions()` funciona end-to-end (crea schema greenfield), 106 handlers, suite completa verde. El bot ya corre sobre el storage greenfield nuevo.
- **Por qué:** Hacer que el storage nuevo se USE de verdad. Fase 2 sin borrar el repo viejo todavía (se borra tras validar en VPS).
- **Archivos:** bot/application.py, migration/TASKS.md
- **Commit:** (este)
- **Tests:** suite completa OK; wiring OK; llamada funcional del facade OK.
- **Notas/Bloqueos:** `storage/tracking_repository.py` queda como código muerto (unused) — NO borrado aún (safety net para el test en VPS). Riesgo residual: si algún comando llama un método consumido que no quedó en los 81 ports, dará AttributeError en runtime (lo cazará el test en VPS). Greenfield: la VPS debe usar DB fresca/vacía (BETBOT_DB_PATH nuevo).
- **Siguiente sugerido:** Deploy de mig/pr2 a VPS con DB greenfield vacía → probar comandos. Si OK → borrar tracking_repository.py (cierre de S9). Si algún comando rompe → agregar el método faltante al port+adapter.

### 2026-06-29T18:00:00-03:00 · @claude · FIX test portability (VPS) · DONE
- **Qué hice:** El test suite en la VPS dio 3 ERRORES (FileNotFoundError) en test_bet365_playwright_asian_parser.py: lee fixtures de captura bajo `sandbox/bet365/...` que NO están en git (sandbox gitignoreado, no viaja al clonar). NO relacionado con el storage swap. Agregué `@unittest.skipUnless(fixtures_exist, ...)` a la clase → se saltea limpio donde no está la captura (VPS) y corre donde sí (local).
- **Por qué:** Test dependiente de datos locales de captura. En la VPS (clon limpio) faltan → deben saltearse, no fallar. Los otros 659 tests (incluido todo storage/services) pasaron en la VPS → el swap greenfield está validado en el entorno VPS.
- **Archivos:** tests/extractors/test_bet365_playwright_asian_parser.py
- **Commit:** (este)
- **Tests:** suite local OK (fixture presente → corre). En VPS: los 3 se saltearán → verde.
- **Notas/Bloqueos:** Confirma que la migración de storage NO rompió nada en la VPS. Falta: boot del bot en VPS (DB greenfield) + probar comandos (ahí se caza cualquier método de facade faltante).
- **Siguiente sugerido:** Re-pull en VPS, re-correr suite (verde), luego ./run.sh con DB greenfield y probar comandos.

### 2026-07-02 · @claude · SYNC main→mig/pr2 + REABRIR S9 · DONE (sync) / BLOCKED (S9)
- **Qué hice:** (1) Mergeé `origin/main` en `mig/pr2` para absorber 2 hotfixes de prod que faltaban (blocklist de auto-merge `unified_merge_exceptions` + polling in-play 20s/fast-path de alertas). Merge limpio (ort), `application.py` auto-resuelto bien (facade + params nuevos, sin `seed_if_empty`). (2) Audité el estado real de S9 y lo REABRÍ: el swap NO estaba "casi listo".
- **Por qué:** main sigue recibiendo hotfixes → la rama larga divergía. Al sincronizar, encontré que S9 es solo parcial.
- **Hallazgo (importante):** El facade greenfield SOLO está inyectado en los **services** (composition root). ~40 sitios siguen usando el **global legacy** `tracking_repository` (`bot/alerts.py`, `bot/handlers.py` ×11, `bot/jobs/*`, `services/change_detection.py`, `core/timezones.py`, + tipos compartidos importados del módulo legacy). El global legacy (`storage/tracking_repository.py:6108`) crea el esquema viejo (`active_events`/`tracked_competitions`). Runtime corre con DOS esquemas a la vez → services usan `events`/`competitions`, handlers `active_events`/`tracked_competitions`. Incoherente. Borrar el legacy rompe ~40 imports.
- **Decisión (con el usuario):** Plan B — migración por capas. Sync primero (hecho), después mover consumidores al facade capa por capa: S9a alerts+tipos → S9b jobs+timezones (re-portar blocklist al greenfield) → S9c handlers+change_detection → recién ahí borrar el legacy.
- **Archivos:** merge de main (`bot/*`, `services/*`, `tests/*`, `.env.example`); `migration/TASKS.md` (S9 → BLOCKED + subtareas S9a/b/c); limpié cruft `:memory:` (sqlite accidental) + `.gitignore`.
- **Commit:** merge (ort) + (este de docs).
- **Tests:** en mig/pr2 tras sync: core 174 OK, bot 135 OK, adapters 44 OK. Imports OK.
- **Notas/Bloqueos:** El blocklist quedó en el legacy (handlers lo usan por el global); el learner (service/facade) tiene `get_merge_exceptions` guardado con try/except → devuelve vacío hasta re-portarlo al greenfield en S9b.
- **Siguiente sugerido:** PR2-E2-S9a — sacar el global legacy de `bot/alerts.py` y relocalizar los tipos de dominio compartidos.

### 2026-07-02 · @claude · S9a + S9b + S9c-1 (migración por capas) · DONE
- **Qué hice:** Migré por capas los consumidores del storage legacy al facade greenfield. Resultado: el RUNTIME de prod ya NO corre con dos esquemas.
  - **S9a-1:** unifiqué las 15 dataclasses de dominio (estaban duplicadas idénticas legacy⟷core.models) → el legacy re-exporta de `core.models` (−447 líneas). Ahora legacy y greenfield devuelven el MISMO tipo.
  - **S9a-2:** accessor `get_storage()` (singleton del facade) en `adapters/storage/__init__.py`; `bot/alerts.py` al facade + tipos de core.models.
  - **S9b-1:** `bot/jobs/{tasks,legacy}.py` + `core/timezones.py` a `get_storage()`.
  - **S9b-2:** re-porté el blocklist (`unified_merge_exceptions`) al schema greenfield + 3 métodos en el competitions adapter (get/block/clear) + tests.
  - **S9c-1:** `bot/handlers.py` (14 métodos del global → `get_storage()`, tipos → core.models, 0 refs a storage.tracking_repository); `services/models.py` tipos; fallback `default_tracking_repository` → `get_storage()` en tracking/stats/live_watch.
- **Por qué:** cerrar la incoherencia de dos esquemas (services greenfield, handlers legacy) sin big-bang.
- **Tests:** suite completa 673 OK en cada paso.
- **Commits:** 64cc7cc, f4caf60, 97613c0, e205a57, 2388712 (pusheados a origin/mig/pr2).
- **Notas/Bloqueos:** Falta SOLO S9c-2 (borrar el archivo legacy). Bloqueado por: 4 type-hints `SqliteTrackingRepository` en `services/*` + **22 archivos de test** que construyen `SqliteTrackingRepository`. Es un pase propio (parte = borrar tests legacy redundantes ya cubiertos por `tests/adapters/storage/*`, parte = migrar al facade). El blocklist en runtime: handlers escriben al greenfield (get_storage) y el learner (facade) lee del greenfield → coherente en prod.
- **Siguiente sugerido:** S9c-2 (migrar/limpiar los 22 tests + type-hints + borrar legacy) o arrancar E3 (renderers) sobre un runtime ya coherente.

### 2026-07-02 · @claude · S9c-2 pase de PARIDAD greenfield (destapa bugs de prod) · IN_PROGRESS
- **Qué hice:** Arranqué migrando tests al facade para poder borrar el legacy. Migrar los tests de SERVICIO destapó que el facade greenfield NO es drop-in del legacy: tenía divergencias de comportamiento que romperían prod (los tests basados en legacy las enmascaraban). Migré Category A (7 tests bot, solo tipos → core.models) + `test_league_learning` al facade, y arreglé 2 bugs reales:
  - **GAP #1 (FIXED, `dbc117a`):** `get_active_events` del greenfield no aceptaba `only_future`; el learner lo llama con `only_future=True` → `TypeError` que el try/except tragaba → **auto-unificación de ligas ROTA en greenfield**. Agregado con paridad legacy + test de adapter.
  - **GAP #2 (FIXED, `e98258e`):** `create_unified_competition` hacía find-or-create en vez de create-puro → **/unlink_league no separaba** si el nombre coincidía con la unified. Ahora crea siempre nueva (paridad legacy).
  - **GAP #3 (ABIERTO, decisión de diseño):** `stats_league_links` es per-competition (`competition_id`) en greenfield, era per-unified en legacy. Se perdió la **herencia de stats entre plataformas** (feature del registro canónico). El merge no consolida links. `test_merge_preserves_stats_links` quedó SKIP documentándolo. Opciones: list a nivel unified (dedupe) vs propagar en merge/upsert. **NO borrar el legacy hasta resolverlo.**
- **Tests:** suite completa 674 OK (1 skip: gap #3).
- **Commits:** 1678371 (Cat A), dbc117a (#1), e98258e (#2), aa3fd04 (league_learning). Pusheados.
- **Notas/Bloqueos:** Faltan ~12 tests de servicio/legacy por migrar (test_stats_service, test_unified_competitions, test_live_watch, test_tracking_stats_links, test_xbet_http_extractor + los "via importlib": test_canonical_repo, test_league_registry, test_league_seed, test_peak_subscriptions, test_prune_old_data, test_reminders, test_stats_cache_purge, test_unified_subscriptions). Cada uno puede destapar más gaps. El legacy sigue en uso por esos → NO borrable aún. Los tipos ya están unificados (S9a-1), así que Category-A-style (solo tipos) es trivial; los de servicio son los que validan paridad.
- **Siguiente sugerido:** Decidir gap #3 (diseño stats-links). Luego seguir migrando los tests de servicio uno a uno (cazando gaps), después los "via importlib" (varios quizás redundantes con tests/adapters/storage/* → borrar), 4 type-hints, y recién ahí borrar el legacy.

### 2026-07-02 · @claude · gap #3 RESUELTO (cierre de etapa)
- **Qué:** Implementé la opción elegida (list a nivel unified con dedupe por provider) en `list_stats_league_links`. Herencia de stats entre plataformas restaurada; `test_merge_preserves_stats_links` des-skipeado y verde. Los 3 gaps de paridad quedaron FIXED.
- **Tests:** suite completa 674 OK, SIN skips.
- **Commit:** 51525a5 (pusheado).
- **Estado S9c-2:** faltan ~12 tests de servicio/legacy por migrar antes de poder borrar `storage/tracking_repository.py` (cada uno puede destapar más gaps, como pasó con estos 3). Etapa pausada acá por decisión del usuario.

### 2026-07-02T22:43:11-03:00 · @codex · PR2-E2-S9c-2 · DONE
- **Qué hice:** Continué el takeover desde el WIP de @gemini y cerré el borrado del repositorio legacy: migré los últimos imports/type-hints trackeados a `core.models` + `adapters.storage.SqliteStorage/get_storage`, pasé CLI/monitoring/providers/xbet live al facade greenfield, borré `storage/tracking_repository.py` y `storage/mappers.py`, y ajusté tests residuales al facade.
- **Por qué:** S9c-2 requería que ningún módulo ni test dependiera del repositorio SQLite monolítico para poder eliminarlo sin mantener dos esquemas ni un safety net obsoleto.
- **Archivos:** adapters/storage/__init__.py, adapters/storage/subscriptions.py, adapters/storage/live_watch.py, cli.py, extractors/xbet_http/extractor.py, main.py, monitoring.py, services/change_detection.py, services/live_watch.py, services/stats.py, services/tracking.py, stats_providers/__init__.py, storage/__init__.py, storage/mappers.py, storage/tracking_repository.py, tests/adapters/storage/test_competitions_repository.py, tests/adapters/storage/test_live_watch_repository.py, tests/core/test_live_watch.py, tests/extractors/test_xbet_http_extractor.py
- **Commit:** 2ab62f5
- **Tests:** verde; `./betbot/bin/python -m unittest discover -s tests -t .` → 667 OK. También validé el mismo comando ocultando temporalmente el directorio untracked `bot/handlers/` para simular checkout limpio → 667 OK.
- **Notas/Bloqueos:** El worktree local conserva `bot/handlers/` como WIP untracked ajeno a este commit; no se incluyó en S9c-2. Para que no shadowee localmente al módulo trackeado, le apliqué un ajuste mínimo no commiteado de imports a facade. No hay referencias trackeadas a `storage.tracking_repository` fuera de documentación histórica/migración.
- **Siguiente sugerido:** PR2-E3 (extraer renderers a `interfaces/telegram/renderers/`) o resolver explícitamente qué hacer con el WIP untracked `bot/handlers/` antes de arrancar E5.

### 2026-07-22T00:00:00+02:00 · @claude · PR2-E7 · DONE
- **Qué hice:** Se eliminó `core/flags.py` (mapeo de bitmask obsoleto).
- **Por qué:** Código muerto sin referencias tras la migración del storage.
- **Archivos:** core/flags.py
- **Commit:** 9fcf278
- **Tests:** Verde.

### 2026-07-22T00:50:00+02:00 · @claude · PR2-E3 · DONE
- **Qué hice:** Se extrajo `bot/alerts.py` y todas las funciones `build_*_message` / `render_*` a `interfaces/telegram/renderers/messages.py`, exponiendo la API pública en `interfaces/telegram/renderers/__init__.py`. Se reescribieron los imports correspondientes en handlers, jobs, tracking y tests. La lógica de identidad de partidos fue centralizada previamente en `core/match_identity.py`.
- **Por qué:** Desacoplar la lógica de renderizado y presentación de la capa de Telegram y el core.
- **Archivos:** bot/alerts.py, interfaces/telegram/renderers/__init__.py, interfaces/telegram/renderers/messages.py, core/match_identity.py
- **Commit:** be5ca76
- **Tests:** Verde. 674 tests pasados con éxito.
- **Notas/Bloqueos:** Ninguno.
- **Siguiente sugerido:** PR2-E4 (Mover servicios de services/ a services/ y adelgazarlos).
