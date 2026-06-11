#!/bin/sh

echo "Starting vpn service..."



# check ovpn config
OVPN_FILE=$(shuf -n1 -e /ovpn/*.ovpn)

echo "Connecting to VPN by $OVPN_FILE"

openvpn --config $OVPN_FILE --data-ciphers "AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-128-CBC"
#openvpn --config $OVPN_FILE --daemon

