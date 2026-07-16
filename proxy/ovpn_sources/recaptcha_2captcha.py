"""Optional reCAPTCHA v2/v3 solver via 2Captcha HTTP API.

Env:
  TWOCAPTCHA_API_KEY / TWO_CAPTCHA_API_KEY / CAPTCHA_API_KEY
  TWOCAPTCHA_MIN_SCORE   (v3, default 0.3)
  TWOCAPTCHA_POLL_SECONDS (default 120)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

IN_URL = "https://2captcha.com/in.php"
RES_URL = "https://2captcha.com/res.php"


def captcha_api_key() -> str:
    for name in (
        "TWOCAPTCHA_API_KEY",
        "TWO_CAPTCHA_API_KEY",
        "CAPTCHA_API_KEY",
        "OPENPROXYLIST_2CAPTCHA_KEY",
    ):
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return ""


def solve_recaptcha_v3(
    *,
    sitekey: str,
    pageurl: str,
    action: str = "validate_captcha",
    min_score: float | None = None,
    poll_seconds: int | None = None,
) -> str:
    """Return g-recaptcha-response token or raise RuntimeError."""
    api_key = captcha_api_key()
    if not api_key:
        raise RuntimeError("2captcha API key not set (TWOCAPTCHA_API_KEY)")

    if min_score is None:
        raw = os.environ.get("TWOCAPTCHA_MIN_SCORE", "0.3").strip()
        try:
            min_score = float(raw)
        except ValueError:
            min_score = 0.3

    if poll_seconds is None:
        raw = os.environ.get("TWOCAPTCHA_POLL_SECONDS", "120").strip()
        poll_seconds = int(raw) if raw.isdigit() else 120

    payload = {
        "key": api_key,
        "method": "userrecaptcha",
        "version": "v3",
        "action": action,
        "min_score": str(min_score),
        "googlekey": sitekey,
        "pageurl": pageurl,
        "json": "1",
    }
    task_id = _create_task(payload)
    return _poll_result(api_key, task_id, poll_seconds)


def _create_task(payload: dict) -> str:
    body = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        IN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", "replace")
    data = json.loads(raw)
    if data.get("status") != 1:
        raise RuntimeError(f"2captcha create failed: {data.get('request') or raw}")
    return str(data["request"])


def _poll_result(api_key: str, task_id: str, poll_seconds: int) -> str:
    deadline = time.monotonic() + max(30, poll_seconds)
    # 2captcha docs: wait ~10-20s before first poll for recaptcha
    time.sleep(10)
    while time.monotonic() < deadline:
        qs = urllib.parse.urlencode(
            {
                "key": api_key,
                "action": "get",
                "id": task_id,
                "json": "1",
            }
        )
        req = urllib.request.Request(f"{RES_URL}?{qs}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", "replace")
            data = json.loads(raw)
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            time.sleep(5)
            continue

        if data.get("status") == 1:
            token = str(data.get("request") or "")
            if not token:
                raise RuntimeError("2captcha returned empty token")
            return token
        req_msg = str(data.get("request") or "")
        if req_msg == "CAPCHA_NOT_READY" or req_msg == "CAPTCHA_NOT_READY":
            time.sleep(5)
            continue
        raise RuntimeError(f"2captcha poll failed: {req_msg or raw}")
    raise RuntimeError(f"2captcha timeout after {poll_seconds}s (task {task_id})")
