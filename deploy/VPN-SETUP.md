# Correr el bot detrás de ProtonVPN (sin lockear el SSH)

Algunas casas (MrPunter/FSB, Solcasino/sptpub) bloquean la IP de datacenter de
la VM. Solución robusta: meter **solo el bot** en un *network namespace* con
WireGuard. El bot sale por ProtonVPN; SSH y el resto del host siguen por la red
directa, así que un full-tunnel **nunca** te deja afuera y una caída de VPN solo
afecta al bot.

## Requisitos
- `sudo apt install -y wireguard`
- La config de Proton en `/etc/wireguard/proton.conf` (chmod 600). Generala en
  account.protonvpn.com → Downloads → WireGuard (Linux). **No la commitees.**

## Instalación (una vez)
```bash
cd ~/betbot && git pull
chmod +x deploy/botvpn-netns.sh

# 1) Probar que levanta el namespace y destraba las casas:
sudo deploy/botvpn-netns.sh up
sudo ip netns exec botvpn curl -s -o /dev/null -w "fssb: %{http_code}\n"  https://prod20296-144090624.fssb.io/es/spbk/
sudo ip netns exec botvpn curl -s -o /dev/null -w "sptpub: %{http_code}\n" "https://api-g-c7818b61-607.sptpub.com/api/v4/live/brand/2392759269461204992/en/0"
# Tu SSH NO debería cortarse (el túnel está aislado en el netns).
sudo deploy/botvpn-netns.sh down

# 2) Instalar los servicios:
sudo cp deploy/botvpn.service /etc/systemd/system/betbot-vpn.service
sudo cp deploy/betbot.service /etc/systemd/system/betbot.service
sudo systemctl daemon-reload
sudo systemctl enable --now betbot-vpn.service     # crea el netns al boot
sudo systemctl restart betbot                       # el bot ahora corre dentro del netns
journalctl -u betbot -f                             # ya no deberías ver 403 fssb / 503 sptpub
```
> El unit del netns se instala como `betbot-vpn.service` (el archivo se llama
> `botvpn.service` en el repo). `betbot.service` depende de él vía `Requires=`.

## Verificar
```bash
systemctl status betbot-vpn betbot
# IP de salida del bot (debe ser la de Proton, no la de la VM):
sudo ip netns exec botvpn curl -s https://api.ipify.org; echo
```

## Apagar la VPN (volver a salida directa)
```bash
sudo sed -i 's#NetworkNamespacePath=.*##; s#BindReadOnlyPaths=.*##' /etc/systemd/system/betbot.service
sudo sed -i 's#Requires=botvpn.service##' /etc/systemd/system/betbot.service
sudo systemctl daemon-reload
sudo systemctl disable --now betbot-vpn.service
sudo systemctl restart betbot
```

## Notas
- **Seguridad**: si tu `proton.conf` se filtró (clave privada), regeneralo en Proton.
- **Si el bot queda sin red** (handshake falla), revisá `sudo ip netns exec botvpn wg`
  (debe mostrar `latest handshake`). El SSH no se ve afectado pase lo que pase.
- Reconexión: si la VPN se cae, `sudo systemctl restart betbot-vpn betbot` la rearma.
