#!/bin/sh

set -u

HAPROXY_SOURCE_CONFIG=/usr/local/etc/haproxy/haproxy.cfg
HAPROXY_CONFIG=/tmp/haproxy.cfg
HAPROXY_PID=
PROXY_LINKS_UI_PID=

build_haproxy_config() {
	cp "$HAPROXY_SOURCE_CONFIG" "$HAPROXY_CONFIG"

	if [ -n "${COUNTRY_FILTER:-}" ]; then
		echo "COUNTRY_FILTER=$COUNTRY_FILTER, disabling non-country backends (warp, proxy001)."
		sed -i \
			-e '/^[[:space:]]*server warp /d' \
			-e '/^[[:space:]]*server proxy001 /d' \
			"$HAPROXY_CONFIG"
	fi
}

start_haproxy() {
	build_haproxy_config

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

start_proxy_links_ui() {
	echo "Starting proxy links UI..."
	python3 /proxy/proxy-links-ui.py &
	PROXY_LINKS_UI_PID=$!
}

ensure_proxy_links_ui() {
	if [ -z "${PROXY_LINKS_UI_PID:-}" ] || ! kill -0 "$PROXY_LINKS_UI_PID" 2>/dev/null; then
		echo "Proxy links UI is not running, starting it..."
		start_proxy_links_ui || true
	fi
}

start_haproxy
start_proxy_links_ui || true

while :; do
	python3 /proxy/vpngate.py || echo "VPNGate refresh failed; keeping existing ovpn files."

	for _ in $(seq 1 1800); do
		ensure_haproxy
		ensure_proxy_links_ui
		sleep 1
	done
done
