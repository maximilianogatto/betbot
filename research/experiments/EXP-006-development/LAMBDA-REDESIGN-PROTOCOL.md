# Pre-registración v3: rediseño de la corrección de λ (protocolo 2025-only)

**Estado**: CONGELADO al commitear. Resuelve la contradicción central de la v2
(mezclar "evaluar un procedimiento adaptativo" con "promover una familia fija")
adoptando la **Opción A** del dictamen: *el candidato es el procedimiento de
selección completo*, no un par (a,τ) ni una familia elegida retrospectivamente.
Solo 2025; nada ≥ 27-jul-2026. No se ejecuta hasta que el director apruebe la v3.

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

Todas con **ρ=0**; matriz de marcadores con truncamiento y renormalización de §5.

1. **`S_poisson`**: λ'=λ.
2. **`S_full`**: `log λ' = (1−a)log λ + a log τ` si λ<τ, `log λ` si λ≥τ; (a,τ)
   por MLE de log-loss de marcador. Multi-start **`a0=0.5`** fijo × `τ0∈{0.9,1.2,1.5}`;
   Nelder-Mead (`xatol=1e-3,fatol=1e-5,maxiter=200`, bounds `a∈[0,1],τ∈[0.4,2.5]`);
   se toma el de menor objetivo; empate → menor a, luego menor τ; fallo de
   convergencia en todos los starts → spec no disponible en ese fold.
3. **`S_tau_fixed`**: τ por **regla de train** (abajo); a por
   `scipy.optimize.minimize_scalar(method="bounded", bounds=(0,1))` (1-D
   determinista, sin punto inicial).
   - **Regla de τ (bins disjuntos, sin dilución de cola)**: deciles de λ del
     `inner_train`; en cada **bin disjunto** `[q_k, q_{k+1})` se computa el sesgo
     `mean(Y−λ)` con IC bloque-semana. τ = **borde izquierdo del primer bin
     (de menor a mayor λ) cuyo IC de sesgo incluye 0** (donde el sesgo positivo de
     baja intensidad deja de ser detectable). Si **todos** los bins incluyen 0 →
     τ = q10 (corrección mínima). Si **ningún** bin incluye 0 y todos los sesgos
     son > 0 → τ = q90 (corregir todo el rango bajo). Caso degenerado (ningún bin
     incluye 0, signos mezclados) → τ = mediana de λ, `tau_fallback=True`.
4. **`S_negbin`** (solo comparador externo, **no** entra a la selección interna):
   `Var=λ+φλ²`, φ estimado por momentos **en cada inner-train**
   `φ̂ = Σ((y−λ)²−λ)λ² / Σλ⁴`, con **`φ = max(0, φ̂)`** (si 0 → Poisson en ese fold).
   PMF: `scipy.stats.nbinom(n=1/φ, p=(1/φ)/((1/φ)+λ))`, renormalizada como en §5.

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
     se predice en cada outer fold con su φ de inner-train; es comparador, no se
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

## 5. Detalles congelados (resuelve #7 y adicionales)

- `maxg=12`; PMF por lado renormalizada a suma 1 tras truncar (Poisson y NB).
- log-loss marcador `−log(clip(P(g_h,g_a),1e-12,1))`; RPS `½Σ_{H<D<A}(cumP−cumY)²`.
- Bootstrap: no-paramétrico por bloque-semana `W-SUN`, `n_boot=4000`, percentil.
  Semillas: score `47`, RPS `7`, región/P0/sesgo `41/43`, selección-estabilidad `71`.
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

## 7. Fuera de alcance

CMP y hurdle en pausa. No se toca producción ni EXP-005. **No se ejecuta hasta
aprobación de la v3; si el director prefiere el objeto "familia fija", se
reescribe como Opción B antes de correr.**
