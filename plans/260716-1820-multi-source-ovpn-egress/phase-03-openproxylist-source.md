---
title: "Phase 3 — OpenProxyList OpenVPN source"
status: completed
effort: 3h
priority: P2
---

# Phase 3: OpenProxyList adapter

## Context

- Depends: Phase 1–2
- Site: https://openproxylist.com/openvpn/
- Country counts on page; per-server pages e.g. `/openvpn/{id}` with downloadable `.ovpn`
- **Must use Chrome DevTools** if no stable bulk API found

## Overview

Implement `ovpn_sources/openproxylist.py` with conservative download limits.

## Discovery steps (before code freeze)

1. Chrome: open list page; filter by country if UI supports
2. Capture network: list JSON/XHR? download URL pattern for `.ovpn`
3. Document endpoints in `reports/openproxylist-endpoints.md`
4. Prefer API over HTML scrape if exists

## Requirements

1. Source key: `openproxylist`
2. When COUNTRY_FILTER set: only fetch those countries
3. Cap: `OPENPROXYLIST_MAX=30` (env) or share global max
4. Filename: `opl_{id}.ovpn`
5. Timeout/retry; skip bad downloads
6. Fail-soft

## Implementation steps

1. Chrome recon → write endpoint notes
2. Implement fetcher (HTTP only in production code; Chrome is verify tool not runtime)
3. Register source
4. Smoke with `COUNTRY_FILTER=VN` or `JP`

## Todo

- [ ] Chrome recon report
- [ ] `proxy/ovpn_sources/openproxylist.py`
- [ ] Register + env cap
- [ ] Smoke multi-source with vpngate+ipspeed+openproxylist

## Risks

- Rate limit / bot protection
- Per-server download N+1 requests slow → strict max
- Country code mapping from flags/names

## Success

- Adapter returns ≥1 config for a known country when site healthy
- Does not hang refresh loop (> hard timeout per source, e.g. 60–90s)

## Rollback

Disable source in OVPN_SOURCES.
