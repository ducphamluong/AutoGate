"""IPSpeed free OpenVPN list adapter (HTML + direct .ovpn URLs)."""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from typing import Set
from urllib.parse import urljoin

from .base import OvpnConfig, parse_remote, safe_filename_part
from .country_map import normalize_country

LIST_URL = "https://ipspeed.info/free-openvpn.php"
TIMEOUT_SECONDS = 30
USER_AGENT = "AutoGate/1.0 (+research; polite scrape)"

# Site HTML is often invalid (<td>Country</th>). Prefer regex over HTMLParser.
# Example row: <td>Japan</th> <td><a ... href="https://ipspeed.info/ovpn/x.y.z.ovpn"
ROW_RE = re.compile(
    r"<t[dh][^>]*>\s*([^<]+?)\s*</t[dh]>\s*"
    r"<td[^>]*>\s*<a[^>]+href=[\"']([^\"']+\.ovpn)[\"']",
    re.IGNORECASE,
)
OVPN_HREF_RE = re.compile(
    r"https?://[^\s\"']+/ovpn/([^\s\"']+\.ovpn)|(/ovpn/[^\s\"']+\.ovpn)",
    re.IGNORECASE,
)


class IpSpeedSource:
    key = "ipspeed"

    def fetch(self, allowed_countries: Set[str]) -> list[OvpnConfig]:
        max_per_source = self._max_configs()
        html_text = self._download_text(LIST_URL)
        entries = self._parse_entries(html_text)

        selected: list[tuple[str, str]] = []
        for href, country in entries:
            if allowed_countries and country and country not in allowed_countries:
                continue
            if allowed_countries and not country:
                continue
            selected.append((href, country))
            if len(selected) >= max_per_source:
                break

        configs: list[OvpnConfig] = []
        for href, country in selected:
            url = href if href.startswith("http") else urljoin(LIST_URL, href)
            try:
                body = self._download_text(url)
            except Exception:
                continue
            if not body.strip() or "remote " not in body.lower():
                continue

            ip_part = url.rstrip("/").split("/")[-1].replace(".ovpn", "")
            host, port = parse_remote(body)
            name = safe_filename_part(ip_part)
            cfg = OvpnConfig(
                source=self.key,
                name=name,
                country=country,
                body=body,
                remote_host=host,
                remote_port=port,
            )
            cfg.detect_auth()
            configs.append(cfg)
        return configs

    def _max_configs(self) -> int:
        raw = os.environ.get("IPS_SPEED_MAX", "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        return 40

    def _download_text(self, url: str) -> str:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} for {url}") from exc

    def _parse_entries(self, html_text: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        seen: set[str] = set()

        for match in ROW_RE.finditer(html_text):
            location = match.group(1).strip()
            href = match.group(2).strip()
            country = normalize_country(location)
            if href in seen:
                continue
            seen.add(href)
            results.append((href, country))

        if results:
            return results

        # Fallback: bare .ovpn links without reliable country
        for match in OVPN_HREF_RE.finditer(html_text):
            href = match.group(0)
            if href in seen:
                continue
            seen.add(href)
            results.append((href, ""))
        return results
