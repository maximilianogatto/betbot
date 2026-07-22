# Enmienda 002 a la pre-registración EXP-005 — decisión sobre H4

**Fecha efectiva**: 2026-07-23 (Europe/Madrid)
**Decisión**: H4 (`dc_dyn_gamma`, localía dinámica) **NO se activa** en la ventana
confirmatoria. Se retira de la batería del cierre.

`H_GAMMA_FROZEN: none`

## Justificación (evidencia de desarrollo, solo 2025)

La pre-registración estableció que H4 se activaría "si se implementa antes del
2026-08-01 sin mirar datos de la ventana; si no llega, se cae". Se implementó
(`models.py::fit_poisson`, parámetro `gamma_halflife`, con perfil de
verosimilitud de solución cerrada) y se tuneó exclusivamente con 2025
(`dyn_gamma_tuning.py`, walk-forward jul→nov, más leave-one-country-out).
Resultado: **señal nula**.

| H_γ (días) | RPS 2025 | log-loss 2025 |
|---|---|---|
| 30 | 0.1952 | 0.9198 |
| 60 | 0.1951 | 0.9198 |
| 120 (= base) | 0.1951 | 0.9200 |
| 240 | 0.1952 | 0.9202 |
| base (kernel general) | 0.1951 | 0.9200 |

Mejor candidato vs base (IC por bloques semanales):
- ΔRPS = **−0.0000**, IC [−0.0002, +0.0002] — centrado en cero.
- Δlog-loss = −0.0002, IC [−0.0008, +0.0004].

Leave-one-country-out: el H_γ óptimo cambia de país a país (sin FIN gana 240,
sin SWE gana 30, sin NOR gana 60) — no hay un valor estable, síntoma de que se
está ajustando ruido.

## Interpretación mecanística

La ablación (EXP-004) mostró que la localía es el único componente cuya
remoción deteriora claramente el modelo — por eso H4 era una apuesta razonable.
Pero **hacerla dinámica no agrega** porque γ ya está bien estimada: es un único
escalar por liga, y el kernel general de 120 días ya captura su deriva
intra-temporada. El corrimiento de localía entre temporadas observado en M1
(0.52→0.39) lo absorbe el propio decaimiento (los partidos de 2025 pesan ~0.1
en junio de 2026). No había un residuo que un kernel separado para γ pudiera
explicar. Regla del programa: *cada nueva complejidad debe explicar un residuo
medido* — esta no lo hizo.

## Efecto sobre el registro

- H1, H2, H3, H5 permanecen sin cambios.
- La ventana confirmatoria queda con **cuatro** hipótesis, no cinco.
- `run_confirmatory.py` lee `H_GAMMA_FROZEN` de este archivo; con valor `none`
  no incorpora el modelo (verificado en el dry-run: `dc_dyn_gamma` ausente).
- Esta decisión se tomó con datos de 2025 únicamente; ningún partido posterior
  al 2026-07-26 fue observado para tomarla.
