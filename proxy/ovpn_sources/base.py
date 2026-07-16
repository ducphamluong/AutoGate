"""Shared models and helpers for OpenVPN source adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Protocol, Set

AUTH_PATH = "/ovpn/auth.txt"
REMOTE_RE = re.compile(
    r"^\s*remote\s+(\S+)(?:\s+(\d+))?",
    re.MULTILINE | re.IGNORECASE,
)
AUTH_USER_PASS_RE = re.compile(
    r"^(\s*auth-user-pass)(?:\s+\S+)?\s*$",
    re.MULTILINE | re.IGNORECASE,
)
HAS_AUTH_RE = re.compile(r"^\s*auth-user-pass\b", re.MULTILINE | re.IGNORECASE)


@dataclass
class OvpnConfig:
    """Normalized OpenVPN profile from any source."""

    source: str
    name: str
    country: str
    body: str
    remote_host: Optional[str] = None
    remote_port: Optional[int] = None
    needs_auth: bool = False

    def ensure_parsed_remote(self) -> None:
        if self.remote_host:
            return
        host, port = parse_remote(self.body)
        self.remote_host = host
        self.remote_port = port

    def detect_auth(self) -> None:
        if HAS_AUTH_RE.search(self.body):
            self.needs_auth = True


class OvpnSource(Protocol):
    """Source adapter protocol."""

    key: str

    def fetch(self, allowed_countries: Set[str]) -> list[OvpnConfig]:
        """Return configs. Empty allowed_countries means no country filter."""
        ...


def parse_remote(body: str) -> tuple[Optional[str], Optional[int]]:
    match = REMOTE_RE.search(body or "")
    if not match:
        return None, None
    host = match.group(1)
    port_raw = match.group(2)
    port = int(port_raw) if port_raw else None
    return host, port


def inject_auth_path(body: str) -> str:
    """Rewrite auth-user-pass lines to use the shared auth file path."""
    if not HAS_AUTH_RE.search(body):
        return body
    return AUTH_USER_PASS_RE.sub(rf"\1 {AUTH_PATH}", body)


def safe_filename_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value or "vpn")
