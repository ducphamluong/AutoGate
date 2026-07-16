FROM alpine
EXPOSE 8080

RUN apk --update add openvpn curl tinyproxy

COPY slave /slave
# COPY ovpn /ovpn

RUN find /slave -type f -exec sed -i 's/\r$//' {} + \
    && find /slave -name "*.sh" -exec chmod +x {} +

# Scheduled IP rotate: OFF by default — keep profile while healthy; only failover on down.
# Set OVPN_ROTATE_ENABLE=1 to force a new random .ovpn every ROTATING_DELAY seconds.
ENV OVPN_ROTATE_ENABLE=0
ENV ROTATING_DELAY=300
# Health probe interval / consecutive fails before auto-switch
ENV OVPN_HEALTH_INTERVAL=8
ENV OVPN_HEALTH_FAILS=2
# Ignore fails this many seconds after (re)connect
ENV OVPN_CONNECT_GRACE=35
# 1 = curl via tinyproxy must succeed (end-to-end); 0 = only process+tun0
ENV OVPN_EGRESS_CHECK=1
ENV OVPN_EGRESS_URL=http://ifconfig.me/ip
ENV OVPN_EGRESS_TIMEOUT=6

CMD /slave/run.sh
