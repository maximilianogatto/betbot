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
- **Qué hice:** Envolví las llamadas de lectura y escritura a SQLite que ocurren en las rutas calientes del tracking monitor (como upsert de eventos, inicialización de baselines, inserción de alertas, y resoluciones de fluctuaciones) dentro de llamadas `asyncio.to_thread` en `monitors/tracking.py`.
- **Por qué:** Evitar bloquear el bucle de eventos (event loop) principal de `asyncio` durante las consultas/actualizaciones síncronas de SQLite de fondo.
- **Archivos:** monitors/tracking.py
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






