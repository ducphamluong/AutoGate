---
title: "Phase 2 — IPSpeed OpenVPN source"
status: pending
effort: 2h
priority: P1
---

# Phase 2: IPSpeed adapter

## Context

- Depends: Phase 1 complete
- Site: https://ipspeed.info/free-openvpn.php
- Direct files: `https://ipspeed.info/ovpn/{IP}.ovpn`
- Location column: full country names (Japan, USA, Vietnam, …)

## Overview

Implement `ovpn_sources/ipspeed.py`: parse HTML table, map country→ISO2, filter, download `.ovpn` bodies.

## Requirements

1. Fetch page with timeout + User-Agent
2. Parse rows: location + `.ovpn` href
3. Normalize country via `country_map.py`
4. Apply COUNTRY_FILTER before download (tiết kiệm bandwidth)
5. Download each selected `.ovpn` (limit per source optional `IPS_SPEED_MAX=40` or share global cap)
6. Filename: `ipspeed_{safe_ip}.ovpn`
7. Detect `auth-user-pass` in body → mark needs_auth; rely on phase-1 inject
8. Register source key: `ipspeed`
9. Default `OVPN_SOURCES=vpngate,ipspeed` after this phase (or document enable)

## Implementation steps

1. Implement parser (stdlib `html.parser` or regex careful — prefer html.parser / re on table links)
2. Unit-like dry run: print counts per country without write
3. Integrate into orchestrator source registry
4. If layout ambiguous → Chrome open page, inspect link pattern (known: `/ovpn/IP.ovpn`)

## Todo

- [ ] `proxy/ovpn_sources/ipspeed.py`
- [ ] Register in refresh
- [ ] country_map entries for IPSpeed names (USA, Russian Federation, …)
- [ ] Smoke: `OVPN_SOURCES=ipspeed COUNTRY_FILTER=JP` produces files

## Risks

- HTML layout change → fail-soft
- Many JP servers → hit MAX_OVPN_CONFIGS; OK
- Auth fail on some nodes → worker watchdog rotates

## Success

- IPSpeed contributes configs when enabled
- Country filter respects ISO2
- Failure does not empty VPNGate files if VPNGate succeeded first (orchestrator: only replace if total > 0)

## Rollback

Remove `ipspeed` from OVPN_SOURCES default; delete adapter file.
