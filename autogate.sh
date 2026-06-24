#!/bin/bash
# AutoGate manager - run inside WSL2 Ubuntu-24.04
# Usage: autogate.sh [COUNTRY] [start|stop|restart|status|logs [service]]
set -u

DIR="/home/ducph/AutoGate"
ACTION="${1:-start}"
EXTRA_ARG="${2:-}"

if [[ "$ACTION" =~ ^[A-Za-z]{2}$ ]]; then
  export COUNTRY_FILTER="${ACTION^^}"
  ACTION="${2:-start}"
  EXTRA_ARG="${3:-}"
elif [[ "${2:-}" =~ ^[A-Za-z]{2}$ ]]; then
  export COUNTRY_FILTER="${2^^}"
  EXTRA_ARG="${3:-}"
fi

if [ -n "${COUNTRY_FILTER:-}" ]; then
  export COUNTRY_FILTER="${COUNTRY_FILTER^^}"
fi

wait_docker() {
  for _ in $(seq 1 40); do
    docker info >/dev/null 2>&1 && return 0
    sleep 1
  done

  echo "[!] Docker daemon chua san sang sau 40s. Kiem tra: systemctl status docker"
  return 1
}

compose() {
  cd "$DIR" && docker compose "$@"
}

case "$ACTION" in
  start)
    echo "[1/3] Doi Docker daemon ..."
    wait_docker || exit 1
    echo "[2/3] docker compose up -d --build ..."
    compose up -d --build
    echo "[3/3] Trang thai container:"
    compose ps --format "table {{.Name}}\t{{.Service}}\t{{.Status}}" 2>/dev/null | head -30
    echo
    if [ -n "${COUNTRY_FILTER:-}" ]; then
      echo "=> Country filter  : $COUNTRY_FILTER"
    fi
    echo "=> Proxy xoay vong: http://localhost:56789"
    echo "=> Stats UI       : http://localhost:2086"
    echo "=> Proxy list UI  : http://localhost:2087"
    echo "=> Worker proxies : http://127.0.0.1:56800 ... http://127.0.0.1:56809"
    echo "=> Test nhanh     : curl -x http://localhost:56789 http://ifconfig.me/ip"
    echo "                    curl -x http://127.0.0.1:56800 http://ifconfig.me/ip"
    echo "   (worker VPN can ~60s de ket noi, watchdog tu heal)"
    ;;
  stop)
    compose down
    echo "=> Da tat stack (data/config van giu nguyen)."
    ;;
  restart)
    compose up -d --build --force-recreate haproxy psiphon001
    compose restart
    if [ -n "${COUNTRY_FILTER:-}" ]; then
      echo "=> Country filter  : $COUNTRY_FILTER"
    fi
    echo "=> Da restart stack."
    ;;
  status)
    compose ps
    ;;
  logs)
    compose logs --tail=30 "${EXTRA_ARG:-haproxy}"
    ;;
  *)
    echo "Cach dung: autogate.sh [COUNTRY] [start|stop|restart|status|logs [service]]"
    echo "  US      - bat stack voi proxy US"
    echo "  start   - bat stack (mac dinh)"
    echo "  restart US - khoi dong lai voi proxy US"
    echo "  stop    - tat stack"
    echo "  status  - xem trang thai"
    echo "  logs    - xem log (vd: logs ovpn_proxy_00)"
    echo "  Proxy UI: http://localhost:2087 de copy proxy list"
    ;;
esac
