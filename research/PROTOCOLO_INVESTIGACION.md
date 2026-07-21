# Protocolo de investigación: detección de value bets en fútbol

**Rol del documento**: protocolo científico del proyecto. Toda decisión de modelado debe poder
rastrearse a una sección de este documento o a un experimento registrado en `research/experiments/`.

**Versión**: 0.1 — 2026-07-12
**Estado**: borrador para revisión del director del proyecto (el usuario)

---

## 0. Resumen ejecutivo

- **Objetivo**: producir probabilidades calibradas pre-partido para 1X2, AH, O/U, BTTS y goles
  por equipo, y detectar desvíos significativos frente a las probabilidades implícitas del mercado.
  La métrica de éxito es **EV/ROI fuera de muestra y Closing Line Value**, no accuracy.
- **Hallazgo crítico de la auditoría de datos (§1)**: el bot hoy **no archiva historia**. La tabla
  `event_odds_snapshots` contiene 154 filas de un solo día (2026-06-27). Sin archivo de cuotas
  de cierre no hay backtest honesto. La **Fase 0** (archivado) es prerequisito de todo lo demás
  y debe arrancar ya, porque cada día sin archivar es un día menos de dataset propio.
- **Hipótesis central** (falsable): los mercados de ligas menores (Kakkonen, 3. divisjon,
  Deild islandesas, USL League Two, femenino, reservas) son menos eficientes que los de ligas
  top — menor volumen, menos modelos compitiendo, información pública más lenta — y por lo tanto
  un modelo estadístico bien calibrado puede encontrar EV positivo sostenido allí. La literatura
  respalda la premisa de ineficiencia relativa pero **no garantiza** que el edge supere el vig
  (que en ligas menores es más alto). Esto se decide con datos, no con fe.
- **Arquitectura propuesta**: jerárquica con *partial pooling* bayesiano (no niveles ad-hoc):
  un modelo global aprende estructura compartida, efectos aleatorios por liga capturan
  idiosincrasias (localía, media de goles, tasa de empates), y clustering de ligas define la
  estructura de pooling. El mercado se usa como **benchmark y ancla de calibración**, nunca como
  feature del modelo cuya divergencia queremos medir (§5.4).

### Criterios go/no-go del proyecto

| Gate | Criterio | Si falla |
|---|---|---|
| G1 (Fase 2) | Dataset ≥ 3.000 partidos con cuotas pre-match verificadas, 0 leakage detectado en auditoría | No se entrena nada |
| G2 (Fase 3) | Algún modelo supera al baseline de mercado en log-loss/RPS **o** muestra desvíos explotables en algún segmento | Revisar features, no forzar |
| G3 (Fase 4) | ROI > 0 en rolling validation con intervalos bootstrap que excluyen 0, y CLV medio > 0 | El modelo describe, no apuesta |
| G4 (Fase 5) | ROI sostenido en paper-trading prospectivo ≥ 8 semanas | Volver a G2 |

---

## 1. Auditoría de datos existentes (hecha 2026-07-12)

### 1.1 Lo que hay

| Activo | Estado | Uso para el proyecto |
|---|---|---|
| `data/tracking.sqlite3` → `event_odds_snapshots` | **154 filas, un solo día** (2026-06-27), 9 plataformas | Esquema correcto (1X2 + BTTS + `markets_json`), pero sin historia. Verificar cuánta historia tiene la DB del VPS de producción. |
| Extractores de cuotas (9): 1xbet, betovo, betsson, betwarrior, bz, mrpunter, mystake, solcasino, bet365 | Operativos, HTTP-only | Fuente de cuotas *hacia adelante* (Fase 0) |
| `sportradar_http/engine` | Endpoints por temporada: `stats_season_fixtures2`, `stats_season_tables`, `stats_season_teamscoringconceding`, `stats_season_injuries`, `stats_formtable`, `stats_team_lastx`, H2H, `match_markets` | **Columna vertebral de resultados históricos**: fixtures + resultados + tablas por temporada para ligas menores. `match_markets` a veces viene vacío en partidos terminados — no confiar para odds históricas. |
| `footystats_http` | Provider operativo | FootyStats expone datos históricos por temporada **incluyendo cuotas pre-match** para muchas ligas menores → candidato principal para el dataset retrospectivo 2025. Verificar cobertura exacta por liga y qué cuota reportan (apertura/cierre/promedio). |
| Providers de federaciones: `palloliitto` (FIN), `svenskfotboll` (SWE), `norway_http` (NOR), más flashscore/sofascore | Operativos | Resultados oficiales, tablas, fixtures para reconstrucción punto-en-el-tiempo |
| `unified_competitions` + registro canónico de ligas | Operativo | Clave de join entre libros y proveedores de stats — ya resuelve el problema de entity matching |

### 1.2 Los dos gaps que definen el proyecto

1. **No hay archivo de cuotas de cierre propio.** Acción: Fase 0.
2. **Las tablas/standings históricos deben reconstruirse "as-of" la fecha de cada partido**, no
   tomarse de la tabla final. Sportradar/federaciones dan resultados con fecha → la tabla en la
   jornada N se reconstruye computacionalmente. Esto es trabajo determinista y verificable.

### 1.3 Fuentes externas de cuotas históricas (para el retrospectivo 2025)

- **FootyStats** (ya integrado): primera opción; validar qué timestamp de cuota entregan.
- **football-data.co.uk**: cierre de Pinnacle/B365 pero solo ligas principales — sirve como
  *conjunto de control* para validar la metodología en un mercado eficiente conocido.
- **BetExplorer/OddsPortal**: cubren ligas menores con historial de movimiento de cuotas;
  requiere scraping (evaluar costo/fragilidad; mismo patrón HTTP-only que ya usa el proyecto).

Regla: cada cuota del dataset lleva metadato `odds_source`, `odds_timestamp_type`
(opening/closing/unknown) y `bookmaker`. Backtests reportados siempre declaran contra qué cuota
se simuló. Simular contra "mejor cuota del mercado" y contra "cuota promedio" por separado.

---

## 2. Fase 1 — Revisión bibliográfica

Referencias canónicas que anclan cada decisión metodológica. Regla de trabajo: antes de
implementar un método, leer el paper y registrar en `research/lit/` una ficha de 10 líneas
(qué hace, dataset, resultado vs mercado, qué reutilizamos).

### 2.1 Modelos estadísticos de goles

- Maher (1982), *Modelling association football scores* — Poisson independiente con ataque/defensa.
- **Dixon & Coles (1997)**, JRSS-C — corrección de dependencia en marcadores bajos + **decaimiento
  temporal exponencial** de partidos pasados. Es el baseline estadístico obligatorio del proyecto
  y la justificación formal del decaimiento que exigimos en H2H y forma. También demostró
  ineficiencias explotables en el mercado inglés de los 90.
- Karlis & Ntzoufras (2003) — Poisson bivariada (covarianza de goles; relevante para BTTS/O/U).
- Rue & Salvesen (2000) — fuerzas dinámicas bayesianas (los equipos cambian durante la temporada).
- Koopman & Lit (2015), JRSS-A — state-space bivariado; evidencia de que fuerzas variantes en el
  tiempo mejoran sobre estáticas.
- Boshnakov, Kharrat & McHale (2017) — conteo Weibull; alternativa si Poisson subajusta colas.
- **Baio & Blangiardo (2010)** — **modelo jerárquico bayesiano** para fútbol: es exactamente el
  marco formal para la arquitectura multi-liga propuesta (§5.3): hiperpriors globales, efectos
  por liga, shrinkage automático para ligas con pocos datos.

### 2.2 Ratings

- Hvattum & Arntzen (2010), IJF — Elo para fútbol: informativo pero **pierde contra el mercado**.
  Fija la vara: un rating solo no alcanza.
- Constantinou & Fenton (2013) — **pi-ratings**: rating recursivo con decaimiento y separación
  local/visitante; barato de computar y fuerte como feature.
- Ley, Van de Wiele & Van Eetvelde (2019) — comparación sistemática de ratings; el decaimiento
  temporal óptimo se **estima**, no se elige a mano (half-life como hiperparámetro).
- FiveThirtyEight SPI (Boice & Silver) — referencia de diseño para rating ofensivo/defensivo global.

### 2.3 ML vs estadística vs mercado

- **Hubáček, Šourek & Železný (2019)**, IJF — gradient boosting con features de dominio;
  hallazgo clave: **descorrelacionarse del bookmaker** importa más para el profit que la accuracy.
  Justifica no usar cuotas como feature del modelo detector (§5.4).
- Groll, Ley, Schauberger & Van Eetvelde (2019) — híbrido random forest + ranking: los ensambles
  estadística+ML superan a cada uno por separado.
- Walsh & Joshi (2024) — optimizar **calibración** en vez de accuracy aumenta el profit de manera
  significativa. Confirma la función objetivo del proyecto.
- Revisión sistemática de ML en sports betting: arXiv:2410.21484 (2024) — mapa actualizado del
  campo; usarla como checklist de métodos a considerar.
- 2025 (verificar): trabajos con xG reportan ROI ~10-15% en nichos — tomar con escepticismo
  (survivorship y multiple testing en esta literatura son endémicos).

### 2.4 Mercado, eficiencia y value

- Shin (1993) + Štrumbelj (2014) — las probabilidades implícitas deben extraerse con el **modelo
  de Shin** (o al menos comparar contra normalización proporcional y power/margin methods);
  la normalización ingenua sesga en presencia de favorite-longshot bias.
- Kaunitz, Zhong & Kreiner (2017) — *Beating the bookies with their own numbers*: el consenso de
  cierre es el mejor predictor disponible; los libros limitan a ganadores (riesgo operativo real).
- Angelini & De Angelis (2019), IJF — eficiencia de mercados online: heterogeneidad por liga y
  bookmaker; base empírica para la hipótesis "ligas menores = menos eficientes".
- Wheatcroft (2020), IJF — modelo rentable para el mercado **O/U** usando ratings de goles:
  evidencia directa para nuestros targets de goles.
- Buchdahl — *Squares & Sharps* y trabajo sobre **CLV**: el CLV como test de skill con mucha menos
  varianza que el ROI. Adoptamos CLV como métrica norte (§6.3).
- Constantinou & Fenton (2012) — **Ranked Probability Score** como scoring rule apropiado para
  1X2 (respeta el orden home/draw/away).

### 2.5 Síntesis operativa de la literatura

1. El cierre de Pinnacle en ligas top es en la práctica insuperable tras el vig → no gastar
   presupuesto de investigación ahí; usarlo como *control negativo* (si el pipeline "encuentra
   edge" sistemático contra el cierre de Pinnacle en la Premier, hay un bug, no un descubrimiento).
2. El espacio de búsqueda con prior razonable de éxito: **ligas menores, mercados secundarios
   (O/U, AH, BTTS), y líneas tempranas** vs cierre.
3. Calibración > accuracy. Proper scoring rules (log-loss, RPS, Brier) como métricas primarias.
4. Descorrelación del mercado: el valor del modelo está exactamente donde discrepa del mercado
   y tiene razón.
5. Con ~3-6k partidos, los modelos estadísticos con pooling son favoritos a priori sobre deep
   learning; los GBMs compiten si las features condensan bien la historia. No asumir: medir (G2).

---

## 3. Fase 2 — Dataset

### 3.1 Alcance

- **Período**: temporadas 2025 completas + 2026 hasta hoy. Las ligas nórdicas juegan
  primavera-otoño → 2025 completo + 2026 parcial ≈ 1,5 temporadas por liga.
- **Ligas** (≥10, priorizando extractores existentes): Finlandia (Veikkausliiga, Ykkösliiga,
  Ykkönen, Kakkonen, femenino), Suecia (Allsvenskan→div. inferiores, Damallsvenskan), Noruega
  (Eliteserien→3. divisjon, Toppserien), Islandia (Besta, 1./2. deild), USL League Two,
  + 1-2 ligas top como control negativo.
- **Unidad**: un partido = una fila por mercado objetivo, con clave `(match_id, market)`.

### 3.2 Regla anti-leakage (innegociable)

> Toda feature se computa con un **snapshot congelado a T-1h del kickoff** usando únicamente
> partidos con `fecha_fin < kickoff`. La tabla de posiciones es la reconstruida a esa fecha.
> Un test automatizado (`tests/research/test_no_leakage.py`) verifica por construcción que
> ninguna feature correlaciona con información posterior al kickoff (p. ej., recomputar la
> feature borrando el futuro y exigir igualdad bit a bit).

Fuentes de leakage típicas a auditar: tabla final en vez de as-of; "promedio de goles de la
temporada" que incluye el partido; cuotas de cierre usadas como feature para predecir un
mercado ya cerrado; equipos renombrados a mitad de temporada que rompen joins.

### 3.3 Catálogo de features (cada una con ficha de justificación)

Cada feature entra al catálogo (`research/features/CATALOG.md`) con: definición formal,
ventana/decaimiento, fundamento bibliográfico, y resultado de su evaluación individual (§3.5).

- **Tabla as-of** (normalizada): percentil de posición (no posición absoluta), PPG, DG/partido,
  GF/GC por partido — todo relativo al tamaño y media de la liga.
- **Forma**: puntos y goles en últimos 5/10; **forma con decaimiento exponencial** con half-life
  estimado por CV (Dixon-Coles); racha ajustada por rival.
- **Local/visitante**: PPG, GF, GC separados por condición; delta localía del equipo vs media
  de localía de su liga.
- **Goles**: tasas de ataque/defensa relativas a la liga (ratios, no diferencias absolutas —
  una liga con media 3.2 goles no es comparable a una con 2.1); over/under rate histórico;
  BTTS rate; varianza de marcadores (proxy de volatilidad del equipo).
- **Ratings**: pi-ratings (local/visitante separados) + Elo con K y half-life estimados;
  ataque/defensa Dixon-Coles como feature para los ML (stacking estadística→ML).
- **H2H con decaimiento**: suma ponderada exp(-λ·Δt) de resultados H2H; λ estimado, no fijado.
  Con prior de que H2H aporta poco tras controlar por fuerza (la literatura es escéptica) —
  se queda solo si sobrevive la ablación.
- **Rivales comunes**: diferencial de performance (puntos y DG) contra el conjunto de rivales
  compartidos en los últimos 12 meses, ponderado por recencia.
- **Momentum / cambio de régimen**: pendiente de rating en últimos N partidos; CUSUM sobre
  residuos (resultado real – esperado por rating) para detectar quiebres tipo *Washington
  Spirit 2021* (arranque malo → campeón); diferencia forma-últimos-5 vs forma-temporada.
- **Strength of schedule**: rating medio de rivales enfrentados (total y en la ventana de forma);
  ajusta la forma bruta.
- **Congestión/descanso**: días desde el último partido, partidos en 14/21 días, torneo del
  partido anterior (liga/copa).
- **Copas y diferencia de categoría**: delta de nivel de liga entre rivales (usando el registro
  canónico de ligas), flag equipo B/reservas (el detector B-Team de `special_peak` ya existe),
  distancia en la pirámide.
- **Viajes**: distancia entre venues (`stats_season_venues` da coordenadas) — solo si el dato
  es confiable; en islas nórdicas puede importar.
- **Lesiones/sanciones** (`stats_season_injuries`): conteo de bajas ponderado por minutos jugados
  — *solo hacia adelante* (no reconstruible retrospectivamente sin bias); entra en v2.
- **Contexto de liga**: media de goles de la liga, tasa de empates, ventaja localía media —
  estas son exactamente las variables que la capa jerárquica absorbe como efectos por liga.

### 3.4 Targets

`home_win/draw/away_win` (1X2), `total_goals` + umbrales 1.5/2.5/3.5 (O/U), `btts`,
`home_goals`/`away_goals` (para AH y team goals vía distribución de marcadores), margen de
victoria (para AH directo). Correct score queda como derivado de los modelos de conteo, no
como target propio (opcional, baja prioridad).

### 3.5 Evaluación de features

- Univariada: mutual information y AUC marginal contra cada target, con CV temporal.
- Colinealidad: matriz de correlación + **VIF**; ante pares redundantes gana la de mejor ficha.
- PCA solo si un grupo colineal (p. ej., las 6 variantes de forma) mejora en CV al condensarse.
- **Ablation study** por grupos (tabla / forma / ratings / H2H / momentum / calendario):
  cada grupo debe pagar su lugar en log-loss de validación; se registra en el reporte.
- Permutation importance + SHAP en los GBMs; PDPs para verificar monotonía donde la teoría la
  exige (más rating → más P(win); si no es monótona, sospechar leakage o sobreajuste).

---

## 4. Fase 3 — Modelos

Todos compiten bajo el mismo protocolo (§6). Nadie gana por defecto.

| Familia | Modelos | Rol |
|---|---|---|
| Baselines duros | (a) probabilidades implícitas del mercado (Shin); (b) siempre-local; (c) frecuencias históricas de la liga | (a) es LA vara. Si nada lo supera en ningún segmento, no hay proyecto de apuestas — hay un paper de eficiencia. |
| Estadísticos | Poisson GLM, **Dixon-Coles con decaimiento**, Poisson bivariada, versión dinámica (Rue-Salvesen/Koopman-Lit si el costo lo justifica) | Generan la distribución completa de marcadores → 1X2, AH, O/U, BTTS, team goals de una sola pieza coherente |
| Ratings | Elo (optimizado), pi-ratings | Features + baseline intermedio |
| ML | Regresión logística (multinomial), Random Forest, **XGBoost/LightGBM/CatBoost** sobre el catálogo de features | Hipótesis: capturan interacciones que Poisson no ve |
| Jerárquico | Baio-Blangiardo extendido multi-liga (§5.3) | Candidato principal según prior |
| Ensambles | Stacking (estadístico como feature del GBM), promedio logit ponderado por log-loss de validación | Solo si superan a sus componentes con significancia |

Presupuesto de cómputo honesto: Dixon-Coles y GLMs son triviales; el jerárquico bayesiano
(PyMC/Stan) con ~5k partidos es tratable; los dinámicos completos se evalúan solo si G2 pasó.

## 5. Arquitectura jerárquica (la propuesta del director, formalizada)

### 5.1 Por qué partial pooling y no un modelo por liga ni un modelo global plano

Con ~150-400 partidos por liga-temporada: un modelo por liga sobreajusta; un modelo global plano
sesga (asume que la Kakkonen y la Allsvenskan comparten media de goles y localía). El punto medio
es shrinkage: cada liga tiene sus parámetros, pero provienen de una distribución común aprendida.

### 5.2 Especificación (versión estadística)

```
goles_home ~ Poisson(exp(μ_liga + localía_liga + atq_home − def_away))
atq_i, def_i ~ Normal(0, σ_liga)          # fuerzas por equipo, centradas por liga
μ_liga, localía_liga, σ_liga ~ hiperpriors comunes (o por cluster de ligas)
```

### 5.3 Clustering de ligas

Clusterizar ligas por perfil observable (media de goles, tasa de empates, ventaja localía,
varianza de resultados, nivel en la pirámide) — k-means/jerárquico sobre esos 5-6 descriptores —
y usar el cluster como nivel intermedio de pooling. Hipótesis del director a validar: Kakkonen ≈
3. divisjon ≈ deild bajas islandesas. El test: ¿el pooling por cluster mejora el log-loss de
validación vs pooling global? Si no mejora, se descarta (evidencia, no intuición).

Para los GBMs, el equivalente es: entrenar global con `liga`/`cluster` como categóricas +
features *relativas a la liga* (ya normalizadas en §3.3).

### 5.4 El mercado en la arquitectura — decisión de diseño clave

Dos modos, con roles distintos y separación estricta:

- **Modelo detector (sin cuotas como feature)**: produce P_modelo independiente del mercado.
  Es el que se compara contra P_mercado para medir edge. Si le diéramos las cuotas como input,
  colapsaría hacia el mercado y el "edge" medido sería ruido residual (Hubáček et al.).
- **Modelo híbrido (con cuotas)**: benchmark superior de calibración y detector de "cuánta
  información única tiene el modelo" (si el híbrido no mejora al mercado solo, el modelo no
  aporta señal). También sirve para *shrinkage del edge*: la apuesta se dimensiona sobre una
  probabilidad intermedia entre P_modelo y P_mercado (§7.2), que es la formalización correcta de
  "usar el mercado como calibración final".

---

## 6. Fase 4 — Protocolo de validación

### 6.1 Esquema temporal

1. **Split de desarrollo**: entrenar con partidos hasta 2025-09-30, validar 2025-10-01→12-31
   (ajuste de hiperparámetros, selección de features).
2. **Rolling-origin evaluation** (la cifra reportable): reentrenar cada 4 semanas con toda la
   historia disponible y predecir las 4 siguientes, desde 2025-07 hasta hoy. Nada de random split.
3. **Holdout intocable**: 2026-04-01→hoy no se mira hasta congelar metodología (una sola pasada).

### 6.2 Métricas

- **Primarias (probabilísticas)**: log-loss, **RPS** (1X2), Brier, ECE + curvas de calibración
  (reliability diagrams por decil), sharpness.
- **Secundarias (clasificación)**: accuracy, precision/recall/F1, ROC-AUC, confusion matrix —
  se reportan pero **no deciden nada**.
- **Económicas**: ROI, yield, profit, bankroll simulado, max drawdown, max losing streak,
  **CLV medio** (cuota tomada vs cierre) — el CLV es la métrica norte porque converge órdenes de
  magnitud más rápido que el ROI.
- **Significancia**: bootstrap por bloques temporales para IC del ROI y del Δlog-loss vs mercado;
  test de que el CLV medio > 0. Corrección por comparaciones múltiples (Benjamini-Hochberg) al
  escanear segmentos liga×mercado — sin esto, con 10 ligas × 5 mercados algo va a "dar rentable"
  por azar seguro.

### 6.3 Simulación de apuestas (realista o no vale)

Flat stake y Kelly fraccionado (¼ y ½); apuesta solo si EV > umbral (§7.1); cuota simulada = la
archivada al momento de decisión (nunca el cierre si decidimos antes); sensibilidad a: vig por
libro, disponibilidad real del mercado, y slippage. Reportar también la simulación "contra
cuota promedio del mercado" como escenario conservador.

### 6.4 Calibración post-hoc

Platt scaling vs **isotonic regression** vs beta calibration, ajustadas solo en train/validation
de cada ventana rolling. Comparar ECE antes/después. La isotónica necesita ≥ ~1000 puntos —
con menos, Platt/beta.

## 7. Fase 5 — Detección de value y staking

### 7.1 Umbral de edge

Para cada (partido, mercado): P_modelo, P_shin_mercado, edge = P_modelo·cuota − 1.
El umbral mínimo de edge **se estima** como el que maximiza el ROI de validación con IC bootstrap
que excluya 0 (esperable: 3-8% en ligas menores; el edge chico es indistinguible de error de
modelo). Umbral por segmento si la evidencia lo sostiene tras B-H.

### 7.2 Shrinkage del edge

Apostar sobre P* = w·P_modelo + (1−w)·P_mercado con w estimado en validación (equivale a asumir
que el modelo tiene parte de la verdad). Kelly fraccionado sobre P*. Esto reduce ruina por
sobreconfianza del modelo — es la versión cuantitativa de la humildad.

### 7.3 Tipos de señal (mismatch taxonomy)

Cada alerta se etiqueta: favorito subvalorado / línea AH desplazada / O-U mal centrado (media de
goles del par vs línea) / BTTS mal precificado / trampa de mercado (cuota que se mueve contra el
consenso de los 9 libros archivados — detectable con los snapshots multi-libro que ya recolecta
el bot). Cada tipo se backtestea por separado.

## 8. Reproducibilidad y registro de experimentos

- `research/experiments/EXP-NNN/` por experimento: `config.yaml` (datos, features, modelo,
  seeds, ventanas), `results.json`, reporte MD + PDF con: curvas de calibración, ROC, matriz de
  confusión, histograma de probabilidades, SHAP/importances, ROI/bankroll/drawdown, comparación
  vs baselines. Generación automática (matplotlib + pandoc), nada a mano.
- Datos versionados: snapshot del dataset con hash; el experimento referencia el hash.
- Ningún resultado se cita en decisiones si no tiene EXP-NNN.

## 9. Fase 6 — Operación (post-G3)

Job diario (infra de monitors existente): descargar fixtures próximos 7 días → congelar snapshot
de features → predecir → comparar contra cuotas archivadas del día → ranking por EV con umbral →
reporte + push Telegram (solo edge positivo). Cada predicción operativa se archiva con su cuota
tomada y luego su cierre → el CLV prospectivo es la auditoría permanente del sistema (G4).

## 10. Amenazas a la validez

1. **Multiple testing** al escanear segmentos — mitigado con B-H + holdout intocable.
2. **Cuotas históricas no representativas** (¿podías apostar a esa cuota? ¿con qué límite?) —
   mitigado declarando fuente/timestamp y escenario conservador.
3. **Ligas menores = límites bajos + cuentas limitadas** (Kaunitz et al.) — el ROI% puede no
   escalar en €; es una restricción del negocio, no del modelo. Documentar límites observados.
4. **Régimen no estacionario** (mercados aprenden) — rolling evaluation + G4 prospectivo.
5. **Datos sucios en ligas menores** (walkovers, cambios de nombre, partidos reprogramados) —
   validadores de integridad en el pipeline de dataset antes que cualquier modelo.

## 11. Roadmap

| Fase | Entregable | Estimación |
|---|---|---|
| 0. Archivado (¡ya!) | Snapshots diarios + cuota de cierre por evento en todos los libros; job en VPS | días |
| 1. Literatura | Fichas en `research/lit/` de las ~20 referencias §2 | 1-2 semanas, paralelizable |
| 2. Dataset | Builder as-of + auditoría anti-leakage + catálogo features (G1) | 2-4 semanas |
| 3. Modelos | Torneo de modelos bajo protocolo §6 (G2) | 2-3 semanas |
| 4. Validación | Rolling + backtest económico + reporte (G3) | 1-2 semanas |
| 5. Paper trading | 8+ semanas prospectivas (G4) | calendario |
| 6. Operación | Job diario + alertas | 1 semana |
