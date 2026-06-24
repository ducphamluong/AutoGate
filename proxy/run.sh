#!/bin/sh

set -u

HAPROXY_CONFIG=/usr/local/etc/haproxy/haproxy.cfg
HAPROXY_PID=

start_haproxy() {
	while ! haproxy -c -f "$HAPROXY_CONFIG"; do
		echo "HAProxy config is not ready yet, retrying in 2s..."
		sleep 2
	done

	echo "Starting HAProxy..."
	haproxy -W -db -f "$HAPROXY_CONFIG" &
	HAPROXY_PID=$!
}

ensure_haproxy() {
	if [ -z "${HAPROXY_PID:-}" ] || ! kill -0 "$HAPROXY_PID" 2>/dev/null; then
		echo "HAProxy is not running, starting it..."
		start_haproxy
	fi
}

start_haproxy

while :; do
	python3 /proxy/vpngate.py || echo "VPNGate refresh failed; keeping existing ovpn files."

	for _ in $(seq 1 1800); do
		ensure_haproxy
		sleep 1
	done
done
