# Protocolo de Coordinación Multi-Agente — Migración BetBot

> **LEÉ ESTO PRIMERO, ANTES DE TOCAR CÓDIGO.**
> Varios modelos de IA (Claude, Gemini, otros) trabajan sobre esta misma migración.
> Estos archivos son la **única fuente de verdad** para saber qué se hizo, qué falta y quién está haciendo qué.

## Los 3 archivos

| Archivo | Rol | Cómo se usa |
| :--- | :--- | :--- |
| `migration/PROTOCOL.md` | Las reglas (este archivo). | Solo lectura. No se edita salvo para mejorar el proceso. |
| `migration/TASKS.md` | El backlog ordenado de tareas con estado. **El "qué sigue".** | Se edita el estado/owner de la tarea en la que trabajás. |
| `migration/LOG.md` | Diario append-only de lo que pasó. **La trazabilidad.** | Se **agrega** una entrada al final por cada acción. Nunca se reescribe lo viejo. |

## El loop que sigue CADA agente (sin excepción)

1. **Leer** `PROTOCOL.md` (este) → `TASKS.md` → últimas entradas de `LOG.md`.
2. **`git pull`** para tener lo último (si trabajás en copia separada).
3. **Elegir** la primera tarea `TODO` de `TASKS.md` cuyas dependencias estén `DONE`. Respetá el orden; no saltees PRs.
4. **Reclamar**: editar esa fila en `TASKS.md` → estado `IN_PROGRESS` + tu nombre (`@claude` / `@gemini`) + fecha. Commitear ese cambio solo (`[TASKS] claim <ID>`). Esto evita que dos modelos hagan lo mismo.
5. **Implementar** SOLO esa tarea. No mezcles cambios de otras tareas.
6. **Tests**: correr `./run_tests.sh -t .` (o el subset relevante). Una tarea no está `DONE` si los tests no están en verde.
7. **Commit** con el ID de la tarea (ver formato abajo).
8. **Registrar**: agregar una entrada en `LOG.md` (template abajo).
9. **Cerrar**: marcar la tarea `DONE` en `TASKS.md`. Commit `[TASKS] done <ID>`.
10. Volver al paso 1 para la siguiente tarea.

## Estados de tarea (en TASKS.md)

- `TODO` — libre, nadie la tomó.
- `IN_PROGRESS @agente (fecha)` — alguien la está haciendo. **No la toques.**
- `BLOCKED` — no se puede avanzar; ver el motivo en `LOG.md`.
- `DONE` — terminada y con tests verdes.
- `FAILED` — se intentó y falló; ver `LOG.md`. Otro agente puede retomarla.

## Reglas de oro

- **Una tarea a la vez.** No abras un frente nuevo si dejaste otro a medias.
- **Nunca toques una tarea `IN_PROGRESS` de otro agente.**
- **Nunca marques `DONE` sin tests verdes.**
- **`LOG.md` es append-only.** Nunca borres ni edites entradas pasadas (ni las tuyas).
- **Commits chicos**, uno por tarea (o sub-paso claro). Pushear apenas terminás cada tarea.
- **Si te bloqueás**: marcá la tarea `BLOCKED`, agregá entrada en `LOG.md` con el motivo exacto (error, decisión pendiente, etc.) y, si podés, seguí con otra tarea independiente; si no, parate y dejá el estado claro.
- **No cambies el diseño** definido en `REPORTE_ARQUITECTURA_BetBot.md` sin registrarlo como decisión en `LOG.md`. Si algo del plan no cierra, marcá `BLOCKED` y explicá; no improvises una arquitectura distinta en silencio.
- **Scope acotado**: tocá solo los archivos que la tarea declara. Si necesitás tocar otro, anotalo en el LOG.

## Formato de commit

```
[<TASK-ID>] <descripción corta en imperativo>

<detalle opcional: qué y por qué>

Co-Authored-By: <Modelo> <harness>
```
Ejemplo: `[PR1-T1] add weekly VACUUM to maintenance job`

## Template de entrada de LOG.md (copiar al final del archivo)

```
### <fecha-hora ISO> · @<agente> · <TASK-ID> · <STATUS>
- **Qué hice:** ...
- **Por qué:** ...
- **Archivos:** path/a/archivo.py, ...
- **Commit:** <hash o "pendiente">
- **Tests:** <verde / rojo / N° de tests / qué falló>
- **Notas/Bloqueos:** ... (o "ninguno")
- **Siguiente sugerido:** <TASK-ID o "—">
```

## Ramas, commits y merges

### Disciplina de ramas
- Cada PR vive en **su** rama: PR1 → `mig/pr1`, PR2 → `mig/pr2`, PR3 → `mig/pr3`. Ver la rama activa en el encabezado de `TASKS.md`.
- **Regla de oro:** trabajá SOLO en la rama de la PR activa. **Nunca** commitees trabajo de PR2 sobre `mig/pr1` (eso enreda el historial — ya pasó). Si una PR está mergeada, su rama queda congelada.
- `mig/prN` se crea **a partir de `main`** recién cuando la PR anterior ya está mergeada a `main`.

### Reglas de commit
- Un commit por tarea (o sub-paso claro). Mensaje: `[<TASK-ID>] <descripción>` (ver formato arriba) con el trailer del modelo que lo hizo.
- **Commiteá solo los archivos de tu tarea.** No incluyas trabajo (ni archivos sin trackear) de otro agente.
- Los cambios de estado en `TASKS.md`/`LOG.md` van en commits aparte: `[TASKS] claim/done <ID>`, `[LOG] record <ID>`.
- Pusheá apenas cerrás una tarea (si trabajás en copia separada).

### Protocolo de MERGE a `main` (todos de acuerdo)
Mergear una PR a `main` es la única acción que **requiere consenso de los agentes**. Pasos obligatorios, en orden:

1. **Pre-condiciones** (todas verdaderas): todas las tareas de la PR en `DONE` · suite verde (`./run_tests.sh -t .`) · smoke hecho si aplica · **ningún agente `IN_PROGRESS`** en esa PR.
2. **Propuesta:** el agente que va a mergear agrega al `LOG.md` una entrada `MERGE-PROPOSAL prN` listando el commit final y que las pre-condiciones se cumplen.
3. **Acuerdo:** cada otro agente activo responde en el `LOG.md` con una línea `MERGE-ACK prN @agente`. Sin el ACK de todos, **no se mergea**. (Si un agente no está activo, lo decide el humano.)
4. **Merge (un solo agente, árbol limpio):**
   ```
   git checkout main && git pull
   git status --short        # DEBE estar limpio; si no, parar
   git merge --no-ff mig/prN
   ./run_tests.sh -t .       # verde
   # push solo cuando el humano lo apruebe
   ```
5. **Nunca** mergear con árbol sucio, ni una rama que tenga commits de otra PR mezclados.
6. **Post-merge:** entrada `MERGE-DONE prN` en `LOG.md` con el hash del merge. Se congela `mig/prN` y se crea `mig/pr(N+1)` desde el nuevo `main`.

> Regla de seguridad: ante cualquier duda sobre el estado de git (ramas enredadas, árbol sucio, cambios de otro agente), **parar y registrar `BLOCKED` en el LOG** — no improvisar git surgery.
