"""Parsing of Woolworths category API responses into Product records."""

from __future__ import annotations

import html as html_mod
import re
from typing import Optional

from .models import Product


def _clean_text(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_mod.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def parse_category_page(data: dict, category_name: str,
                        subcategory_name: Optional[str], page_number: int,
                        base_url: str, exclude_market: bool = False) -> tuple[list[Product], int]:
    """Parse a category browse response into (products, total_record_count).

    When ``exclude_market`` is true, third-party "Everyday Market" products
    (``IsMarketProduct``) are skipped so only Woolworths Supermarkets items remain.
    """
    total = int(data.get("TotalRecordCount") or 0)
    products: list[Product] = []
    for bundle in data.get("Bundles", []) or []:
        for item in (bundle.get("Products") or []):
            if exclude_market and item.get("IsMarketProduct"):
                continue
            products.append(_parse_product(item, category_name, subcategory_name,
                                           page_number, base_url))
    return products, total


def _parse_product(item: dict, category_name: str,
                   subcategory_name: Optional[str], page_number: int,
                   base_url: str) -> Product:
    stockcode = str(item.get("Stockcode") or "")
    price = _num(item.get("Price"))
    was = _num(item.get("WasPrice"))
    is_half = bool(item.get("IsHalfPrice"))
    on_special = bool(item.get("IsOnSpecial"))
    savings = _num(item.get("SavingsAmount"))

    # was price only meaningful when it exceeds the current price (i.e. a cut)
    price_was = was if (was and price and was > price) else None
    save_amount = savings if savings else (
        (was - price) if (price_was and price) else None)
    if is_half:
        save_percent = 50.0
    elif price_was and price:
        save_percent = round((price_was - price) / price_was * 100.0, 2)
    else:
        save_percent = None

    centre_tag = item.get("CentreTag") or {}
    image_tag = item.get("ImageTag") or {}
    mb = centre_tag.get("MultibuyData") or {}
    promo_type = centre_tag.get("PromotionType")
    if promo_type in (None, "NOT_SET", ""):
        promo_type = None

    price_description = image_tag.get("FallbackText") or centre_tag.get("FallbackText")
    offer_description = centre_tag.get("FallbackText")
    if mb and isinstance(mb, dict) and mb.get("Description"):
        offer_description = mb.get("Description")

    return Product(
        sku_id=stockcode,
        name=item.get("Name"),
        brand=item.get("Brand"),
        description=_clean_text(item.get("Description")),
        size=item.get("PackageSize"),
        category=category_name,
        subcategory=subcategory_name,
        aisle=None,
        merch_category=None,
        merch_subcategory=None,
        trade_profit_centre=(item.get("AdditionalAttributes") or {}).get("sapdepartmentname"),
        price_now=price,
        price_was=price_was,
        save_amount=save_amount,
        save_percent=save_percent,
        unit_price=_num(item.get("CupPrice")),
        unit_of_measure=item.get("CupMeasure"),
        unit_price_display=item.get("CupString"),
        promotion_type="SPECIAL" if on_special else None,
        special_type=promo_type,
        price_description=_clean_text(price_description),
        offer_description=_clean_text(offer_description),
        online_special=bool(item.get("IsOnlineOnly")),
        multibuy_type=(mb or {}).get("Type") if isinstance(mb, dict) else None,
        multibuy_min_qty=(mb or {}).get("MinimumQuantity") if isinstance(mb, dict) else None,
        multibuy_reward=None,
        multibuy_unit_price_display=None,
        available=bool(item.get("IsAvailable")),
        availability_type=None,
        available_quantity=None,
        retail_limit=item.get("SupplyLimit") or item.get("ProductLimit"),
        promotional_limit=None,
        image_uri=item.get("LargeImageFile") or item.get("SmallImageFile"),
        product_url=f"{base_url}/shop/productdetails/{stockcode}" if stockcode else None,
        source_page=page_number,
        raw_json=item,
    )
