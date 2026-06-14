# Sacar el tráfico del bot por ProtonVPN (sin lockear el SSH)

Algunas casas (MrPunter/FSB, Solcasino/sptpub) bloquean la IP de datacenter de la
VM. Para alcanzarlas, el tráfico del bot tiene que salir por una VPN.

## ✅ Opción A — wireproxy + BOT_PROXY_URL (recomendada)

WireGuard en **espacio de usuario** (`wireproxy`) levanta el túnel Proton y expone
un **SOCKS5 local**; el bot manda todo su HTTP por ahí con una env. Sin root, sin
tocar el ruteo del host, **sin riesgo de cortar el SSH**, y si la VPN se cae solo
afecta al bot (no tu acceso).

### 1) Instalar wireproxy (binario único)
```bash
cd /tmp
curl -L -o wireproxy.tar.gz https://github.com/whyvl/wireproxy/releases/latest/download/wireproxy_linux_amd64.tar.gz
tar xzf wireproxy.tar.gz
sudo install -m755 wireproxy /usr/local/bin/wireproxy
wireproxy --version
```

### 2) Config (tu WireGuard de Proton + bloque [Socks5])
Tomá `deploy/wireproxy.conf.example`, completá con tus valores de Proton y guardalo:
```bash
sudo cp ~/betbot/deploy/wireproxy.conf.example /etc/wireguard/wireproxy.conf
sudo nano /etc/wireguard/wireproxy.conf      # pegá PrivateKey/PublicKey/Endpoint reales
sudo chmod 600 /etc/wireguard/wireproxy.conf
```
> Si ya tenés `/etc/wireguard/proton.conf`, podés copiarlo y solo agregarle el
> bloque `[Socks5]`. **No lo commitees** (tiene tu clave privada).

### 3) Servicio + probar el SOCKS
```bash
sudo cp ~/betbot/deploy/wireproxy.service /etc/systemd/system/wireproxy.service
sudo systemctl daemon-reload
sudo systemctl enable --now wireproxy
# probar que el SOCKS sale por Proton y destraba:
curl -s --socks5-hostname 127.0.0.1:25344 https://api.ipify.org; echo
curl -s -o /dev/null -w "fssb: %{http_code}\n" --socks5-hostname 127.0.0.1:25344 https://prod20296-144090624.fssb.io/es/spbk/
```

### 4) Decirle al bot que use el proxy
En `~/betbot/.env`:
```ini
BOT_PROXY_URL=socks5://127.0.0.1:25344
```
y reiniciar:
```bash
cd ~/betbot && git pull
betbot/bin/pip install -r requirements.txt   # instala socksio (soporte SOCKS de httpx)
sudo systemctl restart betbot
journalctl -u betbot -f                        # ya no deberías ver 403 fssb / 503 sptpub
```

Listo: TODO el HTTP del bot (extractores + stats) sale por Proton. El SSH y el host
quedan en la red directa. (El bootstrap de Sportradar via Chromium sigue directo;
si statshub te bloqueara, avisá y le agrego el proxy al navegador también.)

## Opción B — network namespace (avanzada)
Aísla al bot en un netns con WireGuard de kernel (`deploy/botvpn-netns.sh` +
`deploy/botvpn.service` + `deploy/betbot.service`). Más robusta a nivel red pero
con más piezas y requiere root. Usala solo si la Opción A no te alcanza.

## Notas
- **Seguridad**: si tu clave privada se filtró, regeneralá en Proton.
- **Reconexión**: `wireproxy.service` tiene `Restart=always`; si Proton corta, vuelve solo.
- **Volver a directo**: comentá `BOT_PROXY_URL` en `.env` y `sudo systemctl restart betbot`
  (y opcional `sudo systemctl disable --now wireproxy`).
