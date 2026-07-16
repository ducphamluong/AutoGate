# OpenProxyList endpoints (Chrome recon 2026-07-16)

## Confirmed

| Path | Method | Notes |
|------|--------|-------|
| `/openvpn/` | GET | List UI; rows filled after reCAPTCHA POST |
| `/openvpn/country/{iso2}` | GET | Country filter UI (e.g. `jp`) |
| `/openvpn/{id}` | GET | Server detail |
| `/openvpn/download/{id}` | GET | **Works over plain HTTP** → `application/octet-stream` `.ovpn` |
| `POST` form + `grecaptcha` | POST | Required to hydrate list HTML (`main.min.js` → `get_list`) |
| `POST /openvpn/bulk-download` | POST | Zip of selected keys (needs session/list) |

## Feasibility (HTTP-only in container)

- **Download by known id:** YES
- **Enumerate ids without captcha:** NO (static HTML has no download links; JS + reCAPTCHA loads them)
- **Default in `OVPN_SOURCES`:** NO
- **Escape hatch:** `OPENPROXYLIST_IDS=124,1,123`

## Runtime policy

Adapter returns `[]` + log if no ids; fail-soft does not wipe other sources.
