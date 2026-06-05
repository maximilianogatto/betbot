# Peak models — research sandbox

Dataset + guía para experimentar con modelos de predicción de partidos de las
ligas de Finlandia (las "ligas especiales" del bot). La idea: vos probás los
modelos en notebooks; acá tenés los datos listos y un mapa de qué hacer.

---

## 1. Qué hay en `data/`

| Archivo | Contenido |
|---|---|
| `finland_matches_played.csv` | **Master**: todos los partidos *jugados* de 2025+2026, las 5 ligas. Es el que usás para entrenar. |
| `by_league_year/<CODE>_<YEAR>.csv` | Todos los partidos (jugados + programados) de una liga y temporada. Separado como pediste. |
| `today_fixtures.csv` | Fixtures de hoy de ligas senior (para predecir). *Ojo:* puede traer partidos ya en juego (status `Live`). |

Ligas (`league_code`): `VL` Veikkausliiga (1ª), `M1L` Ykkösliiga (2ª), `M1`
Ykkönen (3ª), `M2` Miesten Kakkonen (4ª), `NL` Kansallinen Liiga (femenina 1ª).

### Esquema (una fila = un partido; `team_A`/`home` es LOCAL)
`season, league_code, league_name, competition_id, group_id, group_name, round,
match_id, date, time, home_team_id, home_team, away_team_id, away_team,
home_goals, away_goals, ht_home, ht_away, status, result` (`result` ∈ H/D/A).

> **`group_id`/`group_name` importa**: M2 (Kakkonen) se juega en *lohkos*
> regionales (Lohko A, B, …). Equipos de distinto lohko casi no se cruzan →
> **modelá dentro del grupo**. VL/M1L corren una sola serie (Runkosarja) + playoffs.

## 2. Cómo cargar (pandas)
```python
from research.peak_models import loader
df    = loader.load_matches()                  # master jugado
longf = loader.to_team_long(df)                # 1 fila por equipo/partido (gf, ga, venue, points)
tabla = loader.table_as_of(df, "2026-05-01",   # standings point-in-time (sin leakage)
                           league_code="VL", season=2026, group_id=1)
hoy   = loader.load_today()
```
(Necesitás `pandas`. Corré `build_dataset.py` para regenerar/actualizar.)

---

## 3. Definir la META (lo más importante)

Sugiero una escalera; elegí hasta dónde querés llegar:

- **G0 — Baseline.** Predecir 1X2 con solo *ventaja de local + posición de tabla*.
  Es el piso contra el que TODO se compara. Si un modelo no le gana, no sirve.
- **G1 — Núcleo: distribución del resultado.** Predecir `P(local), P(empate),
  P(visita)` (y/o la distribución de goles) de cada partido pre-match.
  Métrica norte: **RPS** (ranked probability score, ideal para 1X2 ordinal) +
  log-loss. Es un objetivo de ML bien planteado y medible.
- **G2 — El "peak".** Derivar de esa distribución un *favorito + confianza*.
  Un peak = `P(favorito)` alta **y** (cuando sumemos cuotas) *edge* vs la cuota.
  O sea: el peak es una **decisión sobre la distribución de G1**, no un modelo aparte.

**Mi recomendación de meta**: apuntá a **G1** (predecir bien la distribución,
medido por RPS contra el baseline G0). El "peak" (G2) sale gratis una vez que
G1 está calibrado. El valor real vs casa de apuestas es una capa extra que
necesita las cuotas (las extrae el bot; se puede cruzar después).

---

## 4. Ideas de modelos (de simple a rico)

Para cada uno: **qué predice** y **cómo se entrena**.

1. **Poisson independiente** *(arrancá por acá)*. Goles local ~ Poisson(λ_H),
   visita ~ Poisson(λ_A), con `log λ_H = μ + atk_home − def_away + ventaja_local`
   y `log λ_A = μ + atk_away − def_home`. Parámetros `atk_i, def_i` por equipo +
   `ventaja_local`. Ajuste por MLE (statsmodels GLM Poisson con dummies de
   equipo, o scipy). De `λ_H, λ_A` sacás la matriz de marcadores → 1X2, over/under.
2. **Dixon-Coles**. Poisson + (a) corrección de dependencia en marcadores bajos
   (0-0,1-0,0-1,1-1) y (b) **decaimiento temporal** (partidos viejos pesan menos,
   `e^{-ξ·Δt}`). Es el estándar de la industria para fútbol. Mejora notablemente
   sobre Poisson plano.
3. **Bayesiano jerárquico** (PyMC/Stan). Mismos `atk/def` pero con **priors** y
   **pooling parcial**: equipos con pocos partidos se encogen hacia la media de
   liga (shrinkage = tu intuición de la función de Fermi, bien hecha). Te da la
   **distribución posterior** → intervalos de credibilidad y P(...) con incertidumbre.
   Resuelve de raíz el problema de muestra chica de principio de temporada.
4. **Dinámico / state-space (Kalman)**. `atk_i, def_i` como **estados latentes que
   evolucionan** (random walk) y se actualizan tras cada fecha. La forma reciente
   pesa sola (el ruido de proceso fija la velocidad), el empalme 2025→2026 es un
   prior que se diluye, y es la base natural para el análisis en vivo.
5. **Logística sobre features** *(la capa de calibración que ya charlamos)*.
   Tomar features pre-match (Δposición, z de ataque/defensa local/visita, H2H
   decaído, transitividad) y ajustar una multinomial/ordinal para 1X2.
   **Aprende los pesos de los datos** (el backtest mostró: position +0.41,
   transitivity +0.38, supremacy +0.37, h2h +0.27) y **calibra** la salida.
   Sirve como modelo directo o como capa final sobre 1–4.

> H2H y transitividad: en 1–4 (modelos de fuerza) son *emergentes* —las fuerzas
> ya se estiman conjuntamente sobre el grafo de partidos. En 5 son features
> explícitas. No hace falta ponerlos a mano si vas por modelos de fuerza.

---

## 5. Cómo evaluar bien (clave para no engañarse)

- **Split temporal (walk-forward), nunca aleatorio.** Entrená con `date < D`,
  testeá con `date ≥ D`. `loader.table_as_of` y armar features "as of" evita leakage.
  Pseudo: para cada fecha, reentrenás (o actualizás) con lo previo y predecís la fecha.
- **Métricas propias**: **RPS** (1X2 ordinal), **log-loss**, Brier. Curva de
  **calibración** (lo predicho vs lo observado por bin). *No* uses accuracy a secas.
- **Baselines obligatorios**: (a) tasa base de la liga (≈ % local/empate/visita),
  (b) ventaja-local + tabla. Y cuando haya cuotas, la **probabilidad implícita de
  la casa** (sin vig) es el rival a vencer de verdad.
- **Empates ~25%**: en estas ligas el empate es frecuente → por eso 1X2/Poisson
  (que lo modelan nativo) > un binario "gana favorito".

---

## 6. Caveats de los datos
- **Grupos**: filtrá por `group_id` antes de armar tablas/fuerzas en M2.
- **Muestra**: 2026 lleva pocas fechas (VL 58 jugados, M2 105, etc.) → usá 2025
  como prior y/o shrinkage; no confíes en estimaciones de equipos con <4-5 PJ.
- **Empalme de temporada**: hay ascensos/descensos; un equipo puede estar en 2025
  y no en 2026. Tratá 2025 como información previa que decae, no como misma muestra.
- **Ventaja de local**: estimala de los datos (acá suele ser ~+0.2–0.4 goles); no la asumas.
- **`today_fixtures.csv`**: hoy había 2 partidos y ya estaban `Live`. Para una
  predicción limpia, regenerá en un día con fixtures `Scheduled`, o filtrá por status.

---

## 7. Notebooks
- **`g0_baseline.ipynb`** — G0 ya implementado y corrido: EDA, feature Δppg
  point-in-time, curva empírica H/D/A, base-rate vs logística multinomial,
  RPS/log-loss con split 2025→2026, calibración y predicción de hoy.
  (Validado: RPS logística 0.220 < base 0.237.)

Próximos:
1. Poisson (modelo 1) → batir el baseline. Mirar calibración.
2. Dixon-Coles (decaimiento + corrección) → comparar.
3. Incertidumbre/muestra chica: jerárquico bayesiano. Forma/tiempo: Kalman.
4. Capa logística de calibración + definir el corte de "peak".

> El backtest del bot (`monitors/peak_backtest.py` en main) ya hace el walk-forward
> point-in-time del modelo heurístico actual: úsalo como vara de comparación.
