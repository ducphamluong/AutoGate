---
title: "Brainstorm multi-source OpenVPN + EGRESS_MODE + locale"
status: approved
created: 2026-07-16
tags: [brainstorm, ovpn, sources, egress]
---

# Brainstorm: Multi-source OpenVPN + mode + locale

## Problem

AutoGate chỉ fetch OpenVPN từ VPNGate (`proxy/vpngate.py`). User muốn:

1. Thêm nguồn: openproxylist.com, ipspeed.info, publicvpnlist.com
2. Setting chỉ chạy OpenVPN (và profile linh hoạt)
3. Filter locale ISO2 multi-country (`US,JP`)

## Decisions (approved)

| Topic | Choice |
|-------|--------|
| Architecture | **Approach A** — multi-source plugin trong master (haproxy container) |
| Scope | Full P1→P4 (4 sources phased) |
| Egress control | `EGRESS_MODE` env profiles + `custom` ENABLE_* |
| Locale | ISO2 multi-country, normalize tên nước → ISO2 |
| Scrape verify | Dùng Chrome DevTools MCP nếu HTML/API mơ hồ |
| Next | Implementation plan |

## Current constraints

- Master refresh: `proxy/run.sh` gọi `vpngate.py` mỗi ~30 phút
- `COUNTRY_FILTER` filter VPNGate + side-effect xóa warp/proxy001 (giữ psiphon) — **sẽ tách**
- `slave/ovpn.sh` random `.ovpn`, **không** auth-user-pass
- Free public VPN không tin cậy — cap pool, fail-soft

## Source feasibility

| Source | Method | Locale | Difficulty |
|--------|--------|--------|------------|
| VPNGate | CSV API base64 | CountryShort ISO2 | Easy |
| IPSpeed | HTML + direct `.ovpn` URLs | Full country name | Easy |
| OpenProxyList | Country list + per-server download | Country UI | Medium |
| PublicVPNList | Large catalog, short-lived downloads | Country slug | Hard — cap top-N |

## Recommended design summary

```
OVPN_SOURCES=vpngate,ipspeed,openproxylist,publicvpnlist
COUNTRY_FILTER=US,JP,KR
MAX_OVPN_CONFIGS=80
EGRESS_MODE=all|ovpn|ovpn+psiphon|ovpn+warp|custom
OVPN_DEFAULT_USER=vpn
OVPN_DEFAULT_PASS=vpn
```

- `COUNTRY_FILTER` → only filter ovpn pool
- `EGRESS_MODE` → only HAProxy backends
- Prefix files per source; dedupe host:port; inject auth if needed
- PublicVPNList: top-N/country, fail-soft, Chrome verify when implementing

## Phases (high level)

1. Framework + EGRESS_MODE + multi-country CLI + auth inject
2. IPSpeed adapter
3. OpenProxyList adapter
4. PublicVPNList adapter (capped)
5. Docs + smoke / Chrome scrape validation notes

## Risks

- Scraper break khi site đổi HTML
- Dead configs tăng nếu không cap/probe
- Breaking: COUNTRY_FILTER không còn auto-disable warp
- Auth không universal (`vpn`/`vpn` không đủ mọi server)

## Success metrics

- `EGRESS_MODE=ovpn` → chỉ vpn* backends
- Multi ISO2 filter trên mọi source
- ≥1 source fail không wipe pool
- CLI: `autogate.bat US,JP 10 ovpn`

## Unresolved at brainstorm time

- Exact OpenProxyList/PublicVPNList download endpoints (verify khi cook bằng Chrome)
- Có cần TCP probe trước khi ghi file? (optional, default off P1)
