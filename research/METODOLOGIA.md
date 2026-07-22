# Cómo se hacen las simulaciones: guía metodológica del pipeline

**Para**: el director del proyecto. **Objetivo**: que puedas leer cualquier número o
figura de los experimentos sabiendo exactamente qué operación lo produjo, qué está
"simulado" y qué es dato real.

---

## 1. El flujo de datos, de la cancha al CSV

```
federaciones (Palloliitto API / svenskfotboll.se / fotball.no)
        │  build_dataset.py · build_dataset_nordics.py   ← HTTP, ids por temporada mapeados
        ▼
research/peak_models/data/*.csv     ← una fila = un partido JUGADO
        │  loader.load_all()
        ▼
DataFrame con: season, league_code, country, date, home/away_team_id,
home/away_goals, result (H/D/A)
```

No hay nada inventado ni interpolado: cada fila es un partido real con su
resultado oficial. La "manipulación" de datos se reduce a: normalizar nombres de
equipo a ids, convertir fechas, y descartar partidos sin resultado (suspendidos).
Regenerar el dataset es re-llamar a las APIs — los scripts son deterministas.

## 2. Qué es "una simulación" acá (y qué NO es)

**No simulamos partidos.** No hay Monte Carlo de goles en ninguna evaluación: la
distribución de marcadores del modelo es **analítica** (una matriz 11×11 de
probabilidades exactas dada λH, λA, ρ). Lo que llamamos "simulación" es un
**replay histórico del proceso de decisión** (walk-forward):

```
para cada semana W del período de test (lunes a domingo):
    train  = todos los partidos TERMINADOS antes del lunes de W    # nunca el futuro
    ajustar cada modelo usando SOLO train                          # refit semanal
    para cada partido de la semana W:
        emitir (p_H, p_D, p_A) antes del kickoff                   # predicción congelada
    recién después, comparar con los resultados reales de W
```

Esto reproduce exactamente la situación operativa: el lunes 8-jun-2026 el modelo
sabía lo que cualquiera podía saber ese lunes, y nada más. Las features (tabla,
ppg, posición) se reconstruyen "as-of" ese lunes — no se usa la tabla final.

Los únicos dos lugares donde hay azar computacional son:
1. **El bootstrap** (§5): remuestrea partidos/bloques ya jugados para medir la
   incertidumbre de las métricas. Semilla fija → reproducible.
2. **La integración de Laplace** (EXP-004.5): muestrea parámetros alrededor del
   MAP para propagar incertidumbre paramétrica.

## 3. Un partido real, paso a paso

**Inter Turku vs AC Oulu**, Veikkausliiga, sábado 13-jun-2026. Cutoff: lunes 9-jun.

1. `train` = 235 partidos de VL terminados antes del lunes (2025 completo + 2026
   parcial), cada uno con peso temporal $w = 2^{-\Delta t/120\text{ días}}$ (un
   partido de hace 4 meses pesa 0.5; uno de 2025, ~0.1).
2. Maximizar la verosimilitud penalizada da los parámetros de la liga ese lunes:
   $\mu=0.146$, localía $\gamma=0.245$, $\rho=-0.096$, y por equipo:
   Inter Turku (atk $+0.163$, def $+0.399$), AC Oulu (atk $+0.071$, def $+0.201$).
3. Intensidades del partido:
   $\lambda_H = e^{0.146+0.245+0.163-0.201} = 1.42$,
   $\lambda_A = e^{0.146+0.071-0.399} = 0.83$ goles esperados.
4. Matriz de marcadores (esquina 4×4; la completa es 11×11 y suma 1):

   |  | 0 | 1 | 2 | 3 |
   |---|---|---|---|---|
   | **0** | .116 | .075 | .036 | .010 |
   | **1** | .137 | .136 | .052 | .014 |
   | **2** | .106 | .088 | .037 | .010 |
   | **3** | .050 | .042 | .017 | .005 |

   (el 0-0 de .116 ya incluye el empuje de ρ<0; sin ρ sería .107)
5. Sumando triángulos y diagonales: $p_H=0.497$, $p_D=0.295$, $p_A=0.208$;
   además over 2.5 = 0.393 y BTTS = 0.441 — **todo sale de la misma matriz**.
6. Resultado real: **0-0**. El RPS de este partido:
   $\frac{1}{2}[(0.497-0)^2 + (0.792-1)^2] = 0.145$.
   Nota: el modelo "no acertó" (el máximo era H) pero el RPS lo premia por haber
   puesto 29.5% al empate — eso es evaluar la distribución, no el palpite.

## 4. De 1.619 partidos a un número

El RPS del modelo es el **promedio** de ese cálculo sobre todos los partidos del
test. Por eso las diferencias parecen chicas (0.2139 vs 0.2225): son promedios
sobre cientos de partidos donde ambos modelos suelen decir cosas parecidas; la
diferencia la hacen los partidos donde discrepan. Referencias para ubicarse:
predecir (⅓,⅓,⅓) siempre da RPS ≈ 0.222 en promedio con estas tasas base; la
tasa base por liga da 0.238; el mercado (cuando podamos medirlo) suele estar en
0.19-0.20 en ligas top. Log-loss y Brier son promedios análogos con otras
penalizaciones (el log-loss castiga brutalmente la sobreconfianza equivocada).

## 5. Cómo se comparan dos modelos (y por qué pareado)

Nunca comparamos promedios sueltos: para cada partido computamos
$d_i = \mathrm{RPS}^{(A)}_i - \mathrm{RPS}^{(B)}_i$ **sobre los mismos partidos**
(pareo). Eso cancela la dificultad intrínseca del partido — un fin de semana de
sorpresas castiga a ambos por igual y no ensucia la comparación.

El intervalo de confianza sale de bootstrap: re-muestrear los $d_i$ con
reemplazo 4.000 veces y mirar los percentiles 2.5/97.5 de la media. Tras la
revisión del referee, esto se hace en **cuatro variantes** (EXP-004.1): partido a
partido (asume independencia), por bloques de semana (respeta que toda la semana
sale del mismo ajuste), semana×liga, y bloques móviles de 4 semanas. Si el IC
excluye al 0 en todas las variantes, la diferencia es robusta a la dependencia;
si solo en la iid, es sospechosa. (dc−g0 sobrevivió a las cuatro;
stack_cal−dc no quedó establecida en ninguna.)

## 6. Cómo se compara el modelo con la realidad

Tres niveles, del más grueso al más fino, cada uno con su figura:

1. **¿Ordena bien?** — RPS/log-loss vs baselines (dot plot con IC). Responde
   "¿saber más reduce el error?" pero no dice si las probabilidades son creíbles.
2. **¿Las probabilidades son honestas?** — curvas de confiabilidad: junto todos
   los partidos donde el modelo dijo "local ≈ 45%" y miro cuántos ganó el local
   de verdad. Si da ≈45%, calibrado. La **pendiente de calibración** resume esto:
   1 = perfecto; <1 = el modelo exagera sus diferencias (sobreconfianza). Medido:
   DC tiene pendiente 0.80 (H), 0.37 (D), 0.71 (A) → exagera, sobre todo empates;
   la recalibración las lleva a 0.90/0.68/0.83.
3. **¿El mecanismo generador es correcto?** — diagnósticos distribucionales
   (EXP-004.2): comparo la distribución real de goles con la **mezcla** de las
   Poisson predichas partido a partido; miro los residuos de Pearson
   $(g-\hat\lambda)/\sqrt{\hat\lambda}$, cuya varianza debería ser 1 si el
   Poisson condicional fuera exacto (medido: 1.27 local, 1.14 visitante → los
   goles reales son más "anchos" que Poisson); y las celdas 0-0/1-0/0-1/1-1
   observadas vs predichas (el 0-0 real es 4.5%, el modelo dice 5.6%).

La cadena completa es: **realidad** (goles) → **modelo** (λs y matriz) →
**probabilidades** (1X2/OU/BTTS) → **score** (RPS por partido) → **agregado**
(media) → **incertidumbre** (bootstrap por bloques) → **diagnóstico** (¿dónde y
por qué difiere la predicción de lo observado?).

## 7. Mapa de artefactos: qué script produce qué

| Script | Produce | Pregunta que responde |
|---|---|---|
| `peak_models/build_dataset*.py` | `data/*.csv` | los datos crudos |
| `peak_models/models.py` | fits Poisson/DC/jerárquico | los λ y las matrices |
| `peak_models/evaluate.py` | `walk_forward()`, métricas | el replay y los scores |
| `EXP-00N/run.py` | `walkforward_*.csv`, `results.json` | tablas de comparación |
| `EXP-00N/figures.py` | `fig/*.png` | las figuras del informe |
| `EXP-004/block_bootstrap.py` | `block_bootstrap.csv` | robustez a dependencia |
| `EXP-004/poisson_diagnostics.py` | `lambdas_2026.csv`, diagnósticos | ¿Poisson describe los goles? |
| `EXP-004/calibration_deep.py` | `calibration_deep.json` | ¿las p son honestas? |
| `EXP-004/laplace.py` | `laplace.json` | ¿cuánto importa la incertidumbre paramétrica? |

Cada `walkforward_*.csv` guarda por partido y modelo: fecha, cutoff del ajuste,
equipos, probabilidades emitidas y resultado real — con eso podés reconstruir
cualquier número de los informes a mano, o auditar un partido puntual como en §3.
