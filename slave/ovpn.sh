#!/bin/sh

echo "Starting vpn service..."

# Pick a random .ovpn profile; never use auth.txt or non-config files.
# Prefer find+shuf when available; fall back to shell glob (Alpine busybox).
if command -v find >/dev/null 2>&1 && command -v shuf >/dev/null 2>&1; then
	OVPN_FILE=$(find /ovpn -maxdepth 1 -type f -name '*.ovpn' 2>/dev/null | shuf -n1)
else
	OVPN_FILE=""
	set -- /ovpn/*.ovpn
	if [ -f "$1" ]; then
		# portable pseudo-random among up to N files
		count=0
		for f in /ovpn/*.ovpn; do
			[ -f "$f" ] || continue
			count=$((count + 1))
		done
		if [ "$count" -gt 0 ]; then
			# $$ changes per process; good enough for rotation
			idx=$(( ($$ % count) + 1 ))
			n=0
			for f in /ovpn/*.ovpn; do
				[ -f "$f" ] || continue
				n=$((n + 1))
				if [ "$n" -eq "$idx" ]; then
					OVPN_FILE=$f
					break
				fi
			done
		fi
	fi
fi

if [ -z "${OVPN_FILE:-}" ] || [ ! -f "$OVPN_FILE" ]; then
	echo "No OpenVPN configs found in /ovpn (*.ovpn). Waiting for master refresh..."
	exit 1
fi

# Shared auth for free SoftEther-style configs that reference auth-user-pass.
if [ ! -f /ovpn/auth.txt ]; then
	USER="${OVPN_DEFAULT_USER:-vpn}"
	PASS="${OVPN_DEFAULT_PASS:-vpn}"
	printf '%s\n%s\n' "$USER" "$PASS" > /ovpn/auth.txt 2>/dev/null || true
fi

echo "Connecting to VPN by $OVPN_FILE"

openvpn --config "$OVPN_FILE" --data-ciphers "AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-128-CBC"
