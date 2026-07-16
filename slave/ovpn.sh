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

# ---------------------------------------------------------------------------
# Publish current profile → /ovpn/status/vpnXX.json  (UI + CLI map)
# Worker index from hostname (autogate-ovpn_proxy_00-1) or fixed IP last octet.
# ---------------------------------------------------------------------------
resolve_worker_index() {
	# Prefer explicit env if compose ever sets it
	if [ -n "${WORKER_INDEX:-}" ]; then
		echo "$WORKER_INDEX" | tr -cd '0-9'
		return
	fi
	hn=$(hostname 2>/dev/null || echo "")
	# ...ovpn_proxy_00... or ...ovpn_proxy_0...
	idx=$(echo "$hn" | sed -n 's/.*ovpn_proxy_\([0-9][0-9]*\).*/\1/p')
	if [ -n "$idx" ]; then
		echo "$idx"
		return
	fi
	# compose IPs: vpn00=172.21.0.102 … vpn19=172.21.0.121
	ip=""
	if command -v hostname >/dev/null 2>&1; then
		ip=$(hostname -i 2>/dev/null | awk '{print $1}')
	fi
	if [ -z "$ip" ] && [ -f /proc/net/fib_trie ]; then
		ip=$(ip -4 -o addr show eth0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
	fi
	if [ -n "$ip" ]; then
		last=$(echo "$ip" | awk -F. '{print $4}')
		if [ -n "$last" ] && [ "$last" -ge 102 ] 2>/dev/null; then
			echo $((last - 102))
			return
		fi
	fi
	echo ""
}

write_ovpn_status() {
	idx=$(resolve_worker_index)
	[ -n "$idx" ] || idx="xx"
	# zero-pad 2 digits when numeric
	case "$idx" in
		[0-9]|[0-9][0-9]) name=$(printf "vpn%02d" "$idx"); port=$((56800 + idx)) ;;
		*) name="vpn_unknown"; port=0 ;;
	esac

	base=$(basename "$OVPN_FILE")
	# local_pvl_… → original name in ovpn-list
	local_name="$base"
	case "$base" in
		local_*) local_name=$(echo "$base" | sed 's/^local_//') ;;
	esac

	remote_host=""
	remote_port=""
	proto=""
	# first non-comment remote / proto lines
	remote_line=$(grep -E '^[[:space:]]*remote[[:space:]]+' "$OVPN_FILE" 2>/dev/null | head -1)
	if [ -n "$remote_line" ]; then
		remote_host=$(echo "$remote_line" | awk '{print $2}')
		remote_port=$(echo "$remote_line" | awk '{print $3}')
	fi
	proto_line=$(grep -E '^[[:space:]]*proto[[:space:]]+' "$OVPN_FILE" 2>/dev/null | head -1)
	if [ -n "$proto_line" ]; then
		proto=$(echo "$proto_line" | awk '{print $2}')
	fi
	[ -z "$remote_port" ] && remote_port=$(grep -E '^[[:space:]]*port[[:space:]]+' "$OVPN_FILE" 2>/dev/null | awk '{print $2}' | head -1)

	# escape JSON string fields (minimal)
	json_escape() {
		printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
	}

	ts=$(date +%s 2>/dev/null || echo 0)
	mkdir -p /ovpn/status 2>/dev/null || true
	status_file="/ovpn/status/${name}.json"
	tmp="${status_file}.tmp.$$"

	cat > "$tmp" 2>/dev/null <<EOF
{"worker":"$(json_escape "$name")","index":$([ "$idx" = "xx" ] && echo -1 || echo "$idx"),"port":$port,"file":"$(json_escape "$base")","local_list_file":"$(json_escape "$local_name")","file_path":"$(json_escape "$OVPN_FILE")","remote_host":"$(json_escape "$remote_host")","remote_port":"$(json_escape "$remote_port")","proto":"$(json_escape "$proto")","updated_at":$ts}
EOF
	mv -f "$tmp" "$status_file" 2>/dev/null || cp "$tmp" "$status_file" 2>/dev/null || true
	rm -f "$tmp" 2>/dev/null || true

	# human one-liner for docker logs + tail
	echo "OVPN_MAP worker=$name host_port=$port file=$base local_list=$local_name remote=${remote_host}:${remote_port} proto=${proto:-?}"
}

write_ovpn_status

echo "Connecting to VPN by $OVPN_FILE"

openvpn --config "$OVPN_FILE" --data-ciphers "AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-128-CBC"
