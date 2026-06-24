#!/bin/bash
# AutoGate manager - run inside WSL2 Ubuntu-24.04
# Usage: autogate.sh [COUNTRY] [start|stop|restart|status|logs [service]] [PORT_COUNT]
set -u

DIR="${AUTOGATE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
ACTION="start"
EXTRA_ARG=""
MAX_WORKER_COUNT=20
PROXY_WORKER_COUNT="${PROXY_WORKER_COUNT:-10}"

parse_args() {
  for arg in "$@"; do
    if [[ "$arg" =~ ^[A-Za-z]{2}$ ]]; then
      export COUNTRY_FILTER="${arg^^}"
    elif [[ "$arg" =~ ^[0-9]+$ ]]; then
      PROXY_WORKER_COUNT="$arg"
    elif [[ "$arg" =~ ^(start|stop|restart|status|logs)$ ]]; then
      ACTION="$arg"
    elif [ "$ACTION" = "logs" ]; then
      EXTRA_ARG="$arg"
    else
      EXTRA_ARG="$arg"
    fi
  done
}

parse_args "$@"

if [ -n "${COUNTRY_FILTER:-}" ]; then
  export COUNTRY_FILTER="${COUNTRY_FILTER^^}"
fi

if ! [[ "$PROXY_WORKER_COUNT" =~ ^[0-9]+$ ]] || [ "$PROXY_WORKER_COUNT" -lt 1 ] || [ "$PROXY_WORKER_COUNT" -gt "$MAX_WORKER_COUNT" ]; then
  echo "[!] PORT_COUNT phai trong khoang 1..$MAX_WORKER_COUNT"
  exit 1
fi

export PROXY_WORKER_COUNT

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

worker_port_range() {
  last_port=$((56800 + PROXY_WORKER_COUNT - 1))
  if [ "$PROXY_WORKER_COUNT" -eq 1 ]; then
    echo "http://127.0.0.1:56800"
  else
    echo "http://127.0.0.1:56800 ... http://127.0.0.1:$last_port"
  fi
}

case "$ACTION" in
  start)
    echo "[1/3] Doi Docker daemon ..."
    wait_docker || exit 1
    echo "[2/3] docker compose up -d --build ..."
    compose up -d --build --remove-orphans
    echo "[3/3] Trang thai container:"
    compose ps --format "table {{.Name}}\t{{.Service}}\t{{.Status}}" 2>/dev/null | head -30
    echo
    if [ -n "${COUNTRY_FILTER:-}" ]; then
      echo "=> Country filter  : $COUNTRY_FILTER"
    fi
    echo "=> Proxy xoay vong: http://localhost:56789"
    echo "=> Stats UI       : http://localhost:2086"
    echo "=> Proxy list UI  : http://localhost:2087"
    echo "=> Worker count   : $PROXY_WORKER_COUNT"
    echo "=> Worker proxies : $(worker_port_range)"
    echo "=> Test nhanh     : curl -x http://localhost:56789 http://ifconfig.me/ip"
    echo "                    curl -x http://127.0.0.1:56800 http://ifconfig.me/ip"
    echo "   (worker VPN can ~60s de ket noi, watchdog tu heal)"
    ;;
  stop)
    compose down
    echo "=> Da tat stack (data/config van giu nguyen)."
    ;;
  restart)
    echo "[1/2] Doi Docker daemon ..."
    wait_docker || exit 1
    echo "[2/2] docker compose up -d --build --force-recreate ..."
    compose up -d --build --force-recreate --remove-orphans
    if [ -n "${COUNTRY_FILTER:-}" ]; then
      echo "=> Country filter  : $COUNTRY_FILTER"
    fi
    echo "=> Worker count   : $PROXY_WORKER_COUNT"
    echo "=> Worker proxies : $(worker_port_range)"
    echo "=> Proxy list UI  : http://localhost:2087"
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
    echo "  US 10   - bat stack US voi 10 worker ports (56800-56809)"
    echo "  20      - bat stack voi 20 worker ports (56800-56819)"
    echo "  start   - bat stack (mac dinh)"
    echo "  restart US - khoi dong lai voi proxy US"
    echo "  restart US 5 - khoi dong lai voi 5 worker ports"
    echo "  stop    - tat stack"
    echo "  status  - xem trang thai"
    echo "  logs    - xem log (vd: logs ovpn_proxy_00)"
    echo "  Proxy UI: http://localhost:2087 de copy proxy list"
    ;;
esac
