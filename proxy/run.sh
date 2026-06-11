#!/bin/sh


haproxy -f /usr/local/etc/haproxy/haproxy.cfg &

while :
do
	python3 /proxy/vpngate.py
	sleep 1800
done
