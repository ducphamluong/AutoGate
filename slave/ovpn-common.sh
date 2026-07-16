#!/bin/sh
# Shared helpers for OVPN pick / blacklist / status (sourced by ovpn.sh + watchdog).

BLACKLIST_FILE="${OVPN_BLACKLIST_FILE:-/tmp/ovpn_blacklist.txt}"
CURRENT_FILE_PATH="${OVPN_CURRENT_FILE:-/tmp/ovpn_current_path}"
STATUS_DIR="${OVPN_STATUS_DIR:-/ovpn/status}"

ensure_auth_txt() {
	if [ ! -f /ovpn/auth.txt ]; then
		_u="${OVPN_DEFAULT_USER:-vpn}"
		_p="${OVPN_DEFAULT_PASS:-vpn}"
		printf '%s\n%s\n' "$_u" "$_p" > /ovpn/auth.txt 2>/dev/null || true
	fi
}

resolve_worker_index() {
	if [ -n "${WORKER_INDEX:-}" ]; then
		echo "$WORKER_INDEX" | tr -cd '0-9'
		return
	fi
	_hn=$(hostname 2>/dev/null || echo "")
	_idx=$(echo "$_hn" | sed -n 's/.*ovpn_proxy_\([0-9][0-9]*\).*/\1/p')
	if [ -n "$_idx" ]; then
		echo "$_idx"
		return
	fi
	_ip=""
	if command -v hostname >/dev/null 2>&1; then
		_ip=$(hostname -i 2>/dev/null | awk '{print $1}')
	fi
	if [ -z "$_ip" ] && command -v ip >/dev/null 2>&1; then
		_ip=$(ip -4 -o addr show eth0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
	fi
	if [ -n "$_ip" ]; then
		_last=$(echo "$_ip" | awk -F. '{print $4}')
		if [ -n "$_last" ] && [ "$_last" -ge 102 ] 2>/dev/null; then
			echo $((_last - 102))
			return
		fi
	fi
	echo ""
}

worker_name_and_port() {
	_idx=$(resolve_worker_index)
	if [ -z "$_idx" ]; then
		echo "vpn_unknown 0"
		return
	fi
	printf "vpn%02d %s\n" "$_idx" "$((56800 + _idx))"
}

is_blacklisted() {
	_base="$1"
	[ -f "$BLACKLIST_FILE" ] || return 1
	grep -Fxq "$_base" "$BLACKLIST_FILE" 2>/dev/null
}

blacklist_add() {
	_path="$1"
	[ -n "$_path" ] || return 0
	_base=$(basename "$_path")
	mkdir -p "$(dirname "$BLACKLIST_FILE")" 2>/dev/null || true
	touch "$BLACKLIST_FILE" 2>/dev/null || true
	if ! grep -Fxq "$_base" "$BLACKLIST_FILE" 2>/dev/null; then
		echo "$_base" >> "$BLACKLIST_FILE"
		echo "OVPN_FAILOVER blacklist += $_base"
	fi
}

blacklist_clear() {
	rm -f "$BLACKLIST_FILE" 2>/dev/null || true
	echo "OVPN_FAILOVER blacklist cleared (pool exhausted or reset)"
}

blacklist_count() {
	[ -f "$BLACKLIST_FILE" ] || { echo 0; return; }
	grep -c . "$BLACKLIST_FILE" 2>/dev/null || echo 0
}

# Count usable .ovpn files (optionally excluding blacklist).
count_ovpn_candidates() {
	_n=0
	for _f in /ovpn/*.ovpn; do
		[ -f "$_f" ] || continue
		_b=$(basename "$_f")
		if [ "${1:-}" = "skip_blacklisted" ] && is_blacklisted "$_b"; then
			continue
		fi
		_n=$((_n + 1))
	done
	echo "$_n"
}

# Pick a random .ovpn; prefer non-blacklisted; avoid CURRENT if alternatives exist.
# Sets OVPN_FILE on success.
pick_ovpn_file() {
	OVPN_FILE=""
	_avoid="${1:-}"
	_pool=""
	_pool_n=0

	_collect() {
		_mode="$1"
		_pool=""
		_pool_n=0
		for _f in /ovpn/*.ovpn; do
			[ -f "$_f" ] || continue
			_b=$(basename "$_f")
			if [ "$_mode" = "clean" ] && is_blacklisted "$_b"; then
				continue
			fi
			if [ -n "$_avoid" ] && [ "$_f" = "$_avoid" ]; then
				# skip current when we have other candidates
				continue
			fi
			_pool="$_pool
$_f"
			_pool_n=$((_pool_n + 1))
		done
	}

	_collect clean
	if [ "$_pool_n" -eq 0 ] && [ -n "$_avoid" ]; then
		# only the current file was excluded — allow blacklisted others, still avoid current if possible
		_collect all
	fi
	if [ "$_pool_n" -eq 0 ]; then
		# include current / clear blacklist
		if [ "$(count_ovpn_candidates skip_blacklisted)" -eq 0 ] && [ "$(count_ovpn_candidates)" -gt 0 ]; then
			blacklist_clear
		fi
		_collect clean
	fi
	if [ "$_pool_n" -eq 0 ]; then
		# last resort: any file including avoid
		for _f in /ovpn/*.ovpn; do
			[ -f "$_f" ] || continue
			_pool="$_pool
$_f"
			_pool_n=$((_pool_n + 1))
		done
	fi

	if [ "$_pool_n" -eq 0 ]; then
		return 1
	fi

	_list=$(printf '%s\n' "$_pool" | sed '/^$/d')
	if command -v shuf >/dev/null 2>&1; then
		OVPN_FILE=$(printf '%s\n' "$_list" | shuf -n1)
	else
		_idx=$(( ($$ + ${RANDOM:-0} + $(date +%s 2>/dev/null || echo 0)) % _pool_n + 1 ))
		OVPN_FILE=$(printf '%s\n' "$_list" | sed -n "${_idx}p")
	fi

	[ -n "$OVPN_FILE" ] && [ -f "$OVPN_FILE" ]
}

json_escape() {
	printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

write_ovpn_status() {
	# args: reason [healthy 0|1]
	_reason="${1:-start}"
	_healthy="${2:-0}"
	_path="${OVPN_FILE:-}"
	[ -n "$_path" ] || _path=$(cat "$CURRENT_FILE_PATH" 2>/dev/null || true)

	set -- $(worker_name_and_port)
	_name="$1"
	_port="$2"
	_idx=$(resolve_worker_index)
	[ -n "$_idx" ] || _idx=-1

	_base=""
	_local=""
	_rh=""
	_rp=""
	_proto=""
	if [ -n "$_path" ] && [ -f "$_path" ]; then
		_base=$(basename "$_path")
		_local="$_base"
		case "$_base" in
			local_*) _local=$(echo "$_base" | sed 's/^local_//') ;;
		esac
		_rl=$(grep -E '^[[:space:]]*remote[[:space:]]+' "$_path" 2>/dev/null | head -1)
		if [ -n "$_rl" ]; then
			_rh=$(echo "$_rl" | awk '{print $2}')
			_rp=$(echo "$_rl" | awk '{print $3}')
		fi
		_pl=$(grep -E '^[[:space:]]*proto[[:space:]]+' "$_path" 2>/dev/null | head -1)
		if [ -n "$_pl" ]; then
			_proto=$(echo "$_pl" | awk '{print $2}')
		fi
		[ -z "$_rp" ] && _rp=$(grep -E '^[[:space:]]*port[[:space:]]+' "$_path" 2>/dev/null | awk '{print $2}' | head -1)
	fi

	_ts=$(date +%s 2>/dev/null || echo 0)
	mkdir -p "$STATUS_DIR" 2>/dev/null || true
	_sf="$STATUS_DIR/${_name}.json"
	_tmp="${_sf}.tmp.$$"
	cat > "$_tmp" 2>/dev/null <<EOF
{"worker":"$(json_escape "$_name")","index":$_idx,"port":$_port,"file":"$(json_escape "$_base")","local_list_file":"$(json_escape "$_local")","file_path":"$(json_escape "$_path")","remote_host":"$(json_escape "$_rh")","remote_port":"$(json_escape "$_rp")","proto":"$(json_escape "$_proto")","updated_at":$_ts,"reason":"$(json_escape "$_reason")","healthy":$_healthy,"blacklist_size":$(blacklist_count)}
EOF
	mv -f "$_tmp" "$_sf" 2>/dev/null || cp "$_tmp" "$_sf" 2>/dev/null || true
	rm -f "$_tmp" 2>/dev/null || true

	echo "OVPN_MAP worker=$_name host_port=$_port file=$_base local_list=$_local remote=${_rh}:${_rp} proto=${_proto:-?} reason=$_reason healthy=$_healthy"
}

remember_current() {
	printf '%s\n' "$OVPN_FILE" > "$CURRENT_FILE_PATH" 2>/dev/null || true
}

get_current_ovpn() {
	cat "$CURRENT_FILE_PATH" 2>/dev/null || true
}

tun0_has_addr() {
	if command -v ip >/dev/null 2>&1; then
		ip -4 addr show dev tun0 2>/dev/null | grep -q 'inet '
		return $?
	fi
	# fallback: /sys
	[ -d /sys/class/net/tun0 ] || return 1
	return 1
}

openvpn_running() {
	if command -v pidof >/dev/null 2>&1; then
		pidof openvpn >/dev/null 2>&1
		return $?
	fi
	ps | grep -v grep | grep -q '[o]penvpn'
}

tinyproxy_running() {
	if command -v pidof >/dev/null 2>&1; then
		pidof tinyproxy >/dev/null 2>&1
		return $?
	fi
	ps | grep -v grep | grep -q '[t]inyproxy'
}

# Optional egress via local tinyproxy (proves end-to-end proxy path).
egress_ok() {
	_en=$(echo "${OVPN_EGRESS_CHECK:-1}" | tr '[:upper:]' '[:lower:]')
	case "$_en" in
		0|false|no|off) return 0 ;;
	esac
	command -v curl >/dev/null 2>&1 || return 0
	# ifconfig.me/ip returns body on success; avoid -f (4xx flaky on some nets)
	_url="${OVPN_EGRESS_URL:-http://ifconfig.me/ip}"
	_to="${OVPN_EGRESS_TIMEOUT:-6}"
	_body=""
	if tinyproxy_running; then
		_body=$(curl -sS -m "$_to" -x "http://127.0.0.1:8080" "$_url" 2>/dev/null) || _body=""
		[ -n "$_body" ] && return 0
		_body=$(curl -sS -m "$_to" --interface tun0 "$_url" 2>/dev/null) || _body=""
		[ -n "$_body" ] && return 0
		return 1
	fi
	_body=$(curl -sS -m "$_to" --interface tun0 "$_url" 2>/dev/null) || _body=""
	[ -n "$_body" ]
}

# Full health: process + tun + (optional) egress. Grace handled by caller.
vpn_is_healthy() {
	openvpn_running || return 1
	tun0_has_addr || return 1
	# After tun is up, tinyproxy should appear; if missing for long, unhealthy
	if ! tinyproxy_running; then
		return 1
	fi
	egress_ok || return 1
	return 0
}

kill_vpn_stack() {
	echo "OVPN_FAILOVER stopping openvpn + tinyproxy..."
	killall -SIGINT openvpn 2>/dev/null || true
	killall -SIGINT tinyproxy 2>/dev/null || true
	sleep 1
	killall -9 openvpn 2>/dev/null || true
	killall -9 tinyproxy 2>/dev/null || true
	# give kernel a moment to drop tun0
	sleep 1
}

start_vpn_stack() {
	_reason="${1:-start}"
	ensure_auth_txt
	_cur=$(get_current_ovpn)
	if ! pick_ovpn_file "$_cur"; then
		echo "OVPN_FAILOVER no .ovpn candidates in /ovpn"
		return 1
	fi
	remember_current
	write_ovpn_status "$_reason" 0
	echo "Connecting to VPN by $OVPN_FILE (reason=$_reason)"
	# openvpn in background so watchdog can supervise
	openvpn --config "$OVPN_FILE" \
		--data-ciphers "AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-128-CBC" \
		--connect-retry-max 2 \
		--connect-timeout 20 \
		--ping 10 \
		--ping-restart 30 \
		--persist-tun \
		--script-security 2 &
	# tinyproxy waits for tun0
	sh /slave/tinyproxy.sh &
	return 0
}
