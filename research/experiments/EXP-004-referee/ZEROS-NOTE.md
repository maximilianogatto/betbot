# Nota — El defecto distribucional dominante tiene signo contrario al de NB/mezcla

**Fecha**: 2026-07-23 · `zeros_diagnosis.py` → `zeros_diagnosis.json`,
`fig/zeros_deficit_by_lambda.png`. Datos: λ OOS 2025+2026 (dev), sin ventana.

## Pregunta

El director propuso una mezcla abierto/cerrado para la sobredispersión. Antes de
construirla: ¿puede una distribución más sobredispersa arreglar el defecto medido
del 0-0? El 0-0 observado (0.044) está **por debajo** del Poisson (0.053 con ρ=0):
es un *déficit* de ceros, no un exceso.

## Tres resultados

1. **Jensen, confirmado numéricamente**: cualquier mezcla de dos Poisson que
   preserve la media **aumenta** P(0) (e^{−λ} es convexa). A λ=1.3, un spread de
   ±0.4 lleva P(0) de 0.273 a 0.310. Una NB hace lo mismo. **Ambas empujan el
   0-0 en la dirección equivocada** respecto del déficit observado.

2. **El déficit de ceros es estructural y REPLICA — en baja intensidad**
   (`fig/zeros_deficit_by_lambda.png`). Estratificando P(Y=0)−Poisson por decil
   de λ: en el decil más bajo (λ<1) el déficit es −0.08 (2025) y −0.10 (2026),
   **ambos con IC 95% por bloques que excluyen 0**. Es el primer residuo
   condicional que encontramos que se mantiene entre temporadas. En λ alto el
   déficit se desvanece o invierte — por eso el promedio global era no
   significativo en 2026 (−0.008) mientras el condicional a baja λ sí lo es.

3. **ρ agrava el 0-0**: obs 0.044 | DC(ρ) 0.056 | DC(ρ=0) 0.053. ρ=0 mejora pero
   sigue sobreprediciendo. Refuerza la Línea 4 (ρ=0) y muestra que el 0-0 no se
   arregla por la vía de ρ.

## Consecuencia para la Línea 1 (cambia de dirección)

El defecto dominante del Poisson **no es falta de cola** (que NB/mezcla
arreglarían) sino **exceso de ceros predichos en partidos de baja intensidad**:
en los duelos que DC espera cerrados, los equipos marcan más seguido de lo que
una Poisson(λ bajo) admite. Esto es *sub-dispersión en el cero a baja media* —
signo opuesto al de toda la familia sobredispersa.

Candidatos coherentes con la evidencia (para desarrollo futuro, con los criterios
de rechazo del director):
- **Corrección de media a baja intensidad**: un piso/encogimiento de λ hacia
  arriba en contextos defensivos (DC subestima λ cuando la fuerza ofensiva es
  baja). Barato, interpretable.
- **Distribución con menos masa en 0 a media baja**: Conway-Maxwell-Poisson con
  ν>1 (sub-dispersa) o un hurdle en el cero. Más complejo.

Lo que **queda descartado por esta nota**: NB como sustitución (agrava el 0-0,
ya visto) y la mezcla mean-preserving abierto/cerrado (agrava el 0-0 por Jensen).
Una mezcla NO mean-preserving equivale a corregir la media — mejor atacarlo
directamente como corrección de media a baja λ.

**Regla del director satisfecha**: este es un residuo *medido y estable entre
temporadas* (a diferencia de la dispersión per-liga o la pendiente E[r²|λ], que
no replican). Es el único candidato con base empírica para justificar más
complejidad distribucional — y apunta en dirección contraria a la NB.
