# Sportradar / Statshub — token en un server

El token de Statshub se "mintea" con JavaScript, así que el bootstrap necesita un
navegador real (Playwright/Chromium). **Hallazgo clave:** Akamai **bloquea el
Chromium headless** (devuelve sin token, `usable=False fetch_count=0`), mientras
que el **headed funciona** (verificado local: `usable=True fetch_count=41`).

Hay dos formas de operarlo en un server. En una **VPS chica (1 GB)** Chrome es
pesado y colisiona el perfil cuando se lanza varias veces → **recomendado: Opción A
(replay-only)**. La Opción B (Xvfb) sirve en VMs con más RAM.

---

## Opción A — replay-only (recomendada para VPS chica)

El server **nunca** abre navegador. Generás el token en tu PC (donde el navegador
funciona) y se lo pasás al bot, que hace HTTP puro.

1. **En el server**, en `~/betbot/.env`:
   ```ini
   SPORTRADAR_REPLAY_ONLY=true
   STATS_SESSION_REFRESH_ENABLED=false
   STATS_PREFETCH_ENABLED=false
   ```
   (Si tenías `xvfb-run` en el `ExecStart`, sacalo: en replay-only no hace falta.)
   `sudo systemctl restart betbot`.

2. **En tu PC** (dentro del repo, una vez por día / cuando venza):
   ```bash
   python -m stats_providers.sportradar_http.engine.session_manager --headed --seconds 8
   ```
   Genera `stats_providers/sportradar_http/engine/reports/session_state_headed.json`.

3. **Subir el token al bot:** mandá ese `.json` por Telegram **como archivo**, con el
   texto `/sportradar_token` en el pie (caption). El bot responde con la fecha de
   vencimiento. (Alternativa: `scp` el archivo al mismo path en la VM.)

4. `/sportradar_token` (sin archivo) muestra el estado del token vigente.

El token dura ~24h; cuando venza, repetí los pasos 2-3. Si está vencido y pedís
`/stats`, el bot te avisa que lo renueves (no abre navegador).

---

## Opción B — Chrome headed bajo Xvfb (VMs con más RAM)

Correr Chromium **headed bajo un display virtual (Xvfb)**: Chrome cree que tiene
pantalla, Akamai lo ve como browser real, y no se abre ninguna ventana visible.

### Pasos en la VM (una sola vez)

1. **Librerías de Chromium + Xvfb:**
   ```bash
   sudo ~/betbot/betbot/bin/python -m playwright install-deps chromium
   sudo apt-get install -y xvfb
   ```
   (Si `install-deps` no está disponible, instalá manualmente: `libnss3 libnspr4
   libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1
   libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64`.)

2. **Modo headed por env** (`~/betbot/.env`):
   ```ini
   SPORTRADAR_BOOTSTRAP_MODE=headed
   ```

3. **Correr el bot bajo Xvfb.** Editá el unit de systemd para envolver el arranque:
   ```bash
   sudo systemctl edit --full betbot   # o editá /etc/systemd/system/betbot.service
   ```
   Cambiá la línea `ExecStart=` para anteponer `xvfb-run -a`:
   ```ini
   ExecStart=/usr/bin/xvfb-run -a /home/maximilianogatto/betbot/run.sh
   ```
   Luego:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart betbot
   ```

## Verificar
```bash
journalctl -u betbot -f | grep -iE "sportradar|CHROME"
```
Deberías ver `🌐 CHROME ABIERTO | headless=False` y, tras unos segundos, que el
token se renueva sin error. Probá `/stats` de una liga linkeada a Sportradar: ya
debería traer el reporte completo (forma/H2H/tabla/goles), no solo cuotas.

## Notas
- El `SPORTRADAR_BOOTSTRAP_MODE=headed` ahora aplica también al pre-refresh de
  fondo (arranque + cada 30 min), así que deja de fallar en cada ciclo.
- Un bootstrap headed exitoso deja cookies de Akamai en el perfil compartido
  (`chrome_profile`), así que renovaciones posteriores son más livianas.
- RAM: Chromium en una VPS de 1 GB es pesado (ya van los flags
  `--disable-dev-shm-usage`/`--disable-gpu`). Si queda al límite, bajá la
  frecuencia del pre-refresh o pasá Sportradar a on-demand.
