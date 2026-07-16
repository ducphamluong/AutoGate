#!/usr/bin/env python3
import csv
import json
import os
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = "0.0.0.0"
PORT = int(os.environ.get("PROXY_LINKS_UI_PORT", "2087"))
DEFAULT_HTML_FILE = os.path.join(os.path.dirname(__file__), "proxy-links-ui.html")
HTML_FILE = os.environ.get("PROXY_LINKS_UI_HTML", DEFAULT_HTML_FILE)
STATS_URL = os.environ.get("HAPROXY_STATS_CSV_URL", "http://127.0.0.1:10000/;csv")
PUBLIC_HOST = os.environ.get("PROXY_PUBLIC_HOST", "127.0.0.1")
WORKER_BASE_PORT = int(os.environ.get("PROXY_WORKER_BASE_PORT", "56800"))
WORKER_COUNT = int(os.environ.get("PROXY_WORKER_COUNT", "10"))
ROTATING_PORT = int(os.environ.get("PROXY_ROTATING_PORT", "56789"))
OVPN_STATUS_DIR = Path(os.environ.get("OVPN_STATUS_DIR", "/ovpn/status"))


def proxy_url(port):
    return f"http://{PUBLIC_HOST}:{port}"


def fetch_haproxy_stats():
    try:
        with urllib.request.urlopen(STATS_URL, timeout=2) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception:
        return {}

    lines = [line.lstrip("# ") if line.startswith("#") else line for line in text.splitlines()]
    rows = {}
    for row in csv.DictReader(lines):
        pxname = row.get("pxname", "")
        svname = row.get("svname", "")
        if not svname or svname in {"FRONTEND", "BACKEND"}:
            continue
        if pxname == f"worker_{svname}":
            rows[svname] = row.get("status") or "UNKNOWN"
        elif pxname == "vpn" and svname not in rows:
            rows[svname] = row.get("status") or "UNKNOWN"
    return rows


def status_kind(status):
    status = status or "UNKNOWN"
    if status.startswith("UP"):
        return "up"
    if status in {"UNKNOWN", ""}:
        return "unknown"
    return "down"


def load_ovpn_status_map():
    """Read /ovpn/status/vpnXX.json written by slave/ovpn.sh."""
    out = {}
    if not OVPN_STATUS_DIR.is_dir():
        return out
    for path in sorted(OVPN_STATUS_DIR.glob("vpn*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        name = data.get("worker") or path.stem
        out[name] = data
    return out


def empty_ovpn_fields():
    return {
        "file": "",
        "local_list_file": "",
        "remote_host": "",
        "remote_port": "",
        "remote": "",
        "proto": "",
        "updated_at": 0,
    }


def enrich_worker(index, stats, ovpn_map):
    name = f"vpn{index:02d}"
    status = stats.get(name) or "UNKNOWN"
    kind = status_kind(status)
    ovpn = ovpn_map.get(name) or {}
    remote_host = ovpn.get("remote_host") or ""
    remote_port = str(ovpn.get("remote_port") or "")
    remote = f"{remote_host}:{remote_port}" if remote_host else ""
    return {
        "name": name,
        "label": f"Worker {index:02d}",
        "port": WORKER_BASE_PORT + index,
        "url": proxy_url(WORKER_BASE_PORT + index),
        "status": status,
        "kind": kind,
        "file": ovpn.get("file") or "",
        "local_list_file": ovpn.get("local_list_file") or "",
        "remote_host": remote_host,
        "remote_port": remote_port,
        "remote": remote,
        "proto": ovpn.get("proto") or "",
        "updated_at": int(ovpn.get("updated_at") or 0),
    }


def build_payload():
    stats = fetch_haproxy_stats()
    ovpn_map = load_ovpn_status_map()
    workers = [enrich_worker(index, stats, ovpn_map) for index in range(WORKER_COUNT)]
    backend_up_count = sum(1 for w in workers if w["kind"] == "up")
    mapped = sum(1 for w in workers if w.get("file"))

    rotating_kind = "up" if backend_up_count else "unknown"
    rotating = {
        "label": "Rotating pool",
        "port": ROTATING_PORT,
        "url": proxy_url(ROTATING_PORT),
        "status": "READY" if backend_up_count else "UNKNOWN",
        "kind": rotating_kind,
        **empty_ovpn_fields(),
        "file": "(round-robin all backends)",
    }
    return {
        "generated_at": int(time.time()),
        "country": os.environ.get("COUNTRY_FILTER", ""),
        "ovpn_status_dir": str(OVPN_STATUS_DIR),
        "ovpn_mapped": mapped,
        "rotating": rotating,
        "workers": workers,
    }


def read_html():
    with open(HTML_FILE, "r", encoding="utf-8") as file:
        return file.read()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/", "/index.html"}:
            self.send(read_html(), "text/html; charset=utf-8")
            return
        if self.path == "/api/proxies":
            try:
                payload = build_payload()
            except Exception as exc:
                print(f"proxy-links-ui: payload error: {exc}", flush=True)
                payload = fallback_payload()
            self.send(json.dumps(payload).encode("utf-8"), "application/json")
            return
        if self.path == "/api/ovpn-map":
            try:
                payload = build_payload()
                slim = {
                    "generated_at": payload["generated_at"],
                    "country": payload.get("country", ""),
                    "workers": [
                        {
                            "port": w["port"],
                            "name": w["name"],
                            "status": w["status"],
                            "file": w.get("file") or "",
                            "local_list_file": w.get("local_list_file") or "",
                            "remote": w.get("remote") or "",
                            "proto": w.get("proto") or "",
                            "url": w["url"],
                            "updated_at": w.get("updated_at") or 0,
                        }
                        for w in payload["workers"]
                    ],
                }
            except Exception as exc:
                print(f"proxy-links-ui: ovpn-map error: {exc}", flush=True)
                slim = {"generated_at": int(time.time()), "workers": [], "error": str(exc)}
            self.send(json.dumps(slim, indent=2).encode("utf-8"), "application/json")
            return
        self.send_error(404)

    def send(self, body, content_type):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print("proxy-links-ui:", format % args, flush=True)


def fallback_payload():
    workers = []
    for index in range(WORKER_COUNT):
        port = WORKER_BASE_PORT + index
        workers.append(
            {
                "name": f"vpn{index:02d}",
                "label": f"Worker {index:02d}",
                "port": port,
                "url": proxy_url(port),
                "status": "UNKNOWN",
                "kind": "unknown",
                **empty_ovpn_fields(),
            }
        )
    return {
        "generated_at": int(time.time()),
        "country": os.environ.get("COUNTRY_FILTER", ""),
        "ovpn_mapped": 0,
        "rotating": {
            "label": "Rotating pool",
            "port": ROTATING_PORT,
            "url": proxy_url(ROTATING_PORT),
            "status": "UNKNOWN",
            "kind": "unknown",
            **empty_ovpn_fields(),
            "file": "(round-robin all backends)",
        },
        "workers": workers,
    }


if __name__ == "__main__":
    print(f"Starting proxy links UI on {HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
