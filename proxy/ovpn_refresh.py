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
from ovpn_sources.registry import (  # noqa: E402
    get_source,
    list_source_keys,
    register_builtin_sources,
)

OVPN_DIR = os.environ.get("OVPN_DIR", "/ovpn")
DEFAULT_SOURCES = "vpngate,ipspeed"
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
    seen: set[str] = set()
    result: list[OvpnConfig] = []
    for cfg in configs:
        key = dedupe_key(cfg)
        if key in seen:
            continue
        seen.add(key)
        result.append(cfg)
        if len(result) >= max_configs:
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


def fetch_all(allowed: set[str]) -> list[OvpnConfig]:
    register_builtin_sources()
    available = set(list_source_keys())
    collected: list[OvpnConfig] = []

    for key in selected_sources():
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


def main() -> None:
    log("ovpn_refresh - start")
    allowed = parse_country_filter(os.environ.get("COUNTRY_FILTER", ""))
    if allowed:
        log(f"ovpn_refresh - country filter: {','.join(sorted(allowed))}")

    max_configs = env_int("MAX_OVPN_CONFIGS", DEFAULT_MAX)
    sources = selected_sources()
    log(f"ovpn_refresh - sources: {','.join(sources)} max={max_configs}")

    collected = fetch_all(allowed)
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
