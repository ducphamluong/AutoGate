FROM alpine
EXPOSE 8080

RUN apk --update add openvpn curl tinyproxy

COPY slave /slave
# COPY ovpn /ovpn

RUN find /slave -type f -exec sed -i 's/\r$//' {} + \
    && find /slave -name "*.sh" -exec chmod +x {} +

ENV ROTATING_DELAY=60


CMD /slave/run.sh
