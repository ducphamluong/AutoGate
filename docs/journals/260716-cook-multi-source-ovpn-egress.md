# Journal: cook multi-source OVPN + EGRESS_MODE

Date: 2026-07-16  
Plan: `plans/260716-1820-multi-source-ovpn-egress/`

## What shipped

- Multi-source framework: `proxy/ovpn_refresh.py` + `proxy/ovpn_sources/*`
- Sources: `vpngate` (default), `ipspeed` (default), `openproxylist` (optional/captcha), `publicvpnlist` (skip — no stable HTTP)
- `EGRESS_MODE` in `proxy/run.sh` (COUNTRY_FILTER no longer strips warp/proxy)
- Multi-country CLI: `autogate.bat US,JP 10 ovpn`
- Auth inject: `/ovpn/auth.txt` + rewrite `auth-user-pass`
- Docs: README, `.env.example`, recon reports, smoke-results

## Hard lessons

- IPSpeed HTML is invalid (`<td>…</th>`) → regex rows, not strict HTMLParser
- OpenProxyList list needs reCAPTCHA; download-by-id still works
- PublicVPNList download pages mint temporary links after interactive check — not container-safe

## Follow-ups

- Optional: TCP probe before writing configs
- Revisit publicvpnlist if they expose a stable API
- Full docker e2e curl smoke on host with WSL stack
