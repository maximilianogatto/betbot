# Pre-registración v2: rediseño de la corrección de λ (protocolo 2025-only)

**Estado**: CONGELADO al commitear. Cierra las 10 ambigüedades señaladas en la
auditoría del director sobre la v1 (`28bc51e`). Ningún dato ≥ 27-jul-2026
(ventana EXP-005) se toca; toda selección y estimación usa **solo 2025**. Ningún
número se reporta hasta correr el procedimiento completo tal como queda escrito
acá; cualquier desvío es una violación del registro.

## 0. Objeto y regla de archivo

Decidir si existe UNA especificación de corrección de media a baja intensidad que
sea identificable, localizada, sin sobrecorrección, y mejor que Poisson **y** que
NB. Si el procedimiento cerrado abajo no selecciona ninguna, **el candidato se
archiva** (no se re-ajusta).

## 1. Datos, unidad estadística y calendario (issues #5, #6)

- **Fuente de λ**: se regeneran los λ OOS de **todo 2025** por walk-forward
  semanal del DC (config congelada: `halflife_days=120, ridge_sigma=0.75,
  fit_rho=True`; fallback base-rate cuando `fit_poisson` devuelve None por
  `<20` partidos de historia). NO se reusa el `lambdas_2025.csv` truncado a
  jul–nov; se recomputa desde el primer partido 2025.
- **Unidad estadística = el partido**. Cada partido aporta λ_h y λ_a; ambos lados
  viven en el **mismo bloque**. Todo bootstrap resamplea **semanas ISO completas**
  (cada bloque-semana contiene todos sus partidos con sus dos lados). Nunca se
  resamplean lados ni partidos como independientes.
- **Calendario exacto** (UTC, semanas vía `to_period("W")`, lunes-domingo):
  - Warmup train-only: partidos con fecha `< 2025-06-01`.
  - Rango de test externo: semanas ISO con `2025-06-01 ≤ fecha < 2025-12-01`.
  - Tamaño mínimo de train para evaluar una semana externa: ≥ 300 partidos
    acumulados; semanas que no lo alcancen quedan solo-train.
  - Semanas incompletas se inclual-as-is (bloques más chicos, sin relleno).

## 2. Especificaciones candidatas (cerradas) (issues #2, #8)

Todas transforman λ→λ' y construyen la matriz de marcadores con **ρ=0** (Línea 4).

1. **`S_poisson`**: λ'=λ (nulo de referencia).
2. **`S_full`**: `log λ' = (1−a)log λ + a log τ` si λ<τ, `log λ` si λ≥τ; (a,τ)
   ambos libres, ajustados por MLE de log-loss de marcador en el train.
3. **`S_tau_fixed`** (cerrada exactamente): τ se **fija por regla de train**, solo
   a libre.
   - Estadístico: sesgo `mean(Y − λ)` por bin, con IC 95% por bloque-semana.
   - Grilla: los 9 bordes de decil de λ del **inner-train** (q10…q90).
   - Regla de τ: escaneando los bordes de menor a mayor λ, τ = el **primer**
     borde q donde el IC del sesgo en el bin `[borde, +∞)` **incluye 0**
     (el punto donde el sesgo positivo de baja intensidad deja de ser
     detectable). Desempate: el menor λ que cumple. Si **ningún** borde cumple
     (sesgo excluye 0 en todos, o en ninguno): τ = mediana de λ del inner-train
     (fallback fijo) y se marca `tau_fallback=True`.
   - a: MLE de log-loss de marcador en el train, con ese τ fijo.
4. **`S_negbin`**: NB con `Var=λ+φλ²`. **φ se estima DENTRO de cada inner-train**
   por el estimador de momentos `φ = Σ((y−λ)²−λ)λ² / Σ λ⁴` sobre el inner-train.
   **Nunca** un φ global (el 0.074 usaba 2026 → look-ahead, prohibido).

## 3. Nested walk-forward (issues #1, #9)

Selección y estimación separadas para que la multiplicidad de elegir entre formas
no infle los IC.

- **Bucle interno** (selección), corre sobre un `outer_train` dado:
  expanding-window por semanas dentro de `outer_train`. Para cada semana interna
  w_i: `inner_train` = semanas de `outer_train` `< w_i`; se ajusta cada spec en
  `inner_train` (incl. la regla de τ y la estimación de φ, ambas solo con
  `inner_train`) y se puntúa en w_i. Se acumulan por spec los scores internos.
  **Selección interna**: entre las specs que satisfacen los criterios de
  admisibilidad §4 evaluados sobre los folds internos, se elige la de **menor
  log-loss de marcador interno**. Desempate: menor a, luego menor τ. Si ninguna
  spec (salvo Poisson) es admisible, la selección es `S_poisson`.
- **Bucle externo** (estimación de UNA decisión): expanding-window sobre el rango
  de test externo §1. Para cada semana externa w_o: `outer_train` = semanas
  `< w_o`; se corre el bucle interno → devuelve UNA spec seleccionada; se re-ajusta
  esa spec en todo `outer_train` y se predice w_o. Se acumulan los scores de w_o
  **de la spec que el procedimiento eligió en ese paso** (no el mínimo sobre specs).
- El desempeño externo = esos scores acumulados. Mide el **procedimiento**, no la
  mejor forma a posteriori.
- **Selección final única**: correr el bucle interno una vez sobre **todo 2025**
  → la spec (y sus parámetros) que se pre-registraría a una ventana futura, o el
  archivo del candidato si no hay admisible.

## 4. Criterios de admisibilidad y de decisión (issues #3, #10)

Márgenes de equivalencia práctica **fijados ahora** (no "IC incluye 0", que se
cumple por baja potencia):

- P(0) por región: déficit/exceso tolerable `ε0 = 0.02` (en probabilidad).
- Sesgo `Y−λ'` por región: sesgo absoluto tolerable `ε_λ = 0.05` (goles).
- **Regiones por tertiles de λ del train** (issue #4): baja/media/alta = los
  tertiles de λ calculados **dentro de cada train**, no cortes fijos 1.0/1.8
  (que fueron informados por los deciles de 2026). Se reportan los bordes.

Una spec es **admisible** (evaluado sobre los folds externos acumulados de esa
spec) si cumple TODAS:

1. Δlog-loss marcador vs `S_poisson` < 0, IC bloque-semana **excluye 0**.
2. Δlog-loss marcador vs `S_negbin` < 0, IC **excluye 0** (la falla de v1).
3. RPS 1X2 vs Poisson: IC del Δ **enteramente < +0.0005** (no-inferioridad).
4. **Equivalencia P(0)**: en las 3 regiones, el IC completo del residuo
   `P0_obs − P0_pred` dentro de `[−ε0, +ε0]` (mata la sobrecorrección: no basta
   que cruce 0, debe estar acotado).
5. **Equivalencia sesgo**: en la región baja, el IC completo de `mean(Y−λ')`
   dentro de `[−ε_λ, +ε_λ]`.
6. **Identificabilidad** (criterios separados, issue #10):
   - `S_full`: (a) IQR bootstrap-semana de â < 0.15 y de τ̂ < 0.5; **y**
     (b) estabilidad multi-start: los óptimos desde τ0 ∈ {0.9,1.2,1.5}
     coinciden en â dentro de 0.05 y τ̂ dentro de 0.2.
   - `S_tau_fixed`: (a) IQR bootstrap de â < 0.15; **y** (b) estabilidad de la
     regla de τ: en ≥ 80% de las réplicas bootstrap-semana la regla elige un τ
     dentro de ±1 decil del τ del ajuste completo (y `tau_fallback=False` en
     ≥ 80%).

**Decisión**: la spec pre-registrable es la seleccionada por el bucle interno
sobre todo-2025 **si** es admisible por los 6 en el externo. Si más de una fuese
admisible, gana la de menor log-loss externo. Si ninguna: **archivar**.

## 5. Detalles de cálculo congelados (issue #7)

- Truncamiento de goles por lado: `maxg = 12`. PMF de cada lado renormalizada a
  suma 1 tras truncar.
- Log-loss de marcador: `−log(clip(P(g_h,g_a), 1e-12, 1))`, P = producto de las
  dos PMF renormalizadas.
- RPS 1X2 = `½ Σ_{k∈{H,D,A}} (cumP_k − cumY_k)²`, orden H<D<A.
- Bootstrap: no-paramétrico por **bloque-semana**, `n_boot = 4000`, intervalo
  **percentil** [2.5, 97.5]. Semillas fijas: contrastes de score `seed=47`,
  RPS `seed=7`, rotación `seed=53/59`, P(0)/sesgo `seed=41/43`, identificabilidad
  `seed=71`.
- Optimizador: Nelder-Mead multi-start `τ0∈{0.9,1.2,1.5}`, se toma el de menor
  objetivo; `xatol=1e-3, fatol=1e-5, maxiter=200`. Bounds `a∈[0,1], τ∈[0.4,2.5]`.
  Empate de óptimos → menor a, luego menor τ. **Fallo de convergencia** de una
  spec en un fold → esa spec se marca no-admisible en ese fold (no se imputa).

## 6. Salidas y reproducibilidad

`lambda_redesign.json` (scores externos por spec, IC de los 6 criterios,
selección por paso externo y selección final, bordes de región por fold,
bootstraps de identificabilidad) + figuras (superficie de perfil (a,τ) con
contornos e IC; residuos de P(0) por región con IC y las bandas ±ε0). Entorno:
`research/requirements.txt` (ver caveat de lock incompleto en LAMBDA-CORRECTION.md).

## 7. Fuera de alcance

CMP y hurdle en pausa (dependen de que persista un residuo de forma DESPUÉS de una
corrección de media aceptada). No se toca producción ni EXP-005. **No se ejecuta
este protocolo hasta que el director apruebe esta v2.**
