---
title: "Phase 1 — Framework sources + EGRESS_MODE + multi-country + auth"
status: completed
effort: 4h
priority: P1
---

# Phase 1: Framework + EGRESS_MODE + locale + auth

## Context

- Brainstorm: [reports/brainstorm-multi-source-ovpn.md](./reports/brainstorm-multi-source-ovpn.md)
- Plan: [plan.md](./plan.md)
- Baseline: `proxy/vpngate.py`, `proxy/run.sh`, `slave/ovpn.sh`, `autogate.sh`

## Overview

Refactor fetcher thành multi-source framework; port VPNGate vào adapter; thêm EGRESS_MODE; multi-country CLI; inject auth mặc định.

## Requirements

1. Module structure (giữ file mỏng, kebab-case nếu split):

```text
proxy/
  ovpn_refresh.py              # entry (thay vpngate.py main)
  ovpn_sources/
    __init__.py
    base.py                    # OvpnConfig + Source protocol
    country_map.py             # name/ISO normalize
    vpngate.py                 # port logic cũ
```

2. `OvpnConfig` fields tối thiểu: `source`, `name`, `country` (ISO2), `body`, `remote_host`, `remote_port` (optional parse), `needs_auth`.

3. Orchestrator:
   - Read `OVPN_SOURCES` (default `vpngate`)
   - Fetch từng source (try/except log, continue)
   - Filter `COUNTRY_FILTER` set
   - Dedupe by `(remote_host, remote_port)` nếu parse được; else by filename
   - Cap `MAX_OVPN_CONFIGS`
   - Atomic replace `/ovpn` (temp dir + swap như hiện tại)
   - Nếu **total written == 0** → raise (giữ fail nếu pool trống); nếu partial sources fail nhưng có files → OK

4. Auth prep:
   - Ghi `/ovpn/auth.txt` hoặc per-config auth path với `OVPN_DEFAULT_USER`/`PASS`
   - Nếu body có `auth-user-pass` không path → rewrite thành `auth-user-pass /ovpn/auth.txt`
   - Nếu body không có auth nhưng SoftEther-style free lists thường cần → optional detect later; phase 1: chỉ rewrite khi directive đã có

5. `slave/ovpn.sh`:
   - Vẫn random `/ovpn/*.ovpn` nhưng **exclude** `auth.txt` và non-`.ovpn`
   - Giữ data-ciphers flag

6. `proxy/run.sh` EGRESS_MODE:
   - **Bỏ** side-effect “COUNTRY_FILTER xóa warp/proxy001”
   - Build backend list theo mode:

| Mode | Keep |
|------|------|
| `all` | warp, proxy001, psiphon001, vpn* |
| `ovpn` | vpn* only |
| `ovpn+psiphon` | vpn* + psiphon001 |
| `ovpn+warp` | vpn* + warp |
| `custom` | ENABLE_WARP / ENABLE_PROXYBROKER / ENABLE_PSIPHON / ENABLE_OVPN |

   - Implement: sed/delete server lines không enable; hoặc generate backend block
   - Psiphon `EGRESS_REGION`: có thể map first country from COUNTRY_FILTER (optional keep current)

7. CLI `autogate.sh` / `autogate.bat`:
   - Parse multi-country: `US,JP` → `COUNTRY_FILTER=US,JP`
   - Optional 3rd positional or flag for mode: `ovpn` | `all` | …
   - Export `EGRESS_MODE`, `COUNTRY_FILTER`, `PROXY_WORKER_COUNT`
   - Tránh conflict với subcommands `stop|restart|status|logs`

### CLI grammar (KISS)

```text
autogate.sh [start|restart|stop|status|logs [svc]] [COUNTRIES] [PORTS] [EGRESS_MODE]
# examples
autogate.sh start US,JP 10 ovpn
autogate.sh restart KR 5 all
autogate.sh stop
```

Windows bat forward args y hệt.

8. `docker-compose.yml`:
   - Pass env vào `haproxy`: `OVPN_SOURCES`, `EGRESS_MODE`, `MAX_OVPN_CONFIGS`, `OVPN_DEFAULT_*`, `COUNTRY_FILTER`, `PROXY_WORKER_COUNT`
   - Optional: profile/scale không bắt buộc phase 1

9. Backward compat:
   - `vpngate.py` có thể thin-wrap `ovpn_refresh.main()` hoặc update `run.sh` gọi `ovpn_refresh.py`
   - Default behavior không set mode ≈ `all` (như stack cũ full backends)
   - Default sources = `vpngate` only until phase 2 enables ipspeed default

## Implementation steps

1. Extract VPNGate fetch/write → `ovpn_sources/vpngate.py` + `base.py` + `country_map.py`
2. Write `ovpn_refresh.py` orchestrator
3. Update `run.sh` call + EGRESS_MODE backend filter
4. Update `ovpn.sh` exclude non-config files; auth path support
5. Wire compose env + autogate.sh/bat parse
6. Manual smoke: `COUNTRY_FILTER=JP` refresh writes only JP; `EGRESS_MODE=ovpn` config không còn server warp

## Todo checklist

- [ ] `proxy/ovpn_sources/base.py`
- [ ] `proxy/ovpn_sources/country_map.py`
- [ ] `proxy/ovpn_sources/vpngate.py`
- [ ] `proxy/ovpn_refresh.py`
- [ ] Update `proxy/run.sh` EGRESS_MODE
- [ ] Update `slave/ovpn.sh` auth + file filter
- [ ] `docker-compose.yml` env
- [ ] `autogate.sh` / `autogate.bat` multi-country + mode
- [ ] Smoke: filter + mode

## Risks

| Risk | Mitigation |
|------|------------|
| sed HAProxy brittle | Prefer explicit allowlist of server names to delete |
| Country map incomplete | Extend map when new sources land |
| Breaking old COUNTRY_FILTER auto-strip | Document; users set `EGRESS_MODE=ovpn` explicitly |

## Success criteria

- VPNGate-only path vẫn fill `/ovpn` như cũ
- `EGRESS_MODE=ovpn` → `haproxy -c` OK; no warp/proxy001/psiphon lines in runtime cfg
- `COUNTRY_FILTER=US,JP` multi work
- Refresh fail soft per-source (VPNGate still only source → fail if VPNGate down, same as today)

## Rollback

Revert to single `vpngate.py` call + old sed COUNTRY_FILTER behavior.
