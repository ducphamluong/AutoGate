#!/bin/sh

set -u

HAPROXY_SOURCE_CONFIG=/usr/local/etc/haproxy/haproxy.cfg
HAPROXY_CONFIG=/tmp/haproxy.cfg
HAPROXY_PID=
PROXY_LINKS_UI_PID=
PROXY_WORKER_COUNT="${PROXY_WORKER_COUNT:-10}"
EGRESS_MODE="${EGRESS_MODE:-all}"
OVPN_REFRESH_SECONDS="${OVPN_REFRESH_SECONDS:-1800}"

if ! echo "$PROXY_WORKER_COUNT" | grep -Eq '^[0-9]+$' || [ "$PROXY_WORKER_COUNT" -lt 1 ] || [ "$PROXY_WORKER_COUNT" -gt 20 ]; then
	echo "Invalid PROXY_WORKER_COUNT=$PROXY_WORKER_COUNT, using 10."
	PROXY_WORKER_COUNT=10
fi

if ! echo "$OVPN_REFRESH_SECONDS" | grep -Eq '^[0-9]+$' || [ "$OVPN_REFRESH_SECONDS" -lt 60 ]; then
	echo "Invalid OVPN_REFRESH_SECONDS=$OVPN_REFRESH_SECONDS, using 1800."
	OVPN_REFRESH_SECONDS=1800
fi

append_worker_frontends() {
	for index in $(seq 0 $((PROXY_WORKER_COUNT - 1))); do
		port=$((56800 + index))
		name=$(printf "vpn%02d" "$index")
		cat >> "$HAPROXY_CONFIG" <<EOF

frontend worker_$name
  mode http
  bind *:$port
  default_backend worker_$name

backend worker_$name
  mode http
  default-server resolvers docker init-addr libc,none inter 5s fall 2 rise 1
  server $name $name:8080 check
EOF
	done
}

# Resolve EGRESS_MODE into which named servers stay in the rotating backend.
# COUNTRY_FILTER no longer strips warp/proxy001 — use EGRESS_MODE instead.
apply_egress_mode() {
	mode=$(echo "${EGRESS_MODE:-all}" | tr '[:upper:]' '[:lower:]')
	echo "EGRESS_MODE=$mode (COUNTRY_FILTER only filters OpenVPN configs)"

	enable_warp=1
	enable_proxybroker=1
	enable_psiphon=1
	enable_ovpn=1

	case "$mode" in
		all)
			;;
		ovpn)
			enable_warp=0
			enable_proxybroker=0
			enable_psiphon=0
			;;
		ovpn+psiphon)
			enable_warp=0
			enable_proxybroker=0
			;;
		ovpn+warp)
			enable_proxybroker=0
			enable_psiphon=0
			;;
		custom)
			enable_warp="${ENABLE_WARP:-0}"
			enable_proxybroker="${ENABLE_PROXYBROKER:-0}"
			enable_psiphon="${ENABLE_PSIPHON:-0}"
			enable_ovpn="${ENABLE_OVPN:-1}"
			;;
		*)
			echo "Unknown EGRESS_MODE=$mode, falling back to all."
			;;
	esac

	if [ "$enable_warp" = "0" ] || [ "$enable_warp" = "false" ]; then
		sed -i '/^[[:space:]]*server warp /d' "$HAPROXY_CONFIG"
		echo "  disabled backend server: warp"
	fi
	if [ "$enable_proxybroker" = "0" ] || [ "$enable_proxybroker" = "false" ]; then
		sed -i '/^[[:space:]]*server proxy001 /d' "$HAPROXY_CONFIG"
		echo "  disabled backend server: proxy001"
	fi
	if [ "$enable_psiphon" = "0" ] || [ "$enable_psiphon" = "false" ]; then
		sed -i '/^[[:space:]]*server psiphon001 /d' "$HAPROXY_CONFIG"
		echo "  disabled backend server: psiphon001"
	fi
	if [ "$enable_ovpn" = "0" ] || [ "$enable_ovpn" = "false" ]; then
		sed -i '/^[[:space:]]*server vpn[0-9][0-9] /d' "$HAPROXY_CONFIG"
		echo "  disabled backend servers: vpn*"
	fi
}

build_haproxy_config() {
	cp "$HAPROXY_SOURCE_CONFIG" "$HAPROXY_CONFIG"
	apply_egress_mode
	append_worker_frontends
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
	python3 /proxy/ovpn_refresh.py || echo "OpenVPN refresh failed; keeping existing ovpn files."

	for _ in $(seq 1 "$OVPN_REFRESH_SECONDS"); do
		ensure_haproxy
		ensure_proxy_links_ui
		sleep 1
	done
done
