# PublicVPNList endpoints (Chrome recon 2026-07-16)

## Confirmed

| Path | Method | Notes |
|------|--------|-------|
| `/` | GET | Live catalog (~9k servers) |
| `/country/{slug}/` | GET | e.g. `japan`, `usa`, `south-korea` |
| `/server/{id}/` | GET | Server detail |
| `/download/{id}/` | GET | **HTML interstitial**, not raw `.ovpn` |
| UI "Run current check" | browser | Mints **short-lived** temporary `.ovpn` URL |

## Feasibility gate

| Question | Answer |
|----------|--------|
| Pure HTTP stable `.ovpn` download? | **NO** |
| Safe to enable by default? | **NO** |
| Adapter behavior | Skip with clear log; no crash |

## Runtime policy

Source key `publicvpnlist` registered but returns empty until a stable API appears.
Do **not** dump full catalog.
