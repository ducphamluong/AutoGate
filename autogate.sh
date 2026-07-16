#!/bin/bash
# AutoGate manager - run inside WSL2 Ubuntu-24.04
# Usage:
#   autogate.sh [start|restart|stop|status|logs [svc]] [COUNTRIES] [PORTS] [EGRESS_MODE]
# Examples:
#   autogate.sh start US,JP 10 ovpn
#   autogate.sh restart KR 5 all
#   autogate.sh stop
set -u

DIR="${AUTOGATE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
ACTION="start"
EXTRA_ARG=""
MAX_WORKER_COUNT=20
PROXY_WORKER_COUNT="${PROXY_WORKER_COUNT:-10}"
EGRESS_MODE="${EGRESS_MODE:-all}"
export COMPOSE_PARALLEL_LIMIT="${COMPOSE_PARALLEL_LIMIT:-2}"

is_egress_mode() {
  case "$1" in
    all|ovpn|ovpn+psiphon|ovpn+warp|custom) return 0 ;;
    *) return 1 ;;
  esac
}

# Country token: single ISO2 or comma-separated list (US,JP,KR)
is_country_token() {
  local token="$1"
  [[ "$token" =~ ^[A-Za-z]{2}(,[A-Za-z]{2})*$ ]]
}

parse_args() {
  for arg in "$@"; do
    if is_egress_mode "$arg"; then
      EGRESS_MODE="$arg"
    elif [[ "$arg" =~ ^[0-9]+$ ]]; then
      PROXY_WORKER_COUNT="$arg"
    elif [[ "$arg" =~ ^(start|stop|restart|status|logs|help|-h|--help)$ ]]; then
      ACTION="$arg"
    elif is_country_token "$arg"; then
      export COUNTRY_FILTER="$(echo "$arg" | tr '[:lower:]' '[:upper:]')"
    elif [ "$ACTION" = "logs" ]; then
      EXTRA_ARG="$arg"
    else
      EXTRA_ARG="$arg"
    fi
  done
}

parse_args "$@"

if [ -n "${COUNTRY_FILTER:-}" ]; then
  # Normalize each ISO2 part to uppercase
  COUNTRY_FILTER="$(echo "$COUNTRY_FILTER" | tr '[:lower:]' '[:upper:]')"
  export COUNTRY_FILTER
  # Psiphon accepts a single region — use first country from the filter
  if [ -z "${PSIPHON_EGRESS_REGION:-}" ]; then
    export PSIPHON_EGRESS_REGION="${COUNTRY_FILTER%%,*}"
  fi
fi

if ! [[ "$PROXY_WORKER_COUNT" =~ ^[0-9]+$ ]] || [ "$PROXY_WORKER_COUNT" -lt 1 ] || [ "$PROXY_WORKER_COUNT" -gt "$MAX_WORKER_COUNT" ]; then
  echo "[!] PORT_COUNT phai trong khoang 1..$MAX_WORKER_COUNT"
  exit 1
fi

if ! is_egress_mode "$EGRESS_MODE"; then
  echo "[!] EGRESS_MODE khong hop le: $EGRESS_MODE"
  echo "    Hop le: all | ovpn | ovpn+psiphon | ovpn+warp | custom"
  exit 1
fi

export PROXY_WORKER_COUNT
export EGRESS_MODE
export OVPN_SOURCES="${OVPN_SOURCES:-vpngate,ipspeed}"
export MAX_OVPN_CONFIGS="${MAX_OVPN_CONFIGS:-80}"
export OVPN_REFRESH_SECONDS="${OVPN_REFRESH_SECONDS:-1800}"
export OVPN_DEFAULT_USER="${OVPN_DEFAULT_USER:-vpn}"
export OVPN_DEFAULT_PASS="${OVPN_DEFAULT_PASS:-vpn}"

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

print_runtime_info() {
  if [ -n "${COUNTRY_FILTER:-}" ]; then
    echo "=> Country filter  : $COUNTRY_FILTER"
  fi
  echo "=> Egress mode     : $EGRESS_MODE"
  echo "=> OVPN sources    : $OVPN_SOURCES"
  echo "=> Proxy xoay vong: http://localhost:56789"
  echo "=> Stats UI       : http://localhost:2086"
  echo "=> Proxy list UI  : http://localhost:2087"
  echo "=> Worker count   : $PROXY_WORKER_COUNT"
  echo "=> Worker proxies : $(worker_port_range)"
  echo "=> Test nhanh     : curl -x http://localhost:56789 http://ifconfig.me/ip"
  echo "                    curl -x http://127.0.0.1:56800 http://ifconfig.me/ip"
  echo "   (worker VPN can ~60s de ket noi, watchdog tu heal)"
  echo
  echo "   Migration: COUNTRY_FILTER chi loc file .ovpn — khong con tu dong tat warp/proxy."
  echo "   Muon chi OpenVPN: them mode 'ovpn' (vd: autogate.sh US,JP 10 ovpn)"
}

print_help() {
  cat <<'EOF'
Cach dung:
  autogate.sh [start|restart|stop|status|logs [service]] [COUNTRIES] [PORTS] [EGRESS_MODE]

Vi du:
  US,JP 10 ovpn     - multi-country OpenVPN only, 10 worker ports
  US 10             - filter US, mode mac dinh all (warp+proxy+psiphon+ovpn)
  start KR 5 all    - 5 workers, full egress
  restart JP ovpn+psiphon
  stop | status | logs haproxy

EGRESS_MODE:
  all            warp + proxy001 + psiphon + vpn*   (mac dinh)
  ovpn           chi vpn*
  ovpn+psiphon   vpn* + psiphon
  ovpn+warp      vpn* + warp
  custom         dung ENABLE_WARP / ENABLE_PROXYBROKER / ENABLE_PSIPHON / ENABLE_OVPN

Env bo sung (optional):
  OVPN_SOURCES=vpngate,ipspeed[,openproxylist][,publicvpnlist]
  MAX_OVPN_CONFIGS=80
  OVPN_DEFAULT_USER=vpn  OVPN_DEFAULT_PASS=vpn

Proxy UI: http://localhost:2087
EOF
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
    print_runtime_info
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
    echo
    print_runtime_info
    echo "=> Da restart stack."
    ;;
  status)
    compose ps
    ;;
  logs)
    compose logs --tail=30 "${EXTRA_ARG:-haproxy}"
    ;;
  help|-h|--help)
    print_help
    ;;
  *)
    print_help
    ;;
esac
