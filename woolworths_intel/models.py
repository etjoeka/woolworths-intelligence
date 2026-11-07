"""Data models for Coles Intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class Product:
    """A single normalized SKU record scraped from a Coles browse page."""

    sku_id: str
    name: str
    brand: Optional[str] = None
    description: Optional[str] = None
    size: Optional[str] = None

    # category taxonomy
    category: Optional[str] = None          # top aisle ("Frozen")
    subcategory: Optional[str] = None       # onlineHeirs.category ("Ice Cream")
    aisle: Optional[str] = None             # onlineHeirs.aisle ("Ice Cream Sticks")
    merch_category: Optional[str] = None    # merchandiseHeir.category
    merch_subcategory: Optional[str] = None  # merchandiseHeir.subCategory
    trade_profit_centre: Optional[str] = None

    # pricing
    price_now: Optional[float] = None
    price_was: Optional[float] = None
    save_amount: Optional[float] = None
    save_percent: Optional[float] = None
    unit_price: Optional[float] = None
    unit_of_measure: Optional[str] = None   # e.g. "100g", "100mL"
    unit_price_display: Optional[str] = None  # comparable string "$1.12/ 100g"

    # promotional activity
    promotion_type: Optional[str] = None    # "SPECIAL" or None
    special_type: Optional[str] = None      # MULTI_SAVE / PERCENT_OFF / ...
    price_description: Optional[str] = None  # "1/2 Price"
    offer_description: Optional[str] = None  # "Pick any 3 for $12"
    online_special: bool = False
    multibuy_type: Optional[str] = None
    multibuy_min_qty: Optional[int] = None
    multibuy_reward: Optional[float] = None
    multibuy_unit_price_display: Optional[str] = None

    # availability / limits
    available: bool = True
    availability_type: Optional[str] = None
    available_quantity: Optional[int] = None
    retail_limit: Optional[int] = None
    promotional_limit: Optional[int] = None

    # media / links
    image_uri: Optional[str] = None
    product_url: Optional[str] = None

    # provenance
    scrape_timestamp: Optional[str] = None
    source_page: Optional[int] = None
    raw_json: Optional[dict] = None

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        d = asdict(self)
        if not include_raw:
            d.pop("raw_json", None)
        return d


@dataclass
class Subcategory:
    """A sub-category node discovered from a browse page's catalogGroupView."""

    name: str
    seo_token: str
    product_count: int
    level: int = 2
    category_slug: str = ""


@dataclass
class CrawlResult:
    """Result of crawling one category: products + taxonomy + metadata."""

    slug: str
    products: list[Product] = field(default_factory=list)
    subcategories: list[Subcategory] = field(default_factory=list)
    total_expected: Optional[int] = None
    pages_crawled: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    # (sku_id, aisle_name) memberships discovered in this category's browse
    memberships: list[tuple[str, str]] = field(default_factory=list)
