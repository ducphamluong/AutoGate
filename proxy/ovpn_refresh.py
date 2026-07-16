#!/usr/bin/env python3
"""Multi-source OpenVPN config refresh orchestrator."""

from __future__ import annotations

import datetime
import os
import shutil
import sys
import tempfile
from typing import Iterable

# Ensure /proxy (or local proxy dir) is on path when executed as a script.
_PROXY_DIR = os.path.dirname(os.path.abspath(__file__))
if _PROXY_DIR not in sys.path:
    sys.path.insert(0, _PROXY_DIR)

from ovpn_sources.base import (  # noqa: E402
    OvpnConfig,
    inject_auth_path,
    safe_filename_part,
)
from ovpn_sources.country_map import parse_country_filter  # noqa: E402
from ovpn_sources.live_check import filter_live, live_check_enabled  # noqa: E402
from ovpn_sources.local_list import list_dir_has_ovpn, resolve_list_dir  # noqa: E402
from ovpn_sources.registry import (  # noqa: E402
    get_source,
    list_source_keys,
    register_builtin_sources,
)

OVPN_DIR = os.environ.get("OVPN_DIR", "/ovpn")
# Full sample set; override via OVPN_SOURCES / .env
DEFAULT_SOURCES = "vpngate,ipspeed,openproxylist,publicvpnlist"
DEFAULT_MAX = 80
DEFAULT_USER = "vpn"
DEFAULT_PASS = "vpn"


def log(message: str) -> None:
    print(datetime.datetime.now(), message, flush=True)


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def selected_sources() -> list[str]:
    raw = os.environ.get("OVPN_SOURCES", DEFAULT_SOURCES)
    keys = [part.strip().lower() for part in raw.split(",") if part.strip()]
    return keys or ["vpngate"]


def write_auth_file(output_dir: str) -> None:
    user = os.environ.get("OVPN_DEFAULT_USER", DEFAULT_USER) or DEFAULT_USER
    password = os.environ.get("OVPN_DEFAULT_PASS", DEFAULT_PASS) or DEFAULT_PASS
    path = os.path.join(output_dir, "auth.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"{user}\n{password}\n")


def config_filename(cfg: OvpnConfig) -> str:
    cfg.ensure_parsed_remote()
    # Preserve human name for local pin files
    if cfg.source in {"local", "ovpn-list"}:
        return f"local_{safe_filename_part(cfg.name)}.ovpn"
    if cfg.remote_host and cfg.remote_port:
        base = f"{cfg.source}_{safe_filename_part(cfg.remote_host)}_{cfg.remote_port}"
    elif cfg.remote_host:
        base = f"{cfg.source}_{safe_filename_part(cfg.remote_host)}"
    else:
        base = f"{cfg.source}_{safe_filename_part(cfg.name)}"
    return f"{base}.ovpn"


def dedupe_key(cfg: OvpnConfig) -> str:
    cfg.ensure_parsed_remote()
    if cfg.remote_host and cfg.remote_port:
        return f"{cfg.remote_host.lower()}:{cfg.remote_port}"
    if cfg.remote_host:
        return f"{cfg.remote_host.lower()}:"
    return f"name:{cfg.source}:{cfg.name.lower()}"


def dedupe_and_cap(configs: Iterable[OvpnConfig], max_configs: int) -> list[OvpnConfig]:
    """Dedupe by host:port, then interleave sources so one source cannot fill the cap alone."""
    seen: set[str] = set()
    by_source: dict[str, list[OvpnConfig]] = {}
    order: list[str] = []
    for cfg in configs:
        key = dedupe_key(cfg)
        if key in seen:
            continue
        seen.add(key)
        src = cfg.source or "unknown"
        if src not in by_source:
            by_source[src] = []
            order.append(src)
        by_source[src].append(cfg)

    if not by_source:
        return []

    result: list[OvpnConfig] = []
    indices = {src: 0 for src in order}
    while len(result) < max_configs:
        progressed = False
        for src in order:
            i = indices[src]
            bucket = by_source[src]
            if i >= len(bucket):
                continue
            result.append(bucket[i])
            indices[src] = i + 1
            progressed = True
            if len(result) >= max_configs:
                break
        if not progressed:
            break
    return result


def prepare_body(cfg: OvpnConfig) -> str:
    return inject_auth_path(cfg.body)


def write_configs(configs: list[OvpnConfig], output_dir: str) -> int:
    write_auth_file(output_dir)
    written = 0
    used_names: set[str] = set()
    for cfg in configs:
        filename = config_filename(cfg)
        if filename in used_names:
            stem, ext = os.path.splitext(filename)
            filename = f"{stem}_{written}{ext}"
        used_names.add(filename)

        body = prepare_body(cfg)
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        written += 1
        country = cfg.country or "?"
        log(f"ovpn_refresh - write [{cfg.source}] {filename} country={country}")
    return written


def replace_configs(source_dir: str) -> None:
    os.makedirs(OVPN_DIR, exist_ok=True)
    new_files = set(os.listdir(source_dir))

    for filename in os.listdir(source_dir):
        src = os.path.join(source_dir, filename)
        dst = os.path.join(OVPN_DIR, filename)
        if os.path.isdir(src):
            continue
        shutil.move(src, dst)

    for filename in os.listdir(OVPN_DIR):
        path = os.path.join(OVPN_DIR, filename)
        if not os.path.isfile(path):
            continue
        if filename not in new_files:
            os.unlink(path)


def fetch_sources(source_keys: list[str], allowed: set[str]) -> list[OvpnConfig]:
    register_builtin_sources()
    available = set(list_source_keys())
    collected: list[OvpnConfig] = []

    for key in source_keys:
        if key not in available:
            log(
                "ovpn_refresh - unknown source "
                f"'{key}', skip (available: {','.join(sorted(available))})"
            )
            continue
        source = get_source(key)
        if source is None:
            continue
        try:
            log(f"ovpn_refresh - fetch start: {key}")
            configs = source.fetch(allowed)
            log(f"ovpn_refresh - fetch done: {key} ({len(configs)} configs)")
            collected.extend(configs)
        except Exception as exc:
            log(f"ovpn_refresh - fetch failed: {key}: {exc}")
            continue
    return collected


def maybe_live_filter(configs: list[OvpnConfig], *, force: bool = False) -> list[OvpnConfig]:
    """Run TCP live-check when forced (local list) or OVPN_LIVE_CHECK=1."""
    if not configs:
        return configs
    if force or live_check_enabled(default=False):
        log("ovpn_refresh - live_check enabled")
        return filter_live(configs)
    return configs


def fetch_prefer_local(allowed: set[str]) -> list[OvpnConfig]:
    """If ovpn-list has *.ovpn, use only those (after live-check); else remote sources."""
    list_dir = resolve_list_dir()
    priority = env_bool("OVPN_LIST_PRIORITY", True)
    live_local = env_bool("OVPN_LIST_LIVE_CHECK", True)

    if priority and list_dir_has_ovpn(list_dir):
        log(f"ovpn_refresh - ovpn-list present: {list_dir} (priority over remote sources)")
        local_cfgs = fetch_sources(["local"], allowed)
        if live_local:
            local_cfgs = maybe_live_filter(local_cfgs, force=True)
        if local_cfgs:
            log(f"ovpn_refresh - using {len(local_cfgs)} live local profile(s) only")
            return local_cfgs
        log(
            "ovpn_refresh - ovpn-list had files but none passed live-check; "
            "falling back to OVPN_SOURCES"
        )

    sources = selected_sources()
    # Avoid double-fetch if user already put local in OVPN_SOURCES
    collected = fetch_sources(sources, allowed)
    return maybe_live_filter(collected, force=False)


def main() -> None:
    log("ovpn_refresh - start")
    allowed = parse_country_filter(os.environ.get("COUNTRY_FILTER", "all"))
    if allowed:
        log(f"ovpn_refresh - country filter: {','.join(sorted(allowed))}")
    else:
        log("ovpn_refresh - country filter: all")

    max_configs = env_int("MAX_OVPN_CONFIGS", DEFAULT_MAX)
    list_dir = resolve_list_dir()
    log(
        f"ovpn_refresh - OVPN_LIST_DIR={list_dir} "
        f"has_files={list_dir_has_ovpn(list_dir)} "
        f"priority={env_bool('OVPN_LIST_PRIORITY', True)}"
    )
    log(f"ovpn_refresh - remote sources: {','.join(selected_sources())} max={max_configs}")

    collected = fetch_prefer_local(allowed)
    selected = dedupe_and_cap(collected, max_configs)
    log(f"ovpn_refresh - after dedupe/cap: {len(selected)} (raw={len(collected)})")

    if not selected:
        raise RuntimeError("No usable ovpn configs from any enabled source")

    with tempfile.TemporaryDirectory() as temp_dir:
        written = write_configs(selected, temp_dir)
        if written == 0:
            raise RuntimeError("Failed to write any ovpn configs")
        replace_configs(temp_dir)
        log(f"ovpn_refresh - end ({written} configs)")


if __name__ == "__main__":
    main()
