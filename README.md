# BetBot

Bot de Telegram que sigue competiciones de fútbol en varias casas de apuestas,
detecta cambios de cuotas, avisa cuando un partido vigilado entra en vivo y
genera reportes estadísticos desde proveedores externos.

Arrancó siendo un seguidor de ligas de Bet365 y hoy son **9 casas** y **11
proveedores de estadísticas**, con el dominio separado de Telegram para poder
agregar plataformas sin tocar el resto.

---

## Qué hace

**Sigue ligas y detecta movimientos de cuota.** Se agrega una competición por
URL, el bot la refresca periódicamente y avisa de partidos nuevos y de cambios
de cuota que superen el umbral configurado por chat. Los cambios chicos no
generan aviso: se acumulan y se revisan a pedido.

**Unifica la misma liga entre casas.** La "Primera Nacional" de una casa y la de
otra son la misma competición: el registro canónico las agrupa bajo una *liga
unificada*, de modo que los comandos muestran una entrada por liga y no una por
plataforma. Vincular estadísticas a una plataforma se hereda al resto.

**Vigila partidos en vivo.** Una lista de partidos a seguir —cargada a mano o
importada de una planilla— se cruza contra los feeds en vivo de las casas que
los exponen, y dispara avisos de gol, roja y amarilla.

**Genera reportes de estadísticas.** Tabla, forma, historial y reportes de
partido desde el proveedor vinculado a cada liga.

**Calcula picos de rotación** (`/peaks`), con su propio modelo y backtest.

---

## Arquitectura

La regla es que las dependencias apuntan siempre hacia adentro, y hay un test
que lo verifica (`tests/test_architecture_layers.py`): si alguien importa
Telegram desde un servicio, la suite falla.

```
core/          dominio puro: modelos, eventos, naming de ligas, línea justa.
               No importa nada del proyecto.
core/ports/    interfaces que el dominio necesita (13 puertos)

services/      lógica de negocio: tracking, detección de cambios, live watch,
               stats, predicción, peak. No sabe que Telegram existe.

adapters/      implementaciones de los puertos
  storage/     SQLite: un adapter por agregado + facade

interfaces/    entrada y salida
  telegram/    handlers, renderers y listener del bus de eventos
  cli/

runtime/       scheduler neutral (asyncio), sin dependencia del framework
extractors/    una casa de apuestas por paquete
stats_providers/ un proveedor de estadísticas por paquete
research/      notebooks y experimentos del modelo (fuera del runtime)
```

Los avisos viajan por un **bus de eventos**: los servicios publican
`NewMatchesEvent`, `OddsChangedEvent`, `MatchLiveEvent`; el listener de Telegram
los traduce a mensajes. Por eso el núcleo se puede ejercitar sin un bot.

---

## Plataformas

**Casas de apuestas** (`extractors/`):

| Extractor | Cómo obtiene los datos | En vivo |
| :--- | :--- | :---: |
| `bet365` | Playwright (navegador) | — |
| `xbet_http` | HTTP (LineFeed / LiveFeed) | ✅ |
| `betsson_http` | HTTP (OBG) | ✅ |
| `betwarrior_http` | HTTP (Kambi) | ✅ |
| `bz_http` | HTTP | ✅ |
| `betovo_http` | HTTP (Altenar) | ✅ |
| `mrpunter_http` | HTTP (FSB) | ✅ |
| `mystake_http` | HTTP | ✅ |
| `solcasino_http` | HTTP (Betby) | ✅ |

Salvo Bet365 y 1xBet, cada extractor se registra sólo si su configuración está
presente en el `.env`. `BOT_DISABLED_PLATFORMS` permite apagar cualquiera.

**Proveedores de estadísticas** (`stats_providers/`): `sportradar_http`
(Statshub), `sofascore_http`, `flashscore_http`, `footystats_http`, y los
federativos `palloliitto` (FIN), `svenskfotboll_http` (SWE), `norway_http`,
`romania_http`, `slovakia_http`, `algeria_http`, `special_federation`.

Sólo Sportradar necesita un token que se mintea con navegador; el resto es HTTP
directo.

---

## Comandos

Son ~98. Agrupados por lo que hacen:

**Ligas y seguimiento** — `/track_url`, `/competition_url`, `/event_url`,
`/confirm_track`, `/update_track_url`, `/list_tracks`, `/refresh_tracks`,
`/untrack`, `/leagues`, `/league`, `/link_league`, `/unlink_league`,
`/relink_leagues`, `/platforms`

**Partidos y cuotas** — `/matches`, `/match`, `/view_match`, `/today`,
`/fixtures`, `/standings`, `/odds_on`, `/odds_off`, `/set_change_percent`,
`/check_little_changes`, `/confirm_change`, `/confirm_all_little_changes`,
`/reminders_league`, `/reminders_match`

**Estadísticas** — `/stats`, `/stats_leagues`, `/stats_links`, `/stats_tracks`,
`/link_stats`, `/track_stats`, `/explore_stats`, `/sportradar_token`

**En vivo** — `/watch_live`, `/watching`, `/unwatch`, `/live_match`,
`/live_status`, `/live_settings`, `/view_live_match`, `/import_sheet`

**Picos** — `/peaks`, `/peak_on`, `/peak_off`, `/peak_today`

**Ligas con soporte federativo propio** — prefijos `al_` (Argelia), `fin_`
(Finlandia), `no_` (Noruega), `ro_` (Rumania), `sk_` (Eslovaquia), `swe_`
(Suecia), cada uno con `_today`, `_fixtures`, `_standings`, `_leagues`,
`_match`, `_help`

**Sistema** — `/start`, `/help`, `/guide`, `/ping`, `/status`, `/resources`,
`/cancel`, y las ayudas por tema (`/help_leagues`, `/help_live`,
`/help_matches`, `/help_stats`)

---

## Persistencia

SQLite, esquema *current-state*: 20 tablas creadas por
`adapters/storage/schema.py`.

La distinción que ordena el diseño:

- **`events`** guarda el estado actual de cada partido y se pisa en cada
  refresco. No acumula historial.
- **`match_results`** es el archivo histórico: acumula cómo terminó cada partido
  y es el dataset sobre el que corren los análisis. Distingue `FINISHED` de
  `SUSPENDED`/`POSTPONED` a propósito, porque un suspendido guardado como 0-0
  envenena cualquier estadística.

Las suscripciones son por chat; el estado scrapeado es global, para no duplicar
los mismos partidos cuando varios chats siguen la misma liga. Cada chat compara
contra su propia baseline, así que distintos umbrales conviven sin duplicar el
estado.

---

## Instalación

Requiere Python 3.11+.

```bash
./install.sh          # crea el venv, instala deps y Playwright Chromium
cp .env.example .env  # completar TELEGRAM_BOT_TOKEN
./run.sh
```

En Windows, `install.ps1` y `run.ps1`.

### Configuración

Todo se configura por `.env` (ver `.env.example`, que documenta cada variable).
Los grupos:

| Prefijo | Para qué |
| :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | requerido |
| `EXTRACTOR_*` | paralelismo, timeouts y reciclado del navegador |
| `TRACKING_*` | intervalos de refresco y umbrales por defecto |
| `STATS_*`, `SPORTRADAR_*` | prefetch, caché y modo de bootstrap del token |
| `LIVE_WATCH_*` | vigilancia en vivo e importación de planilla |
| `BOT_PROXY_URL`, `BOT_PROXY_PLATFORMS` | salida por VPN, selectiva por casa |
| `MONITOR_*` | monitoreo de recursos |

### Salida por VPN

Algunas casas bloquean IPs de datacenter. `deploy/VPN-SETUP.md` explica el
esquema: wireproxy expone un SOCKS5 local y `BOT_PROXY_PLATFORMS` lista **sólo**
las plataformas que deben salir por ahí. El resto —incluido Telegram— sale
directo, que es más rápido y más estable.

### Token de Sportradar

Statshub firma su token con JavaScript, así que hace falta un navegador real, y
Akamai bloquea el headless. En un server chico conviene **replay-only**: el
token se genera en una máquina con navegador

```bash
python -m stats_providers.sportradar_http.engine.session_manager --headed --seconds 8
```

y se le pasa al bot mandando el `.json` por Telegram con `/sportradar_token` en
el pie. Dura ~24 h. Detalles y la alternativa con Xvfb en
`deploy/SPORTRADAR-CHROME.md`.

---

## Desarrollo

```bash
./run_tests.sh -t .                                  # suite completa
python -m unittest discover -s tests -t .            # equivalente
```

Son ~840 tests. Conviene correrlos con una base limpia
(`BETBOT_DB_PATH=/tmp/test.sqlite3`): algunos tests tocan el almacenamiento y
una base con esquema viejo produce fallos que no son del código.

**Herramientas de línea de comandos** (`scripts/`, `cli.py`):

```bash
python cli.py stats                                  # tamaño y filas de la DB
python cli.py list-competitions                      # ligas bajo seguimiento
python -m scripts.link_stats_bulk --chat-id N        # linkeo masivo (dry-run)
python -m scripts.seed_leagues                       # semilla del registro
```

`migration/` conserva el registro del rediseño (`LOG.md`, `TASKS.md`,
`PORTS_SPEC.md`) y `REPORTE_ARQUITECTURA_BetBot.md` el diseño de referencia.
