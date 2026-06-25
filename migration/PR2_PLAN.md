# PR2 — Desglose detallado (archivo estable)

> Re-home del desglose de PR2 que se sobrescribió en TASKS.md por edición concurrente.
> Lo volátil/planificado vive acá (no en TASKS.md, que es el tablero de estado). Detalle de ports en `PORTS_SPEC.md`.
> **PR2 NO arranca a codear hasta que PR1 esté DONE y mergeada.**

## ⚠️ Decisión de PR2 (confirmar)
NO partir mecánicamente el `tracking_repository.py` legacy (6063 líneas) para luego rehacer su esquema en greenfield — sería trabajo tirado. En cambio: **escribir los adapters de `adapters/storage/*` de cero contra el esquema limpio** (§9.A del reporte), **portando** la lógica de query que valga, y **borrar** el repo viejo al final. Esto fusiona el viejo PR3-E4 (greenfield) dentro de PR2-F3.

## Fundaciones (en serie — bloquean el resto)
| ID | Tarea | Archivos | Deps |
| :--- | :--- | :--- | :--- |
| PR2-F1 | Esqueleto de carpetas + `__init__.py`: `core/ports/`, `services/`, `adapters/storage/`, `interfaces/telegram/{handlers,renderers}`, `interfaces/cli/`, `runtime/`. | (carpetas) | PR1 mergeada |
| PR2-F2 | Traducir `PORTS_SPEC.md` a `core/ports/*.py` (ABC/Protocol por agregado + externos). | `core/ports/*` | F1 |
| PR2-F3 | `adapters/storage/connection.py` + `schema.py` (esquema limpio greenfield). | `adapters/storage/connection.py`, `schema.py` | F1 |

## Adapters de storage por agregado (PARALELIZABLE — 1 archivo por agente, tras F2+F3)
| ID | Adapter | Archivo | Métodos aprox. | Port |
| :--- | :--- | :--- | :--- | :--- |
| PR2-S1 | Competitions/tracking/unified/pending/discovery | `adapters/storage/competitions.py` | ~43 | CompetitionsPort |
| PR2-S2 | Events + odds (estado actual) | `adapters/storage/events.py` | ~20 | EventsPort |
| PR2-S3 | Subscriptions (cuotas + stats-only + peak) | `adapters/storage/subscriptions.py` | ~9 | SubscriptionsPort |
| PR2-S4 | Baselines + small_changes + sent_alerts | `adapters/storage/baselines.py` | ~7 | BaselinesPort |
| PR2-S5 | Stats links (league + match) | `adapters/storage/stats_links.py` | ~5 | StatsLinksPort |
| PR2-S6 | Live watch | `adapters/storage/live_watch.py` | ~13 | LiveWatchPort |
| PR2-S7 | Cache + maintenance (cap, prune, vacuum) | `adapters/storage/maintenance.py` | ~5 | MaintenancePort |
| PR2-S8 | **Facade**: compone los repos, implementa los ports, swap de imports en services, **borra** `storage/tracking_repository.py`. | `adapters/storage/__init__.py` | — | (todos) |

## Capas no-storage (PARALELIZABLE con los S*, dependen de ports/DTOs)
| ID | Tarea | Archivos | Deps |
| :--- | :--- | :--- | :--- |
| PR2-R1 | Renderers: `bot/alerts.py` + `build_*_message`/`render_*` → `interfaces/telegram/renderers/`. Servicios devuelven DTOs. | `interfaces/telegram/renderers/*` | F2 |
| PR2-V1 | Mover servicios `monitors/` → `services/`, adelgazar (sin telegram, sin SQL inline). | `services/*` | F2 |
| PR2-H1 | Handlers finos `interfaces/telegram/handlers/` (mismos comandos). | `interfaces/telegram/handlers/*` | R1, V1 |
| PR2-SCH | `runtime/scheduler.py` neutro (asyncio); borrar `bot/jobs/legacy.py` + scheduler propio. | `runtime/scheduler.py` | V1 |
| PR2-DEL | Borrar muertos: `core/flags.py`, `monitoring.py`(→service), residuos `bot/jobs/*`, revisar `sandbox/`/`temp/`. | varios | S8, SCH |

## Reparto entre 3 agentes (tras F1-F3, en serie por un agente)
Una vez listas las fundaciones, los 3 agentes toman **un archivo cada uno**: ej. @gemini→S1, @claude→S2+S4, @codex→S6, etc., y en paralelo R1/V1. El facade S8 va al final (depende de S1-S7).

**Cierre PR2:** suite verde + bot arranca con la estructura nueva y DB vacía limpia (sin `active_events`, sin `tracking_repository.py`).
