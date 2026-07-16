"""Browser-like HTTP + optional real browser for reCAPTCHA v3.

reCAPTCHA v3 is score-based (not a puzzle). A real browser session that loads
the page and calls grecaptcha.execute() usually gets a valid token without
any external captcha-solving service.

Order of preference:
  1. Playwright (OPENPROXYLIST_BROWSER=playwright|auto)
  2. Camoufox   (OPENPROXYLIST_BROWSER=camoufox|auto)
  3. Manual OPENPROXYLIST_RECAPTCHA_TOKEN

HTTP transport:
  - curl_cffi Chrome TLS impersonation when installed
  - urllib fallback
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_IMPERSONATE = "chrome131"


def browser_mode() -> str:
    """auto | playwright | camoufox | off"""
    return os.environ.get("OPENPROXYLIST_BROWSER", "auto").strip().lower() or "auto"


def http_get_or_post(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> str:
    """Browser-like request: curl_cffi (Chrome TLS) then urllib."""
    h = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        h.update(headers)

    cffi_error: Exception | None = None

    # 1) curl_cffi — JA3/TLS close to Chrome
    try:
        from curl_cffi import requests as curl_requests  # type: ignore

        impersonate = os.environ.get("CURL_CFFI_IMPERSONATE", DEFAULT_IMPERSONATE)
        method = "POST" if data is not None else "GET"
        resp = curl_requests.request(
            method,
            url,
            data=data,
            headers=h,
            timeout=timeout,
            impersonate=impersonate,
            allow_redirects=True,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code} for {url}")
        text = resp.text
        if isinstance(text, bytes):
            return text.decode("utf-8", "replace")
        return str(text)
    except ImportError:
        pass
    except Exception as exc:
        cffi_error = exc

    # 2) stdlib urllib
    req = urllib.request.Request(
        url, data=data, headers=h, method="POST" if data is not None else "GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        msg = f"HTTP {exc.code} for {url}"
        if cffi_error is not None:
            msg += f" (curl_cffi also failed: {cffi_error})"
        raise RuntimeError(msg) from exc


def get_recaptcha_v3_token(
    *,
    sitekey: str,
    pageurl: str,
    action: str = "validate_captcha",
    timeout_ms: int = 60000,
) -> str:
    """Obtain g-recaptcha-response by running grecaptcha in a real browser.

    No third-party captcha API. Token quality depends on browser fingerprint.
    """
    mode = browser_mode()
    if mode in ("off", "0", "false", "no"):
        raise RuntimeError("OPENPROXYLIST_BROWSER=off")

    errors: list[str] = []

    if mode in ("auto", "camoufox"):
        try:
            token = _token_camoufox(sitekey, pageurl, action, timeout_ms)
            if token:
                return token
        except Exception as exc:
            errors.append(f"camoufox: {exc}")
            if mode == "camoufox":
                raise RuntimeError("; ".join(errors)) from exc

    if mode in ("auto", "playwright"):
        try:
            token = _token_playwright(sitekey, pageurl, action, timeout_ms)
            if token:
                return token
        except Exception as exc:
            errors.append(f"playwright: {exc}")
            if mode == "playwright":
                raise RuntimeError("; ".join(errors)) from exc

    raise RuntimeError(
        "no browser token ("
        + ("; ".join(errors) if errors else "install playwright or camoufox")
        + ")"
    )


def _token_playwright(
    sitekey: str, pageurl: str, action: str, timeout_ms: int
) -> str:
    from playwright.sync_api import sync_playwright  # type: ignore

    headless = os.environ.get("OPENPROXYLIST_HEADLESS", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    channel = os.environ.get("OPENPROXYLIST_PLAYWRIGHT_CHANNEL", "").strip() or None
    # Prefer system Chrome if requested or on Windows (often already installed)
    if channel is None and os.environ.get("OPENPROXYLIST_USE_SYSTEM_CHROME", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        channel = "chrome"

    with sync_playwright() as p:
        launch_kwargs: dict = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        }
        if channel:
            launch_kwargs["channel"] = channel

        try:
            browser = p.chromium.launch(**launch_kwargs)
        except Exception:
            # Retry without channel (bundled chromium)
            launch_kwargs.pop("channel", None)
            browser = p.chromium.launch(**launch_kwargs)

        try:
            context = browser.new_context(
                user_agent=DEFAULT_UA,
                locale="en-US",
                viewport={"width": 1365, "height": 900},
            )
            # Light stealth
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page = context.new_page()
            page.goto(pageurl, wait_until="domcontentloaded", timeout=timeout_ms)
            # Wait for grecaptcha
            page.wait_for_function(
                "() => typeof grecaptcha !== 'undefined' && !!grecaptcha.execute",
                timeout=timeout_ms,
            )
            token = page.evaluate(
                """async ({sitekey, action}) => {
                    await new Promise((resolve) => grecaptcha.ready(resolve));
                    return await grecaptcha.execute(sitekey, { action });
                }""",
                {"sitekey": sitekey, "action": action},
            )
            if not token or not isinstance(token, str):
                raise RuntimeError("empty token from playwright grecaptcha.execute")
            return token
        finally:
            browser.close()


def _token_camoufox(
    sitekey: str, pageurl: str, action: str, timeout_ms: int
) -> str:
    # Camoufox anti-detect Firefox
    from camoufox.sync_api import Camoufox  # type: ignore

    headless = os.environ.get("OPENPROXYLIST_HEADLESS", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    with Camoufox(headless=headless) as browser:
        page = browser.new_page()
        page.goto(pageurl, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_function(
            "() => typeof grecaptcha !== 'undefined' && !!grecaptcha.execute",
            timeout=timeout_ms,
        )
        token = page.evaluate(
            """async ({sitekey, action}) => {
                await new Promise((resolve) => grecaptcha.ready(resolve));
                return await grecaptcha.execute(sitekey, { action });
            }""",
            {"sitekey": sitekey, "action": action},
        )
        if not token or not isinstance(token, str):
            raise RuntimeError("empty token from camoufox grecaptcha.execute")
        return token


def list_available_backends() -> list[str]:
    found: list[str] = []
    try:
        import playwright  # noqa: F401

        found.append("playwright")
    except ImportError:
        pass
    try:
        import camoufox  # noqa: F401

        found.append("camoufox")
    except ImportError:
        pass
    try:
        import curl_cffi  # noqa: F401

        found.append("curl_cffi")
    except ImportError:
        pass
    return found
