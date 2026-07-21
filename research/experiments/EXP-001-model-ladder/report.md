# EXP-001 — Escalera de modelos 1X2 (Finlandia)

**Fecha**: 2026-07-21 · **Dataset**: 1.394 partidos jugados (2025-04-05 → 2026-07-20),
5 ligas finlandesas (VL, M1L, M1, M2, NL) vía Palloliitto.
**Protocolo**: walk-forward semanal (refit lunes, predicción de la semana), features
point-in-time, hiperparámetros elegidos solo con 2025, evaluación pura en 2026 (507 partidos).

## Pregunta

¿Un modelo de fuerzas ataque/defensa sobre goles (Poisson / Dixon-Coles con decaimiento
temporal y shrinkage ridge) supera al baseline G0 (logística multinomial sobre Δppg) y a la
tasa base por liga?

## Selección de hiperparámetros (solo 2025, walk-forward jul→nov, 509 partidos)

| Config | RPS |
|---|---|
| **halflife 120d, σ=0.75** | **0.1954** |
| halflife 120d, σ=1.5 | 0.1956 |
| halflife 240d, σ=0.75 | 0.1958 |
| sin decaimiento, σ=0.75 | 0.1963 |
| + ρ (Dixon-Coles) | 0.1953 (mejora marginal, se adopta) |

El decaimiento temporal ayuda (consistente con Dixon-Coles 1997); el shrinkage más fuerte
(σ=0.75) ayuda — esperable con equipos de pocas fechas. Config final: **hl=120d, σ=0.75, ρ on**.

## Resultado principal (2026, 507 partidos, walk-forward)

| Modelo | RPS | log-loss | Brier | ECE(H) | acc | ΔRPS vs G0 (IC 95%) | P(mejor) |
|---|---|---|---|---|---|---|---|
| **dc_best** | **0.2107** | **0.9918** | 0.5921 | 0.069 | 0.552 | −0.0086 (−0.0179, +0.0010) | 0.963 |
| poisson_plain | 0.2159 | 1.0075 | 0.6034 | 0.074 | 0.519 | −0.0034 (−0.0145, +0.0073) | 0.732 |
| g0_logistic_dppg | 0.2193 | 1.0224 | 0.6123 | 0.060 | 0.523 | — | — |
| b0_base_rate | 0.2377 | 1.0675 | 0.6468 | 0.089 | 0.446 | +0.0184 (+0.0093, +0.0272) | 0.000 |

### RPS por liga (2026)

| Modelo | M1 | M1L | M2 | NL | VL |
|---|---|---|---|---|---|
| dc_best | 0.2376 | 0.2194 | **0.2118** | **0.1535** | 0.2077 |
| g0_logistic | **0.2292** | 0.2212 | 0.2242 | 0.2062 | **0.2058** |

## Conclusiones

1. **La escalera se ordena como predice la teoría**: base < logística-tabla < Poisson < Dixon-Coles,
   en RPS y log-loss. G0 queda batido por el modelo de goles.
2. **Honestidad estadística**: la mejora de dc_best sobre G0 tiene P(mejor)≈0.96 en RPS
   (IC 95% roza el 0: −0.0179 a +0.0010) y P≈0.97 en log-loss. Evidencia **fuerte pero no
   concluyente al 95%** con 507 partidos. Se re-evalúa al cerrar la temporada 2026 (+~300
   partidos) — no se declara G2 superado todavía, pero el rumbo es claro.
3. **La ganancia se concentra donde más importa para el proyecto**: NL (femenina, RPS 0.154 vs
   0.206 de G0, −25%) y M2/Kakkonen (0.212 vs 0.224) — exactamente las ligas "especiales" de
   menor eficiencia hipotetizada. En M1 (Ykkönen) el DC pierde contra G0 → investigar (¿grupos?
   ¿ascensos? EXP-002 candidato).
4. El decaimiento de 120 días implica que media temporada atrás pesa 50% — la forma reciente
   importa en estas ligas.
5. El modelo emite además `p_over25` y `p_btts` gratis (matriz de marcadores) — pendiente de
   evaluación cuando definamos targets O/U (necesita cuotas para lo económico).

## Limitaciones / próximos pasos

- Equipos ascendidos/descendidos entran como "equipo promedio" de la liga (atk=def=0 con
  shrinkage): sesgo conocido; el jerárquico multi-liga del protocolo (§5) lo resuelve.
- Sin cuotas archivadas aún no hay métricas económicas (ROI/CLV) — bloqueado por Fase 0.
- Siguiente: EXP-002 (diagnóstico M1 + capa de calibración logística sobre λs),
  EXP-003 (jerárquico bayesiano multi-liga con Noruega/Suecia/Islandia cuando el dataset
  builder se extienda a esas federaciones).

## Reproducir

```bash
research/.venv/bin/python research/experiments/EXP-001-model-ladder/run.py
research/.venv/bin/python research/experiments/EXP-001-model-ladder/build_notebook.py
```

Artefactos: `config.json`, `results.json`, `walkforward_2026.csv`,
notebook analítico `research/peak_models/g1_poisson_dc.ipynb`.
