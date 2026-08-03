# Resultados de la corrida única — rediseño de λ (protocolo v3.1, Opción A)

**Fecha**: 2026-08-03 · Ejecutado una sola vez sobre 2025 tras pasar los 14 tests
del instrumento (`VERIFICATION.md`). **No se re-ejecutó con variaciones ni se
modificó regla o parámetro alguno.** Artefactos: `lambda_redesign.json`,
`lambda_redesign_oos_{match,side}.csv`, `lambdas_2025_full.csv`.

## Veredicto: `promotion_pass = False` — el candidato se ARCHIVA

Datos: 2.925 partidos con λ DC-OOS (2025-04-14→11-30); ventana externa de test
2.280 partidos en 27 folds semanales.

**El procedimiento adaptativo P eligió `S_poisson` en los 27 folds** (frecuencia
de selección 27/27), y la selección final sobre todo-2025 también es `S_poisson`.
Es decir: bajo el procedimiento honesto, **ninguna corrección se activó nunca**.

### Las 6 compuertas

| Gate | Resultado | Pasa |
|---|---|---|
| 1 · P vs Poisson (log-loss) | Δ=0 (P≡Poisson) | No (no mejora: no hay corrección) |
| 2 · P vs NB (log-loss) | Δ=+0.0021, IC [−0.0074, +0.0126] | No (P=Poisson no bate a NB) |
| 3 · RPS vs Poisson | Δ=0 | Sí (trivial, P≡Poisson) |
| 4 · Equivalencia P(0) por región | baja −0.066 [−0.100,−0.028] (excluye 0) | No |
| 5 · Sesgo región baja | +0.201 [+0.124, +0.277] | No |
| 6 · Estabilidad de selección | S_poisson 27/27 = 100% | Sí (trivial) |

## Por qué P eligió Poisson (mecanismo, `diagnose_null.py`)

Ambas familias se ajustan y **mejoran el log-loss marginal** (criterio a), pero
**violan las cotas de equivalencia de la región baja**:

| Familia (fit sobre ene–ago 2025) | a | τ | (a) log-loss ↓ | (b) sobrecorrige baja | (c) sesgo baja |
|---|---|---|---|---|---|
| S_full | 0.489 | 1.674 | sí (3.249<3.292) | **sí** (resid P0 +0.118 > 0.02) | **−0.287** ( >0.05 ) |
| S_tau_fixed | 0.607 | 1.458 | sí (3.250<3.292) | **sí** (+0.118) | **−0.311** |

El ajuste que minimiza el log-loss **de marcador promedio** empuja λ hacia arriba
con fuerza (a≈0.5–0.6), y **sobrepasa la región baja**: pasa a predecir muy pocos
ceros ahí (residuo +0.118) y voltea el sesgo de +0.20 (subestimación original) a
−0.29 (sobreestimación). Mejora el promedio a costa de romper la región que la
motivaba → no es `inner_eligible` en ningún fold → P cae a Poisson.

## Interpretación (honesta)

1. **El residuo que motivó todo es REAL y sobrevive**: gate 4 muestra que a baja
   intensidad Poisson predice demasiados ceros (residuo −0.066, IC excluye 0) y
   gate 5 que subestima la media (+0.20). El diagnóstico de EXP-004.9 se replica
   en la corrida limpia.
2. **Pero la familia de corrección propuesta NO puede arreglarlo** dentro de las
   cotas: fijar el sesgo de media a baja λ exige una contracción fuerte que
   sobrecorrige la misma región. No hay (a,τ) que enhebre ambas cosas.
3. **El "6/6" anterior era un artefacto de evaluación laxa**: aquel a=0.20/τ=2.14
   era una elección a mano evaluada sobre 2026 con criterios flojos y sin la cota
   regional de sobrecorrección. Bajo el procedimiento pre-registrado —con márgenes
   de equivalencia por región y sin tuning post-hoc— la corrección no gana su
   lugar. **Exactamente lo que el protocolo estaba diseñado para exponer.**

## Decisión (regla del protocolo)

Por la regla de archivo (§0: "si el procedimiento no selecciona ninguna, el
candidato se archiva; no se re-ajusta"): **la corrección suave de media a baja λ,
en su forma de contracción hacia τ, queda ARCHIVADA.** No se re-ajustan (a,τ) ni
se relajan las cotas.

## Qué queda vivo para el futuro (no ahora, no sin nueva pre-registración)

El residuo de baja intensidad es real. Lo que fracasó es la *forma* de corrección
(contracción monótona de la media), que sobrepasa. Candidatos que podrían enhebrar
la aguja —a pre-registrar de cero, con estas mismas cotas por región—:
- una corrección de media **más suave y acotada por región** (no un único (a,τ)
  global), o
- una distribución con **menos masa en 0 sólo a media baja** (hurdle/CMP ν>1),
  que era la rama que el director dejó condicionada a "si persiste el déficit tras
  corregir la media" — y persiste, pero sin que la corrección de media global
  funcione. Requiere su propio protocolo.

Ninguno se toca hasta cerrar EXP-005. CMP/hurdle siguen en pausa salvo nueva
pre-registración.

## Reproducir

```bash
research/.venv/bin/python research/experiments/EXP-006-development/test_lambda_redesign.py   # 14/14
research/.venv/bin/python research/experiments/EXP-006-development/run_lambda_redesign.py     # corrida única
research/.venv/bin/python research/experiments/EXP-006-development/diagnose_null.py           # mecanismo
```
