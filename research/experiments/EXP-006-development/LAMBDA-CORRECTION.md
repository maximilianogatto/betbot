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
| Mismo signo en los tres países (criterio pre-registrado) | FIN/SWE/NOR: Δlog-loss todos <0 → **el criterio literal se cumple 3/3**. El criterio más fuerte (efecto individualmente establecido) NO: log-loss excluye cero en **2/3** (SWE, NOR; FIN [−0.024,+0.0016] cruza), RPS en **1/3** (solo NOR) | **Consistencia direccional 3/3; evidencia individual 2/3 (LL) y 1/3 (RPS)** |
| No requiere parámetros por temporada | a=0.20/τ=2.14 (2025) vs a=0.31/τ=1.80 (2026); los de 2025 **transfieren** a 2026 (eval principal) y la rotación es estable (a≈0.20-0.24) | **Parcial** (ver caveat) |

Supera de forma estable a Poisson y a la **corrección global constante**
($\lambda'=1.055\lambda$). Su media es menor que la de **NB drop-in**, pero el
contraste contra NB no excluye cero: Δ=−0.0052, IC [−0.0127,+0.0028]. La
superioridad sobre NB no queda establecida.

![Corrección de λ y su efecto en P(0)](fig/lambda_correction.png)
*Izq.: la contracción empuja las intensidades hacia arriba y se funde con la
identidad en λ≥τ. Centro: P(0) puntual por decil (observado/Poisson/corregido).
Der. (panel de residuos con IC 95% semanal, agregado tras la revisión): obs−Poisson
(rojo) es negativo y excluye cero en los deciles bajos —el déficit original de
ceros— mientras que obs−corregido (verde) lo cierra ahí pero cruza a **positivo
en los deciles 3 y 7** (λ≈1.14 y 1.7), con IC que excluyen cero: la corrección
sobre-eleva λ y pasa a predecir muy pocos ceros a intensidad media. Es la
sobrecorrección que el panel central puntual escondía.*

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

## Reproducibilidad (entorno fijado)

Dependencias/versiones en `research/requirements.txt` (Python 3.13). Verificado:
un venv limpio creado desde ese archivo reproduce los números de este informe
bit a bit (a=0.202, τ=2.140; vs-Poisson −0.0158 [−0.022,−0.0096]; vs-NB −0.0052
[−0.0127,+0.0028]).

```bash
uv venv research/.venv --python 3.13
uv pip install -p research/.venv/bin/python -r research/requirements.txt
research/.venv/bin/python research/experiments/EXP-006-development/lambda_correction.py
```

(Depende de `research/experiments/EXP-004-referee/lambdas_{2025,2026}.csv`; si
faltan, regenerarlos con `poisson_diagnostics.py` y `overdispersion_structure.py`
del mismo directorio, en ese orden.)
