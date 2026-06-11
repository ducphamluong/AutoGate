#!/bin/sh

#waiting for ovpn files from master
echo "Sleep 10s"
sleep 10

sh /slave/ovpn.sh &
sh /slave/tinyproxy.sh &
sh /slave/watchdog.sh &

while :
do
	echo "Running.."
	sleep 180
done
