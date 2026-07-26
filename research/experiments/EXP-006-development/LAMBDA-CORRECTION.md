# EXP-006.1 — Corrección suave de λ: prometedora, requiere revisión

**Fecha**: 2026-07-23 · `lambda_correction.py` → `.json` + `fig/lambda_correction.png`.
Autorizada por el director (contracción continua, no piso duro). Ajuste solo con
λ OOS de 2025; evaluación descriptiva en 2026 (dev). Ningún dato de la ventana
confirmatoria (≥ 27-jul) fue tocado.

## Modelo

$$\log\lambda' = (1-a)\log\lambda + a\log\tau \ \ (\lambda<\tau); \qquad \log\lambda'=\log\lambda\ \ (\lambda\ge\tau)$$

Ajuste 2025 (minimizando log-loss de **marcador**): **a = 0.202, τ = 2.140**.
Es una contracción suave hacia arriba que actúa sobre todo $\lambda<2.14$ —casi
ocho deciles en 2026—, con fuerza creciente hacia $\lambda$ bajo. No debe
describirse como una intervención localizada únicamente en el decil inferior.

## Resultado vs los seis criterios de promoción del director

| Criterio | Resultado 2026 (dev) | ¿Cumple? |
|---|---|---|
| Reduce log-loss de marcador | Poisson 3.2196 → **3.2038**; Δ=−0.0158, IC semanal [−0.0220,−0.0096] | **Sí** |
| No empeora RPS 1X2 > 0.0005 | Δ = **−0.0009**, IC [−0.0018, +0.0000] — mejora, no empeora | **Sí** |
| Reduce el sesgo Y−λ del decil bajo | 0.205 [0.112,0.291] → **0.030 [−0.064,0.120]** (ahora incluye 0) | **Sí** |
| Mejora P(0) sin déficit en intensidades medias | Cierra el primer decil, pero en el tercero crea déficit de ceros: obs−corregido=+0.0457, IC [+0.0068,+0.0833] | **No** |
| Mismo signo en los tres países | FIN/SWE/NOR tienen Δll negativo, pero FIN cruza cero [−0.0240,+0.0016]; en RPS sólo NOR excluye cero | **Direccional, no robusto 3/3** |
| No requiere parámetros por temporada | a=0.20/τ=2.14 (2025) vs a=0.31/τ=1.80 (2026); los de 2025 **transfieren** a 2026 (eval principal) y la rotación es estable (a≈0.20-0.24) | **Parcial** (ver caveat) |

Supera de forma estable a Poisson y a la **corrección global constante**
($\lambda'=1.055\lambda$). Su media es menor que la de **NB drop-in**, pero el
contraste contra NB no excluye cero: Δ=−0.0052, IC [−0.0127,+0.0028]. La
superioridad sobre NB no queda establecida.

![Corrección de λ y su efecto en P(0)](fig/lambda_correction.png)
*Izq.: la contracción empuja las intensidades hacia arriba y se funde con la
identidad en λ≥τ. Der.: cierra gran parte del déficit en los primeros dos bins,
pero sobrecorrige algunos bins medios. Los IC por bin están en el JSON.*

## Encuadre de evidencia (regla del director)

**Este es un éxito de desarrollo, no evidencia confirmatoria.** El decil bajo se
destacó tras inspeccionar diez bins, sin corrección por multiplicidad, y tanto
2025 como 2026 son conjuntos de desarrollo. La corrección pasa los criterios
globales de log-loss, RPS y sesgo medio bajo, pero falla el criterio estricto de
no crear déficit de ceros intermedio y no demuestra superioridad sobre NB. Es
un candidato prometedor que requiere revisar la parametrización.

**No entra a la ventana confirmatoria en curso** (instrucción explícita del
director: ningún modelo nuevo a EXP-005, que empezó el 27-jul). No corresponde
congelar todavía $a=0.202,\tau=2.140$: $\tau$ extiende la intervención mucho más
allá del residuo que la motivó y el ajuste 2026 se mueve a $(0.311,1.799)$. El
siguiente paso es medir incertidumbre/perfil de parámetros y elegir una forma
más localizada usando sólo 2025. Todo rediseño deberá probarse en otra ventana.

**Caveat de estacionalidad**: los puntos (a, τ) difieren entre temporadas
(a 0.20 vs 0.31). No es descalificante —los parámetros de 2025 funcionan en 2026
y la rotación por países da a≈0.20-0.24 estable— pero la pre-registración debe
fijar los valores de 2025 y tratar cualquier re-ajuste como violación.

## Qué NO se hizo (y por qué)

No se construyó CMP ni hurdle. La corrección elimina el sesgo medio del decil
bajo, pero la sobrecorrección intermedia impide usarla todavía como nuevo
baseline para diagnosticar un residuo de forma.
