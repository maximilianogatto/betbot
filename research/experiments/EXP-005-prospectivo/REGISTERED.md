# Pre-registración: evaluación prospectiva confirmatoria (EXP-005)

**Fecha de registro**: 2026-07-21 · **Estado**: CONGELADO — este documento no se
edita después del commit que lo introduce; cualquier cambio invalida la ventana.

Motivación (revisión del referee, §5 y §13): tras EXP-001..004, el conjunto 2026
hasta el 2026-07-20 adquirió carácter parcialmente exploratorio (selección de
modelos, diagnósticos y explicaciones se construyeron mirándolo). Esta
pre-registración define una ventana nueva y las hipótesis ANTES de observarla.

## Ventana confirmatoria

Partidos de las 17 ligas del dataset **jugados desde el 2026-07-22 (inclusive)
hasta el 2026-11-30**, descargados con los builders existentes sin cambios de
esquema. Ningún análisis sobre esa ventana se corre hasta su cierre; una sola
pasada.

## Pipeline congelado

Modelos y configuración exactamente como en el commit que introduce este
archivo (`research/peak_models/` + `research/experiments/EXP-00{1,2,3,4}`):

- `dc_best`: Poisson Dixon-Coles por liga, half-life 120 días, σ=0.75, ρ ajustado.
- `stack_cal`: recalibración logística entrenada solo con OOS previas.
- `g0_logistic_dppg`, `b0_base_rate`: baselines como están.
- `jer_pais`: jerárquico MAP, τ_liga=0.15, sin cluster, como está.
- Harness: walk-forward semanal de `evaluate.py`, sin modificaciones.

Se permite (y registra) UNA adición antes de abrir la ventana: el modelo
`dc_dyn_gamma` (localía por liga-temporada, hipótesis H4) **si se implementa
antes del 2026-08-01 sin mirar datos de la ventana**; si no llega, H4 se cae.

## Hipótesis pre-registradas

Análisis primario: Δ métrica por partido, pareado, IC 95% por bootstrap de
bloques semana (esquema `week` de EXP-004.1, 4.000 réplicas, semilla 7).

- **H1 (confirmatoria)**: RPS(dc_best) < RPS(g0_logistic_dppg). Éxito: IC de la
  diferencia excluye 0.
- **H2 (confirmatoria)**: log-loss(stack_cal) < log-loss(dc_best) **y**
  RPS(stack_cal) ≤ RPS(dc_best) + 0.0005 (no-inferioridad). Éxito: ambas.
- **H3 (confirmatoria, generada en EXP-003)**: RPS(jer_pais) < RPS(dc_best)
  **restringido a las ligas C1 = {M2, NL}** (asignación congelada en
  `EXP-003-jerarquico/league_clusters.csv`). Éxito: IC excluye 0 en ese segmento.
- **H4 (condicional a implementación)**: RPS(dc_dyn_gamma) < RPS(dc_best),
  global. Motivada por la no-estacionariedad de localía (EXP-003a).
- **H5 (confirmatoria, diagnóstico)**: la varianza de residuos de Pearson del
  DC en la ventana es > 1 (IC bootstrap excluye 1) — replica la sobredispersión
  de EXP-004.2 en datos nuevos.

Todo lo demás que se calcule sobre la ventana se reporta como **exploratorio**.

## Criterios de lectura

- H1 y H2 sostienen el uso de dc_best+stack_cal como predictor de referencia.
- H3 decide si el jerárquico entra en producción para C1.
- H5 decide si se implementa binomial negativa (EXP-006 candidato).
- Si H1 falla, el programa vuelve a G2 (protocolo §gates) — sin excusas post hoc.

## Fuera del alcance de esta ventana

La comparación contra probabilidades implícitas del mercado (referee §4) queda
para cuando la Fase 0 acumule cuotas archivadas; se pre-registrará por separado
(CLV y log-loss vs $q_r = (1/o_r)/\sum_s 1/o_s$ del cierre).
