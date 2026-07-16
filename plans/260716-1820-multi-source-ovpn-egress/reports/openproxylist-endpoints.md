# OpenProxyList endpoints (Chrome recon + reverse 2026-07-16)

## Feasibility

| Path | Captcha? | Works pure HTTP? |
|------|----------|------------------|
| `POST /openvpn/list` | **reCAPTCHA v3 required** | Only with valid token |
| `GET /openvpn/download/{id}` | No | **YES** |
| `POST /openvpn/bulk-download` | Session/list keys | Zip of selected ids |

## List API

```http
POST /openvpn/list
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest
Referer: https://openproxylist.com/openvpn/

dataType=openvpn
&g-recaptcha-response=<TOKEN>
&page=1
&sort=sortlast
&country[]=jp          # optional, lowercase ISO2
&response=
```

Response: HTML fragment (pagination + table). Parse:

- `/openvpn/download/{id}`
- `/openvpn/country/{cc}`

Empty/invalid captcha →:

```html
<div class="... bg-danger ...">reCAPTCHA verification failed. Please try again.</div>
```

## reCAPTCHA v3

| Field | Value |
|-------|-------|
| sitekey | `6LepNaEaAAAAAMcfZb4shvxaVWulaKUfjhOxOHRS` |
| action | `validate_captcha` |
| load | `grecaptcha.execute(sitekey, {action})` in `main.min.js` |

### Solving options

1. **2Captcha** (recommended for container): set `TWOCAPTCHA_API_KEY`
2. **Manual token**: `OPENPROXYLIST_RECAPTCHA_TOKEN` (short-lived)
3. **Skip list**: `OPENPROXYLIST_IDS=124,1,123` then download-only

2Captcha request shape: `method=userrecaptcha&version=v3&action=validate_captcha&googlekey=...&pageurl=https://openproxylist.com/openvpn/`

## Download

```http
GET /openvpn/download/{id}
→ application/octet-stream  (.ovpn with remote ...)
```

## Adapter env

```bash
OVPN_SOURCES=...,openproxylist
OPENPROXYLIST_MAX=30
OPENPROXYLIST_MAX_PAGES=3
OPENPROXYLIST_BUDGET_SECONDS=120
OPENPROXYLIST_SORT=sortlast
TWOCAPTCHA_API_KEY=...
# or:
OPENPROXYLIST_RECAPTCHA_TOKEN=...
OPENPROXYLIST_IDS=124,960
```
