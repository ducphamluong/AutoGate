"""TCP live-check for OpenVPN remote endpoints (optional parallel)."""

from __future__ import annotations

import os
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def live_check_workers() -> int:
    raw = os.environ.get("OVPN_LIVE_CHECK_WORKERS", "40").strip()
    if raw.isdigit() and int(raw) > 0:
        return min(200, int(raw))
    return 40


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
    workers: int | None = None,
) -> list[OvpnConfig]:
    """Keep configs whose remote host:port accepts TCP connect."""
    timeout = live_check_timeout() if timeout is None else timeout
    workers = live_check_workers() if workers is None else max(1, workers)
    items = list(configs)
    if not items:
        return []

    def probe(cfg: OvpnConfig) -> tuple[OvpnConfig, str]:
        cfg.ensure_parsed_remote()
        host = cfg.remote_host
        port = cfg.remote_port
        if not host or not port:
            return cfg, "skip"
        if tcp_alive(host, int(port), timeout):
            return cfg, "up"
        return cfg, "down"

    alive: list[OvpnConfig] = []
    dead = 0
    skipped = 0

    if workers <= 1 or len(items) <= 1:
        results = [probe(c) for c in items]
    else:
        results = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(probe, c) for c in items]
            for fut in as_completed(futs):
                results.append(fut.result())

    # Preserve input order roughly by re-walking items with a status map
    status_map: dict[int, str] = {}
    for cfg, status in results:
        status_map[id(cfg)] = status

    for cfg in items:
        status = status_map.get(id(cfg), "skip")
        host = cfg.remote_host or "?"
        port = cfg.remote_port or 0
        if status == "up":
            print(f"live_check UP {host}:{port} [{cfg.source}/{cfg.name}]", flush=True)
            alive.append(cfg)
        elif status == "down":
            dead += 1
            print(f"live_check DOWN {host}:{port} [{cfg.source}/{cfg.name}]", flush=True)
        else:
            skipped += 1
            if require_remote:
                print(
                    f"live_check skip (no remote): {cfg.source}/{cfg.name}",
                    flush=True,
                )
            else:
                alive.append(cfg)

    print(
        f"live_check summary: alive={len(alive)} dead={dead} skipped={skipped} "
        f"workers={workers}",
        flush=True,
    )
    return alive


def filter_rows_live(
    rows: list[dict],
    *,
    host_keys: tuple[str, ...] = ("host", "ip"),
    port_key: str = "port",
    timeout: float | None = None,
    workers: int | None = None,
    stop_after: int | None = None,
) -> list[dict]:
    """Parallel TCP filter on catalog rows (before downloading .ovpn)."""
    timeout = live_check_timeout() if timeout is None else timeout
    workers = live_check_workers() if workers is None else max(1, workers)

    def host_of(row: dict) -> str:
        for k in host_keys:
            v = row.get(k)
            if v:
                return str(v).strip()
        return ""

    def port_of(row: dict) -> int:
        try:
            return int(row.get(port_key) or 0)
        except (TypeError, ValueError):
            return 0

    # Probe all candidates in parallel, then order by original index
    indexed = list(enumerate(rows))

    def probe(item: tuple[int, dict]) -> tuple[int, dict, bool]:
        idx, row = item
        h, p = host_of(row), port_of(row)
        if not h or not p:
            return idx, row, False
        return idx, row, tcp_alive(h, p, timeout)

    alive_pairs: list[tuple[int, dict]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(probe, it) for it in indexed]
        for fut in as_completed(futs):
            idx, row, ok = fut.result()
            if ok:
                alive_pairs.append((idx, row))
                h, p = host_of(row), port_of(row)
                print(f"precheck UP {h}:{p} id={row.get('id')}", flush=True)

    alive_pairs.sort(key=lambda x: x[0])
    alive = [row for _, row in alive_pairs]
    if stop_after is not None and stop_after > 0:
        alive = alive[:stop_after]
    print(
        f"precheck summary: candidates={len(rows)} alive={len(alive_pairs)} "
        f"kept={len(alive)} workers={workers}",
        flush=True,
    )
    return alive
