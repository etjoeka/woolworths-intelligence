"""Transform raw Woolworths Products into flat DB rows with promo classification."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from .models import Product
from .parser import _clean_text  # noqa: F401 (kept for parity)

MELBOURNE = ZoneInfo("Australia/Melbourne")


def classify_promo(p: Product) -> str:
    """Map a Woolworths product's pricing fields to a human-friendly promo kind."""
    st = (p.special_type or "").upper()
    pd = (p.price_description or "").lower()
    if p.multibuy_type:
        return "Multi-buy"
    if "1/2" in pd or "half" in pd or (p.save_percent and p.save_percent >= 49.9):
        return "Half price"
    if p.save_percent or p.save_amount:
        return "Price cut"
    if p.online_special:
        return "Online-only special"
    if p.promotion_type == "SPECIAL":
        return "Special"
    return "Regular price"


def discount_percent(p: Product) -> Optional[float]:
    if p.save_percent is not None:
        return p.save_percent
    if p.price_was and p.price_now is not None and p.price_was > 0:
        return round((p.price_was - p.price_now) / p.price_was * 100.0, 2)
    return None


def display_name(p: Product) -> str:
    # Woolworths `Name` already includes the brand, so don't re-prefix it.
    name = p.name.strip() if p.name else ""
    if p.size:
        name = f"{name} | {p.size}"
    return name or p.sku_id


def to_row(p: Product, scrape_timestamp: datetime, include_raw: bool = False) -> dict[str, Any]:
    return {
        "sku_id": p.sku_id,
        "name": p.name,
        "display_name": display_name(p),
        "brand": p.brand,
        "description": p.description,
        "size": p.size,
        "category": p.category,
        "subcategory": p.subcategory,
        "aisle": p.aisle,
        "merch_category": p.merch_category,
        "merch_subcategory": p.merch_subcategory,
        "trade_profit_centre": p.trade_profit_centre,
        "price_now": p.price_now,
        "price_was": p.price_was,
        "save_amount": p.save_amount,
        "save_percent": p.save_percent,
        "discount_percent": discount_percent(p),
        "unit_price": p.unit_price,
        "unit_of_measure": p.unit_of_measure,
        "unit_price_display": p.unit_price_display,
        "promotion_type": p.promotion_type,
        "special_type": p.special_type,
        "promo_kind": classify_promo(p),
        "is_on_special": 1 if (p.promotion_type == "SPECIAL") else 0,
        "price_description": p.price_description,
        "offer_description": p.offer_description,
        "online_special": 1 if p.online_special else 0,
        "multibuy_type": p.multibuy_type,
        "multibuy_min_qty": p.multibuy_min_qty,
        "multibuy_reward": p.multibuy_reward,
        "multibuy_unit_price_display": p.multibuy_unit_price_display,
        "available": 1 if p.available else 0,
        "availability_type": p.availability_type,
        "available_quantity": p.available_quantity,
        "retail_limit": p.retail_limit,
        "promotional_limit": p.promotional_limit,
        "image_uri": p.image_uri,
        "image_url": p.image_uri,
        "product_url": p.product_url,
        "scrape_timestamp": scrape_timestamp.isoformat(),
        "scrape_date": scrape_timestamp.strftime("%Y-%m-%d"),
        "source_page": p.source_page,
        "raw_json": (json.dumps(p.raw_json, ensure_ascii=False) if (include_raw and p.raw_json) else None),
    }
