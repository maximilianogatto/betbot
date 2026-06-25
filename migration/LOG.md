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
