FROM alpine
EXPOSE 8080

RUN apk --update add openvpn curl tinyproxy

COPY slave /slave
# COPY ovpn /ovpn

RUN find /slave -type f -exec sed -i 's/\r$//' {} + \
    && find /slave -name "*.sh" -exec chmod +x {} +

# Force new random OVPN profile on this interval (seconds)
ENV ROTATING_DELAY=60
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
