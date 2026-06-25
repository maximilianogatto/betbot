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
