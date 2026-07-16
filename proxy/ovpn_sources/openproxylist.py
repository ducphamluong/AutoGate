"""OpenProxyList OpenVPN adapter — best-effort HTTP.

Chrome recon (2026-07-16):
  - Download by id works: GET /openvpn/download/{id} → application/octet-stream
  - List requires reCAPTCHA (POST form + grecaptcha) — pure HTTP cannot enumerate IDs
  - Country pages: /openvpn/country/{iso2} (JS-hydrated rows)

Strategy:
  1. If OPENPROXYLIST_IDS is set → download those ids (optional escape hatch)
  2. Try parse any /openvpn/download/{id} already present in static HTML
  3. Otherwise return [] with a clear log (fail-soft; not in default OVPN_SOURCES)
"""

from __future__ import annotations

import os
import re
import time
import urllib.error
import urllib.request
from typing import Set
from urllib.parse import urljoin

from .base import OvpnConfig, parse_remote, safe_filename_part

BASE_URL = "https://openproxylist.com"
LIST_URL = "https://openproxylist.com/openvpn/"
TIMEOUT_SECONDS = 25
SOURCE_BUDGET_SECONDS = 90
USER_AGENT = (
    "Mozilla/5.0 (compatible; AutoGate/1.0; +research; polite scrape)"
)
DOWNLOAD_ID_RE = re.compile(r"/openvpn/download/(\d+)", re.IGNORECASE)
COUNTRY_NEAR_RE = re.compile(
    r"/openvpn/download/(\d+)[\s\S]{0,400}?/openvpn/country/([a-z]{2})",
    re.IGNORECASE,
)


class OpenProxyListSource:
    key = "openproxylist"

    def fetch(self, allowed_countries: Set[str]) -> list[OvpnConfig]:
        deadline = time.monotonic() + self._budget()
        max_configs = self._max_configs()
        ids = self._resolve_ids(allowed_countries, deadline)

        if not ids:
            print(
                "openproxylist: no server ids "
                "(list needs reCAPTCHA; set OPENPROXYLIST_IDS=1,2,3 or skip source)",
                flush=True,
            )
            return []

        configs: list[OvpnConfig] = []
        for server_id, country in ids:
            if time.monotonic() > deadline or len(configs) >= max_configs:
                break
            if allowed_countries and country and country not in allowed_countries:
                continue
            try:
                body = self._download_ovpn(server_id)
            except Exception:
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

    def _get(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} for {url}") from exc

    def _download_ovpn(self, server_id: str) -> str:
        return self._get(urljoin(BASE_URL, f"/openvpn/download/{server_id}"))

    def _resolve_ids(
        self, allowed: Set[str], deadline: float
    ) -> list[tuple[str, str]]:
        # Manual override
        raw_ids = os.environ.get("OPENPROXYLIST_IDS", "").strip()
        if raw_ids:
            result = []
            for part in raw_ids.split(","):
                sid = part.strip()
                if sid.isdigit():
                    result.append((sid, ""))
            return result

        pages = [LIST_URL]
        if allowed:
            for code in sorted(allowed):
                pages.append(urljoin(BASE_URL, f"/openvpn/country/{code.lower()}"))

        by_id: dict[str, str] = {}
        for page_url in pages:
            if time.monotonic() > deadline:
                break
            try:
                html_text = self._get(page_url)
            except Exception:
                continue
            default = ""
            m = re.search(r"/country/([a-z]{2})", page_url, re.I)
            if m:
                default = m.group(1).upper()
            for match in COUNTRY_NEAR_RE.finditer(html_text):
                by_id[match.group(1)] = match.group(2).upper()
            for match in DOWNLOAD_ID_RE.finditer(html_text):
                by_id.setdefault(match.group(1), default)
        return list(by_id.items())
