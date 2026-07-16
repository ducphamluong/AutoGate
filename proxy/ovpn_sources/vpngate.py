"""VPNGate CSV API source adapter."""

from __future__ import annotations

import base64
import csv
import urllib.request
from typing import Set

from .base import OvpnConfig, parse_remote, safe_filename_part
from .country_map import normalize_country

API_URL = "http://www.vpngate.net/api/iphone/"
TIMEOUT_SECONDS = 30
CONFIG_FIELD = "OpenVPN_ConfigData_Base64"
USER_AGENT = "AutoGate/1.0 (+https://github.com/TinyActive/AutoGate; research)"


class VpnGateSource:
    key = "vpngate"

    def fetch(self, allowed_countries: Set[str]) -> list[OvpnConfig]:
        csv_text = self._download_csv()
        configs: list[OvpnConfig] = []
        for row in self._csv_rows(csv_text):
            country = normalize_country(row.get("CountryShort", ""))
            if allowed_countries and country not in allowed_countries:
                continue

            name = safe_filename_part(row.get("HostName", "vpn"))
            try:
                body = base64.b64decode(row.get(CONFIG_FIELD, "")).decode("utf-8")
            except Exception:
                continue
            if not body.strip():
                continue

            host, port = parse_remote(body)
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

    def _download_csv(self) -> str:
        request = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", errors="replace")

    def _csv_rows(self, csv_text: str):
        lines = []
        for line in csv_text.splitlines():
            if line.startswith("*") or not line.strip():
                continue
            if line.startswith("#"):
                line = line[1:]
            lines.append(line)
        return csv.DictReader(lines)
