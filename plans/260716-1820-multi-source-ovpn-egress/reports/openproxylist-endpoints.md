# OpenProxyList endpoints + reCAPTCHA v3 browser path

## reCAPTCHA v3 reality

v3 is **not** a click-puzzle. Google returns a score for the session.

- Real browser loads page → `grecaptcha.execute(sitekey, {action})` → high score → list OK
- Headless bot / bad TLS / no JS → low score or missing token → `reCAPTCHA verification failed`
- **No 2Captcha required** if Playwright/Camoufox can run on the host

## Token mint (preferred)

```text
Playwright Chromium/Chrome  or  Camoufox
  → open https://openproxylist.com/openvpn/
  → wait grecaptcha
  → token = grecaptcha.execute(sitekey, { action: 'validate_captcha' })
```

sitekey: `6LepNaEaAAAAAMcfZb4shvxaVWulaKUfjhOxOHRS`

## List + download

```http
POST /openvpn/list
  dataType=openvpn&g-recaptcha-response=TOKEN&page=1&sort=sortlast&country[]=jp

GET /openvpn/download/{id}
  → .ovpn (no captcha)
```

HTTP layer prefers **curl_cffi** Chrome TLS impersonation when installed.

## Env

```bash
pip install -r requirements-ovpn-scrape.txt
playwright install chromium
# or: set OPENPROXYLIST_PLAYWRIGHT_CHANNEL=chrome

OVPN_SOURCES=vpngate,ipspeed,openproxylist
OPENPROXYLIST_BROWSER=auto          # playwright | camoufox | off
OPENPROXYLIST_HEADLESS=1            # 0 if score still low
OPENPROXYLIST_MAX_PAGES=2
```

## Docker note

Default `haproxy` Alpine image has **no** browser. Options:

1. Refresh OpenProxyList on the **host** (Windows/WSL with Playwright), write `./ovpn`
2. Or use `OPENPROXYLIST_IDS=...` only inside container
3. Or build a heavier image with Chromium (not default)

VPNGate / IPSpeed / PublicVPNList do not need a browser.
