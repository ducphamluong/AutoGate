#!/bin/sh

echo "Watchdog is running, ROTATING_DELAY = $ROTATING_DELAY"

while :
do
    sleep $ROTATING_DELAY
    echo "Watchdog: killing the current connections..."
    killall -SIGINT openvpn
    killall -SIGINT tinyproxy

    sleep 2
    echo "Watchdog: reconnecting..."
    sh /slave/ovpn.sh &
    sh /slave/tinyproxy.sh &

    sleep 120
    
    #random sleeping
    sleep $((RANDOM % 20))
done
