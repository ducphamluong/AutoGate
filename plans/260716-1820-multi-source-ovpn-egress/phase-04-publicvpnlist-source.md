---
title: "Phase 4 — PublicVPNList source (capped best-effort)"
status: completed
effort: 3h
priority: P2
---

# Phase 4: PublicVPNList adapter

## Context

- Depends: Phase 1–3
- Site: https://publicvpnlist.com/
- ~9k servers; short-lived `.ovpn` download links; freshness/speed filters
- **Chrome recon mandatory** for download URL lifecycle

## Overview

Best-effort adapter: **never** dump full catalog. Top-N per filtered country only.

## Discovery steps

1. Chrome: filter country + “checked within 1h”
2. Trace download button network request (signed URL? cookie?)
3. Document in `reports/publicvpnlist-endpoints.md`
4. If only browser cookies work → evaluate feasibility; may ship **disabled by default**

## Requirements

1. Source key: `publicvpnlist`
2. Env: `PUBLICVPNLIST_MAX_PER_COUNTRY=10`, global still under MAX_OVPN_CONFIGS
3. Prefer fresh/high score endpoints if metadata available
4. Hard timeout source budget (e.g. 90s)
5. Default: **not** in `OVPN_SOURCES` unless user enables (risk high)
6. Filename: `pvl_{host}_{port}.ovpn`

## Implementation steps

1. Chrome recon + endpoint doc
2. Implement if pure HTTP possible
3. If auth/cookie wall: document “manual only” and skip auto-enable
4. Register optional source
5. Smoke with single country + low max

## Todo

- [ ] Chrome recon report
- [ ] Feasibility gate: HTTP-only OK? Y/N
- [ ] Adapter or “unsupported” stub with clear log
- [ ] Default OVPN_SOURCES remains without publicvpnlist unless stable

## Risks

| Risk | Mitigation |
|------|------------|
| Short-lived URLs | Download immediately after list |
| Anti-bot | Cap + optional disable default |
| Legal/ToS scrape | User authorized research only; polite UA rate limit |

## Success

- If feasible: contributes capped configs under filter
- If not: clear log `publicvpnlist skipped: no stable HTTP API` — no crash

## Rollback

Remove/disable source.
