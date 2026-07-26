# Pre-registración: rediseño de la corrección de λ (protocolo exclusivamente 2025)

**Estado**: CONGELADO al commitear. Fija el procedimiento y los criterios de
decisión ANTES de correrlo, para evitar la reinterpretación retrospectiva que
invalidó la primera versión (a=0.202, τ=2.140 sobrecorregía y no era localizada).
Motivado por el dictamen del director. Ningún dato ≥ 27-jul-2026 (ventana EXP-005)
se toca; toda la selección usa **solo 2025**.

## Objeto

Decidir si existe una especificación de corrección de media a baja intensidad que
sea (a) identificable, (b) genuinamente localizada, (c) sin sobrecorrección
intermedia, y (d) mejor que Poisson **y** que NB en log-loss de marcador. Si
ninguna lo logra, el candidato se archiva.

## Datos y partición

- Solo λ OOS de 2025 (`lambdas_2025.csv`). 2026 NO se usa ni para mirar.
- **Walk-forward temporal anidado dentro de 2025**: para cada semana w del tramo
  de test 2025 (jul→nov), ajustar con las semanas < w y evaluar en w. Todos los
  contrastes con bootstrap por bloques de semana.

## Especificaciones candidatas (cerradas)

1. `S_full`: (a, τ) ambos libres (la forma original).
2. `S_tau_fixed`: τ fijado por un criterio de train (p.ej. el percentil de λ donde
   el sesgo Y−λ deja de excluir cero), solo a libre. **Localizada por construcción.**
3. `S_poisson`: a=0 (nulo de referencia).
4. `S_negbin`: NB drop-in φ=0.074 (competidor de complejidad comparable).

## Análisis obligatorios (todos con solo 2025)

1. **Identificabilidad**: perfil de log-loss de marcador en el plano (a, τ) —
   la superficie completa, no el óptimo puntual — y bootstrap por semanas de
   (â, τ̂). Reportar la dispersión de (â, τ̂) entre réplicas.
2. **Calibración por regiones predefinidas** (fijadas ahora, no post hoc):
   - baja: λ < 1.0; media: 1.0 ≤ λ < 1.8; alta: λ ≥ 1.8.
   - En cada región: sesgo Y−λ' y residuo P(0) obs−pred, con IC por bloques.
3. **Evaluación conjunta**: log-loss de marcador, RPS 1X2 y residuos de P(0) por
   región, para las 4 especificaciones, en el walk-forward anidado.

## Criterios de decisión (cerrados — se aplican sin reinterpretar)

Una especificación se selecciona para pre-registrar a una ventana futura **solo
si cumple TODOS**:

1. Δlog-loss de marcador vs `S_poisson` < 0 con IC de bloques que **excluye 0**.
2. Δlog-loss de marcador vs `S_negbin` < 0 con IC que **excluye 0** (la falla de
   la v1: no batía a NB).
3. RPS 1X2 no peor que Poisson por más de 0.0005 (IC no cruza +0.0005).
4. **Ningún** residuo de P(0) por región con IC que excluya 0 en la dirección de
   sobrecorrección (obs−pred > 0) — mata la sobrecorrección intermedia de la v1.
5. Sesgo Y−λ' de la región baja con IC que **incluye 0** (corrige el defecto que
   la motivó).
6. Identificabilidad: el bootstrap de (â, τ̂) debe concentrarse (criterio operativo:
   rango intercuartil de â < 0.15 y de τ̂ < 0.5); si (a,τ) no es identificable,
   preferir `S_tau_fixed` o archivar.

Regla de selección: si más de una especificación cumple los 6, elegir la de menor
log-loss de marcador. Si ninguna cumple, **archivar el candidato** (no forzar).

## Salida

`lambda_redesign.json` (superficies, bootstraps, tabla de criterios por
especificación) + figuras (superficie de perfil con contornos, residuos por
región con IC). Una única especificación elegida —o el archivo del candidato—
queda escrita ANTES de mirar cualquier ventana posterior a EXP-005. Cualquier
re-ajuste posterior de (a, τ) es una violación del registro.

## Fuera de alcance

CMP y hurdle siguen en pausa (dependen de que persista un residuo de forma
DESPUÉS de una corrección de media aceptada). No se toca producción ni EXP-005.
