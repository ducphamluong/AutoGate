---
title: "Multi-source OpenVPN + EGRESS_MODE + multi-country locale"
description: "Adapter nhiều nguồn .ovpn, profile egress linh hoạt, filter ISO2 multi-country; scrape verify bằng Chrome khi cần."
status: pending
priority: P1
effort: 14h
branch: main
tags: [feature, infra, ovpn, proxy, refactor]
created: 2026-07-16
---

# Multi-source OpenVPN + EGRESS_MODE + locale

## Overview

Mở rộng AutoGate: fetch OpenVPN từ nhiều nguồn (VPNGate, IPSpeed, OpenProxyList, PublicVPNList), tách control **locale** (`COUNTRY_FILTER` multi ISO2) và **egress** (`EGRESS_MODE`), hỗ trợ auth mặc định cho free SoftEther-style configs.

**Design approved:** Approach A (plugin sources), full P1→P4.  
**Brainstorm:** [reports/brainstorm-multi-source-ovpn.md](./reports/brainstorm-multi-source-ovpn.md)

## Goals

- `OVPN_SOURCES` bật/tắt từng fetcher; merge + dedupe + cap vào `/ovpn`
- `COUNTRY_FILTER=US,JP` áp cho mọi source (normalize name→ISO2)
- `EGRESS_MODE=all|ovpn|ovpn+psiphon|ovpn+warp|custom` điều khiển HAProxy backends
- CLI: country multi + ports + mode (vd `autogate.bat US,JP 10 ovpn`)
- Fail-soft: source lỗi không xóa pool hiện có
- Chrome DevTools: verify scrape/download path khi implement OpenProxyList / PublicVPNList

## Non-goals

- Không thêm WireGuard/V2Ray
- Không dump toàn bộ 9k PublicVPNList
- Không guarantee uptime free VPN public
- Không auto TCP-probe health (optional later)

## Current baseline

| File | Role |
|------|------|
| `proxy/vpngate.py` | Only VPNGate CSV → `/ovpn` |
| `proxy/run.sh` | Refresh loop + strip warp/proxy001 if COUNTRY_FILTER |
| `proxy/haproxy.cfg` | Backends: warp, proxy001, psiphon, vpn00–19 |
| `slave/ovpn.sh` | Random `.ovpn`, no auth-user-pass |
| `autogate.sh` / `autogate.bat` | Positional country + port count |

## Phases

| # | Phase | Status | Effort | Link |
|---|-------|--------|--------|------|
| 1 | Framework + EGRESS_MODE + multi-country + auth | pending | 4h | [phase-01](./phase-01-framework-egress-locale.md) |
| 2 | IPSpeed source adapter | pending | 2h | [phase-02-ipspeed-source.md](./phase-02-ipspeed-source.md) |
| 3 | OpenProxyList source adapter | pending | 3h | [phase-03-openproxylist-source.md](./phase-03-openproxylist-source.md) |
| 4 | PublicVPNList source adapter (capped) | pending | 3h | [phase-04-publicvpnlist-source.md](./phase-04-publicvpnlist-source.md) |
| 5 | Docs, CLI polish, smoke validation | pending | 2h | [phase-05-docs-smoke.md](./phase-05-docs-smoke.md) |

## Dependencies

- Docker + WSL stack hiện tại (không đổi topology containers)
- Python3 trong image haproxy (đã có)
- Network outbound từ container master để scrape

## Key env contract

```bash
OVPN_SOURCES=vpngate,ipspeed          # default phase1+2; full later
COUNTRY_FILTER=                       # empty=all; US,JP,KR multi
MAX_OVPN_CONFIGS=80
OVPN_REFRESH_SECONDS=1800
OVPN_DEFAULT_USER=vpn
OVPN_DEFAULT_PASS=vpn
EGRESS_MODE=all                       # all|ovpn|ovpn+psiphon|ovpn+warp|custom
# custom only:
ENABLE_WARP=1 ENABLE_PROXYBROKER=1 ENABLE_PSIPHON=1 ENABLE_OVPN=1
```

## Success criteria (global)

1. `EGRESS_MODE=ovpn` → HAProxy rotating backend chỉ `vpn*`
2. Multi-country filter đúng trên file ghi ra
3. ≥2 sources khi bật full; fail 1 source vẫn refresh được nếu source khác OK
4. Worker openvpn không crash vì thiếu auth file khi config yêu cầu auth
5. Docs + launcher phản ánh env/CLI mới

## Risks

| Risk | Mitigation |
|------|------------|
| HTML scrape gãy | Isolate adapter; fail-soft; Chrome verify endpoints |
| Dead configs | MAX_OVPN_CONFIGS + keep VPNGate backbone |
| Breaking COUNTRY_FILTER side-effect | Doc migration; map mode rõ trong CLI |
| PublicVPNList anti-bot | Cap N; short timeout; optional skip source |

## Cook handoff

```text
/ck:cook plans/260716-1820-multi-source-ovpn-egress/plan.md
```

Implement **tuần tự phase 1→5**. Khi scrape mơ hồ: dùng Chrome DevTools MCP inspect download flow.
