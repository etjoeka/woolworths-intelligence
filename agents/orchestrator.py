"""Agentic orchestration for Woolworths Intelligence (mirrors the Coles pipeline)."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from woolworths_intel.db import Database
from woolworths_intel.fetcher import WoolworthsFetcher
from woolworths_intel.models import CrawlResult, Product
from woolworths_intel.parser import parse_category_page
from woolworths_intel.transform import to_row

log = logging.getLogger(__name__)
MELBOURNE = ZoneInfo("Australia/Melbourne")


class Planner:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def plan(self) -> list[dict]:
        return [{"slug": c["slug"], "name": c["name"],
                 "node_id": c["node_id"], "url_path": c.get("url_path", "")}
                for c in self.cfg.get("categories", [])]


class Crawler:
    def __init__(self, fetcher: WoolworthsFetcher, cfg: dict):
        self.fetcher = fetcher
        self.cfg = cfg
        self._last_pages = 0

    def crawl(self, slug: str, name: str, node_id: str, url_path: str) -> CrawlResult:
        s = self.cfg["scraper"]
        base = s["base_url"]
        page_size = s["page_size"]
        max_pages = s["max_pages_per_category"]
        delay = s["rate_limit"]["delay_between_pages_seconds"]
        exclude_market = bool(s.get("exclude_marketplace", False))
        stall_pages = int(s.get("stall_pages", 60))

        result = CrawlResult(slug=slug, started_at=self._now())
        seen: dict[str, Product] = {}
        memberships: set[tuple[str, str]] = set()
        page = 1
        empty_streak = 0
        stall = 0
        while page <= max_pages:
            data = self.fetcher.fetch_category_page(node_id, page, page_size, url_path)
            raw_count = sum(len(b.get("Products", []) or []) for b in data.get("Bundles", []) or [])
            products, total = parse_category_page(data, name, None, page, base,
                                                  exclude_market=exclude_market)
            if total:
                result.total_expected = total

            if raw_count == 0:
                empty_streak += 1
                log.info("[Crawler] %s page %d truly empty (streak %d)", slug, page, empty_streak)
                if empty_streak >= 2:
                    break
                page += 1
                time.sleep(delay)
                continue
            empty_streak = 0

            new = 0
            for p in products:
                if p.sku_id not in seen:
                    seen[p.sku_id] = p
                    new += 1
                memberships.add((p.sku_id, name))
            result.pages_crawled = page

            if new == 0:
                stall += 1
                log.info("[Crawler] %s page %d: %d raw products, 0 new (%d unique; stall %d)",
                         slug, page, raw_count, len(seen), stall)
                if exclude_market and stall >= stall_pages:
                    log.info("[Crawler] %s stopping: no new Woolworths products for %d pages",
                             slug, stall)
                    break
            else:
                stall = 0
                log.info("[Crawler] %s page %d: parsed %d (%d new, %d unique so far)",
                         slug, page, len(products), new, len(seen))

            if (not exclude_market) and result.total_expected and len(seen) >= result.total_expected:
                log.info("[Crawler] %s coverage reached: %d/%d",
                         slug, len(seen), result.total_expected)
                break
            page += 1
            time.sleep(delay)

        result.products = list(seen.values())
        result.memberships = list(memberships)
        result.finished_at = self._now()
        return result

    @staticmethod
    def _now() -> str:
        return datetime.now(MELBOURNE).isoformat()


class Enricher:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.keep_raw = bool(cfg.get("storage", {}).get("keep_raw_json", False))

    def enrich(self, result: CrawlResult) -> list[dict]:
        ts = datetime.now(MELBOURNE)
        rows = [to_row(p, ts, include_raw=self.keep_raw) for p in result.products]
        log.info("[Enricher] enriched %d products for %s", len(rows), result.slug)
        return rows


class Analyst:
    def __init__(self, db: Database, cfg: dict):
        self.db = db
        self.cfg = cfg

    def validate(self, result: CrawlResult) -> dict:
        found = len(result.products)
        expected = result.total_expected
        coverage = round(found / expected * 100, 1) if expected else None
        summary = {"slug": result.slug, "found": found, "expected": expected,
                   "coverage_pct": coverage, "pages": result.pages_crawled}
        log.info("[Analyst] %s", summary)
        return summary

    def persist(self, result: CrawlResult, rows: list[dict]) -> None:
        self.db.upsert_products(rows)
        if result.memberships:
            self.db.upsert_aisle_memberships(result.memberships)
        self.db.record_run(
            result.slug, result.started_at, result.finished_at,
            result.pages_crawled, len(result.products), result.total_expected,
        )


class Orchestrator:
    def __init__(self, cfg: dict, db_path: str | None = None, cookie_cache: str | None = None):
        from woolworths_intel.config import resolve_path
        self.cfg = cfg
        self.db = Database(str(db_path or resolve_path(cfg["storage"]["db_path"])))
        self.fetcher = WoolworthsFetcher(cfg, cookie_cache_path=cookie_cache)
        self.planner = Planner(cfg)
        self.crawler = Crawler(self.fetcher, cfg)
        self.enricher = Enricher(cfg)
        self.analyst = Analyst(self.db, cfg)

    def run(self, slugs: list[str] | None = None, skip_existing: bool = False) -> list[dict]:
        plan = self.planner.plan()
        if slugs:
            plan = [p for p in plan if p["slug"] in slugs]
        reports = []
        for i, item in enumerate(plan):
            if skip_existing and self.db.category_completed(item["slug"]):
                log.info("[Orchestrator] skipping %s (already scraped)", item["slug"])
                continue
            result = self.crawler.crawl(item["slug"], item["name"],
                                        item["node_id"], item["url_path"])
            rows = self.enricher.enrich(result)
            report = self.analyst.validate(result)
            self.analyst.persist(result, rows)
            reports.append(report)
            if i < len(plan) - 1:
                time.sleep(self.cfg["scraper"]["rate_limit"]["delay_between_categories_seconds"])
        return reports

    def close(self) -> None:
        self.fetcher.close()
        self.db.close()
