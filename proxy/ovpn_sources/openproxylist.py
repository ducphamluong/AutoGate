"""OpenProxyList OpenVPN adapter.

Chrome recon + reverse (2026-07-16):

  POST /openvpn/list
    body: dataType=openvpn
          g-recaptcha-response=<reCAPTCHA v3 token>
          page=1..N
          sort=sortlast|sortresponse
          country[]=jp   (optional, lowercase ISO2)
    → HTML fragment with /openvpn/download/{id} + /openvpn/country/{cc}

  reCAPTCHA v3:
    sitekey 6LepNaEaAAAAAMcfZb4shvxaVWulaKUfjhOxOHRS
    action  validate_captcha
    (solved optionally via 2Captcha — TWOCAPTCHA_API_KEY)

  GET /openvpn/download/{id}
    → application/octet-stream .ovpn  (no captcha)

Strategies (in order):
  1. OPENPROXYLIST_IDS=1,2,3  → download only (no captcha)
  2. OPENPROXYLIST_RECAPTCHA_TOKEN → list with provided token
  3. TWOCAPTCHA_API_KEY → solve v3, then list + download
  4. Else fail-soft with clear log
"""

from __future__ import annotations

import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Set
from urllib.parse import urljoin

from .base import OvpnConfig, parse_remote, safe_filename_part

BASE_URL = "https://openproxylist.com"
LIST_PAGE = "https://openproxylist.com/openvpn/"
LIST_API = "https://openproxylist.com/openvpn/list"
TIMEOUT_SECONDS = 25
SOURCE_BUDGET_SECONDS = 90
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

RECAPTCHA_SITEKEY = "6LepNaEaAAAAAMcfZb4shvxaVWulaKUfjhOxOHRS"
RECAPTCHA_ACTION = "validate_captcha"

DOWNLOAD_ID_RE = re.compile(r"/openvpn/download/(\d+)", re.IGNORECASE)
ID_COUNTRY_RE = re.compile(
    r"/openvpn/download/(\d+)[\s\S]{0,500}?/openvpn/country/([a-z]{2})",
    re.IGNORECASE,
)
ID_COUNTRY_ALT_RE = re.compile(
    r"/openvpn/(\d+)[\s\S]{0,200}?/openvpn/download/\1[\s\S]{0,200}?/openvpn/country/([a-z]{2})",
    re.IGNORECASE,
)
PAGE_RE = re.compile(r'page-data=["\'](\d+)["\']', re.IGNORECASE)


class OpenProxyListSource:
    key = "openproxylist"

    def fetch(self, allowed_countries: Set[str]) -> list[OvpnConfig]:
        deadline = time.monotonic() + self._budget()
        max_configs = self._max_configs()

        pairs = self._resolve_ids(allowed_countries, deadline)
        if not pairs:
            print(
                "openproxylist: no server ids "
                "(need TWOCAPTCHA_API_KEY or OPENPROXYLIST_RECAPTCHA_TOKEN "
                "or OPENPROXYLIST_IDS=1,2,3)",
                flush=True,
            )
            return []

        configs: list[OvpnConfig] = []
        for server_id, country in pairs:
            if time.monotonic() > deadline or len(configs) >= max_configs:
                break
            if allowed_countries and country and country not in allowed_countries:
                continue
            try:
                body = self._download_ovpn(server_id)
            except Exception as exc:
                print(f"openproxylist download fail id={server_id}: {exc}", flush=True)
                continue
            if not body or "remote " not in body.lower() or body.lstrip().startswith("<"):
                continue
            host, port = parse_remote(body)
            cfg = OvpnConfig(
                source=self.key,
                name=f"opl_{safe_filename_part(server_id)}",
                country=(country or "").upper(),
                body=body,
                remote_host=host,
                remote_port=port,
            )
            cfg.detect_auth()
            configs.append(cfg)
        return configs

    def _max_configs(self) -> int:
        raw = os.environ.get("OPENPROXYLIST_MAX", "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        return 30

    def _budget(self) -> int:
        raw = os.environ.get("OPENPROXYLIST_BUDGET_SECONDS", "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        return SOURCE_BUDGET_SECONDS

    def _max_pages(self) -> int:
        raw = os.environ.get("OPENPROXYLIST_MAX_PAGES", "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        return 3

    def _http(
        self,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        h = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json,*/*",
        }
        if headers:
            h.update(headers)
        req = urllib.request.Request(
            url, data=data, headers=h, method="POST" if data is not None else "GET"
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} for {url}") from exc

    def _download_ovpn(self, server_id: str) -> str:
        url = urljoin(BASE_URL, f"/openvpn/download/{server_id}")
        return self._http(
            url,
            headers={"Referer": LIST_PAGE, "Accept": "*/*"},
        )

    def _resolve_ids(
        self, allowed: Set[str], deadline: float
    ) -> list[tuple[str, str]]:
        # 1) Manual IDs
        raw_ids = os.environ.get("OPENPROXYLIST_IDS", "").strip()
        if raw_ids:
            result = []
            for part in raw_ids.split(","):
                sid = part.strip()
                if sid.isdigit():
                    result.append((sid, ""))
            print(f"openproxylist: using OPENPROXYLIST_IDS ({len(result)})", flush=True)
            return result

        # 2) Token: env override or 2captcha
        token = os.environ.get("OPENPROXYLIST_RECAPTCHA_TOKEN", "").strip()
        if not token:
            token = self._solve_captcha()
        if not token:
            return []

        max_pages = self._max_pages()
        countries = sorted(c.lower() for c in allowed) if allowed else [""]
        by_id: dict[str, str] = {}

        for country in countries:
            if time.monotonic() > deadline:
                break
            # Fresh token each country/page batch if 2captcha available and multi-page
            page = 1
            pages_to_fetch = max_pages
            while page <= pages_to_fetch and time.monotonic() < deadline:
                try:
                    html = self._fetch_list_page(token, page=page, country=country)
                except Exception as exc:
                    print(f"openproxylist list fail page={page} country={country or '*'}: {exc}", flush=True)
                    break

                if "reCAPTCHA verification failed" in html or "captcha" in html.lower() and "failed" in html.lower():
                    print("openproxylist: captcha rejected by server", flush=True)
                    # one retry with new token
                    token = self._solve_captcha() or token
                    try:
                        html = self._fetch_list_page(token, page=page, country=country)
                    except Exception as exc:
                        print(f"openproxylist list retry fail: {exc}", flush=True)
                        break
                    if "reCAPTCHA verification failed" in html:
                        break

                page_pairs = self._parse_list_html(html, default_country=country.upper())
                for sid, cc in page_pairs:
                    by_id.setdefault(sid, cc)

                # Discover total pages from first response
                if page == 1:
                    pages = [int(x) for x in PAGE_RE.findall(html) if x.isdigit()]
                    if pages:
                        pages_to_fetch = min(max_pages, max(pages))

                # Need new captcha per page (tokens are single-use typically)
                if page < pages_to_fetch:
                    new_tok = self._solve_captcha()
                    if new_tok:
                        token = new_tok
                page += 1

        print(f"openproxylist: listed {len(by_id)} unique ids", flush=True)
        return list(by_id.items())

    def _solve_captcha(self) -> str:
        try:
            from .recaptcha_2captcha import captcha_api_key, solve_recaptcha_v3
        except Exception:
            return ""

        if not captcha_api_key():
            return ""

        print("openproxylist: solving reCAPTCHA v3 via 2captcha...", flush=True)
        try:
            token = solve_recaptcha_v3(
                sitekey=RECAPTCHA_SITEKEY,
                pageurl=LIST_PAGE,
                action=RECAPTCHA_ACTION,
            )
            print(f"openproxylist: captcha ok (token len={len(token)})", flush=True)
            return token
        except Exception as exc:
            print(f"openproxylist: 2captcha failed: {exc}", flush=True)
            return ""

    def _fetch_list_page(self, token: str, *, page: int, country: str) -> str:
        fields: list[tuple[str, str]] = [
            ("dataType", "openvpn"),
            ("g-recaptcha-response", token),
            ("page", str(page)),
            ("sort", os.environ.get("OPENPROXYLIST_SORT", "sortlast")),
        ]
        if country:
            fields.append(("country[]", country.lower()))
        # empty response filter field present on form
        fields.append(("response", ""))

        body = urllib.parse.urlencode(fields).encode("utf-8")
        return self._http(
            LIST_API,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": LIST_PAGE if not country else f"{BASE_URL}/openvpn/country/{country.lower()}",
            },
        )

    def _parse_list_html(
        self, html_text: str, default_country: str = ""
    ) -> list[tuple[str, str]]:
        by_id: dict[str, str] = {}
        for match in ID_COUNTRY_ALT_RE.finditer(html_text):
            by_id[match.group(1)] = match.group(2).upper()
        for match in ID_COUNTRY_RE.finditer(html_text):
            by_id.setdefault(match.group(1), match.group(2).upper())
        for match in DOWNLOAD_ID_RE.finditer(html_text):
            by_id.setdefault(match.group(1), default_country)
        return list(by_id.items())
