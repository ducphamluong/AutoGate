#!/usr/bin/env python3
"""Download OpenVPN profiles from publicvpnlist.com into ./ovpn-list.

Default (recommended):
  1) catalog
  2) TCP live/die precheck on host:port  ← default ON
  3) download .ovpn only for LIVE hosts
  4) write into ./ovpn-list (never deletes folder or other files)

Examples:
  python download_publicvpnlist.py
  python download_publicvpnlist.py --country JP --max 100
  python download_publicvpnlist.py --no-precheck
  .\\download_publicvpnlist.bat JP 100
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROXY = ROOT / "proxy"
if str(PROXY) not in sys.path:
    sys.path.insert(0, str(PROXY))

from ovpn_sources.base import inject_auth_path, safe_filename_part  # noqa: E402
from ovpn_sources.country_map import parse_country_filter  # noqa: E402
from ovpn_sources.publicvpnlist import PublicVpnListSource  # noqa: E402

# Internal defaults (not exposed as many CLI knobs)
_TOKEN_WORKERS = 1
_TOKEN_DELAY = 0.45
_PRECHECK_WORKERS = 80
_PRECHECK_TIMEOUT = 2.0
_PRECHECK_MULT = 5
_BUDGET = 400


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Download live .ovpn from publicvpnlist.com → ovpn-list/"
    )
    p.add_argument(
        "--country",
        "-c",
        default=os.environ.get("COUNTRY_FILTER", "all"),
        help="ISO2: all | JP | US,JP (default: all)",
    )
    p.add_argument(
        "--max",
        "-n",
        type=int,
        default=int(os.environ.get("PUBLICVPNLIST_MAX", "100") or 100),
        help="How many LIVE profiles to keep (default 100)",
    )
    p.add_argument(
        "--out",
        "-o",
        default=str(ROOT / "ovpn-list"),
        help="Output folder (default ./ovpn-list). Never deleted.",
    )
    # Simple precheck toggle only
    p.add_argument(
        "--precheck",
        dest="precheck",
        action="store_true",
        default=True,
        help="TCP live/die check before download (default: ON)",
    )
    p.add_argument(
        "--no-precheck",
        dest="precheck",
        action="store_false",
        help="Skip live check (download without TCP filter)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Enough candidates so live filter can still fill --max
    max_per = max(args.max * _PRECHECK_MULT, args.max)

    os.environ["PUBLICVPNLIST_MAX"] = str(max(1, args.max))
    os.environ["PUBLICVPNLIST_MAX_PER_COUNTRY"] = str(max_per)
    os.environ["PUBLICVPNLIST_REQUEST_DELAY"] = str(_TOKEN_DELAY)
    os.environ["PUBLICVPNLIST_BUDGET_SECONDS"] = str(_BUDGET)
    os.environ["PUBLICVPNLIST_DOWNLOAD_WORKERS"] = str(_TOKEN_WORKERS)
    # Default: check live/die FIRST
    os.environ["PUBLICVPNLIST_PRECHECK"] = "1" if args.precheck else "0"
    os.environ["PUBLICVPNLIST_PRECHECK_WORKERS"] = str(_PRECHECK_WORKERS)
    os.environ["PUBLICVPNLIST_PRECHECK_TIMEOUT"] = str(_PRECHECK_TIMEOUT)
    os.environ["PUBLICVPNLIST_PRECHECK_MULT"] = str(_PRECHECK_MULT)
    os.environ["PUBLICVPNLIST_LIVE_CHECK"] = "0"

    allowed = parse_country_filter(args.country)
    print("=== PublicVPNList downloader ===", flush=True)
    print(f"country={args.country!r}  max={args.max}  precheck={args.precheck}", flush=True)
    print(f"out={out_dir}", flush=True)
    if args.precheck:
        print("mode: TCP live/die first → only download LIVE hosts", flush=True)
    else:
        print("mode: download without TCP precheck", flush=True)

    t0 = time.time()
    configs = PublicVpnListSource().fetch(allowed)
    elapsed = time.time() - t0
    print(f"got {len(configs)} configs in {elapsed:.1f}s", flush=True)

    if not configs:
        print("ERROR: no configs (empty, all dead, or rate-limited)", flush=True)
        return 1

    written = 0
    for cfg in configs[: args.max]:
        cfg.ensure_parsed_remote()
        host = safe_filename_part(cfg.remote_host or cfg.name)
        port = cfg.remote_port or 0
        country = (cfg.country or "XX").upper()
        name = f"pvl_{country}_{host}_{port}.ovpn"
        (out_dir / name).write_text(inject_auth_path(cfg.body), encoding="utf-8")
        written += 1
        print(f"  write {name}", flush=True)

    auth = out_dir / "auth.txt"
    if not auth.exists():
        user = os.environ.get("OVPN_DEFAULT_USER", "vpn")
        password = os.environ.get("OVPN_DEFAULT_PASS", "vpn")
        auth.write_text(f"{user}\n{password}\n", encoding="utf-8")

    print(f"OK: wrote {written} profiles to {out_dir} ({elapsed:.1f}s)", flush=True)
    print("Next: .\\autogate.bat ovpn", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
