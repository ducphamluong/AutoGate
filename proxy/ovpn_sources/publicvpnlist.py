"""PublicVPNList adapter — catalog + temporary download tokens.

Chrome recon + reverse (2026-07-16):

  GET  /local/api/vpn-data.php
       → JSON array (~10k) with id, country slug, host, port, speed, flags

  GET  /test_server.php?id={id}
       → {ok, status: ok|fail|unknown, latencyMs, ...}  (optional live probe)

  POST /get_token.php   body: id={id}
       headers: Accept: application/json, X-Requested-With: XMLHttpRequest
       → {token, url: /download.php?token=..., expiresIn: 300}

  GET  /download.php?token={token}
       → application/x-openvpn-profile (.ovpn body)

Country pages also expose data-id rows as a lighter fallback.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Set
from urllib.parse import urlencode, urljoin

from .base import OvpnConfig, parse_remote, safe_filename_part
from .country_map import normalize_country
from .live_check import filter_rows_live

BASE_URL = "https://publicvpnlist.com/"
CATALOG_URL = urljoin(BASE_URL, "local/api/vpn-data.php")
TOKEN_URL = urljoin(BASE_URL, "get_token.php")
TEST_URL = urljoin(BASE_URL, "test_server.php")
TIMEOUT_SECONDS = 25
CATALOG_TIMEOUT = 60
SOURCE_BUDGET_SECONDS = 90
USER_AGENT = (
    "Mozilla/5.0 (compatible; AutoGate/1.0; +research; polite scrape)"
)

# ISO2 → site country slug used in catalog /country/{slug}/
ISO2_TO_SLUG: dict[str, str] = {
    "JP": "japan",
    "KR": "south-korea",
    "US": "usa",
    "VN": "vietnam",
    "TH": "thailand",
    "RU": "russia",
    "CA": "canada",
    "ID": "indonesia",
    "FR": "france",
    "DE": "germany",
    "GB": "uk",
    "UK": "uk",
    "TW": "taiwan",
    "HK": "hong-kong",
    "SG": "singapore",
    "IN": "india",
    "BR": "brazil",
    "AU": "australia",
    "NL": "netherlands",
    "PL": "poland",
    "IT": "italy",
    "ES": "spain",
    "CN": "china",
    "PH": "philippines",
    "MY": "malaysia",
    "MX": "mexico",
    "TR": "turkey",
    "UA": "ukraine",
    "AR": "argentina",
    "HR": "croatia-local-name-hrvatska",
}

# reverse slug → ISO2 (best effort)
SLUG_TO_ISO2: dict[str, str] = {v: k for k, v in ISO2_TO_SLUG.items()}
SLUG_TO_ISO2["united-states"] = "US"
SLUG_TO_ISO2["south-korea"] = "KR"
SLUG_TO_ISO2["uk"] = "GB"
SLUG_TO_ISO2["united-kingdom"] = "GB"

DATA_ID_RE = re.compile(r'data-id=["\'](\d+)["\']', re.IGNORECASE)


class PublicVpnListSource:
    key = "publicvpnlist"

    def fetch(self, allowed_countries: Set[str]) -> list[OvpnConfig]:
        deadline = time.monotonic() + self._budget()
        max_per_country = self._max_per_country()
        do_site_live = self._live_check_enabled()
        precheck = self._precheck_enabled()

        candidates = self._load_candidates(allowed_countries, deadline)
        if not candidates:
            print(
                "publicvpnlist: no candidates "
                "(catalog/country pages empty or filtered out)",
                flush=True,
            )
            return []

        global_max = self._global_max()
        # Over-select for precheck so enough survive TCP filter
        pool_size = max(global_max * self._precheck_multiplier(), global_max)
        selected = self._select_candidates(candidates, max_per_country)[:pool_size]
        print(
            f"publicvpnlist: selected {len(selected)} candidates "
            f"(target live downloads={global_max}, precheck={precheck})",
            flush=True,
        )

        if precheck:
            # Fast parallel TCP on catalog host:port BEFORE token download
            selected = filter_rows_live(
                selected,
                timeout=self._precheck_timeout(),
                workers=self._precheck_workers(),
                stop_after=None,
            )
            if not selected:
                print("publicvpnlist: no candidates passed TCP precheck", flush=True)
                return []

        # Only download tokens for live (or top) rows
        to_download = selected[: max(global_max * 2, global_max)]
        configs = self._download_rows_parallel(
            to_download,
            global_max=global_max,
            deadline=deadline,
            do_site_live=do_site_live,
        )

        if not configs:
            print(
                "publicvpnlist: candidates found but no .ovpn downloaded "
                "(token/download failed or rate-limited)",
                flush=True,
            )
        return configs

    def _download_rows_parallel(
        self,
        rows: list[dict[str, Any]],
        *,
        global_max: int,
        deadline: float,
        do_site_live: bool,
    ) -> list[OvpnConfig]:
        """Download tokens with global rate limit (site returns HTTP 429 if burst).

        TCP precheck is already parallel; token API must stay gentle.
        Default: 1 worker, paced delay; retries on 429.
        """
        workers = self._download_workers()
        delay = self._request_delay()
        rate_lock = Lock()
        last_req = {"t": 0.0}
        configs: list[OvpnConfig] = []

        def pace() -> None:
            with rate_lock:
                now = time.monotonic()
                wait = delay - (now - last_req["t"])
                if wait > 0:
                    time.sleep(wait)
                last_req["t"] = time.monotonic()

        def one(row: dict[str, Any]) -> OvpnConfig | None:
            if time.monotonic() > deadline:
                return None
            server_id = str(row.get("id") or "").strip()
            if not server_id:
                return None
            if do_site_live:
                self._live_test(server_id)

            body = None
            for attempt in range(4):
                if time.monotonic() > deadline:
                    return None
                pace()
                try:
                    body = self._download_ovpn(server_id)
                    break
                except Exception as exc:
                    msg = str(exc)
                    print(f"publicvpnlist download fail id={server_id}: {exc}", flush=True)
                    if "429" in msg:
                        sleep_s = min(25, 2 ** (attempt + 1))
                        print(f"publicvpnlist: 429 retry in {sleep_s}s", flush=True)
                        time.sleep(sleep_s)
                        continue
                    return None
            if not body or "remote " not in body.lower() or body.lstrip().startswith("<"):
                return None

            host, port = parse_remote(body)
            if not host:
                host = str(row.get("host") or row.get("ip") or "")
            if not port:
                try:
                    port = int(row.get("port") or 0) or None
                except (TypeError, ValueError):
                    port = None

            country = self._row_country_iso2(row)
            cfg = OvpnConfig(
                source=self.key,
                name=f"pvl_{safe_filename_part(host or server_id)}_{port or 0}",
                country=country,
                body=body,
                remote_host=host or None,
                remote_port=port,
            )
            cfg.detect_auth()
            return cfg

        # Sequential or lightly parallel; always globally paced
        if workers <= 1:
            for row in rows:
                if time.monotonic() > deadline or len(configs) >= global_max:
                    break
                cfg = one(row)
                if cfg is None:
                    continue
                configs.append(cfg)
                print(
                    f"publicvpnlist got {len(configs)}/{global_max}: "
                    f"{cfg.remote_host}:{cfg.remote_port}",
                    flush=True,
                )
            return configs[:global_max]

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = []
            for row in rows:
                if len(futs) >= global_max * 2:
                    break
                futs.append(pool.submit(one, row))
            for fut in as_completed(futs):
                if time.monotonic() > deadline:
                    break
                cfg = fut.result()
                if cfg is None:
                    continue
                configs.append(cfg)
                print(
                    f"publicvpnlist got {len(configs)}/{global_max}: "
                    f"{cfg.remote_host}:{cfg.remote_port}",
                    flush=True,
                )
                if len(configs) >= global_max:
                    break
        return configs[:global_max]

    def _max_per_country(self) -> int:
        raw = os.environ.get("PUBLICVPNLIST_MAX_PER_COUNTRY", "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        return 3

    def _global_max(self) -> int:
        raw = os.environ.get("PUBLICVPNLIST_MAX", "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        return 20

    def _request_delay(self) -> float:
        # Global min spacing between get_token calls (avoid HTTP 429)
        raw = os.environ.get("PUBLICVPNLIST_REQUEST_DELAY", "0.45").strip()
        try:
            return max(0.0, float(raw))
        except ValueError:
            return 0.45

    def _download_workers(self) -> int:
        # Default 1: token API is rate-limited; precheck is already parallel
        raw = os.environ.get("PUBLICVPNLIST_DOWNLOAD_WORKERS", "1").strip()
        if raw.isdigit() and int(raw) > 0:
            return min(8, int(raw))
        return 1

    def _precheck_enabled(self) -> bool:
        raw = os.environ.get("PUBLICVPNLIST_PRECHECK", "1").strip().lower()
        if not raw:
            return True
        return raw in {"1", "true", "yes", "on"}

    def _precheck_workers(self) -> int:
        raw = os.environ.get("PUBLICVPNLIST_PRECHECK_WORKERS", "60").strip()
        if raw.isdigit() and int(raw) > 0:
            return min(200, int(raw))
        return 60

    def _precheck_timeout(self) -> float:
        raw = os.environ.get("PUBLICVPNLIST_PRECHECK_TIMEOUT", "2").strip()
        try:
            return max(0.5, float(raw))
        except ValueError:
            return 2.0

    def _precheck_multiplier(self) -> int:
        """How many candidates to TCP-scan relative to MAX (e.g. 4x)."""
        raw = os.environ.get("PUBLICVPNLIST_PRECHECK_MULT", "4").strip()
        if raw.isdigit() and int(raw) > 0:
            return min(20, int(raw))
        return 4

    def _budget(self) -> int:
        raw = os.environ.get("PUBLICVPNLIST_BUDGET_SECONDS", "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        return SOURCE_BUDGET_SECONDS

    def _live_check_enabled(self) -> bool:
        # Default off: token works without live check; live adds RTT per server.
        return os.environ.get("PUBLICVPNLIST_LIVE_CHECK", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _request(
        self,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = TIMEOUT_SECONDS,
    ) -> bytes:
        h = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        }
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, headers=h, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} for {url}") from exc

    def _load_candidates(
        self, allowed: Set[str], deadline: float
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            if time.monotonic() < deadline:
                raw = self._request(CATALOG_URL, timeout=CATALOG_TIMEOUT)
                data = json.loads(raw.decode("utf-8", "replace"))
                if isinstance(data, list):
                    rows = [r for r in data if isinstance(r, dict)]
                    print(f"publicvpnlist catalog: {len(rows)} rows", flush=True)
        except Exception as exc:
            print(f"publicvpnlist catalog fail: {exc}", flush=True)

        if not rows:
            rows = self._load_from_country_pages(allowed, deadline)

        if not allowed:
            return [r for r in rows if r.get("configAvailable", True) is not False]

        allowed_slugs = {ISO2_TO_SLUG.get(c, "").lower() for c in allowed}
        allowed_slugs.discard("")
        # also accept raw lower country names if map missing
        allowed_lower = {c.lower() for c in allowed}

        filtered: list[dict[str, Any]] = []
        for row in rows:
            slug = str(row.get("country") or "").lower().strip()
            iso = self._row_country_iso2(row)
            if iso in allowed or slug in allowed_slugs or slug in allowed_lower:
                if row.get("configAvailable", True) is False:
                    continue
                filtered.append(row)
        return filtered

    def _load_from_country_pages(
        self, allowed: Set[str], deadline: float
    ) -> list[dict[str, Any]]:
        """Lighter fallback: scrape data-id from /country/{slug}/ pages."""
        targets: list[tuple[str, str]] = []
        if allowed:
            for code in sorted(allowed):
                slug = ISO2_TO_SLUG.get(code.upper())
                if slug:
                    targets.append((code.upper(), slug))
        else:
            # home page snapshot rows only
            targets.append(("", ""))

        rows: list[dict[str, Any]] = []
        for code, slug in targets:
            if time.monotonic() > deadline:
                break
            path = f"country/{slug}/" if slug else ""
            try:
                html = self._request(urljoin(BASE_URL, path)).decode("utf-8", "replace")
            except Exception:
                continue
            seen: set[str] = set()
            for match in DATA_ID_RE.finditer(html):
                sid = match.group(1)
                if sid in seen:
                    continue
                seen.add(sid)
                rows.append(
                    {
                        "id": int(sid) if sid.isdigit() else sid,
                        "country": slug or "",
                        "countryName": code or "",
                        "configAvailable": True,
                    }
                )
        print(f"publicvpnlist country-page fallback: {len(rows)} ids", flush=True)
        return rows

    def _select_candidates(
        self, rows: list[dict[str, Any]], max_per_country: int
    ) -> list[dict[str, Any]]:
        def sort_key(row: dict[str, Any]):
            return (
                0 if row.get("isRecommended") else 1,
                0 if row.get("isFresh") else 1,
                0 if row.get("lastCheckOk") else 1,
                0 if row.get("configAvailable", True) else 1,
                -float(row.get("speed") or row.get("medianRecentSpeed") or 0),
                float(row.get("latency") or row.get("medianRecentLatency") or 9999),
            )

        # Group by ISO2 (or slug)
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = self._row_country_iso2(row) or str(row.get("country") or "XX")
            buckets.setdefault(key, []).append(row)

        selected: list[dict[str, Any]] = []
        for key in sorted(buckets.keys()):
            group = sorted(buckets[key], key=sort_key)
            selected.extend(group[:max_per_country])
        return selected

    def _row_country_iso2(self, row: dict[str, Any]) -> str:
        slug = str(row.get("country") or "").strip().lower()
        if slug in SLUG_TO_ISO2:
            return SLUG_TO_ISO2[slug]
        name = str(row.get("countryName") or "").strip()
        code = normalize_country(name) or normalize_country(slug)
        return code

    def _live_test(self, server_id: str) -> bool | None:
        """Return True/False for reachability; None if API error."""
        try:
            url = f"{TEST_URL}?{urlencode({'id': server_id, '_': str(int(time.time()))})}"
            raw = self._request(url, headers={"Accept": "application/json"})
            data = json.loads(raw.decode("utf-8", "replace"))
            if not data.get("ok"):
                return None
            return data.get("status") == "ok" or data.get("live") is True
        except Exception:
            return None

    def _get_token(self, server_id: str) -> dict[str, Any]:
        body = urlencode({"id": str(server_id)}).encode("utf-8")
        raw = self._request(
            TOKEN_URL,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Referer": urljoin(BASE_URL, f"download/{server_id}/"),
            },
        )
        data = json.loads(raw.decode("utf-8", "replace"))
        if not data.get("token") and not data.get("url"):
            raise RuntimeError(data.get("error") or data.get("message") or "token missing")
        return data

    def _download_ovpn(self, server_id: str) -> str:
        token_data = self._get_token(server_id)
        rel = token_data.get("url") or f"download.php?token={token_data['token']}"
        dl_url = urljoin(BASE_URL, rel)
        raw = self._request(
            dl_url,
            headers={
                "Accept": "*/*",
                "Referer": urljoin(BASE_URL, f"download/{server_id}/"),
            },
        )
        return raw.decode("utf-8", "replace")
