"""SQLite storage for Coles Intelligence."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any, Iterable, Optional

from .models import Product, Subcategory

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    sku_id                 TEXT PRIMARY KEY,
    name                   TEXT,
    display_name           TEXT,
    brand                  TEXT,
    description            TEXT,
    size                   TEXT,
    category               TEXT,
    subcategory            TEXT,
    aisle                  TEXT,
    merch_category         TEXT,
    merch_subcategory      TEXT,
    trade_profit_centre    TEXT,
    price_now              REAL,
    price_was              REAL,
    save_amount            REAL,
    save_percent           REAL,
    discount_percent       REAL,
    unit_price             REAL,
    unit_of_measure        TEXT,
    unit_price_display     TEXT,
    promotion_type         TEXT,
    special_type           TEXT,
    promo_kind             TEXT,
    is_on_special          INTEGER,
    price_description      TEXT,
    offer_description      TEXT,
    online_special         INTEGER,
    multibuy_type          TEXT,
    multibuy_min_qty       INTEGER,
    multibuy_reward        REAL,
    multibuy_unit_price_display TEXT,
    available              INTEGER,
    availability_type      TEXT,
    available_quantity     INTEGER,
    retail_limit           INTEGER,
    promotional_limit      INTEGER,
    image_uri              TEXT,
    image_url              TEXT,
    product_url            TEXT,
    scrape_timestamp       TEXT,
    scrape_date            TEXT,
    source_page            INTEGER,
    raw_json               TEXT
);
CREATE INDEX IF NOT EXISTS idx_products_subcategory ON products(subcategory);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);
CREATE INDEX IF NOT EXISTS idx_products_promo ON products(is_on_special);
CREATE INDEX IF NOT EXISTS idx_products_price ON products(price_now);

CREATE TABLE IF NOT EXISTS categories (
    category_slug  TEXT,
    seo_token      TEXT,
    name           TEXT,
    product_count  INTEGER,
    level          INTEGER,
    PRIMARY KEY (category_slug, seo_token)
);

-- many-to-many: which aisle(s) each SKU appears in (Coles cross-lists heavily)
CREATE TABLE IF NOT EXISTS product_aisles (
    sku_id    TEXT,
    category  TEXT,
    PRIMARY KEY (sku_id, category)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category_slug   TEXT,
    started_at      TEXT,
    finished_at     TEXT,
    pages_crawled   INTEGER,
    products_found  INTEGER,
    total_expected  INTEGER
);
"""

COLUMNS = [
    "sku_id", "name", "display_name", "brand", "description", "size",
    "category", "subcategory", "aisle", "merch_category", "merch_subcategory",
    "trade_profit_centre", "price_now", "price_was", "save_amount", "save_percent",
    "discount_percent", "unit_price", "unit_of_measure", "unit_price_display",
    "promotion_type", "special_type", "promo_kind", "is_on_special",
    "price_description", "offer_description", "online_special", "multibuy_type",
    "multibuy_min_qty", "multibuy_reward", "multibuy_unit_price_display",
    "available", "availability_type", "available_quantity", "retail_limit",
    "promotional_limit", "image_uri", "image_url", "product_url",
    "scrape_timestamp", "scrape_date", "source_page", "raw_json",
]


class Database:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        self._lock = threading.RLock()
        # check_same_thread=False allows a shared connection across the threaded
        # dashboard server; the lock serialises access.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- writes --------------------------------------------------------------
    def upsert_products(self, rows: Iterable[dict[str, Any]]) -> int:
        placeholders = ", ".join("?" for _ in COLUMNS)
        col_list = ", ".join(COLUMNS)
        # Keep first-seen taxonomy (category/subcategory/aisle) on conflict, so a
        # SKU cross-listed in several aisles keeps one stable primary aisle, while
        # volatile pricing/promo/availability fields refresh to the latest snapshot.
        keep_on_conflict = {"sku_id", "category", "subcategory", "aisle"}
        update_set = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c not in keep_on_conflict)
        sql = (
            f"INSERT INTO products ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT(sku_id) DO UPDATE SET {update_set}"
        )
        data = [[r.get(c) for c in COLUMNS] for r in rows]
        with self._lock:
            with self.conn:
                self.conn.executemany(sql, data)
        return len(data)

    def upsert_subcategories(self, subcats: Iterable[Subcategory]) -> None:
        with self._lock:
            with self.conn:
                for s in subcats:
                    self.conn.execute(
                        "INSERT INTO categories (category_slug, seo_token, name, product_count, level) "
                        "VALUES (?,?,?,?,?) "
                        "ON CONFLICT(category_slug, seo_token) DO UPDATE SET "
                        "name=excluded.name, product_count=excluded.product_count, level=excluded.level",
                        (s.category_slug, s.seo_token, s.name, s.product_count, s.level),
                    )

    def upsert_aisle_memberships(self, memberships: Iterable[tuple[str, str]]) -> None:
        """Record (sku_id, aisle) memberships; a SKU may belong to many aisles."""
        with self._lock:
            with self.conn:
                self.conn.executemany(
                    "INSERT OR IGNORE INTO product_aisles (sku_id, category) VALUES (?, ?)",
                    list(memberships),
                )

    def set_subcategory_if_null(self, sku_id: str, subcategory: str) -> None:
        """Tag a product's sub-category only if not already set."""
        with self._lock:
            with self.conn:  # commit each tag immediately
                self.conn.execute(
                    "UPDATE products SET subcategory = ? WHERE sku_id = ? AND subcategory IS NULL",
                    (subcategory, sku_id))

    def record_run(self, slug: str, started_at: str, finished_at: str,
                   pages_crawled: int, products_found: int,
                   total_expected: Optional[int]) -> None:
        with self._lock:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO scrape_runs (category_slug, started_at, finished_at, "
                    "pages_crawled, products_found, total_expected) VALUES (?,?,?,?,?,?)",
                    (slug, started_at, finished_at, pages_crawled, products_found, total_expected),
                )

    # -- reads ---------------------------------------------------------------
    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            cur = self.conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def count_products(self) -> int:
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) AS n FROM products").fetchone()["n"]

    def category_completed(self, slug: str) -> bool:
        """True if a previous scrape run for this slug recorded products."""
        with self._lock:
            row = self.conn.execute(
                "SELECT MAX(products_found) AS n FROM scrape_runs WHERE category_slug = ?",
                (slug,),
            ).fetchone()
            return bool(row and row["n"] and row["n"] > 0)

    def close(self) -> None:
        with self._lock:
            self.conn.close()
