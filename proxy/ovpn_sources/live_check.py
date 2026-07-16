"""TCP live-check for OpenVPN remote endpoints."""

from __future__ import annotations

import os
import socket
from typing import Iterable

from .base import OvpnConfig


def live_check_enabled(default: bool = False) -> bool:
    raw = os.environ.get("OVPN_LIVE_CHECK", "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def live_check_timeout() -> float:
    raw = os.environ.get("OVPN_LIVE_CHECK_TIMEOUT", "3").strip()
    try:
        return max(0.5, float(raw))
    except ValueError:
        return 3.0


def tcp_alive(host: str, port: int, timeout: float) -> bool:
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def filter_live(
    configs: Iterable[OvpnConfig],
    *,
    timeout: float | None = None,
    require_remote: bool = True,
) -> list[OvpnConfig]:
    """Keep configs whose remote host:port accepts TCP connect."""
    timeout = live_check_timeout() if timeout is None else timeout
    alive: list[OvpnConfig] = []
    dead = 0
    skipped = 0
    for cfg in configs:
        cfg.ensure_parsed_remote()
        host = cfg.remote_host
        port = cfg.remote_port
        if not host or not port:
            if require_remote:
                skipped += 1
                print(
                    f"live_check skip (no remote): {cfg.source}/{cfg.name}",
                    flush=True,
                )
                continue
            alive.append(cfg)
            continue
        if tcp_alive(host, int(port), timeout):
            print(f"live_check UP {host}:{port} [{cfg.source}/{cfg.name}]", flush=True)
            alive.append(cfg)
        else:
            dead += 1
            print(f"live_check DOWN {host}:{port} [{cfg.source}/{cfg.name}]", flush=True)
    print(
        f"live_check summary: alive={len(alive)} dead={dead} skipped={skipped}",
        flush=True,
    )
    return alive
