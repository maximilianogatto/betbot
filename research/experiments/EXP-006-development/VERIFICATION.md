# Verificación del instrumento vs cada cláusula del protocolo v3.1

Paso 3 del orden autorizado. Mapea cada cláusula de `LAMBDA-REDESIGN-PROTOCOL.md`
a su implementación en `lambda_redesign.py` y al test que la blinda en
`test_lambda_redesign.py`. Los tests usan **datos sintéticos / fixtures mínimos**
(no son una corrida del experimento). 14/14 pasan (~2 min).

| Cláusula del protocolo | Implementación | Test que la guarda |
|---|---|---|
| Candidato = procedimiento P (Opción A) | `select_family` → `run_outer` (guarda predicción de P por partido) | `outer loop: una predicción de P por partido` |
| Unidad = partido; bloque conserva ambos lados | `to_sides`, bootstrap por `week` | `bloque-semana conserva ambos lados` |
| Semanas `W-SUN` | `week_label` = `to_period("W-SUN")` | `week_label usa W-SUN` |
| Sin leakage temporal | `run_outer`/`select_family` sólo usan `week < w` | `sin leakage temporal` |
| §2.2 `S_full`: multi-start a0=0.5×τ0∈{.9,1.2,1.5}, NM | `fit_s_full`, `A0`, `TAU0_GRID` | `constantes congeladas` |
| §2.3 τ: bins disjuntos, q0=min/q100=max, dedup, último cerrado, vacíos omitidos | `_tau_bins` | `bins repetidos/colapsados` |
| §2.3 τ: rama q0 (todos incluyen 0) | `_tau_decide` | `τ decisión: todos incluyen 0 -> q0` + `τ: bias≈0 -> q0` |
| §2.3 τ: rama q100 (ninguno incluye 0, todos +) | `_tau_decide` | `τ decisión: q100` + `τ: bias>0 -> q100` |
| §2.3 τ: fallback (mixto) = mediana | `_tau_decide` | `τ decisión: fallback` |
| §2.3 seed_τ determinista 41000+1000·outer+inner | `seed_tau` | `constantes congeladas` |
| §2.4 NB: φ de outer_train; rama φ≤0→Poisson | `estimate_phi` (max(0,·)), `_side_logpmf_nb` | `φ̂≤0 -> estimate_phi=0 y NB==Poisson` |
| §3 inner: min inner_train 150, ≥4 semanas o Poisson | `select_family` (`MIN_INNER_TRAIN`,`MIN_INNER_WEEKS`) | `constantes congeladas` (+ integración en outer test) |
| §3 inner_eligible (solo folds internos, punto-estimado) | `_accumulate_family` + `select_family` | (lógica cubierta; puntos vía integración) |
| §4 outer: min 300, promotion_pass 6 gates | `run_outer`, `promotion_pass`, `MIN_OUTER_TRAIN` | `constantes congeladas` |
| §4 sin desempate externo entre familias | `select_family` decide; `promotion_pass` sólo sí/no de P | (por construcción; sin ranking externo en código) |
| §4 agregación regional por etiqueta relativa congelada | `region_borders` del train de cada fold; etiqueta guardada en `oos_side` | (por construcción en `run_outer`) |
| §5 bin de cola Y≥12 (PMF suma 1) | `_side_pmf_full`, `_side_logpmf_*` con `sf(11)` | `Y>=12 usa bin de cola` |
| §5 márgenes ε0=0.02, ε_λ=0.05; n_boot=4000 | `EPS0`,`EPS_LAMBDA`,`N_BOOT` | `constantes congeladas` |
| §5 reproducibilidad por semilla | `week_block_mean_ci`, `tau_rule` deterministas | `reproducibilidad de semillas` |
| §4.6 estabilidad de selección ≥60% | `promotion_pass` gate6, `SELECTION_STABILITY` | `constantes congeladas` |

**Nota de implementación**: `week_block_mean_ci` remuestrea semanas enteras de
forma vectorizada (Σ suma_semana[elegidas] / Σ tamaño_semana[elegidas]) — más
rápido que concatenar por resample y equivalente (resamplea el bloque completo).

Con estos tests en verde, queda habilitada la corrida única sobre 2025 (paso 4).
