# Sportradar / Statshub — Chrome en un server (Xvfb)

El token de Statshub se "mintea" con JavaScript, así que el bootstrap necesita un
navegador real (Playwright/Chromium). **Hallazgo clave:** Akamai **bloquea el
Chromium headless** (devuelve sin token, `usable=False fetch_count=0`), mientras
que el **headed funciona** (verificado local: `usable=True fetch_count=41`).

En un server sin monitor la solución es correr Chromium **headed bajo un display
virtual (Xvfb)**: Chrome cree que tiene pantalla, Akamai lo ve como browser real,
y no se abre ninguna ventana visible.

## Pasos en la VM (una sola vez)

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
