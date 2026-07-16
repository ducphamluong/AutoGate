---
title: "Phase 5 — Docs, CLI polish, smoke validation"
status: pending
effort: 2h
priority: P2
---

# Phase 5: Docs + smoke

## Context

- Depends: Phase 1–4 (or 1–2 minimum if 3–4 deferred)
- Files: `README.md`, `autogate.sh`, `autogate.bat`, optional `LICENSE.md` third-party mention

## Overview

Document env/CLI; migration note COUNTRY_FILTER no longer auto-strips warp; smoke matrix.

## Requirements

1. README sections:
   - OVPN_SOURCES table
   - EGRESS_MODE table
   - Multi-country examples
   - Warning free public VPN trust model
2. Launcher help text parity bat/sh
3. Smoke matrix (manual or script notes):

| Test | Expect |
|------|--------|
| `EGRESS_MODE=ovpn` | no warp/proxy/psiphon in runtime haproxy.cfg |
| `COUNTRY_FILTER=US,JP` | only those ISO2 in /ovpn metadata/logs |
| `OVPN_SOURCES=vpngate,ipspeed` | files from both prefixes |
| Refresh with bad source | pool not wiped if other sources OK |
| `curl -x http://127.0.0.1:56789` | works with ovpn mode when workers UP |

4. Mention Chrome used only for recon during dev, not runtime

## Todo

- [ ] README update
- [ ] autogate help strings
- [ ] Optional `.env.example` with new vars
- [ ] Run smoke checklist; note results in `reports/smoke-results.md`

## Success

- User can start `autogate.bat US,JP 10 ovpn` without reading source code
- Migration note visible for old COUNTRY_FILTER behavior

## Rollback

Docs-only revert.
