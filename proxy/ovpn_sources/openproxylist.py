"""OpenProxyList OpenVPN adapter.

reCAPTCHA v3 is score-based: a normal browser that runs grecaptcha.execute()
usually passes without any puzzle / paid captcha API.

Flow:
  1. OPENPROXYLIST_IDS → download-only (no list/captcha)
  2. OPENPROXYLIST_RECAPTCHA_TOKEN → use token as-is
  3. Real browser (Playwright / Camoufox) → grecaptcha.execute on list page
  4. POST /openvpn/list with token (curl_cffi Chrome TLS if available)
  5. GET /openvpn/download/{id} for each id

Env:
  OPENPROXYLIST_BROWSER=auto|playwright|camoufox|off
  OPENPROXYLIST_HEADLESS=1
  OPENPROXYLIST_PLAYWRIGHT_CHANNEL=chrome   # optional system Chrome
  CURL_CFFI_IMPERSONATE=chrome131
"""

from __future__ import annotations

import os
import re
import time
import urllib.parse
from typing import Set
from urllib.parse import urljoin

from .base import OvpnConfig, parse_remote, safe_filename_part
from .browser_http import (
    get_recaptcha_v3_token,
    http_get_or_post,
    list_available_backends,
)

BASE_URL = "https://openproxylist.com"
LIST_PAGE = "https://openproxylist.com/openvpn/"
LIST_API = "https://openproxylist.com/openvpn/list"
TIMEOUT_SECONDS = 30
SOURCE_BUDGET_SECONDS = 180
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
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
            backends = ", ".join(list_available_backends()) or "none"
            print(
                "openproxylist: no server ids "
                f"(backends={backends}; set OPENPROXYLIST_BROWSER=playwright|camoufox "
                "or OPENPROXYLIST_IDS=... or OPENPROXYLIST_RECAPTCHA_TOKEN=...)",
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
        return 2

    def _http(
        self,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        return http_get_or_post(
            url, data=data, headers=headers, timeout=TIMEOUT_SECONDS
        )

    def _download_ovpn(self, server_id: str) -> str:
        url = urljoin(BASE_URL, f"/openvpn/download/{server_id}")
        return self._http(
            url,
            headers={
                "Referer": LIST_PAGE,
                "Accept": "*/*",
                "User-Agent": USER_AGENT,
            },
        )

    def _resolve_ids(
        self, allowed: Set[str], deadline: float
    ) -> list[tuple[str, str]]:
        # 1) Manual IDs — no browser
        raw_ids = os.environ.get("OPENPROXYLIST_IDS", "").strip()
        if raw_ids:
            result = []
            for part in raw_ids.split(","):
                sid = part.strip()
                if sid.isdigit():
                    result.append((sid, ""))
            print(f"openproxylist: using OPENPROXYLIST_IDS ({len(result)})", flush=True)
            return result

        # 2) Token from env or real browser (v3 score path)
        token = os.environ.get("OPENPROXYLIST_RECAPTCHA_TOKEN", "").strip()
        if token:
            print("openproxylist: using OPENPROXYLIST_RECAPTCHA_TOKEN", flush=True)
        else:
            token = self._browser_token()
        if not token:
            return []

        max_pages = self._max_pages()
        countries = sorted(c.lower() for c in allowed) if allowed else [""]
        by_id: dict[str, str] = {}

        for country in countries:
            if time.monotonic() > deadline:
                break
            page = 1
            pages_to_fetch = max_pages
            while page <= pages_to_fetch and time.monotonic() < deadline:
                try:
                    html = self._fetch_list_page(token, page=page, country=country)
                except Exception as exc:
                    print(
                        f"openproxylist list fail page={page} country={country or '*'}: {exc}",
                        flush=True,
                    )
                    break

                failed = "reCAPTCHA verification failed" in html
                if failed:
                    print(
                        "openproxylist: token rejected (low v3 score or expired); "
                        "retrying with fresh browser token...",
                        flush=True,
                    )
                    token = self._browser_token() or token
                    try:
                        html = self._fetch_list_page(token, page=page, country=country)
                    except Exception as exc:
                        print(f"openproxylist list retry fail: {exc}", flush=True)
                        break
                    if "reCAPTCHA verification failed" in html:
                        print(
                            "openproxylist: still rejected — try "
                            "OPENPROXYLIST_BROWSER=camoufox or HEADLESS=0",
                            flush=True,
                        )
                        break

                page_pairs = self._parse_list_html(html, default_country=country.upper())
                for sid, cc in page_pairs:
                    by_id.setdefault(sid, cc)

                if page == 1:
                    pages = [int(x) for x in PAGE_RE.findall(html) if x.isdigit()]
                    if pages:
                        pages_to_fetch = min(max_pages, max(pages))

                # New token per page (single-use / short TTL)
                if page < pages_to_fetch:
                    new_tok = self._browser_token()
                    if new_tok:
                        token = new_tok
                page += 1

        print(f"openproxylist: listed {len(by_id)} unique ids", flush=True)
        return list(by_id.items())

    def _browser_token(self) -> str:
        print(
            "openproxylist: minting reCAPTCHA v3 token via real browser "
            f"(mode={os.environ.get('OPENPROXYLIST_BROWSER', 'auto')})...",
            flush=True,
        )
        try:
            token = get_recaptcha_v3_token(
                sitekey=RECAPTCHA_SITEKEY,
                pageurl=LIST_PAGE,
                action=RECAPTCHA_ACTION,
            )
            print(f"openproxylist: browser token ok (len={len(token)})", flush=True)
            return token
        except Exception as exc:
            print(f"openproxylist: browser token failed: {exc}", flush=True)
            return ""

    def _fetch_list_page(self, token: str, *, page: int, country: str) -> str:
        fields: list[tuple[str, str]] = [
            ("dataType", "openvpn"),
            ("g-recaptcha-response", token),
            ("page", str(page)),
            ("sort", os.environ.get("OPENPROXYLIST_SORT", "sortlast")),
            ("response", ""),
        ]
        if country:
            fields.append(("country[]", country.lower()))

        body = urllib.parse.urlencode(fields).encode("utf-8")
        referer = (
            LIST_PAGE
            if not country
            else f"{BASE_URL}/openvpn/country/{country.lower()}"
        )
        return self._http(
            LIST_API,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": referer,
                "User-Agent": USER_AGENT,
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
