#!/bin/sh
# Watchdog:
#  1) Scheduled rotate every ROTATING_DELAY (IP diversity)
#  2) Health probe every OVPN_HEALTH_INTERVAL — auto-switch OVPN when down
#
# Env:
#   ROTATING_DELAY       default 60   — force new random profile
#   OVPN_HEALTH_INTERVAL default 8    — seconds between probes
#   OVPN_HEALTH_FAILS    default 2    — consecutive fails before failover
#   OVPN_CONNECT_GRACE   default 35   — seconds after (re)start before counting fails
#   OVPN_EGRESS_CHECK    default 1    — curl via tinyproxy to prove path works
#   OVPN_EGRESS_URL      default http://1.1.1.1
#   OVPN_EGRESS_TIMEOUT  default 6

# shellcheck source=/dev/null
. /slave/ovpn-common.sh

ROTATING_DELAY="${ROTATING_DELAY:-60}"
HEALTH_INTERVAL="${OVPN_HEALTH_INTERVAL:-8}"
FAIL_THRESHOLD="${OVPN_HEALTH_FAILS:-2}"
CONNECT_GRACE="${OVPN_CONNECT_GRACE:-35}"

# sanitize ints
case "$ROTATING_DELAY" in *[!0-9]*|"") ROTATING_DELAY=60 ;; esac
case "$HEALTH_INTERVAL" in *[!0-9]*|"") HEALTH_INTERVAL=8 ;; esac
case "$FAIL_THRESHOLD" in *[!0-9]*|"") FAIL_THRESHOLD=2 ;; esac
case "$CONNECT_GRACE" in *[!0-9]*|"") CONNECT_GRACE=35 ;; esac
[ "$HEALTH_INTERVAL" -lt 3 ] && HEALTH_INTERVAL=3
[ "$FAIL_THRESHOLD" -lt 1 ] && FAIL_THRESHOLD=1
[ "$ROTATING_DELAY" -lt 15 ] && ROTATING_DELAY=15

echo "Watchdog running: ROTATING_DELAY=${ROTATING_DELAY}s HEALTH_INTERVAL=${HEALTH_INTERVAL}s FAIL_THRESHOLD=${FAIL_THRESHOLD} GRACE=${CONNECT_GRACE}s EGRESS_CHECK=${OVPN_EGRESS_CHECK:-1}"

fail_streak=0
last_start_ts=$(date +%s 2>/dev/null || echo 0)
last_rotate_ts=$last_start_ts

mark_started() {
	last_start_ts=$(date +%s 2>/dev/null || echo 0)
	fail_streak=0
}

do_failover() {
	_reason="$1"
	_cur=$(get_current_ovpn)
	echo "OVPN_FAILOVER reason=$_reason current=${_cur:-none} fail_streak=$fail_streak"

	if [ -n "$_cur" ]; then
		blacklist_add "$_cur"
	fi

	kill_vpn_stack

	# Prefer a different file than the one that just failed
	if ! start_vpn_stack "$_reason"; then
		echo "OVPN_FAILOVER could not start new stack — will retry"
		sleep 5
		start_vpn_stack "$_reason" || true
	fi
	mark_started
	last_rotate_ts=$(date +%s 2>/dev/null || echo 0)
}

# Initial grace: run.sh already started ovpn + tinyproxy
mark_started

while :; do
	sleep "$HEALTH_INTERVAL"
	now=$(date +%s 2>/dev/null || echo 0)
	elapsed_start=$((now - last_start_ts))
	elapsed_rotate=$((now - last_rotate_ts))

	# --- scheduled rotation (diversity), independent of health ---
	if [ "$elapsed_rotate" -ge "$ROTATING_DELAY" ]; then
		echo "Watchdog: scheduled rotate after ${elapsed_rotate}s (ROTATING_DELAY=$ROTATING_DELAY)"
		# do not blacklist on healthy rotate — just move on
		_cur=$(get_current_ovpn)
		kill_vpn_stack
		# avoid same file if possible (pass avoid via CURRENT still set)
		if [ -n "$_cur" ]; then
			printf '%s\n' "$_cur" > "$CURRENT_FILE_PATH" 2>/dev/null || true
		fi
		if ! start_vpn_stack "rotate"; then
			start_vpn_stack "rotate" || true
		fi
		mark_started
		last_rotate_ts=$now
		continue
	fi

	# --- health / auto failover ---
	if [ "$elapsed_start" -lt "$CONNECT_GRACE" ]; then
		# still connecting — update status only when process+tun look good
		if vpn_is_healthy; then
			OVPN_FILE=$(get_current_ovpn)
			write_ovpn_status "up" 1
			fail_streak=0
		else
			echo "Watchdog: grace ${elapsed_start}/${CONNECT_GRACE}s — waiting for VPN/tinyproxy"
		fi
		continue
	fi

	if vpn_is_healthy; then
		if [ "$fail_streak" -ne 0 ]; then
			echo "Watchdog: recovered (was fail_streak=$fail_streak)"
		fi
		fail_streak=0
		OVPN_FILE=$(get_current_ovpn)
		write_ovpn_status "up" 1
		continue
	fi

	fail_streak=$((fail_streak + 1))
	_cur=$(get_current_ovpn)
	echo "Watchdog: UNHEALTHY streak=$fail_streak/$FAIL_THRESHOLD file=${_cur:-?} (openvpn=$(openvpn_running && echo y || echo n) tun=$(tun0_has_addr && echo y || echo n) proxy=$(tinyproxy_running && echo y || echo n))"

	if [ "$fail_streak" -ge "$FAIL_THRESHOLD" ]; then
		do_failover "failover"
	fi
done
