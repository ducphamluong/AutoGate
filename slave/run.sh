#!/bin/sh

# Wait for master to populate /ovpn/*.ovpn
echo "Sleep 10s (wait for ovpn pool)..."
sleep 10

# shellcheck source=/dev/null
. /slave/ovpn-common.sh

# Ensure status dir exists on shared volume
mkdir -p /ovpn/status 2>/dev/null || true

echo "Boot: starting OpenVPN + tinyproxy + health watchdog (auto-failover on down)"
export OVPN_START_REASON=start
sh /slave/ovpn.sh &
sh /slave/tinyproxy.sh &
sh /slave/watchdog.sh &

while :; do
	echo "Running.. (failover on down; rotate only if OVPN_ROTATE_ENABLE=1)"
	sleep 180
done
