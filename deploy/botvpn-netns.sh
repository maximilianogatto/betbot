#!/usr/bin/env bash
# Run ONLY the bot through a WireGuard (ProtonVPN) tunnel, isolated in a network
# namespace. SSH and the rest of the host keep using the direct connection, so a
# full-tunnel can never lock you out of the VM and a VPN drop only affects the bot.
#
# Reads the WireGuard config from /etc/wireguard/proton.conf (root, chmod 600).
# Usage: sudo botvpn-netns.sh up | down
set -euo pipefail

NS="${WG_NETNS:-botvpn}"
IF="${WG_IFACE:-botwg}"
CONF="${WG_CONF:-/etc/wireguard/proton.conf}"

_field() { grep -E "^\s*$1" "$CONF" | head -1 | sed -E 's/^[^=]*=\s*//' | cut -d, -f1 | tr -d ' \r'; }

up() {
    command -v wg >/dev/null || { echo "Falta wireguard-tools (sudo apt install wireguard)"; exit 1; }
    [ -f "$CONF" ] || { echo "No existe $CONF"; exit 1; }

    local priv addr dns pub endpoint keepalive
    priv=$(grep -E '^\s*PrivateKey' "$CONF" | head -1 | sed -E 's/^[^=]*=\s*//' | tr -d ' \r')
    addr=$(_field Address); dns=$(_field DNS); pub=$(_field PublicKey)
    endpoint=$(_field Endpoint); keepalive=$(_field PersistentKeepalive); keepalive=${keepalive:-25}

    # Recreate cleanly.
    ip link del "$IF" 2>/dev/null || true
    ip netns del "$NS" 2>/dev/null || true
    ip netns add "$NS"

    # Create the wg iface in the MAIN namespace so its encrypted UDP socket egresses
    # via the host's real internet; THEN move the iface into the netns. The decrypted
    # traffic lives in the netns; the handshake still reaches the endpoint. This is the
    # documented WireGuard "network namespace integration" pattern.
    ip link add "$IF" type wireguard
    wg set "$IF" private-key <(printf '%s' "$priv") \
        peer "$pub" allowed-ips 0.0.0.0/0,::/0 endpoint "$endpoint" persistent-keepalive "$keepalive"
    ip link set "$IF" netns "$NS"

    ip -n "$NS" addr add "$addr" dev "$IF"
    ip -n "$NS" link set lo up
    ip -n "$NS" link set "$IF" up
    ip -n "$NS" route add default dev "$IF"

    # DNS for processes that join this netns (Proton resolver, reached via the tunnel).
    mkdir -p "/etc/netns/$NS"
    printf 'nameserver %s\n' "${dns:-10.2.0.1}" > "/etc/netns/$NS/resolv.conf"

    echo "✓ netns '$NS' arriba (endpoint $endpoint). Probá:"
    echo "    sudo ip netns exec $NS curl -s -o /dev/null -w '%{http_code}\\n' https://prod20296-144090624.fssb.io/es/spbk/"
}

down() {
    ip -n "$NS" link del "$IF" 2>/dev/null || true
    ip link del "$IF" 2>/dev/null || true
    ip netns del "$NS" 2>/dev/null || true
    rm -f "/etc/netns/$NS/resolv.conf" 2>/dev/null || true
    echo "✓ netns '$NS' abajo"
}

case "${1:-}" in
    up) up ;;
    down) down ;;
    *) echo "uso: $0 up|down"; exit 1 ;;
esac
