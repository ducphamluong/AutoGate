# PublicVPNList endpoints (Chrome recon + reverse 2026-07-16)

## Feasibility gate (updated)

| Question | Answer |
|----------|--------|
| Pure HTTP stable list? | **YES** — `GET /local/api/vpn-data.php` |
| Pure HTTP `.ovpn` download? | **YES** — short-lived token (300s) |
| Safe default in `OVPN_SOURCES`? | Optional — cap + budget required |
| Need browser/captcha? | **NO** for token path |

## Flow (from `app.js` initDownloadPage)

```text
1) (optional) GET /test_server.php?id={id}
      → { ok, status: ok|fail|unknown, latencyMs, live, ... }

2) POST /get_token.php
      body: id={id}
      headers: Accept: application/json
               Content-Type: application/x-www-form-urlencoded
               X-Requested-With: XMLHttpRequest
      → { token, url: "/download.php?token=...", expiresIn: 300 }

3) GET /download.php?token={token}
      → application/x-openvpn-profile  (.ovpn text with remote ...)
```

Live check failure still allows token download (`allowUnconfirmed` in UI).

## Catalog

| Path | Method | Notes |
|------|--------|-------|
| `/local/api/vpn-data.php` | GET | ~10k JSON rows; `Accept: application/json` |
| `/country/{slug}/` | GET | HTML with `data-id` fallback |
| `/download/{id}/` | GET | HTML interstitial only (not raw ovpn) |
| `/local/api/vpn-checker/status.php` | GET | ticker, not download |

Catalog row fields (subset): `id`, `country` (slug e.g. `japan`), `countryName`, `host`, `ip`, `port`, `proto`, `speed`, `latency`, `configAvailable`, `isFresh`, `isRecommended`, `lastCheckOk`.

## Adapter env

```bash
PUBLICVPNLIST_MAX_PER_COUNTRY=10
PUBLICVPNLIST_BUDGET_SECONDS=90
PUBLICVPNLIST_LIVE_CHECK=0   # 1 = call test_server.php before token
OVPN_SOURCES=vpngate,ipspeed,publicvpnlist
```

## Policy

- Cap per country; prefer recommended/fresh/high speed
- Download immediately after minting token (TTL 300s)
- Fail-soft if catalog or token fails
