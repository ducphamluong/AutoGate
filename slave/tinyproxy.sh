#!/bin/sh

echo "Running Tinyproxy HTTP proxy server."

until ip link show tun0 2>&1 | grep -qv "does not exist"; do
    echo 'Tunnel not found, sleep...'
    sleep 2
done

function get_addr {
   echo $(ip a show dev $1 | grep inet | cut -d " " -f 6 | cut -d "/" -f 1)
} 

addr_eth=${LISTEN_ON:-$(get_addr eth0)}
addr_tun=$(get_addr tun0)
sed -i \
    -e "/Listen/c Listen $addr_eth" \
    -e "/Bind/c Bind $addr_tun" \
    /slave/tinyproxy.conf


echo "Found tun0 interface. Starting tinyproxy"

tinyproxy -c "/slave/tinyproxy.conf"
