# Smoke results — multi-source OVPN + EGRESS_MODE

Date: 2026-07-16

| Test | Expect | Result |
|------|--------|--------|
| `COUNTRY_FILTER=JP` + `OVPN_SOURCES=vpngate` | only JP files | PASS (5 configs written) |
| `OVPN_SOURCES=ipspeed` + `COUNTRY_FILTER=JP` | ipspeed_* JP | PASS |
| `OVPN_SOURCES=vpngate,ipspeed,openproxylist` + `US,JP` | multi files, fail-soft opl | PASS (vpngate+ipspeed; opl 0 ids, pool kept) |
| Unit: country_map + auth inject | normalize + rewrite path | PASS |
| EGRESS_MODE=ovpn (config filter sim) | only vpn* servers | PASS |
| `publicvpnlist` alone + JP max=3 | token + real `.ovpn` with remote | PASS (catalog 9915 → 3 files) |
| `openproxylist` alone without IDs | clear skip | PASS |
| Full docker `curl -x :56789` | workers UP | NOT RUN (no docker stack in this cook session) |

Notes:

- Default `OVPN_SOURCES=vpngate,ipspeed`
- Chrome used only for recon, not runtime
