"""HTTP fetcher for the Woolworths Australia API.

Woolworths is fronted by Akamai bot protection. We solve the challenge once in a
headless browser (harvesting cookies including ``_abck``/``bm_sz``), then reuse
those cookies in ``requests`` against the JSON category API
(``POST /apis/ui/browse/category``).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

from .browser import ChromeMinter, load_cookies, save_cookies

log = logging.getLogger(__name__)

BLOCK_MARKERS = ("Access Denied", "access denied", "edgesuite.net")


class WoolworthsFetcher:
    def __init__(self, cfg: dict, cookie_cache_path: Optional[str] = None):
        self.cfg = cfg
        s = cfg.get("scraper", {})
        self.base_url = s["base_url"]
        self.user_agent = s["user_agent"]
        self.cookie_cache = cookie_cache_path or "data/cookies.json"
        self.cookie_ttl = s.get("browser", {}).get("cookie_ttl_seconds", 7200)
        self.browser_cfg = s.get("browser", {})
        self.max_retries = s.get("rate_limit", {}).get("max_retries", 4)
        self.backoff_base = s.get("rate_limit", {}).get("backoff_base_seconds", 5.0)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-AU,en;q=0.9",
            "Request-Id": "|b14af797522740e5a25290ac283f739d.037da5c5e87f4706",
        })
        self._ensure_cookies()

    # -- cookies -------------------------------------------------------------
    def _ensure_cookies(self) -> None:
        cached = load_cookies(self.cookie_cache, self.cookie_ttl)
        if cached:
            self.session.cookies.update(cached)
            log.info("Reusing %d cached Woolworths cookies", len(cached))
        else:
            self.refresh_cookies()

    def refresh_cookies(self) -> None:
        log.info("Minting Woolworths cookies via headless Chrome (Akamai)...")
        minter = ChromeMinter(
            headless=self.browser_cfg.get("headless", True),
            user_agent=self.user_agent,
        )
        try:
            cookies = minter.mint_cookies(
                url=f"{self.base_url}/shop/browse/freezer",
                settle_selector="main, header",
                settle_timeout=self.browser_cfg.get("settle_timeout_seconds", 120),
            )
        finally:
            minter.stop()

        self.session.cookies.update(cookies)
        save_cookies(cookies, self.cookie_cache)
        log.info("Minted %d Woolworths cookies", len(cookies))

    # -- fetching ------------------------------------------------------------
    def fetch_category_page(self, category_id: str, page_number: int,
                            page_size: int = 36, url_path: str = "",
                            sort_type: str = "TraderRelevance") -> dict:
        body = {
            "categoryId": category_id,
            "pageNumber": page_number,
            "pageSize": page_size,
            "sortType": sort_type,
            "url": url_path or f"/shop/browse/{category_id}",
            "location": url_path or f"/shop/browse/{category_id}",
            "formatObject": '{"name":""}',
            "isSpecial": False,
            "isBundle": False,
            "isMobile": False,
            "filters": [],
            "token": "",
            "gpBoost": 0,
            "isHideUnavailableProducts": False,
            "isRegisteredRewardCardPromotion": False,
            "enableAdReRanking": False,
            "groupEdmVariants": True,
            "categoryVersion": "v2",
        }
        url = f"{self.base_url}/apis/ui/browse/category"
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.post(
                    url, json=body,
                    headers={"Content-Type": "application/json",
                             "Referer": f"{self.base_url}/shop/browse"},
                    timeout=45,
                )
                if resp.status_code == 403 or self._is_blocked(resp):
                    log.warning("Woolworths blocked (attempt %d); refreshing cookies", attempt)
                    self.refresh_cookies()
                    self._sleep(attempt)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                last_exc = exc
                log.warning("Request error (attempt %d): %s", attempt, exc)
                self._sleep(attempt)
        raise RuntimeError(f"Failed to fetch category {category_id}: {last_exc}") from last_exc

    @staticmethod
    def _is_blocked(resp: requests.Response) -> bool:
        body = resp.content[:5000].decode("utf-8", "replace").lower()
        return any(m in body for m in BLOCK_MARKERS)

    def _sleep(self, attempt: int) -> None:
        time.sleep(self.backoff_base * (2 ** (attempt - 1)))

    def close(self) -> None:
        self.session.close()
