"""Headless-Chrome cookie minter for Coles' Imperva/Incapsula bot protection.

Coles serves an Imperva JS challenge to plain HTTP clients. This module launches a
real (headless) Chrome, lets it solve the challenge once, and harvests the resulting
cookies (``reese84``, ``incap_ses_*``, ``visid_incap_*``, ``nlbi_*``). Those cookies
can then be reused by ``requests`` in :mod:`coles_intel.fetcher` for fast, polite
pagination without a browser on every request.

Implementation uses the Chrome DevTools Protocol (CDP) over a websocket, with no
Selenium/webdriver dependency.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import time
import urllib.request
import urllib.parse
from typing import Any, Optional

import websocket  # websocket-client

log = logging.getLogger(__name__)

DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _http_json(url: str, method: str = "GET", timeout: float = 15.0) -> Any:
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CdpClient:
    """Minimal CDP websocket client supporting command/response + events."""

    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=120)
        self._id = 0

    def cmd(self, method: str, params: Optional[dict] = None) -> dict:
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                return msg
            # events are ignored here

    def evaluate(self, expression: str) -> Any:
        r = self.cmd("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        return r.get("result", {}).get("result", {}).get("value")

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


class ChromeMinter:
    """Launches Chrome, solves the challenge, and returns usable cookies."""

    def __init__(self, chrome_path: str = DEFAULT_CHROME, headless: bool = True,
                 user_agent: Optional[str] = None):
        self.chrome_path = chrome_path
        self.headless = headless
        self.user_agent = user_agent
        self.proc: Optional[subprocess.Popen] = None
        self.port: Optional[int] = None
        self.user_data_dir: Optional[str] = None

    # -- lifecycle -----------------------------------------------------------
    def start(self, port: Optional[int] = None) -> None:
        import tempfile
        self.port = port or self._free_port()
        self.user_data_dir = tempfile.mkdtemp(prefix="coles-chrome-")
        args = [self.chrome_path]
        if self.headless:
            args.append("--headless=new")
        args += [
            "--no-sandbox",
            "--disable-gpu",
            "--disable-gpu-compositing",
            "--disable-software-rasterizer",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--mute-audio",
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.user_data_dir}",
            "--window-size=1440,1200",
            "about:blank",
        ]
        self.proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        self._wait_ready()

    def _free_port(self) -> int:
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def _wait_ready(self, timeout: float = 30.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                _http_json(f"http://127.0.0.1:{self.port}/json/version", timeout=5)
                return
            except Exception:
                time.sleep(0.4)
        raise RuntimeError("Chrome DevTools endpoint did not come up")

    def stop(self) -> None:
        if self.proc is not None:
            try:
                self.proc.terminate()
                time.sleep(0.5)
            except Exception:
                pass
            try:
                self.proc.kill()
            except Exception:
                pass
            self.proc = None
        if self.user_data_dir:
            import shutil
            shutil.rmtree(self.user_data_dir, ignore_errors=True)
            self.user_data_dir = None

    # -- cookie minting ------------------------------------------------------
    def mint_cookies(self, url: str, settle_selector: str,
                     settle_timeout: float = 120.0) -> dict[str, str]:
        """Navigate to ``url``, wait for ``settle_selector``, return cookies dict."""
        if self.proc is None or self.port is None:
            self.start()

        tabs = [t for t in _http_json(f"http://127.0.0.1:{self.port}/json")
                if t.get("type") == "page"]
        if not tabs:
            raise RuntimeError("No page target available from Chrome")
        ws_url = tabs[0]["webSocketDebuggerUrl"]

        cdp = CdpClient(ws_url)
        try:
            cdp.cmd("Page.enable")
            cdp.cmd("Network.enable")
            cdp.cmd("Runtime.enable")
            if self.user_agent:
                cdp.cmd("Network.setUserAgentOverride", {
                    "userAgent": self.user_agent,
                    "acceptLanguage": "en-AU,en;q=0.9",
                    "platform": "macOS",
                })
            cdp.cmd("Page.navigate", {"url": url})
            self._wait_for_selector(cdp, settle_selector, settle_timeout)
            cookies_raw = cdp.cmd("Network.getAllCookies")["result"]["cookies"]
        finally:
            cdp.close()

        cookies = {c["name"]: c["value"] for c in cookies_raw}
        if not any("reese" in k or "incap" in k for k in cookies):
            log.warning("No Imperva cookies observed; challenge may not have cleared.")
        return cookies

    def navigate_and_get_html(self, url: str, settle_timeout: float = 120.0) -> str:
        """Navigate to ``url`` and return the fully-rendered page HTML."""
        if self.proc is None or self.port is None:
            self.start()
        tabs = [t for t in _http_json(f"http://127.0.0.1:{self.port}/json")
                if t.get("type") == "page"]
        if not tabs:
            raise RuntimeError("No page target available from Chrome")
        cdp = CdpClient(tabs[0]["webSocketDebuggerUrl"])
        try:
            cdp.cmd("Page.enable")
            cdp.cmd("Runtime.enable")
            cdp.cmd("Network.enable")
            if self.user_agent:
                cdp.cmd("Network.setUserAgentOverride", {
                    "userAgent": self.user_agent,
                    "acceptLanguage": "en-AU,en;q=0.9",
                    "platform": "macOS",
                })
            cdp.cmd("Page.navigate", {"url": url})
            self._wait_for_selector(cdp, "main, header", settle_timeout)
            time.sleep(6)  # let client-side category tiles finish rendering
            return cdp.evaluate("document.documentElement.innerHTML") or ""
        finally:
            cdp.close()

    @staticmethod
    def _wait_for_selector(cdp: CdpClient, selector: str, timeout: float) -> None:
        deadline = time.time() + timeout
        js = f"document.querySelectorAll({selector!r}).length"
        while time.time() < deadline:
            try:
                count = cdp.evaluate(js)
                # Require both the selector AND substantial page content, so the
                # Akamai challenge page (small HTML) doesn't match prematurely.
                length = cdp.evaluate("document.documentElement.innerHTML.length")
                if isinstance(count, int) and count > 0 and isinstance(length, int) and length > 20000:
                    return
            except Exception:
                pass
            time.sleep(2.0)
        raise TimeoutError(f"Timed out waiting for selector {selector!r}")


def cookies_to_header(cookies: dict[str, str]) -> str:
    """Serialize a cookie dict to a 'k=v; k2=v2' Cookie header value."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def save_cookies(cookies: dict[str, str], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    payload = {"ts": time.time(), "cookies": cookies}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


def load_cookies(path: str, max_age_seconds: float) -> Optional[dict[str, str]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if time.time() - payload.get("ts", 0) < max_age_seconds:
            return payload.get("cookies")
    except Exception:
        return None
    return None
