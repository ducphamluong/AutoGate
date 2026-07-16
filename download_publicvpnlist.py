#!/usr/bin/env python3
"""Download OpenVPN profiles from publicvpnlist.com into ./ovpn-list.

Examples (PowerShell, from repo root):
  python download_publicvpnlist.py
  python download_publicvpnlist.py --country JP --max 10
  python download_publicvpnlist.py --country US,JP --max 5 --no-live
  python download_publicvpnlist.py --out ovpn-list --clear

Flow (same as in-container adapter):
  1) GET  /local/api/vpn-data.php          catalog
  2) POST /get_token.php  id=...
  3) GET  /download.php?token=...          .ovpn body
  4) optional TCP live-check host:port
  5) write files to output dir (default ./ovpn-list)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROXY = ROOT / "proxy"
if str(PROXY) not in sys.path:
    sys.path.insert(0, str(PROXY))

from ovpn_sources.base import inject_auth_path, safe_filename_part  # noqa: E402
from ovpn_sources.country_map import parse_country_filter  # noqa: E402
from ovpn_sources.live_check import filter_live  # noqa: E402
from ovpn_sources.publicvpnlist import PublicVpnListSource  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Download .ovpn list from publicvpnlist.com into ovpn-list/"
    )
    p.add_argument(
        "--country",
        "-c",
        default=os.environ.get("COUNTRY_FILTER", "all"),
        help="ISO2 filter: all | JP | US,JP (default: env COUNTRY_FILTER or all)",
    )
    p.add_argument(
        "--max",
        "-n",
        type=int,
        default=int(os.environ.get("PUBLICVPNLIST_MAX", "10") or 10),
        help="Max configs to download (default 10)",
    )
    p.add_argument(
        "--max-per-country",
        type=int,
        default=int(os.environ.get("PUBLICVPNLIST_MAX_PER_COUNTRY", "5") or 5),
        help="Max per country when multi-country (default 5)",
    )
    p.add_argument(
        "--out",
        "-o",
        default=str(ROOT / "ovpn-list"),
        help="Output directory (default ./ovpn-list)",
    )
    p.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing *.ovpn in output dir before write",
    )
    p.add_argument(
        "--live",
        dest="live",
        action="store_true",
        default=True,
        help="TCP live-check before save (default: on)",
    )
    p.add_argument(
        "--no-live",
        dest="live",
        action="store_false",
        help="Skip TCP live-check",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=float(os.environ.get("PUBLICVPNLIST_REQUEST_DELAY", "1.2") or 1.2),
        help="Seconds between token requests (default 1.2, avoid HTTP 429)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("OVPN_LIVE_CHECK_TIMEOUT", "3") or 3),
        help="Live-check TCP timeout seconds",
    )
    p.add_argument(
        "--budget",
        type=int,
        default=int(os.environ.get("PUBLICVPNLIST_BUDGET_SECONDS", "180") or 180),
        help="Source time budget seconds",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Configure adapter via env (PublicVpnListSource reads these)
    os.environ["PUBLICVPNLIST_MAX"] = str(max(1, args.max))
    os.environ["PUBLICVPNLIST_MAX_PER_COUNTRY"] = str(max(1, args.max_per_country))
    os.environ["PUBLICVPNLIST_REQUEST_DELAY"] = str(max(0.0, args.delay))
    os.environ["PUBLICVPNLIST_BUDGET_SECONDS"] = str(max(30, args.budget))
    os.environ["PUBLICVPNLIST_LIVE_CHECK"] = "0"  # site live probe; we do TCP after
    os.environ["OVPN_LIVE_CHECK_TIMEOUT"] = str(args.timeout)

    allowed = parse_country_filter(args.country)
    print("=== PublicVPNList downloader ===", flush=True)
    print(f"country={args.country!r} -> filter={sorted(allowed) or 'ALL'}", flush=True)
    print(f"max={args.max} max_per_country={args.max_per_country} delay={args.delay}s", flush=True)
    print(f"out={out_dir} live={args.live}", flush=True)

    source = PublicVpnListSource()
    configs = source.fetch(allowed)
    print(f"downloaded raw: {len(configs)}", flush=True)

    if args.live and configs:
        configs = filter_live(configs, timeout=args.timeout)
        print(f"after live-check: {len(configs)}", flush=True)

    if not configs:
        print("ERROR: no configs to write (site empty, 429, or all dead)", flush=True)
        return 1

    # Cap again after live filter
    configs = configs[: args.max]

    if args.clear:
        removed = 0
        for path in out_dir.glob("*.ovpn"):
            path.unlink(missing_ok=True)
            removed += 1
        print(f"cleared {removed} old .ovpn in {out_dir}", flush=True)

    written = 0
    for cfg in configs:
        cfg.ensure_parsed_remote()
        host = safe_filename_part(cfg.remote_host or cfg.name)
        port = cfg.remote_port or 0
        country = (cfg.country or "XX").upper()
        name = f"pvl_{country}_{host}_{port}.ovpn"
        body = inject_auth_path(cfg.body)
        path = out_dir / name
        path.write_text(body, encoding="utf-8")
        written += 1
        print(f"  write {name} country={country}", flush=True)

    # Ensure auth helper exists for SoftEther-style configs
    auth = out_dir / "auth.txt"
    if not auth.exists():
        user = os.environ.get("OVPN_DEFAULT_USER", "vpn")
        password = os.environ.get("OVPN_DEFAULT_PASS", "vpn")
        auth.write_text(f"{user}\n{password}\n", encoding="utf-8")

    print(f"OK: wrote {written} files to {out_dir}", flush=True)
    print(
        "Next: .\\autogate.bat ovpn   "
        "(OVPN_LIST_PRIORITY=1 will use ovpn-list after live-check)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
