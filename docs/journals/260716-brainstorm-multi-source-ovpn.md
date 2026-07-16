---
title: "Brainstorm multi-source OVPN + EGRESS_MODE"
date: 2026-07-16
---

# Journal: multi-source OpenVPN brainstorm

## Context

User muốn ngoài VPNGate: openproxylist, ipspeed, publicvpnlist; setting chỉ OpenVPN + locale.

## What happened

- Scouted AutoGate: single `vpngate.py`, COUNTRY_FILTER side-effect strip warp/proxy001
- Feasibility: IPSpeed easy; OpenProxyList medium; PublicVPNList hard (short-lived, 9k rows)
- Approved Approach A full phased + flexible EGRESS_MODE + ISO2 multi-country
- Chrome allowed for scrape recon when implementing
- Wrote plan `plans/260716-1820-multi-source-ovpn-egress/`

## Decisions

- Separate COUNTRY_FILTER vs EGRESS_MODE
- Cap pool; fail-soft per source
- PublicVPNList optional/default off if unstable
- Auth default vpn/vpn inject

## Next

Cook phase 1 → framework + mode + locale; then IPSpeed; then Chrome recon for remaining sources.
