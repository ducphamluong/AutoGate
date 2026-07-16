#!/bin/sh
# Connect once with a randomly chosen (non-blacklisted) profile.
# Watchdog supervises health and calls start_vpn_stack for failover.

# shellcheck source=/dev/null
. /slave/ovpn-common.sh

echo "Starting vpn service..."

ensure_auth_txt

if ! pick_ovpn_file ""; then
	echo "No OpenVPN configs found in /ovpn (*.ovpn). Waiting for master refresh..."
	exit 1
fi

remember_current
write_ovpn_status "${OVPN_START_REASON:-start}" 0

echo "Connecting to VPN by $OVPN_FILE"

# Foreground when launched alone; run.sh backgrounds this script.
# connect-timeout / ping-restart help dead peers exit faster so watchdog can swap.
exec openvpn --config "$OVPN_FILE" \
	--data-ciphers "AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-128-CBC" \
	--connect-retry-max 3 \
	--connect-timeout 25 \
	--ping 10 \
	--ping-restart 45
