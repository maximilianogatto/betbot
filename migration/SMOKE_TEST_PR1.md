# Smoke Test local de PR1 — BetBot

> Validación **real** (booteo del bot, no solo unit tests) a correr cuando PR1 esté `DONE`.
> **Todo local. NO tocar la VPS.** Usar un **bot de Telegram de test** y una **COPIA** de la DB.
> Objetivo: confirmar que la rama arranca de verdad, los comandos responden, un ciclo de tracking corre sin congelar el loop, y la DB se achica tras el mantenimiento.

## Pre-requisitos
- [ ] PR1 completo (T1-T6 `DONE`) y suite verde.
- [ ] Intérprete con dependencias: `/Users/maximilianogatto/Library/CloudStorage/OneDrive-Personal/Apuestas/BetBot/betbot/bin/python`
      (el `python3` del sistema NO tiene `telegram`/`httpx`/`playwright`).
- [ ] `.env` con un `TELEGRAM_BOT_TOKEN` de **bot de test** (no el de producción).
- [ ] Copia de seguridad / copia de trabajo de la DB:
      `cp data/tracking.sqlite3 data/tracking.smoke.sqlite3` (y apuntar el bot a la copia, o trabajar sobre una DB descartable).

## Paso 0 — Tamaño de DB ANTES (línea base)
```
du -h data/tracking.sqlite3
sqlite3 data/tracking.sqlite3 "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY 2 DESC LIMIT 6;"
```
Anotar el tamaño total (esperado ~16 MB con páginas libres).

## Paso 1 — Boot
```
cd .../BetBot-migration
/.../BetBot/betbot/bin/python main.py
```
- [ ] Arranca sin traceback.
- [ ] Loguea registro de extractores y stats providers.
- [ ] Loguea el arranque de los jobs de fondo (tracking, resource monitor, etc.).
- [ ] Queda en "esperando mensajes por polling".

## Paso 2 — Comandos básicos (en el chat de test)
- [ ] `/status` o `/ping` → responde (bot vivo, lectura de sistema OK).
- [ ] `/list_tracks` (o `/leagues`) → responde sin error (lectura de DB OK).
- [ ] `/matches` → lista partidos o "no hay" sin traceback (lectura de eventos OK).
- [ ] (opcional, ruta de escritura) `/track_url <url de liga conocida>` → tarjeta de confirmación → `/confirm_track` → "monitoreo iniciado".

## Paso 3 — Ciclo de tracking (valida T4: SQLite fuera del event loop)
- [ ] Esperar un ciclo del monitor (intervalo por defecto 120s) **o** forzar con `/refresh_tracks`.
- [ ] En logs: el ciclo termina ("Tracking monitor cycle finished ...") sin congelar el bot.
- [ ] Mientras corre el ciclo, `/ping` **sigue respondiendo** (= el loop no se bloqueó por SQLite síncrono). Esta es la prueba clave de T4.

## Paso 4 — Mantenimiento + achique de DB (valida T1 VACUUM, T6 prune)
Disparar la purga + vacuum manualmente con el CLI (sin esperar al job dominical):
```
/.../BetBot/betbot/bin/python cli.py prune --days 14
du -h data/tracking.sqlite3
```
- [ ] El comando reporta filas borradas por tabla.
- [ ] El tamaño de la DB **bajó** respecto del Paso 0 (esperado de ~16 MB a ~5 MB tras VACUUM).

## Paso 5 — Cache cap (valida T2, opcional)
```
sqlite3 data/tracking.sqlite3 "SELECT COUNT(*) FROM stats_payload_cache;"
```
- [ ] Tras usar `/stats` varias veces, el conteo se mantiene **≤ 200** filas.

## Paso 6 — Shutdown limpio
- [ ] Ctrl+C → cierra sin traceback; los extractores hacen `stop()` y Chromium se cierra (verificar que no quedan procesos `chromium` colgados: `pgrep -fl chromium`).

## Criterio de aprobación (pass/fail)
PR1 pasa el smoke si: **boot sin errores · comandos responden · `/ping` responde durante un ciclo de tracking · la DB se achica tras `cli.py prune` · shutdown limpio sin Chromium huérfano.**

Si todo verde → recién ahí tiene sentido **mergear PR1 a main y deployar a la VPS** (libera espacio, riesgo bajo).
Registrar el resultado (tamaños antes/después + checklist) como una entrada en `LOG.md`.
