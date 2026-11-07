"""Build a fully self-contained static dashboard that can be dropped onto any
static host (GitHub Pages, Netlify, Cloudflare Pages, Vercel, S3, ...).

Produces `data/exports/site/` with:
  index.html, app.js, style.css, vendor/chart.umd.js, data.json

`data.json` embeds the whole dataset (KPIs, chart aggregations, and every SKU),
so the site needs no backend and no /api calls.
"""

from __future__ import annotations

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from woolworths_intel.analyst import (best_value, brand_top, category_stats, filters_meta,
                                 overview, price_histogram, promo_breakdown,
                                 subcategory_stats)
from woolworths_intel.config import PACKAGE_ROOT, load_config, resolve_path
from woolworths_intel.db import Database

PRODUCT_COLUMNS = [
    "sku_id", "display_name", "brand", "category", "subcategory", "aisle", "size",
    "price_now", "price_was", "save_amount", "discount_percent",
    "unit_price", "unit_of_measure", "promo_kind", "offer_description",
    "price_description", "image_url", "product_url", "available",
    "availability_type",
]


def build(out_dir: str | None = None) -> str:
    cfg = load_config()
    out = out_dir or str(resolve_path(cfg["storage"]["export_dir"]) / "site")
    os.makedirs(out, exist_ok=True)
    os.makedirs(os.path.join(out, "vendor"), exist_ok=True)

    db = Database(str(resolve_path(cfg["storage"]["db_path"])))
    products = db.query(
        "SELECT " + ", ".join(PRODUCT_COLUMNS) +
        " FROM products ORDER BY subcategory, brand, display_name"
    )
    memberships: dict[str, list[str]] = {}
    for r in db.query("SELECT sku_id, category FROM product_aisles ORDER BY sku_id, category"):
        memberships.setdefault(r["sku_id"], []).append(r["category"])
    data = {
        "summary": overview(db),
        "categories": category_stats(db),
        "subcategories": subcategory_stats(db),
        "promo": promo_breakdown(db),
        "brands": brand_top(db),
        "histogram": price_histogram(db),
        "best_value": best_value(db),
        "filters": filters_meta(db),
        "memberships": memberships,
        "products": products,
    }
    db.close()

    with open(os.path.join(out, "data.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)

    static = PACKAGE_ROOT / "dashboard" / "static"
    shutil.copyfile(static / "index.static.html", os.path.join(out, "index.html"))
    shutil.copyfile(static / "app.static.js", os.path.join(out, "app.js"))
    shutil.copyfile(static / "style.css", os.path.join(out, "style.css"))
    shutil.copyfile(static / "vendor" / "chart.umd.js",
                    os.path.join(out, "vendor", "chart.umd.js"))
    print(f"Static site built in {out} ({len(products)} SKUs)")
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None)
    args = ap.parse_args()
    build(args.dir)
