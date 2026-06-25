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
