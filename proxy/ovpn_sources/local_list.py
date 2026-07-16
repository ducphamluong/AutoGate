"""Local OpenVPN profiles from folder ``ovpn-list`` (mounted at /ovpn-list).

If the directory contains ``*.ovpn`` files, orchestrator can prefer them
over remote scrapers (see OVPN_LIST_PRIORITY in ovpn_refresh).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Set

from .base import OvpnConfig, parse_remote, safe_filename_part
from .country_map import normalize_country

# Container path by default; host can set OVPN_LIST_DIR=./ovpn-list
DEFAULT_LIST_DIR = "/ovpn-list"
COUNTRY_HINT_RE = re.compile(
    r"(?:^|[_\-.])([a-z]{2})(?:[_\-.]|$)",
    re.IGNORECASE,
)


def resolve_list_dir() -> Path:
    raw = os.environ.get("OVPN_LIST_DIR", DEFAULT_LIST_DIR).strip() or DEFAULT_LIST_DIR
    return Path(raw)


def list_dir_has_ovpn(directory: Path | None = None) -> bool:
    directory = directory or resolve_list_dir()
    if not directory.is_dir():
        return False
    return any(directory.glob("*.ovpn"))


class LocalListSource:
    """Source key: ``local`` (alias registered as ``ovpn-list``)."""

    key = "local"

    def fetch(self, allowed_countries: Set[str]) -> list[OvpnConfig]:
        directory = resolve_list_dir()
        if not directory.is_dir():
            print(f"local_list: directory missing: {directory}", flush=True)
            return []

        configs: list[OvpnConfig] = []
        files = sorted(directory.glob("*.ovpn"))
        print(f"local_list: scanning {directory} ({len(files)} .ovpn)", flush=True)

        for path in files:
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                print(f"local_list: read fail {path.name}: {exc}", flush=True)
                continue
            if not body.strip() or "remote " not in body.lower():
                print(f"local_list: skip invalid {path.name}", flush=True)
                continue

            host, port = parse_remote(body)
            country = self._guess_country(path.stem, body)
            if allowed_countries and country and country not in allowed_countries:
                continue
            if allowed_countries and not country:
                # With filter active and unknown country, keep file (user-provided)
                pass

            cfg = OvpnConfig(
                source=self.key,
                name=safe_filename_part(path.stem),
                country=country,
                body=body,
                remote_host=host,
                remote_port=port,
            )
            cfg.detect_auth()
            configs.append(cfg)

        print(f"local_list: loaded {len(configs)} configs", flush=True)
        return configs

    @staticmethod
    def _guess_country(stem: str, body: str) -> str:
        # Filename hints: jp-server, US_vpn, country_jp
        for match in COUNTRY_HINT_RE.finditer(stem):
            code = normalize_country(match.group(1))
            if code:
                return code
        # Comment lines sometimes include country
        for line in body.splitlines()[:30]:
            line = line.strip()
            if line.startswith("#") or line.startswith(";"):
                code = normalize_country(line.lstrip("#;").strip())
                if code:
                    return code
        return ""


class OvpnListAliasSource(LocalListSource):
    """Same adapter under key ``ovpn-list`` for OVPN_SOURCES readability."""

    key = "ovpn-list"
