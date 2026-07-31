# Pre-registración v3.1: rediseño de la corrección de λ (protocolo 2025-only)

**Estado**: CONGELADO al commitear. v3 adoptó la **Opción A** (el candidato es el
procedimiento de selección P, no un (a,τ) ni familia fija). v3.1 cierra las 6
precisiones bloqueantes del dictamen: NB con φ de `outer_train` (#1); bins de τ
con extremos/cierre/vacíos (#2); semilla determinista de τ (#3); agregación
regional por etiqueta relativa congelada (#4); bin de cola `Y≥12` (#5); rama
explícita `φ≤0`→Poisson (#6). Solo 2025; nada ≥ 27-jul-2026. **Aprobación
condicional del director recibida sujeta a estas 6 precisiones; ejecutar una
única vez tras su confirmación de que quedaron bien.**

> **Objeto científico (elección explícita, no se combinan)**: se promueve/archiva
> el **procedimiento adaptativo P** definido abajo, y para una ventana futura se
> congela **el algoritmo completo**, no un (a,τ) ni una familia. (Alternativa
> registrable si el director prefiere objeto "familia fija": eliminar la selección
> adaptativa y contrastar solo `S_full` vs `S_tau_fixed` con inferencia
> simultánea preregistrada — Opción B. Este documento implementa A.)

## 0. El candidato: procedimiento P

`P(train) → predicción por partido`. Dado cualquier conjunto de entrenamiento, P
corre la **selección interna** (§3) entre `S_full`, `S_tau_fixed` y `S_poisson`
usando **exclusivamente criterios internos**, reajusta la spec elegida en todo
`train` y predice. P es determinista dadas las reglas y semillas de §5. Se
**estima** su desempeño OOS con el bucle externo y, si pasa §4, se congela P
entero para una ventana futura. Si no pasa, **se archiva** (no se re-ajusta nada).

## 1. Datos, unidad, calendario (v2 §1, con cierres)

- **λ de todo 2025** regenerados por walk-forward del DC (`halflife_days=120,
  ridge_sigma=0.75, fit_rho=True`; fallback base-rate si `fit_poisson`→None).
  No se reusa el `lambdas_2025.csv` truncado.
- **Unidad = el partido**; λ_h y λ_a en el mismo bloque. Todo bootstrap resamplea
  **semanas ISO completas** con frecuencia **`W-SUN`** (lunes–domingo inequívoco);
  nunca lados/partidos como independientes.
- **Calendario** (UTC): warmup train-only `fecha < 2025-06-01`; test externo
  `2025-06-01 ≤ fecha < 2025-12-01`; semanas incompletas se **incluyen tal cual**
  (bloques más chicos, sin relleno).

## 2. Especificaciones (cerradas)

Todas con **ρ=0**; matriz de marcadores con el bin de cola `Y≥12` de §5.

1. **`S_poisson`**: λ'=λ.
2. **`S_full`**: `log λ' = (1−a)log λ + a log τ` si λ<τ, `log λ` si λ≥τ; (a,τ)
   por MLE de log-loss de marcador. Multi-start **`a0=0.5`** fijo × `τ0∈{0.9,1.2,1.5}`;
   Nelder-Mead (`xatol=1e-3,fatol=1e-5,maxiter=200`, bounds `a∈[0,1],τ∈[0.4,2.5]`);
   se toma el de menor objetivo; empate → menor a, luego menor τ; fallo de
   convergencia en todos los starts → spec no disponible en ese fold.
3. **`S_tau_fixed`**: τ por **regla de train** (abajo); a por
   `scipy.optimize.minimize_scalar(method="bounded", bounds=(0,1))` (1-D
   determinista, sin punto inicial).
   - **Regla de τ (bins disjuntos, cerrados)** (issue #2): bordes = deciles de λ
     del `inner_train` **con `q0=min(λ)` y `q100=max(λ)`**; se **eliminan bordes
     duplicados**; bins `[q_k, q_{k+1})` salvo el último **cerrado a derecha**
     `[q_{k}, q_{100}]`; **bins vacíos se omiten**. En cada bin, sesgo
     `mean(Y−λ)` con IC bloque-semana bajo semilla `seed_τ(fit)` (§5, issue #3).
     τ = **borde izquierdo del primer bin (menor→mayor λ) cuyo IC de sesgo
     incluye 0**. Si **todos** incluyen 0 → τ=q0 (corrección nula: λ<q0 vacío).
     Si **ninguno** incluye 0 y todos los sesgos son > 0 → τ=q100. Caso
     degenerado (ninguno incluye 0, signos mezclados) → τ=mediana(λ),
     `tau_fallback=True`.
4. **`S_negbin`** (solo comparador externo, **no** entra a la selección interna):
   `Var=λ+φλ²`. **Para cada outer fold, una única φ estimada con TODO
   `outer_train`** (no inner-train; issue #1), por momentos
   `φ̂ = Σ((y−λ)²−λ)λ² / Σλ⁴`, y se predice w_o. **Rama explícita** (issue #6):
   si `φ̂ ≤ 0` → se usa **exactamente la PMF de Poisson** (no se evalúa `nbinom`
   con φ=0, que es indefinido). Si `φ̂ > 0`: `r=1/φ̂`, PMF
   `scipy.stats.nbinom(n=r, p=r/(r+λ))` con el bin de cola de §5.

## 3. Selección interna e inner_eligible (resuelve #2, #4)

`inner_eligible` se define **solo con folds internos** (independiente del externo).

- **Calendario interno** (dado un `outer_train`): semanas de `outer_train` con
  `inner_train` acumulado ≥ **150 partidos**, desde la primera tal semana hasta la
  última de `outer_train`. Se exigen ≥ **4 semanas internas** acumuladas para
  declarar elegible cualquier spec ≠ Poisson; si `outer_train` no las provee
  (outer folds tempranos), **P devuelve `S_poisson`** (default seguro).
- Para cada semana interna w_i: `inner_train` = semanas de `outer_train` < w_i;
  se ajustan `S_full`, `S_tau_fixed`, `S_poisson` en `inner_train`, se predice w_i,
  se acumulan **por spec**: log-loss de marcador, residuo `P0_obs−P0_pred` por
  región y sesgo `Y−λ'` de la región baja (regiones = **tertiles de λ del
  inner_train**, §4).
- **`inner_eligible(spec)`** para spec ∈ {`S_full`,`S_tau_fixed`} (punto-estimado
  sobre folds internos — sin IC, que en interno sería ruidoso):
  (a) log-loss interno < log-loss interno de `S_poisson`;
  (b) ningún residuo `P0` de región con **punto** > `ε0` en dirección
  sobrecorrección; (c) sesgo interno de región baja con `|punto| ≤ ε_λ`.
- **Selección**: entre las specs ≠ Poisson que son `inner_eligible`, la de menor
  log-loss interno; empate → `S_tau_fixed` (más parsimoniosa/localizada). Si
  ninguna es elegible → `S_poisson`.

## 4. Bucle externo y promotion_pass (resuelve #1, #3, #5)

- **Externo**: expanding-window sobre el test externo (§1), `outer_train` ≥ 300
  partidos para evaluar la semana. Para cada semana externa w_o: `outer_train` =
  semanas < w_o; P(`outer_train`) elige UNA spec y predice w_o. Se guarda **la
  predicción de P** por partido (más, **solo para descripción**, la de cada
  familia y la de `S_negbin` — etiquetadas no-inferenciales, no participan de
  ninguna selección).
- **`promotion_pass(P)`** se aplica **una sola vez** a las predicciones externas
  OOS de P. El bootstrap externo **remuestrea las predicciones OOS ya producidas**
  por bloque-semana (`n_boot=4000`, percentil [2.5,97.5]); **no** re-ejecuta el
  pipeline anidado (eso mediría otra incertidumbre). P se promueve **sólo si**:
  1. Δlog-loss marcador P vs `S_poisson` < 0, IC **excluye 0**.
  2. Δlog-loss marcador P vs `S_negbin` < 0, IC **excluye 0** (el comparador NB
     se predice en cada outer fold con su φ de `outer_train`; es comparador, no se
     elige).
  3. RPS 1X2 P vs Poisson: IC del Δ **enteramente < +0.0005**.
  4. **Equivalencia P(0)**: en las 3 regiones, IC completo de `P0_obs−P0_pred`
     dentro de `[−ε0,+ε0]`.
  5. **Equivalencia sesgo** región baja: IC completo de `mean(Y−λ')` dentro de
     `[−ε_λ,+ε_λ]`.
  6. **Estabilidad de selección**: la familia modal elegida por P aparece en
     ≥ **60%** de los outer folds (fracción preregistrada). Si <60%, P no se
     promueve (selector inestable).
- **No hay desempate externo entre familias**: el externo sólo emite un veredicto
  sí/no sobre P vs {Poisson, NB}. La pregunta "qué familia" se responde de forma
  **descriptiva** (frecuencia de selección), nunca por ranking de log-loss externo.
- **Agregación regional entre folds** (issue #4; cada fold tiene tertiles
  distintos): cada observación de test se etiqueta baja/media/alta con los
  **tertiles calculados en su propio `train`**, y la etiqueta queda **congelada**
  junto con su predicción. El residuo externo de una región agrupa todas las
  predicciones OOS con esa **etiqueta relativa** — "baja" = tercio bajo respecto
  del contexto histórico de cada fold, **no** un intervalo fijo de λ. El bootstrap
  remuestrea semanas preservando (etiqueta, predicción, observado).

## 5. Detalles congelados (resuelve #7 y adicionales)

- **Grilla de goles por lado `{0,…,12}` con bin de cola** (issue #5): `p_k=pmf(k,λ)`
  para k=0..11 y **`p_12 = 1 − cdf(11,λ)`** (masa `Y≥12`). Suma 1 exacta, **sin
  renormalizar**. El observado `g` se mapea a `min(g,12)`. Ídem NB con su cola.
- log-loss marcador `−log(clip(P(g_h,g_a),1e-12,1))`; RPS `½Σ_{H<D<A}(cumP−cumY)²`.
- Bootstrap: no-paramétrico por bloque-semana `W-SUN`, `n_boot=4000`, percentil.
  Semillas: score `47`, RPS `7`, región/P0/sesgo `41/43`, selección-estabilidad `71`.
- **Semilla de la regla de τ** (issue #3): cada fit de `S_tau_fixed` usa
  `seed_τ(fit) = 41000 + ordinal`, con `ordinal` **determinista** por posición del
  fit: `ordinal = 1000·outer_ix + inner_ix` (refit sobre `outer_train`: `inner_ix=999`;
  fit final sobre todo-2025: `outer_ix=999, inner_ix=999`). Evita reutilizar la
  misma secuencia pseudoaleatoria entre folds de tamaño compatible.
- Optimizador: como en §2 (S_full multi-start a0=0.5; S_tau_fixed 1-D bounded).
- **Márgenes con interpretación registrada** (issue #3/adic.):
  - `ε0 = 0.02` en P(0): dos puntos porcentuales, ~1/4 del déficit de baja
    intensidad que se corrige (~0.08–0.10) y del orden del piso de ruido del IC
    semanal de un decil — por debajo de eso no es distinguible de ruido ni
    materialmente relevante para 1X2/goles.
  - `ε_λ = 0.05` goles: ~3% de un λ típico (~1.5) y ~1/4 del sesgo de región
    baja que se corrige (~0.20) — tolerancia de sesgo sin impacto práctico.
  - Regiones = **tertiles de λ del train** (no cortes fijos 1.0/1.8, que fueron
    informados por deciles de 2026); se reportan los bordes por fold.

## 6. Salidas

`lambda_redesign.json`: predicciones OOS de P y (descriptivo) de cada familia +
NB; los 6 IC de `promotion_pass`; frecuencia de selección por familia; bordes de
región por fold; diagnósticos descriptivos de identificabilidad de (a,τ) de
`S_full` en el fit sobre todo-2025 (ya **no** es gate — el gate es la estabilidad
de selección §4.6). Figuras: perfil (a,τ) con contornos; residuos de P(0) por
región con IC y bandas ±ε0. Entorno: `research/requirements.txt` (repro local,
no lockfile — ver LAMBDA-CORRECTION.md).

## 6bis. Caveat científico registrado (no bloqueante)

Al ser P un **selector predictivo**, la identificabilidad de (a,τ) dejó
correctamente de ser gate. Eso cambia la pregunta científica: este experimento
responde **si un algoritmo adaptativo mejora predicciones de forma estable**, NO
**si existe un mecanismo paramétrico identificable**. Utilidad predictiva ≠
identificación mecanística. Si el experimento se incorpora al paper, se declara
explícitamente así (los diagnósticos de identificabilidad de (a,τ) quedan como
descriptivos, no como evidencia de mecanismo).

## 7. Fuera de alcance

CMP y hurdle en pausa. No se toca producción ni EXP-005. **No se ejecuta hasta
aprobación de la v3; si el director prefiere el objeto "familia fija", se
reescribe como Opción B antes de correr.**
