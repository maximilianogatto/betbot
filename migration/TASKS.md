# Backlog de Migración — BetBot

> Fuente de verdad del "qué sigue". Editá el **estado/owner** de la tarea en la que trabajás (ver `PROTOCOL.md`).
> Diseño de referencia: `REPORTE_ARQUITECTURA_BetBot.md`.

**PR activa:** PR2 · **Rama activa:** `mig/pr2` · **Última actualización:** 2026-06-26 · por @codex

**Leyenda de estado:** `TODO` · `IN_PROGRESS @agente (fecha)` · `BLOCKED` · `DONE` · `FAILED`

---

## PR 1 — Estabilización operativa urgente
*Objetivo: máximo valor / mínimo riesgo. Cero cambios de arquitectura. Se hace sobre el código actual.*

| ID | Tarea | Archivos principales | Criterio de aceptación | Deps | Estado |
| :--- | :--- | :--- | :--- | :--- | :--- |
| PR1-T1 | VACUUM semanal en el job de mantenimiento (domingo). | `storage/tracking_repository.py`, `bot/jobs/*` | Existe `run_db_vacuum()`; el job lo corre 1×/semana; el archivo `.sqlite3` se achica tras correrlo (verificable con `dbstat`/tamaño). | — | DONE |
| PR1-T2 | Tope FIFO de 200 filas en `stats_payload_cache` (además del TTL). | `storage/tracking_repository.py` | Tras insertar, si hay >200 filas se borran las más viejas. Test que lo verifica. | — | DONE |
| PR1-T3 | Reinicio graceful de Chromium por RAM. | `bot/jobs/*` (resource monitor), `core/browser_handler.py`, `bot/config.py` | Cuando la RAM de Chromium supera el umbral, se llama `request_restart()` (espera `active_pages==0`, no kill). `ENABLE_MONITORING=true` por defecto. | — | DONE |
| PR1-T4 | Envolver lecturas/escrituras SQLite pesadas en `asyncio.to_thread`. | `storage/tracking_repository.py` (llamadas en `monitors/tracking.py`, `change_detection.py`) | Las rutas calientes (upsert de eventos, baselines, blobs) no bloquean el event loop. Tests verdes. | — | DONE |
| PR1-T5 | Índices en FKs que disparan CASCADE. | `storage/tracking_repository.py` (`_initialize_schema`) | `CREATE INDEX` en `user_event_baselines(active_event_id)`, `small_changes(active_event_id)`, `sent_alerts(active_event_id)`, `stats_match_links(active_event_id)`. | — | DONE |
| PR1-T6 | Prune de `sent_alerts` (>30 días) y `small_changes` no confirmados (>7 días). | `storage/tracking_repository.py`, job mantenimiento | Job diario borra registros viejos. Test. | PR1-T1 | DONE |

**Cierre PR1:** suite completa verde (`./run_tests.sh -t .`) + medición de tamaño DB antes/después documentada en `LOG.md`.

---

## PR 2 — Desacople estructural (estructura objetivo, §4 del reporte)
*Epic. Romper en sub-tareas cuando se arranque. Se trabaja hacia la estructura `core/ports`, `services/`, `adapters/`, `interfaces/telegram/`, `runtime/`.*

| ID | Tarea (alto nivel) | Estado |
| :--- | :--- | :--- |
| PR2-E1 | Crear esqueleto de carpetas objetivo + `core/ports/` (interfaces). | DONE |
| PR2-F3 | Crear `adapters/storage/connection.py` + `schema.py` con esquema SQLite greenfield limpio. | IN_PROGRESS @codex (2026-06-26) |
| PR2-E2 | Partir `storage/tracking_repository.py` (6063 líneas) en `adapters/storage/*` por agregado. | BLOCKED |
| PR2-E3 | Extraer renderers (`bot/alerts.py` + `build_*_message`/`render_*`) a `interfaces/telegram/renderers/`. Servicios devuelven DTOs. | TODO |
| PR2-E4 | Mover servicios de `monitors/` a `services/` y adelgazarlos (sin telegram, sin SQL inline). | TODO |
| PR2-E5 | Handlers finos en `interfaces/telegram/handlers/` (mismos comandos). | TODO |
| PR2-E6 | `runtime/scheduler.py` neutro (asyncio) que dispara métodos de services; borrar `bot/jobs/legacy.py` y scheduler propio. | TODO |
| PR2-E7 | Borrar archivos muertos (`core/flags.py`, etc. — ver §4.4 del reporte). | TODO |

---

## PR 3 — EventBus + CLI (alertas reactivas, core sin Telegram)
*Epic. Romper en sub-tareas al arrancar.*

| ID | Tarea (alto nivel) | Estado |
| :--- | :--- | :--- |
| PR3-E1 | Fix bug `timestamp` en `core/events.py` (`field(default_factory=...)`) + `gather` en `EventBus.publish`. | TODO |
| PR3-E2 | `TelegramEventListener` (sink) suscrito al bus; servicios publican en vez de llamar a `bot.send_message`. | TODO |
| PR3-E3 | `CliEventListener` + transporte CLI mínimo en `interfaces/cli/`. | TODO |
| PR3-E4 | DB greenfield: `adapters/storage/schema.py` crea esquema limpio current-state; arranque con DB vacía. | TODO |

---

## Notas de coordinación
- No empezar PR2 hasta que PR1 esté `DONE` y mergeada.
- PR2-E2 no se implementa como split mecánico del repositorio legacy. Cuando PR2 esté habilitada, seguir `migration/PR2_PLAN.md` y `migration/PORTS_SPEC.md`: F1 (esqueleto) → F2 (ports) → F3 (schema greenfield) → adapters nuevos contra el esquema limpio.
- Si una tarea queda `BLOCKED`, dejar el motivo en `LOG.md` y, si se puede, tomar otra tarea independiente del mismo PR.
- **Colisión de archivos en PR1:** las tareas PR1-T1, T2, T4, T5, T6 tocan todas `storage/tracking_repository.py`. **Solo un agente a la vez** debe estar `IN_PROGRESS` sobre ese archivo. El otro agente puede tomar en paralelo **PR1-T3** (toca `browser_handler.py` / `config.py` / jobs, archivos distintos). El resto se hace en serie.
