# Modelos probabilísticos jerárquicos para fútbol de ligas menores nórdicas: teoría, estimación y evaluación walk-forward

**EXP-003 + EXP-003a** · BetBot Research · 2026-07-21
**Datos**: 4.941 partidos, 17 ligas, 3 países (FIN/SWE/NOR), abr-2025 → 20-jul-2026.
**Protocolo**: `research/PROTOCOLO_INVESTIGACION.md` · experimentos previos: EXP-001 (escalera, Finlandia), EXP-002 (multi-país + momentum).

---

## Resumen

Formalizamos la familia completa de modelos usados en el programa (tasa base, logística multinomial, histograma binneado, Poisson de fuerzas, Dixon-Coles, recalibración apilada, ratings dinámicos tipo Elo y el jerárquico multi-nivel), con sus postulados, ecuaciones, límites paramétricos y propiedades de estimación. Evaluamos todo bajo walk-forward semanal estricto en 2026 (1.619 partidos nunca vistos). Resultados principales: (i) el Dixon-Coles por liga con recalibración obtiene el menor RPS global (0.2132); (ii) el jerárquico multi-división es peor en agregado (Δ=+0.0055, IC95 i.i.d. [+0.0018, +0.0094]), aunque obtiene menor RPS en el cluster de ligas con datos escasos (C1: 0.1966 vs 0.1995); (iii) la "anomalía M1" de EXP-001/002 no se distingue de cero en el análisis pareado actual (IC i.i.d. [−0.0113, +0.0311], n=90), y coincide con un cambio descriptivo de localía entre temporadas (0.52 a 0.39); (iv) el análisis de sensibilidad muestra una meseta amplia alrededor de (half-life 120 días, σ=0.75). Los intervalos son provisionales porque el bootstrap implementado remuestrea partidos, no bloques temporales.

---

## 1. Introducción

El objetivo del programa es producir probabilidades pre-partido calibradas $(p_H, p_D, p_A)$ — y, derivadas de la distribución de marcadores, probabilidades de over/under y BTTS — para ligas menores nórdicas, de modo de compararlas luego contra las probabilidades implícitas del mercado (fase bloqueada por el archivado de cuotas, Fase 0). Escribimos $Y\in\{H,D,A\}$ para victoria local, empate y victoria visitante, y $y_r=\mathbf 1(Y=r)$.

La métrica primaria es el **Ranked Probability Score** (RPS), apropiada cuando las clases tienen el orden $H-D-A$:

$$\mathrm{RPS}(p,y)=\frac{1}{2}\sum_{k=1}^{2}\left(\sum_{r=1}^{k}p_r-\sum_{r=1}^{k}y_r\right)^2.$$

Como métricas secundarias usamos: (i) **log-loss**, $-\log p_Y$, que penaliza con especial severidad asignar probabilidad casi nula al resultado ocurrido; (ii) **Brier multiclase**, $\sum_r(p_r-y_r)^2$, una distancia cuadrática entre el vector pronosticado y el observado; y (iii) **Expected Calibration Error** para victoria local,

$$\mathrm{ECE}_H=\sum_{b=1}^{B}\frac{n_b}{n}\,\left|\overline p_{H,b}-\overline y_{H,b}\right|,$$

donde los partidos se separan aquí en ocho bins por cuantiles de $p_H$. RPS, log-loss y Brier son *proper scoring rules*: en esperanza se optimizan declarando la distribución predictiva verdadera. El ECE no lo es, depende del binneado y sólo resume calibración marginal de $H$; por eso se interpreta junto con la curva de calibración, no como criterio único. Ninguna decisión se toma sobre *accuracy*, que descarta toda la información contenida en las probabilidades no máximas.

Todos los experimentos usan el mismo protocolo: *walk-forward* semanal (cada lunes se reajusta con todo lo anterior y se predice la semana), variables congeladas al instante del partido (anti-leakage por construcción), hiperparámetros elegidos exclusivamente con 2025, y 2026 como conjunto de evaluación puro. Los intervalos actualmente reportados se obtuvieron con un bootstrap pareado de partidos (4.000 réplicas). Este remuestreo conserva la comparación partido a partido entre modelos, pero supone independencia entre partidos; no preserva correlaciones dentro de una semana, liga o equipo. Por tanto, los intervalos y las probabilidades bootstrap deben considerarse provisionales hasta repetir el análisis con bloques temporales (idealmente semana × liga) o un procedimiento equivalente para datos dependientes.

### 1.1 Datos

| País | Ligas | Partidos | Fuente |
|---|---|---|---|
| Finlandia | VL, M1L, M1, M2 (4 lohkos), NL | 1.394 | Palloliitto API |
| Suecia | SW-AL, SW-SE, SW-EN, SW-ES, SW-DA, SW-EE | 1.920 | svenskfotboll.se |
| Noruega | NO-ELI, NO-OBOS, NO-PN1, NO-PN2, NO-TS, NO-1DK | 1.627 | fotball.no |

Incluyen 1ª a 4ª división masculina y 1ª-2ª femenina. El pipeline es agnóstico al país (los ids de temporada están mapeados en `build_dataset_nordics.py`); Rumania y Eslovaquia quedan planificadas con los extractores ya existentes.

---

## 2. Modelos

Cada subsección sigue el mismo esquema: **qué postula**, **qué predice**, **ecuaciones**, **estimación** (¿solución exacta?), y **límites** (comportamiento cuando los parámetros tienden a 0 o ∞).

### 2.1 B0 — Tasa base por liga

**Postulado**: el resultado de un partido es intercambiable dentro de su liga; ninguna información de los equipos importa.

$$P(Y=r \mid \text{liga } \ell) = \pi_{r\ell}, \qquad r \in \{H, D, A\}$$

**Estimación**: el MLE multinomial tiene **solución exacta en forma cerrada**: $\hat\pi_{r\ell} = n_{r\ell}/n_\ell$ (frecuencias observadas).

**Límites**: con $n_\ell \to \infty$ converge a las tasas verdaderas de la liga; con $n_\ell$ chico hereda toda la varianza muestral (por eso el fallback jerarquiza liga→global). Es el **piso** de la escalera: cualquier modelo que no lo supere no extrae información de los equipos.

### 2.2 G0 — Logística multinomial sobre Δppg

**Variable de entrada.** En fútbol una victoria vale 3 puntos, un empate 1 y una derrota 0. Para cada equipo calculamos, usando sólo sus partidos anteriores de la misma temporada, liga y grupo, $\mathrm{ppg}=\text{puntos acumulados}/\text{partidos jugados}$. La única entrada del modelo es

$$x=\Delta\mathrm{ppg}=\mathrm{ppg}_H-\mathrm{ppg}_A.$$

Así, $x>0$ significa que el local llega con mayor rendimiento de tabla. Si alguno de los equipos todavía no jugó un partido, $x$ no está definido y la implementación vuelve a la tasa base de la liga.

**Postulado.** G0 es una regresión logística multinomial (*softmax*), un modelo lineal generalizado estándar y no una ley específica del fútbol. Escogiendo $A$ como clase de referencia, se escribe de forma identificable como

$$\log\frac{P(Y=H\mid x)}{P(Y=A\mid x)}=\alpha_H+\beta_Hx,\qquad
\log\frac{P(Y=D\mid x)}{P(Y=A\mid x)}=\alpha_D+\beta_Dx.$$

$$P(Y=r \mid x) = \frac{e^{\alpha_r + \beta_r x}}{\sum_{s} e^{\alpha_s + \beta_s x}}$$

con la convención $\alpha_A=\beta_A=0$. Decimos que es **lineal** porque cada *log-odds* contra la clase de referencia es una recta en $x$; las probabilidades mismas son curvas no lineales por la transformación softmax.

**Parámetros libres e interpretación.** Quedan cuatro: dos interceptos $(\alpha_H,\alpha_D)$, que fijan las odds H/A y D/A cuando ambos equipos tienen el mismo PPG, y dos pendientes $(\beta_H,\beta_D)$, que miden cómo cambian esas log-odds por cada punto adicional de $\Delta\mathrm{ppg}$. La implementación ajusta un único conjunto global a todas las ligas; no hay interceptos ni pendientes específicos por liga. `scikit-learn` usa otra parametrización simétrica y regularizada por defecto, pero representa la misma familia de probabilidades; por ello “cuatro libres” describe el modelo identificable sin penalización, no literalmente el número de coeficientes almacenados por la librería.

**Estimación.** La log-verosimilitud multinomial es cóncava. Sin separación completa, y fijada una referencia, el óptimo es único; no tiene forma cerrada y se obtiene numéricamente. En el código se usa `LogisticRegression` con su penalización L2 por defecto. Esa regularización debe declararse porque cambia el estimador respecto del MLE multinomial puro descrito por las ecuaciones.

**Límites.** Si ambas pendientes valen cero, la predicción deja de depender de $x$ y se reduce a una tasa global constante (no exactamente B0, que en esta implementación tiene tasas distintas por liga). Cuando las diferencias entre pendientes crecen sin cota, el softmax se aproxima a regiones de decisión deterministas; las fronteras dependen también de los interceptos y no tienen por qué estar en $x=0$. La linealidad en log-odds es su restricción estructural. Aun así, $P(D\mid x)$ puede tener un máximo interior si su recta domina cerca de $x=0$ y las rectas H/A dominan en los extremos; lo que el modelo no puede representar son formas más complejas que las inducidas por tres rectas.

### 2.3 G0b — Histograma binneado sobre Δposición (modelo del director)

**Variable de entrada.** Antes de cada partido se reconstruye la tabla usando puntos, diferencia de goles y goles a favor como desempates. Si $\mathrm{pos}=1$ denota el primer puesto y $N$ el número de equipos del grupo, definimos

$$z=-\frac{\mathrm{pos}_H-\mathrm{pos}_A}{N}=\frac{\mathrm{pos}_A-\mathrm{pos}_H}{N}.$$

Por tanto, $z>0$ significa que el local está mejor posicionado. La normalización por $N$ hace comparables, aproximadamente, grupos de tamaños distintos. La predicción no se emite desde esta variable hasta que ambos equipos tienen al menos cuatro partidos; antes se usa la tasa base de la liga.

**Modelo.** El intervalo $[-1,1]$ se divide en $B=9$ subintervalos fijos $I_b=[e_b,e_{b+1})$. Dentro de cada uno la distribución 1X2 se supone constante:

$$\widehat P(Y=r\mid z\in I_b)=\widehat\pi_{rb}
=\frac{n_{rb}}{n_b},\qquad
n_{rb}=\sum_{i\in\mathcal T}\mathbf 1(z_i\in I_b,Y_i=r),\quad
n_b=\sum_r n_{rb},$$

donde $\mathcal T$ contiene únicamente partidos anteriores al corte walk-forward. En palabras: para predecir un partido, se calcula su diferencia normalizada de posición, se localiza el bin correspondiente y se devuelven las frecuencias históricas de H/D/A observadas en ese bin. Los conteos se agrupan entre ligas. Si el bin tiene menos de 15 partidos, la implementación usa el bin válido cuyo centro sea más cercano; si no hay ninguno, vuelve a la tasa base de la liga.

**Estimación.** Condicionalmente a los bins, $\widehat\pi_{rb}=n_{rb}/n_b$ es el MLE multinomial por conteo. No hay optimización numérica ni parámetros compartidos entre bins: son $2B=18$ probabilidades libres (la tercera de cada bin queda fijada porque suman uno), aunque los fallbacks hacen que el predictor implementado no sea simplemente ese modelo saturado.

**Límites.** Con $B=1$ se obtiene una tasa global agrupada, no la tasa base específica por liga. Al aumentar $B$ baja el sesgo de discretización pero crecen la varianza y la frecuencia de fallbacks; con muestras finitas, el límite $B\to\infty$ no define un estimador útil. La elección $B=9$ y el umbral 15 son hiperparámetros heurísticos del modelo del director: no se justifican aquí mediante una selección anidada, por lo que no corresponde presentar $9$ como un óptimo teórico. **Relación con G0:** ambos regresan el resultado sobre un resumen unidimensional de la tabla, pero no usan la misma variable ($\Delta$posición frente a $\Delta$PPG). G0 impone log-odds lineales y comparte cuatro parámetros; G0b permite saltos y usa muchos más parámetros locales. Empíricamente empatan (Δ=−0.0009, IC [−0.0053,+0.0034], intervalo provisional bajo bootstrap i.i.d.) y G0b muestra peor calibración marginal de H (ECE 0.042 vs 0.027).

### 2.4 M1 — Poisson independiente de fuerzas (Maher 1982) con shrinkage

**Postulados**: (i) los goles de cada equipo en un partido son Poisson **independientes**; (ii) la intensidad factoriza multiplicativamente en ataque propio × defensa rival × localía:

$$G_H \sim \mathrm{Poisson}(\lambda_H), \quad G_A \sim \mathrm{Poisson}(\lambda_A)$$
$$\log\lambda_H = \mu + \gamma + \mathrm{atk}_h - \mathrm{def}_a, \qquad \log\lambda_A = \mu + \mathrm{atk}_a - \mathrm{def}_h$$

Aquí $\lambda_H=E[G_H\mid h,a]$ y $\lambda_A=E[G_A\mid h,a]$ son los goles esperados de local y visitante. Cada término es aditivo en escala logarítmica y, por tanto, multiplicativo en la escala de goles:

$$\lambda_H=e^\mu e^\gamma e^{\mathrm{atk}_h}e^{-\mathrm{def}_a},\qquad
\lambda_A=e^\mu e^{\mathrm{atk}_a}e^{-\mathrm{def}_h}.$$

- $\mu$ es el nivel basal de goles por equipo y partido en la muestra de ajuste.
- $\gamma$ es la ventaja de local común a la liga; $e^\gamma$ multiplica sólo la intensidad local.
- $\mathrm{atk}_i$ es la fuerza ofensiva latente del equipo $i$: valores positivos elevan sus goles esperados.
- $\mathrm{def}_i$ es la fortaleza defensiva latente bajo esta convención de signos: valores positivos reducen los goles esperados del rival porque aparece con signo menos.

Con $T$ equipos se ajustan nominalmente $2T+2$ cantidades ($\mu,\gamma$ y un ataque y una defensa por equipo). No se ajusta un $\lambda$ libre para cada partido: cada par $(\lambda_H,\lambda_A)$ se calcula a partir de esos parámetros compartidos. Para un equipo nunca observado, la implementación usa ataque y defensa cero, es decir, el prior de “equipo promedio”.

De la matriz de marcadores $P(G_H=i, G_A=j) = p_i(\lambda_H)\, p_j(\lambda_A)$ (evaluada para 0–10 goles y renormalizada) se derivan **todas** las cuotas de interés: 1X2 (sumas por triángulos), over/under (anti-diagonales), BTTS ($i,j \ge 1$), goles por equipo — una sola pieza coherente, ventaja estructural sobre modelar cada mercado por separado.

**Identificabilidad.** Sin restricciones, varias traslaciones de los efectos de equipo dejan invariantes las intensidades; por ejemplo, sumar la misma constante a todos los ataques y defensas deja invariantes las diferencias $\mathrm{atk}-\mathrm{def}$. También pueden intercambiarse offsets globales con $\mu$. Por ello los niveles absolutos de ataque y defensa no son observables: sólo importan ciertas combinaciones. Lo resolvemos en la estimación con el prior/penalización ridge

$$-\frac{1}{2\sigma^2}\sum_i (\mathrm{atk}_i^2 + \mathrm{def}_i^2)$$

que equivale a priors independientes $\mathcal{N}(0,\sigma^2)$ y a una estimación MAP. La penalización selecciona la representación centrada de menor norma y encoge los efectos hacia cero, que aquí representa al equipo promedio de la muestra de ajuste. No es un modelo bayesiano completo: $\sigma$ se fija externamente y no se integra la incertidumbre posterior.

**Estimación.** Para $\rho=0$, la log-verosimilitud Poisson penalizada es cóncava en los predictores lineales y la penalización elimina las direcciones planas de los efectos de equipo; no hay solución cerrada. La implementación usa L-BFGS-B con gradiente numérico y cotas sobre todos los parámetros. Por ello debe comprobarse y reportarse `converged`; las cotas también pueden producir soluciones de frontera. Cuando se ajusta $\rho$ (M2), la corrección de Dixon-Coles modifica esta geometría y no se invoca aquí una garantía global de unicidad.

**Límites.** Cuando $\sigma\to0$, todos los efectos de equipo se anulan y quedan sólo el nivel medio y la localía. Cuando $\sigma\to\infty$, desaparece el shrinkage y los equipos con poca historia pueden adquirir efectos extremos. La curva normal-normal $\kappa(n)=n\sigma^2/(n\sigma^2+s^2)$ de la Fig. 8 es una analogía didáctica unidimensional, no el factor exacto de shrinkage de esta regresión Poisson acoplada: aquí la información depende además de rivales, localía, pesos temporales y conectividad del calendario. La optimización acota cada parámetro individual en $[-3,3]$ (y $\gamma$ en $[-1.5,1.5]$); esto no equivale a imponer $|\log\lambda|\le3$, porque $\log\lambda$ es una suma de varios parámetros. La matriz de marcadores se evalúa para 0–10 goles por equipo y luego se renormaliza; conviene verificar que la masa truncada sea despreciable para las intensidades obtenidas.

### 2.5 M2 — Dixon-Coles: dependencia en marcadores bajos + decaimiento temporal

Dos correcciones al postulado de independencia y estaticidad de Maher:

**(a) Corrección τ de marcadores bajos.** La independencia falla empíricamente en {0-0, 1-0, 0-1, 1-1}. DC multiplica esas cuatro celdas por

$$\tau(i,j) = \begin{cases} 1 - \lambda_H\lambda_A\rho & (0,0) \\ 1 + \lambda_A\rho & (1,0) \\ 1 + \lambda_H\rho & (0,1) \\ 1 - \rho & (1,1) \end{cases}$$

y renormaliza. **Rango válido**: $\tau > 0$ exige $\rho \in (\max(-1/\lambda_H, -1/\lambda_A),\ \min(1/(\lambda_H\lambda_A), 1))$. **Límite** $\rho \to 0$: recupera independencia exactamente. $\rho < 0$ (lo ajustado: −0.01 a −0.07 según país) **sube** la probabilidad de 0-0 y 1-1 → más empates. La sensibilidad exacta $P(D)$ vs $\rho$ está en la Fig. 7: el efecto es lineal y modesto (±0.01 de probabilidad de empate en el rango ajustado) — consistente con su aporte marginal al RPS (−0.0001 en EXP-001).

**(b) Decaimiento temporal.** Las fuerzas cambian; DC lo aproxima ponderando la verosimilitud del partido $m$ jugado $\Delta t_m$ días antes del ajuste:

$$w_m = 2^{-\Delta t_m / H} \iff w_m = e^{-\xi \Delta t_m},\ \xi = \ln 2 / H$$

**Límites**: $H \to \infty$ ($\xi\to0$): modelo estático (toda la historia pesa igual). $H \to 0$: solo cuenta el último partido → varianza infinita. El óptimo empírico $H \approx 120$ días (media temporada nórdica) es una **meseta ancha**, no un pico (Fig. 6): el modelo no es frágil a esta elección.

**Conexión dinámica.** El kernel exponencial introduce una escala de memoria, pero no es exactamente un filtro de Kalman ni convierte al ajuste estático en un modelo de estado. Una caminata aleatoria $\theta_t=\theta_{t-1}+\eta_t$ ni siquiera posee distribución estacionaria; un proceso de Ornstein–Uhlenbeck, $d\theta=-\theta\,dt/\tau+\sigma_\eta dW$, sí tiene reversión a la media y una memoria exponencial en su autocorrelación. El decaimiento usado aquí puede verse como una aproximación heurística a esa idea. Para afirmar equivalencia habría que especificar la ecuación de observación, las varianzas de proceso y medida y derivar el filtro resultante.

### 2.6 M3 — Recalibración apilada (stack_cal)

**Postulado**: las probabilidades del DC son *casi* correctas; existe una corrección logística global de bajo rango.

$$z = \left(\log\frac{p_H}{p_A},\ \log\frac{p_D}{p_A}\right), \qquad P(Y=r\mid z) = \mathrm{softmax}(\alpha_r + \beta_r^\top z)$$

entrenada **solo con predicciones out-of-sample previas** del propio DC (sin leakage del meta-nivel). **Límite**: $\beta = I,\ \alpha = 0$ es la identidad — el modelo puede aprender a *no* corregir; que aprenda otra cosa es evidencia de miscalibración sistemática del base. Resultado: mejora log-loss con p≈0.998 (corrige la sobre-estimación de empates en cola alta), nunca empeora RPS. Es además el módulo donde naturalmente entrará la probabilidad implícita del mercado como *benchmark* (nunca como feature del detector).

### 2.7 Ratings dinámicos (Elo) y features de forma — por qué quedaron fuera

El rating Elo es el mapa estocástico

$$x_{t+1} = x_t + K\,(S_t - E(x_t)), \qquad E(x) = \frac{1}{1+10^{-x/400}}$$

**Como sistema dinámico** (Fig. 9): el mapa determinista asociado tiene punto fijo $x^* = 400\log_{10}\frac{p^*}{1-p^*}$; su estabilidad depende de $|1 - K E'(x^*)| < 1$. Para $K$ práctico (8–32) el sistema es un rastreador sobreamortiguado (convergencia monótona, sin caos); al crecer $K$ el mapa discreto bifurca a oscilaciones y aperiodicidad tipo mapa logístico — puramente académico: está a dos órdenes de magnitud del rango operativo. El **límite continuo** es la EDO $\dot x = K(p^* - E(x))$, monótona y unidimensional → sin caos posible. $K\to0$: no aprende; $K\to\infty$: memoria de un partido (el análogo exacto de $H\to0$ en DC).

**Resultado empírico (EXP-002)**: las features derivadas (Elo, pendiente de rating, sobre-rendimiento vs expectativa, SoS, PPG contra rivales más fuertes) predicen fuertemente en univariado (28%→59% de victoria local entre quintiles extremos) pero su aporte **sobre** DC es nulo (Δ=+0.0001, IC [−0.0021,+0.0022]): la verosimilitud ponderada en el tiempo del DC *ya es* forma ajustada por rival. Se descartan como aditivos lineales (protocolo §3.5).

### 2.8 M4 — Jerárquico multi-nivel (MAP empírico-Bayes)

**Postulados**: (i) los equipos de un país viven en **una única escala de habilidad** (el mismo `team_id` en divisiones distintas es el mismo equipo → un ascendido conserva su historia); (ii) los interceptos de entorno (nivel de goles, localía) varían por liga y cluster alrededor de medias comunes:

$$\log\lambda_H = \mu_0 + m_{c(\ell)} + \delta_\ell + \big(\gamma_0 + g_{c(\ell)} + g_\ell\big) + \mathrm{atk}_h - \mathrm{def}_a$$
$$m_c \sim \mathcal{N}(0, \tau_c^2), \quad \delta_\ell \sim \mathcal{N}(0, \tau_\ell^2), \quad \mathrm{atk}_i, \mathrm{def}_i \sim \mathcal{N}(0, \sigma^2)$$

Computamos el **MAP** (verosimilitud penalizada, gradiente analítico, un solo ajuste conjunto de ~520 parámetros por semana, 0.1 s) en lugar del posterior completo por MCMC — la aproximación empírico-Bayes estándar cuando el posterior es log-cóncavo y unimodal, como aquí. ρ se fija en 0 (aporte marginal medido en EXP-001/002).

**Límites** (la mecánica del pooling): $\tau_\ell \to 0$: pooling completo — todas las ligas comparten intercepto (una "superliga" por país); $\tau_\ell \to \infty$: sin pooling — equivale a interceptos libres por liga. Ídem $\tau_c$ para clusters. El caso $\sigma$ es el de §2.4. El grid 2025 eligió $\tau_\ell = 0.15$ con meseta hacia 0.5 (RPS 0.1988 vs 0.1992 en 0.05): los datos piden pooling *intermedio*, como manda James-Stein.

**Límite estructural (el que resultó decisivo)**: los grafos de partidos de dos divisiones solo se conectan por los equipos que cambian de división (55 en 2026). La habilidad relativa *entre* divisiones está identificada únicamente por esos pocos enlaces → si el nivel medio de los jugadores difiere entre divisiones (lo hace), la habilidad transferida llega **sesgada**. La sección §5.3 lo cuantifica.

---

## 3. Clustering de ligas

Descriptores por liga computados **solo con 2025** (la asignación queda congelada antes de tocar 2026): media de goles, tasa de empates, ventaja localía ($P(H)-P(A)$), tasa over 2.5, desvío del diferencial. Ward sobre z-scores; $k$ por silhouette.

![Dendrograma](fig/dendrogram.png)
*Fig. 1 — Dendrograma de Ward sobre los 5 descriptores estandarizados (17 ligas, datos 2025). El corte óptimo por silhouette (0.458) da k=2: C1 = {M2 Kakkonen, NL femenina finlandesa} — el par extremo en goles (4.3 y 3.8 por partido) y escasez de empates (12-13%) — y C2 = las 15 restantes. Valores de silhouette para k=3..6 caen a 0.23-0.27: los datos NO soportan la partición fina que hipotetizaba el protocolo.*

![Clusters en el plano goles-empates](fig/cluster_scatter.png)
*Fig. 2 — Las 17 ligas en el plano (goles/partido, tasa de empates) de 2025, coloreadas por cluster. Se ve el continuo — de Superettan/Allsvenskan (2.9 goles, 22-27% empates) a Kakkonen (4.3, 12%) — más que grupos discretos: la estructura es un gradiente goles↔empates (correlación negativa esperable: más goles ⇒ menos 0-0/1-1), con C1 como extremo, no como isla.*

**Lectura**: la hipótesis del director ("Kakkonen ≈ 3. divisjon ≈ deild islandesas") se sostiene *direccionalmente* — las ligas bajas y femeninas se corren al extremo goleador — pero con 17 ligas la evidencia solo permite una partición gruesa. El nivel cluster del jerárquico se implementó con esta C1/C2.

---

## 4. Diseño experimental

- **Walk-forward semanal** idéntico a EXP-001/002; test 2026: 1.619 partidos.
- **Hiperparámetros**: DC congelado de EXP-001 (H=120, σ=0.75, ρ ajustado) con transferencia verificada en SWE+NOR 2025 (0.1950 vs 0.1956 sin decaimiento); jerárquico: $\tau_\ell$ por grid 2025 (§2.8), $\tau_c = 0.25$, $\sigma = 0.75$ heredado.
- **Comparaciones**: bootstrap pareado i.i.d. (4.000 réplicas) sobre el RPS por partido, conjunto común de partidos. Es útil como análisis preliminar, pero no respeta dependencia temporal ni la inducida por equipos compartidos; antes de publicación deben recalcularse los IC con bloques semana × liga y contrastarse su sensibilidad a la elección del bloque. Los desgloses por liga individual se reportan como descriptivos (n = 64-135; sin corrección B-H no se les atribuye significancia).

## 5. Resultados

### 5.1 Comparación global

![Comparación de modelos EXP-003](fig/hier_comparison.png)
*Fig. 3 — RPS medio en 2026 (punto) con IC 95% bootstrap (barra), 1.619 partidos comunes, ordenado de peor a mejor. Los dos jerárquicos (azul, amarillo) quedan entre la tasa base y el DC por liga: el pooling multi-división NO mejoró al modelo que trata cada liga como universo aparte. stack_cal (rosa) mantiene el primer lugar de EXP-002.*

| Modelo | RPS | log-loss | ΔRPS vs DC (IC 95%) | P(mejor que DC) |
|---|---|---|---|---|
| stack_cal | **0.2132** | **0.9940** | −0.0007 (−0.0015, +0.0001) | 0.96 |
| dc_best (por liga) | 0.2139 | 1.0007 | — | — |
| jer_pais | 0.2194 | 1.0128 | **+0.0055 (+0.0018, +0.0094)** | 0.002 |
| jer_cluster | 0.2195 | 1.0132 | +0.0057 (+0.0020, +0.0095) | 0.002 |
| b0_base_rate | 0.2377 | 1.0633 | +0.0238 | 0.000 |

El nivel de cluster no cambia nada (jer_pais ≈ jer_cluster, Δ=0.0001): coherente con que los interceptos de liga ya están bien estimados con 100+ partidos cada uno — el pooling de *hiperparámetros* solo paga cuando la unidad es pobre en datos, que no es el caso de los interceptos. Los parámetros pobres son las habilidades de equipos, y esas **no pueden** poolearse entre países (grafos disjuntos).

### 5.2 Reporte por cluster

| Modelo | RPS C1 (n=247) | RPS C2 (n=1.372) |
|---|---|---|
| jer_pais | **0.1966** | 0.2235 |
| jer_cluster | 0.1976 | 0.2235 |
| dc_best | 0.1995 | 0.2164 |
| stack_cal | 0.1999 | **0.2155** |
| b0_base_rate | 0.2423 | 0.2369 |

**El resultado más instructivo del experimento**: el jerárquico obtiene menor RPS en C1 — Kakkonen (4 lohkos de ~10 equipos, la unidad más pobre en datos del dataset) y NL (8 equipos) — y mayor RPS en C2. El patrón es compatible con la hipótesis de que compartir fuerza estadística ayuda donde cada unidad tiene pocos datos y perjudica donde el sesgo de transferencia domina (§5.3), pero el análisis de subgrupo no fue pre-registrado y no se presenta un IC específico para la diferencia en C1. En C2, el IC i.i.d. de stack_cal frente a DC excluye 0 (−0.0009, [−0.0017, −0.0001]); falta comprobarlo con bloques.

### 5.3 El mecanismo del fracaso: transferencia sesgada entre divisiones

![Segmento movers](fig/movers_segment.png)
*Fig. 4 — RPS 2026 según el partido involucre (naranja) o no (gris) al menos un equipo que cambió de división entre 2025 y 2026 (55 equipos, 763 partidos). Para DC y stack_cal los partidos con "movers" son incluso más fáciles (el prior "equipo promedio de la liga" resulta empíricamente correcto para ascendidos). Para los jerárquicos son mucho más difíciles (0.225 vs 0.214): la historia de la división anterior transfiere una habilidad sobre-estimada — un dominador de Kakkonen no es un equipo fuerte de Ykkönen, pero el modelo de escala única cree que sí. Δ(jer−DC) en movers = +0.0127, IC 95% [+0.0047, +0.0207].*

El postulado (i) de §2.8 — escala de habilidad única entre divisiones — es el que falla. Los interceptos $\delta_\ell$ absorben diferencias de *entorno de goles* pero no de *nivel medio de plantel*; con solo 55 enlaces, el MAP no puede separar ambas cosas y el prior hacia 0 (media país) infla a los equipos de divisiones bajas. Corrección candidata (EXP futuro): offset de habilidad por división ($\mathrm{atk}_i + a_{\ell}$) o re-centrado del prior de cada equipo a la media de su división de origen.

### 5.4 Diagnóstico M1 (EXP-003a): la anomalía era ruido — con un mecanismo real detrás

![Diagnóstico M1](fig/m1_diagnosis.png)
*Fig. 5 — Izquierda: Δ RPS de DC contra sus tres rivales, restringido a los 90 partidos de M1 2026, con IC 95% pareado; los tres intervalos cruzan el cero — la "derrota" de DC en M1 reportada descriptivamente en EXP-001/002 no es estadísticamente distinguible de ruido (P(DC mejor que G0)=0.20). Derecha: tasa de empates por liga finlandesa, 2025 (azul) vs 2026 (amarillo): M1 saltó de 0.19 a 0.24 y M2 de 0.12 a 0.20, mientras la localía de M1 colapsó de 0.52 a 0.39 (tabla en `m1_diagnosis.json`) — el entorno de la liga se movió entre temporadas.*

Conclusión del diagnóstico: (H2) **no se puede rechazar que sea fluctuación muestral** (n=90, y M1 es 1 de 17 ligas escaneadas — el problema clásico de comparaciones múltiples que el protocolo §6.2 anticipa). (H3) queda **refutada**: el jerárquico, que da historia a los ascendidos, es *peor* en M1 (Δ=+0.0120, IC [−0.0035,+0.0271]). (H1) sobrevive solo como mecanismo direccional: la caída de localía 0.52→0.39 y el salto de empates son un corrimiento de régimen real que castiga más a DC (que arrastra la localía 2025 con decaimiento de 120 días) que a G0 (que reestima su intercepto cada semana con datos frescos pooled). Acción: γ (localía) por liga-temporada con decaimiento más corto es una mejora candidata concreta.

### 5.5 Sensibilidad de hiperparámetros

![Curvas de nivel](fig/contour_hl_sigma.png)
*Fig. 6 — Curvas de nivel del RPS walk-forward 2025 (17 ligas, 2.351 partidos; ejes log) sobre el plano (half-life del decaimiento, σ del shrinkage). El ★ (mínimo del grid, RPS 0.1951) **coincide** con la configuración elegida en EXP-001 usando solo Finlandia (● rojo): la selección hecha con un tercio de los datos era ya el óptimo global del grid en el dataset triplicado. La superficie es una meseta — todo H ∈ [60, 480] × σ ∈ [0.5, 2.0] queda dentro de 0.001 del mínimo — con una única pared empinada hacia (H=30, σ=0.3), el rincón "memoria corta + prior rígido" (RPS 0.2054). El modelo no es frágil a sus hiperparámetros.*

![Sensibilidad a rho](fig/rho_draw_curve.png)
*Fig. 7 — P(empate) exacta (matriz de marcadores truncada en 10) como función de ρ para tres pares (λH, λA) representativos. El efecto es lineal y modesto: en el rango ajustado empíricamente (banda gris, ρ ∈ [−0.07, −0.01]) la probabilidad de empate se mueve menos de 0.01. Explica cuantitativamente por qué ρ aporta tan poco al RPS y por qué pudo omitirse del jerárquico sin costo.*

![Curva de shrinkage](fig/shrinkage_curve.png)
*Fig. 8 — Factor exacto de encogimiento normal-normal κ(n) = nσ²/(nσ²+s²): peso que reciben los datos de un equipo con n partidos frente al prior "equipo promedio". Con σ=0.75 (elegido), un equipo con 5 partidos toma ~81% de sus datos; con σ=0.25, solo 32%. Los límites σ→0 (todos iguales) y σ→∞ (MLE puro, línea gris) enmarcan la familia; la elección de σ es la elección de cuánta evidencia exige un equipo nuevo antes de despegarse de la media.*

![Dinámica de Elo](fig/elo_dynamics.png)
*Fig. 9 — Trayectorias del mapa determinista de Elo hacia su punto fijo x*=191 (p*=0.75) para K ∈ {8, 32, 256, 1600}. K prácticos (azul, verde): convergencia monótona sobreamortiguada — el sistema es un filtro estable, no caótico. K=256: sobreimpulso amortiguado. K=1600 (académico): el mapa discreto pierde estabilidad (|1−KE′(x*)|>1) y bifurca a oscilaciones aperiódicas tipo mapa logístico. La EDO límite ẋ = K(p*−E(x)) es monótona unidimensional: el caos es imposible en el continuo; en el rango operativo tampoco existe en el discreto.*

### 5.6 Sobre EDOs y dinámica del sistema — síntesis

Ningún modelo ajustado contiene EDOs deterministas explícitas. Hay tres construcciones relacionadas, pero no equivalentes: (1) el **kernel exponencial** de DC ($w=e^{-\xi\Delta t}$) descuenta observaciones antiguas sin especificar una ley de evolución latente; (2) bajo condiciones de aproximación estocástica, el valor esperado del mapa de Elo se puede estudiar mediante la EDO $\dot x=K(p^*-E(x))$; y (3) un modelo de estado para las fuerzas especificaría explícitamente una transición —por ejemplo, caminata aleatoria u Ornstein–Uhlenbeck— y una ecuación de observación Poisson, y aplicaría filtrado aproximado. Sólo el tercero permitiría estimar y propagar incertidumbre dinámica de manera coherente. Los cambios descriptivos entre temporadas de §5.4 motivan investigar esa extensión, pero no identifican por sí solos el proceso dinámico.

## 6. Análisis de resultados — decisiones que fija este experimento

1. **Candidato de producción**: DC por liga (H=120, σ=0.75, ρ) + recalibración OOS tiene el mejor desempeño agregado observado. Su adopción inferencial queda sujeta al bootstrap por bloques y su utilidad económica, a la comparación prospectiva con cuotas.
2. **Jerárquico como hipótesis para muestras pequeñas**: el resultado descriptivo de C1 motiva probar pooling intra-liga entre lohkos de M2. No demuestra que esa variante funcione, porque el modelo evaluado y el subgrupo seleccionado no constituyen ese experimento.
3. **Anomalía M1 no resuelta estadísticamente**: el intervalo actual cruza cero. El cambio de localía/empates sugiere probar localía por liga-temporada o dinámica, pero no establece el mecanismo causal.
4. **El clustering fino no tiene soporte** con 17 ligas (silhouette 0.24-0.27 para k≥3); mantener C1/C2 como estratos de *reporte* y re-evaluar cuando entren Rumania/Eslovaquia/Islandia.
5. **Empates**: sigue vigente el veto de EXP-002 (sobre-estimación en cola alta; ρ no alcanza a corregirla — Fig. 7 muestra que su palanca es demasiado corta). La recalibración es el camino, y con más datos, una corrección de empates dedicada.
6. **Generalizabilidad**: la meseta de la Fig. 6 y la evaluación FIN→SWE+NOR sin re-tuning son evidencia favorable, pero limitada a países, temporadas y ligas emparentados. La prueba relevante para apuestas sigue siendo prospectiva contra probabilidades de mercado archivadas (G4, *paper trading* — bloqueado por Fase 0).

## 7. Conclusiones

Sobre 4.941 partidos de 17 ligas nórdicas y una evaluación walk-forward de 1.619 partidos de 2026, el modelo Dixon-Coles por liga con recalibración out-of-sample obtiene el menor RPS (0.2132) y log-loss (0.9940) entre los modelos probados. El bootstrap por bloques confirma que DC mejora a G0 tanto en RPS como en log-loss. Para `stack_cal`, la mejora queda establecida en log-loss (bloques semanales: Δ=−0.0067, IC 95% [−0.0120,−0.0009]), pero no en RPS (Δ=−0.0007, [−0.0014,+0.0001]); son dos afirmaciones distintas. Las features de momentum y el pooling jerárquico multi-división no mejoran el resultado agregado. Los análisis de mecanismo sugieren dos explicaciones que deben tratarse como hipótesis y no como demostraciones causales: el decaimiento temporal podría absorber parte de la señal de forma, y una escala de habilidad común podría transferir mal a los equipos que cambian de división. El menor RPS del jerárquico en C1 (−0.003 frente a DC) es consistente con una ventaja del pooling en muestras pequeñas, pero requiere un contraste prospectivo de subgrupo. La meseta de hiperparámetros es evidencia de estabilidad dentro del grid estudiado, no una prueba general de ausencia de sobreajuste.

**Próximos pasos, en orden de valor esperado**: (1) **Fase 0 — archivado de cuotas** (sin esto no hay EV/ROI/CLV: el programa entero espera ese dato); (2) localía dinámica por liga-temporada (mecanismo M1); (3) jerárquico intra-liga para lohkos; (4) targets O/U y BTTS desde la matriz de marcadores ya emitida; (5) dataset Rumania/Eslovaquia/Islandia; (6) filtro de Kalman sobre fuerzas si (2) confirma la no-estacionariedad.

## Adenda v2 — Respuesta a la revisión mayor (EXP-004, 2026-07-21)

El referee (el director) dictaminó revisión mayor con 15 observaciones. Las
computables se ejecutaron en `research/experiments/EXP-004-referee/`; resumen de
qué cambió y qué sobrevivió:

| # Referee | Acción | Resultado |
|---|---|---|
| §3 dependencia en los IC | Bootstrap por bloques: iid / semana / semana×liga / móviles de 4 semanas (`block_bootstrap.csv`) para RPS **y log-loss** | **dc−g0 sobrevive en los 4 esquemas y en ambas métricas**. En RPS, el peor caso es [−0.0151,−0.0025]. `stack_cal−dc` no queda establecido en RPS (semana: Δ=−0.0007, [−0.0014,+0.0001]), pero **sí en log-loss** bajo los cuatro esquemas (semana: Δ=−0.0067, [−0.0120,−0.0009]). `jer−dc` es peor de forma robusta en RPS; en log-loss dos de cuatro intervalos rozan o cruzan cero. El pareo explica parte del poco ensanchamiento: los shocks comunes de semana se cancelan en la diferencia. |
| §6 ¿Poisson describe los goles? | Replay OOS de λ (1.619 partidos) + diagnósticos reproducibles (`poisson_diagnostics.json`, EXP-004.2) | **Sobredispersión condicional**: media de residuos de Pearson al cuadrado H=1.275 (IC semanal [1.172,1.386]), A=1.136 ([1.043,1.240]); ambas excluyen 1. El 0-0 está **sobre-predicho** (obs 4.45% vs 5.58% con ρ; ρ<0 empuja en la dirección equivocada en 2026). Correlación residual H-A = −0.024, compatible descriptivamente con dependencia lineal pequeña, aunque no prueba independencia. Masa truncada media por cola marginal ≈1.31·10⁻⁴. Binomial negativa registrada como EXP-006 candidato (H5 de EXP-005). |
| §12 calibración en profundidad | ECE/pendiente/intercepto/descomposición de Murphy para H, D y A; confiabilidad con IC por bin (`calibration_deep.json`, fig `reliability_3class.png`) | La patología está localizada: **pendiente de calibración del empate = 0.37** en DC (resolución 0.002 vs incertidumbre 0.168 — el modelo casi no puede distinguir empates y aún así exagera); stack_cal la sube a 0.68 y el ECE(D) baja 0.029→0.021. H y A: sobreconfianza leve (0.80/0.71 → 0.90/0.83). Esto muestra directamente de dónde venía la mejora de log-loss de stack_cal. |
| §11 factorial G0 | Matriz 2×2 {Δppg, Δpos} × {logística, histograma} con fallbacks unificados (`factorial.json`) | **Las cuatro celdas son estadísticamente equivalentes** (RPS 0.2225-0.2253; los 4 contrastes cruzan 0). Ni la variable ni la forma funcional explican diferencias: todos son el mismo baseline de tabla. |
| §15.10 ablaciones | DC completo vs −decay, −shrinkage, −ρ, −localía en 2025 (dev), IC por bloques (`ablations.json`) | Único componente individualmente significativo: **la localía** (Δ+0.0045, IC [+0.0014,+0.0078]). Decay +0.0007 y shrinkage +0.0004 direccionales no significativos; **ρ = 0.0000 de aporte** (−0.0002, ns) — coherente con el diagnóstico del 0-0. El valor del DC está en la estructura ataque/defensa + localía; los refinamientos son marginales. |
| §7-§8 incertidumbre paramétrica | Laplace ilustrativa en VL: Hessiano→Σ, sd por equipo vs partidos efectivos, predictiva integrada vs plug-in (`laplace.json`, fig `laplace_sd_vs_n.png`) | La dispersión del sd a n efectivo semejante muestra que n no determina por sí solo la información. Dos ejemplos in-sample cambian poco al integrar parámetros (max p: 0.619→0.618 y 0.572→0.569), pero **no** permiten concluir que el plug-in sea globalmente adecuado ni explicar la sobreconfianza de colas. Falta validar la Hessiana, respetar las cotas y evaluar predictivas OOS en muchos partidos. |
| §5, §13 el test 2026 gastado / post hoc | Registro EXP-005 (`EXP-005-prospectivo/REGISTERED.md`) y enmienda cronológica `AMENDMENT-001.md` | El commit del registro es del 23-jul, por lo que la ventana confirmatoria válida comienza el lunes **2026-07-27**, no el 22-jul. Los partidos del 22–26 quedan fuera o son exploratorios. H1–H5 y la regla de una sola pasada se mantienen. |
| §4 comparación contra mercado | No computable sin cuotas archivadas | Sigue bloqueada por Fase 0; se pre-registrará por separado (CLV y log-loss vs probabilidad implícita sin margen). Las afirmaciones del paper se re-alcance: capacidad predictiva deportiva, no edge. |
| §9 localía rígida | Aceptada como H4 condicional en EXP-005 (`dc_dyn_gamma` si se implementa antes del 2026-08-01 sin mirar la ventana) | Pendiente de implementación. |
| §15.9 alternativas (Skellam, binomial negativa, Poisson bivariado) | Registradas como EXP-006 candidatos, condicionadas a H5 | Pendiente. |

**Reformulaciones aceptadas**: (1) "modelo de producción ratificado" → "predictor
probabilístico de referencia, pendiente de validación prospectiva y de mercado";
(2) el modelo se describe como **"Poisson penalizado con interpretación MAP"**,
no "bayesiano"; (3) toda comparación por liga individual es descriptiva; las
únicas afirmaciones con carácter inferencial son las que sobrevivieron el
bootstrap por bloques; (4) κ(n) de la Fig. 8 se re-etiqueta como ilustración
del mecanismo, no como el shrinkage exacto del modelo (el real es el de
`laplace.json`).

## Reproducibilidad

```bash
research/.venv/bin/python research/experiments/EXP-003-jerarquico/clustering.py
research/.venv/bin/python research/experiments/EXP-003-jerarquico/run.py
research/.venv/bin/python research/experiments/EXP-003-jerarquico/sensitivity.py --contour
research/.venv/bin/python research/experiments/EXP-003-jerarquico/m1_diagnosis.py
research/.venv/bin/python research/experiments/EXP-003-jerarquico/figures.py
```

Artefactos: `league_clusters.csv`, `results.json`, `walkforward_2026.csv`,
`contour_grid.json`, `m1_diagnosis.json`, `fig/*.png`. Modelo jerárquico:
`research/peak_models/models.py::fit_poisson_hier` (MAP con gradiente analítico).
