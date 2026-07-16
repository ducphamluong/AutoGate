# AutoGate

AutoGate is a Docker-based **rotating proxy gateway** that aggregates multiple outbound paths—VPN (OpenVPN via VPNGate), Cloudflare WARP, Psiphon, and public HTTP/HTTPS proxies—and exposes them through a single HAProxy entry point with automatic rotation.

It is intended for **authorized security research, penetration testing, security product evaluation, SEO tooling validation, deployment testing, and controlled system access** in environments where you have explicit permission to test.

> **Important:** Use AutoGate only on systems and networks you own or are explicitly authorized to test. Unauthorized access is illegal.

---

## Features

- **Rotating proxy pool** — HAProxy round-robin across 20+ OpenVPN-backed tinyproxy instances, WARP, Psiphon, and ProxyBroker2
- **Psiphon egress** — Censorship-circumvention tunnel exposing a local HTTP/SOCKS proxy as an additional egress path
- **Multi-source OpenVPN refresh** — Pulls profiles from VPNGate + IPSpeed (optional OpenProxyList / PublicVPNList)
- **EGRESS_MODE profiles** — Choose which backends HAProxy rotates (`all`, `ovpn`, `ovpn+psiphon`, `ovpn+warp`, `custom`)
- **Multi-country locale filter** — `COUNTRY_FILTER=US,JP` filters OpenVPN pool only (ISO2)
- **Connection rotation** — Watchdog reconnects VPN and proxy per container on a configurable interval (`ROTATING_DELAY`)
- **Multiple egress paths** — Combine VPN, WARP, and scraped public proxies for diverse IP/geo testing
- **Stats dashboard** — HAProxy stats UI for backend health monitoring
- **Copyable proxy list UI** — Mở trang `http://127.0.0.1:2087` để xem/copy proxy xoay vòng và các proxy worker riêng
- **Containerized** — Single `docker-compose` stack, reproducible deployments

---

## Use Cases

| Area | How AutoGate helps |
|------|-------------------|
| **Penetration testing** | Route traffic through varied egress IPs to test geo/IP-based controls, rate limits, and WAF rules |
| **Security solution testing** | Validate SIEM, firewall, proxy, and DLP behavior against rotating outbound sources |
| **SEO & web tooling** | Test crawlers, rank checkers, and geo-targeted content from different network perspectives (with permission) |
| **Deployments & access** | Smoke-test applications behind proxies, verify remote access paths, and validate multi-region behavior |

---

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │           HAProxy (haproxy)          │
                    │  :9999  rotating HTTP proxy (frontend)│
                    │  :10000 stats UI                     │
                    │  :2087  proxy list UI                │
                    └──────────────┬──────────────────────┘
                                   │ round-robin
    ┌────────────────────┬────────────┼────────────┬─────────────────────┐
    ▼                    ▼            ▼            ▼                     ▼
┌───────────┐    ┌────────────┐ ┌───────────┐ ┌────────────┐    ┌──────────────┐
│   WARP    │    │ ProxyBroker│ │  Psiphon  │ │  (future)  │    │ ovpn_proxy   │
│  :1080    │    │  proxy001  │ │ psiphon001│ │            │    │ 00 … 19      │
└───────────┘    │  :8888     │ │  :8080    │ └────────────┘    │ OpenVPN +    │
                 └────────────┘ └───────────┘                   │ tinyproxy    │
                                                                │ :8080 each   │
                                                                └──────┬───────┘
                                                                       │
                         ovpn_refresh.py (master) ──► /ovpn/*.ovpn ◄─┘
                         (multi-source; default every 30 min)
```

### Components

| Service | Role |
|---------|------|
| `haproxy` | Front door; balances traffic across all backends |
| `warp` | Cloudflare WARP SOCKS proxy |
| `proxy001` | ProxyBroker2 — discovers and serves high-anonymity HTTP/HTTPS proxies |
| `psiphon001` | Psiphon ConsoleClient — circumvention tunnel exposing a local HTTP proxy (`:8080`) / SOCKS proxy (`:1080`) |
| `ovpn_proxy_00` … `ovpn_proxy_19` | OpenVPN client + tinyproxy; rotates VPN endpoint on watchdog schedule |
| `restarter` | Periodically restarts `proxy001` to refresh the proxy pool |

Trang proxy list UI chạy trong container `haproxy` và đọc HAProxy stats nội bộ để hiển thị trạng thái `UP` / `DOWN` / `UNKNOWN` cho các cổng worker.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- Linux host with `/dev/net/tun` available (required for OpenVPN)
- Sufficient RAM/CPU for ~25 containers (adjust replica count in `docker-compose.yml` if needed)
- **Legal authorization** for all testing activities

---

## Quick Start

1. Clone the repository:

   ```bash
   git clone https://github.com/TinyActive/AutoGate
   cd AutoGate
   ```

2. Create the shared OpenVPN config directory:

   ```bash
   mkdir -p ovpn data psiphon_data
   ```

3. Build and start the stack:

   ```bash
   docker-compose up --build --force-recreate -d
   ```

4. Wait for VPN configs to download (first run may take ~30 seconds before `ovpn/` is populated).

5. Use the rotating proxy:

   ```bash
   curl -x http://127.0.0.1:56789 http://ifconfig.me
   ```

6. Mở danh sách proxy có nút copy:

   ```text
   http://127.0.0.1:2087
   ```

---

## Ports (default host mapping)

| Host port | Container | Description |
|-----------|-----------|-------------|
| `56789` | `haproxy:9999` | Rotating HTTP proxy, bind local-only trên `127.0.0.1` |
| `2086` | `haproxy:10000` | HAProxy stats UI, bind local-only trên `127.0.0.1` |
| `2087` | `haproxy:2087` | Proxy list UI để copy nhanh các proxy URL, bind local-only trên `127.0.0.1` |
| `56800-56819` | `haproxy:56800-56819` | Dedicated worker proxies qua HAProxy, bind local-only trên `127.0.0.1` |

Internal services use the `172.21.0.0/24` custom network defined in `docker-compose.yml`.

Ví dụ dùng worker proxy riêng:

```bash
curl -x http://127.0.0.1:56800 http://ifconfig.me
curl -x http://127.0.0.1:56809 http://ifconfig.me
```

Mỗi cổng worker giữ nguyên URL nhưng worker phía sau vẫn tự xoay VPN theo `ROTATING_DELAY`.

Số lượng worker port có thể chọn khi chạy script:

```bat
autogate.bat US 5
autogate.bat US,JP 10 ovpn
autogate.bat US 20 all
```

Quy ước port:

```text
5 port  = 56800-56804
10 port = 56800-56809
20 port = 56800-56819
```

CLI grammar:

```text
autogate.bat [start|restart|stop|status|logs] [COUNTRIES] [PORTS] [EGRESS_MODE]
```

---

## Configuration

See [`.env.example`](.env.example) (full sample) and local [`.env`](.env) (copy/edit).  
`OVPN_SOURCES` lists enabled OpenVPN fetchers — default sample is **all four remote**:

```text
OVPN_SOURCES=vpngate,ipspeed,openproxylist,publicvpnlist
```

### Local `ovpn-list/` (ưu tiên)

1. Tạo/thả file vào `./ovpn-list/*.ovpn` **hoặc tải từ PublicVPNList** (host, ngoài Docker):

```powershell
# tải list .ovpn về .\ovpn-list
# Mặc định: TCP live/die TRƯỚC, rồi mới download file còn sống
.\download_publicvpnlist.bat JP 100
python download_publicvpnlist.py --country JP --max 100
# tắt precheck (không khuyến nghị):
python download_publicvpnlist.py --country JP --max 100 --no-precheck
```

Downloader **không xóa** folder `ovpn-list` hay file cũ — chỉ thêm/ghi đè theo tên file tải được.

2. Nếu folder **có** `.ovpn` và **TCP live-check** (host:port) pass → master **chỉ** dùng local (bỏ remote scrapers).
3. Worker random trong `./ovpn` — muốn **đúng 1 file**: để **1** file trong `ovpn-list/`.

```env
OVPN_LIST_PRIORITY=1
OVPN_LIST_LIVE_CHECK=1
OVPN_LIVE_CHECK_TIMEOUT=3
```

PublicVPNList trong stack (`OVPN_SOURCES=...publicvpnlist`) cũng tự fetch khi refresh; script `download_publicvpnlist.*` dùng khi muốn **đổ sẵn** vào `ovpn-list` rồi pin local.

Tắt source remote: xóa tên khỏi `OVPN_SOURCES` trong `.env`.

### VPN rotation interval

Set `ROTATING_DELAY` (seconds) on ovpn slave containers via `Dockerfile` / compose `environment`:

```dockerfile
ENV ROTATING_DELAY=60
```

The watchdog kills and reconnects OpenVPN + tinyproxy on this interval.

### OpenVPN multi-source refresh

`proxy/ovpn_refresh.py` (legacy entry: `proxy/vpngate.py`) merges configs from enabled sources into `./ovpn`. Interval: `OVPN_REFRESH_SECONDS` (default **1800**).

| `OVPN_SOURCES` key | Status | Notes |
|--------------------|--------|-------|
| `vpngate` | default | CSV API, reliable backbone |
| `ipspeed` | default | HTML + direct `.ovpn` URLs |
| `openproxylist` | optional | Download free; **list** needs reCAPTCHA v3 score via real browser (Playwright/Camoufox) or `OPENPROXYLIST_IDS` |
| `publicvpnlist` | optional | Catalog `vpn-data.php` + short-lived `get_token.php` (300s); cap per country |

Other knobs: `MAX_OVPN_CONFIGS` (default 80), `OVPN_DEFAULT_USER` / `OVPN_DEFAULT_PASS` (default `vpn`/`vpn`) for SoftEther-style `auth-user-pass`.

> **Trust model:** free public VPN endpoints are untrusted and ephemeral. Use only for authorized testing; prefer your own infrastructure for sensitive work.

### EGRESS_MODE (HAProxy backends)

**Migration:** `COUNTRY_FILTER` no longer auto-removes `warp` / `proxy001`. Use `EGRESS_MODE` instead.

| Mode | Backends kept |
|------|----------------|
| `all` (default) | warp + proxy001 + psiphon001 + vpn* |
| `ovpn` | vpn* only |
| `ovpn+psiphon` | vpn* + psiphon001 |
| `ovpn+warp` | vpn* + warp |
| `custom` | `ENABLE_WARP` / `ENABLE_PROXYBROKER` / `ENABLE_PSIPHON` / `ENABLE_OVPN` |

```bat
autogate.bat US,JP 10 ovpn
```

### Country filter (locale only)

Set `COUNTRY_FILTER` for the **OpenVPN pool only** (default `all` = mọi nước).

```bash
# default in .env
COUNTRY_FILTER=all

# one or multi ISO2:
COUNTRY_FILTER=JP docker compose up -d --build
COUNTRY_FILTER=US,JP EGRESS_MODE=ovpn docker compose up -d --build
```

On Windows:

```bat
autogate.bat US
autogate.bat US,JP 10 ovpn
autogate.bat restart KR 5 all
```

When `COUNTRY_FILTER` is set:

- All enabled OVPN sources are filtered to those ISO2 codes (names normalized where needed).
- Psiphon gets the **first** code as `EGRESS_REGION` (`PSIPHON_EGRESS_REGION`).
- HAProxy backends are **not** changed by the filter alone — set `EGRESS_MODE`.

### Scale VPN workers

Duplicate or remove `ovpn_proxy_XX` service blocks in `docker-compose.yml` and add matching `server vpnXX` entries in `proxy/haproxy.cfg`.

`autogate.sh` truyền `PROXY_WORKER_COUNT` cho HAProxy. Khi container `haproxy` khởi động, `proxy/run.sh` tự sinh frontend `56800 + worker_index` cho từng worker được chọn. Repo hiện có sẵn `ovpn_proxy_00` đến `ovpn_proxy_19`, nên số lượng hợp lệ là `1..20`.

### Cloudflare WARP

Optional `WARP_LICENSE_KEY` can be set on the `warp` service. See [caomingjun/warp](https://hub.docker.com/r/caomingjun/warp) for details.

### Psiphon

The `psiphon001` service builds the [Psiphon ConsoleClient](https://github.com/Psiphon-Labs/psiphon-tunnel-core) from source (`PsiphonDockerfile`) and runs it with the public Psiphon network config in `psiphon/psiphon.config`. It establishes a tunnel and exposes a local HTTP proxy on `:8080` (and SOCKS on `:1080`) that HAProxy chains to like any other backend.

Tunable via `environment` on the service (all optional):

| Variable | Description | Default |
|----------|-------------|---------|
| `EGRESS_REGION` | Pin egress country (e.g. `SG`, `JP`, `US`); empty = fastest/any | empty |
| `DEVICE_REGION` | Client device region hint | empty |
| `HTTP_PORT` | Local HTTP proxy port | `8080` |
| `SOCKS_PORT` | Local SOCKS proxy port | `1080` |
| `CONFIG_URL` | Auto-fetch a fresh config from this URL; empty = always use bundled standard config | empty |
| `CONFIG_REFRESH_INTERVAL` | Seconds between config re-checks when `CONFIG_URL` is set (`0` = off) | `21600` |
| `HEALTHCHECK_URL` | URL the healthcheck fetches *through* the proxy to prove egress | `https://www.google.com/generate_204` |

Build a specific Psiphon version by overriding the `PSIPHON_VERSION` build arg in `PsiphonDockerfile`. Tunnel state persists in `./psiphon_data`.

#### Self-healing / auto-updating config

`psiphon/psiphon.config` is the bundled, read-only **standard** config. The runtime config the client actually uses is **rebuilt from a validated source on every start**, so:

- **Auto-revert to standard** — if the runtime config in `./psiphon_data` is manually edited or corrupted, it is regenerated from the bundled standard config on the next (re)start. No manual cleanup needed.
- **Auto-fetch newer config** — set `CONFIG_URL` to a JSON config endpoint. On start (and every `CONFIG_REFRESH_INTERVAL` seconds) the client downloads it, validates it's well-formed JSON with the required keys (`PropagationChannelId`, `SponsorId`, `RemoteServerListSignaturePublicKey`), and uses it. Any failure (unreachable, bad JSON, missing keys) **falls back to the bundled standard config**. When a newer config is detected, Psiphon is restarted (`restart: always`) to apply it.
- **Note:** Psiphon already refreshes its *server list* automatically at runtime via the remote/obfuscated server-list URLs embedded in the config — so day-to-day server changes need no config update. `CONFIG_URL` is only needed for the rare case where the bootstrap parameters (channel/sponsor IDs, signature key) change.

#### Healthcheck

The container ships a Docker `HEALTHCHECK` that issues a request **through the local HTTP proxy** (not just a port check), so it only reports healthy once the tunnel can actually carry traffic. Inspect with `docker ps` (STATUS column) or `docker inspect --format '{{.State.Health.Status}}' psiphon001`.

---

## Project Layout

```
AutoGate/
├── docker-compose.yml      # Full stack definition
├── Dockerfile              # OpenVPN + tinyproxy slave image
├── HaproxyDockerfile       # HAProxy + vpngate fetcher
├── PsiphonDockerfile       # Psiphon ConsoleClient build + runtime image
├── proxy/
│   ├── haproxy.cfg         # Load balancer config
│   ├── ovpn_refresh.py     # Multi-source OpenVPN refresh orchestrator
│   ├── ovpn_sources/       # Source adapters (vpngate, ipspeed, …)
│   ├── vpngate.py          # Thin legacy wrapper → ovpn_refresh
│   └── run.sh              # HAProxy + EGRESS_MODE + periodic refresh
├── psiphon/
│   ├── psiphon.config      # Bundled standard Psiphon config (ports, server list)
│   ├── run.sh              # Entrypoint: build/validate config + auto-update + launch
│   └── healthcheck.sh      # Tunnel healthcheck (request through the proxy)
├── slave/
│   ├── run.sh              # Slave entrypoint
│   ├── ovpn.sh             # Random OpenVPN connect
│   ├── tinyproxy.sh        # HTTP proxy bound to tun0
│   ├── watchdog.sh         # Periodic VPN/proxy rotation
│   └── tinyproxy.conf      # Tinyproxy settings
├── ovpn/                   # Shared OpenVPN configs (created at runtime)
├── psiphon_data/           # Psiphon tunnel state (created at runtime)
└── data/                   # WARP persistent data
```

---

## Troubleshooting

- **Empty `ovpn/` folder** — Ensure the `haproxy` container can reach `www.vpngate.net`. Check logs: `docker logs haproxy`.
- **Proxy returns errors** — Inspect HAProxy stats at `http://localhost:2086/` for backend `DOWN` states.
- **OpenVPN fails** — VPNGate endpoints are public and ephemeral; rotation will try another config on the next watchdog cycle.
- **High resource usage** — Reduce the number of `ovpn_proxy_*` services in compose.

---

## Third-Party Services & Dependencies

AutoGate integrates with external and third-party components, including:

- [VPNGate](http://www.vpngate.net/) — public VPN relay list (subject to their terms)
- [Cloudflare WARP](https://www.cloudflare.com/warp/) — optional egress path
- [Psiphon](https://github.com/Psiphon-Labs/psiphon-tunnel-core) — open-source censorship-circumvention tunnel (subject to their terms)
- [ProxyBroker2](https://github.com/bluet/proxybroker2) — public proxy discovery
- OpenVPN, HAProxy, tinyproxy — open-source software

You are responsible for complying with the terms of all upstream services and applicable laws.

---

## Disclaimer

AutoGate is provided **as-is** for legitimate, authorized testing and education. The authors and contributors **do not** endorse or accept responsibility for misuse, including but not limited to unauthorized access, fraud, spam, evasion of lawful controls, or any activity that violates **Vietnamese law** or **applicable international law**.

Always obtain written permission before testing systems you do not own.

---

## License

This project is released under a **Non-Commercial Educational License**. See [LICENSE](LICENSE) for full terms.

Commercial use, monetization, or integration into paid products/services **requires prior written authorization** from the copyright holder.
