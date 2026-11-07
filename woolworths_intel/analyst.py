"""Analytics layer: SQL aggregations that power the dashboard.

Every aggregate function accepts an optional ``filters`` dict (category /
subcategory / brand / promo / on_special / search / min_price / max_price), so
the dashboard can scope every chart and KPI to the current catalogue selection.
Aisle filtering goes through the many-to-many ``product_aisles`` table so
cross-listed SKUs are counted under every aisle they appear in.
"""

from __future__ import annotations

from typing import Any, Optional


def _where(filters: Optional[dict]) -> tuple[str, list]:
    """Build a (condition, params) pair from a filter dict."""
    if not filters:
        return "1 = 1", []
    conds: list[str] = []
    params: list = []

    if filters.get("category"):
        conds.append("EXISTS (SELECT 1 FROM product_aisles pa "
                     "WHERE pa.sku_id = products.sku_id AND pa.category = ?)")
        params.append(filters["category"])
    if filters.get("subcategory"):
        conds.append("subcategory = ?")
        params.append(filters["subcategory"])
    if filters.get("brand"):
        conds.append("brand = ?")
        params.append(filters["brand"])
    if filters.get("promo"):
        conds.append("promo_kind = ?")
        params.append(filters["promo"])
    if filters.get("on_special") in ("0", "1", 0, 1):
        conds.append("is_on_special = ?")
        params.append(int(filters["on_special"]))
    if filters.get("search"):
        like = f"%{filters['search']}%"
        conds.append("(display_name LIKE ? OR brand LIKE ? OR description LIKE ?)")
        params += [like, like, like]
    if filters.get("min_price"):
        conds.append("price_now >= ?")
        params.append(float(filters["min_price"]))
    if filters.get("max_price"):
        conds.append("price_now <= ?")
        params.append(float(filters["max_price"]))

    return (" AND ".join(conds), params) if conds else ("1 = 1", [])


def overview(db, filters: Optional[dict] = None) -> dict[str, Any]:
    w, p = _where(filters)
    s = db.query(f"""
        SELECT COUNT(*)                        AS total_skus,
               SUM(is_on_special)              AS on_special,
               ROUND(AVG(price_now), 2)        AS avg_price,
               ROUND(MIN(price_now), 2)        AS min_price,
               ROUND(MAX(price_now), 2)        AS max_price,
               ROUND(AVG(CASE WHEN price_now > 0 THEN price_now END), 2) AS avg_price_nonzero,
               COUNT(DISTINCT subcategory)     AS subcategories,
               COUNT(DISTINCT brand)           AS brands,
               ROUND(AVG(discount_percent), 2) AS avg_discount_pct,
               ROUND(SUM(save_amount), 2)      AS total_savings,
               SUM(CASE WHEN promo_kind='Half price' THEN 1 ELSE 0 END) AS half_price,
               SUM(CASE WHEN promo_kind='Multi-buy' THEN 1 ELSE 0 END)  AS multibuy,
               SUM(CASE WHEN promo_kind='Price cut' THEN 1 ELSE 0 END)  AS price_cut
        FROM products WHERE {w}
    """, tuple(p))[0]
    total = s["total_skus"] or 0
    s["on_special_pct"] = round((s["on_special"] or 0) / total * 100, 1) if total else 0.0
    s["scrape_date"] = db.query(f"SELECT MAX(scrape_date) AS d FROM products WHERE {w}", tuple(p))[0]["d"]
    s["last_run"] = db.query(f"SELECT MAX(scrape_timestamp) AS t FROM products WHERE {w}", tuple(p))[0]["t"]
    return s


def category_stats(db) -> list[dict[str, Any]]:
    """Per-aisle rollup (via membership) for the aisle selector + overview chart."""
    return db.query("""
        SELECT pa.category AS name,
               COUNT(*) AS skus,
               ROUND(AVG(p.price_now), 2) AS avg_price,
               SUM(p.is_on_special) AS on_special,
               COUNT(DISTINCT p.subcategory) AS subcategories,
               COUNT(DISTINCT p.brand) AS brands
        FROM product_aisles pa
        JOIN products p ON p.sku_id = pa.sku_id
        GROUP BY pa.category
        ORDER BY skus DESC
    """)


def subcategory_stats(db, filters: Optional[dict] = None) -> list[dict[str, Any]]:
    w, p = _where(filters)
    return db.query(f"""
        SELECT subcategory AS name,
               COUNT(*) AS skus,
               ROUND(AVG(price_now), 2) AS avg_price,
               ROUND(MIN(price_now), 2) AS min_price,
               ROUND(MAX(price_now), 2) AS max_price,
               SUM(is_on_special) AS on_special,
               ROUND(AVG(CASE WHEN price_now>0 THEN unit_price END), 2) AS avg_unit_price
        FROM products
        WHERE {w} AND subcategory IS NOT NULL
        GROUP BY subcategory
        ORDER BY skus DESC
    """, tuple(p))


def promo_breakdown(db, filters: Optional[dict] = None) -> list[dict[str, Any]]:
    w, p = _where(filters)
    return db.query(f"""
        SELECT promo_kind AS kind, COUNT(*) AS count
        FROM products WHERE {w}
        GROUP BY promo_kind
        ORDER BY count DESC
    """, tuple(p))


def brand_top(db, filters: Optional[dict] = None, limit: int = 12) -> list[dict[str, Any]]:
    w, p = _where(filters)
    return db.query(f"""
        SELECT brand AS name,
               COUNT(*) AS skus,
               ROUND(AVG(price_now), 2) AS avg_price,
               SUM(is_on_special) AS on_special
        FROM products
        WHERE {w} AND brand IS NOT NULL AND brand != ''
        GROUP BY brand
        ORDER BY skus DESC
        LIMIT ?
    """, tuple(p) + (limit,))


def price_histogram(db, filters: Optional[dict] = None, bins: int = 20) -> list[dict[str, Any]]:
    w, p = _where(filters)
    rows = db.query(f"""
        SELECT price_now FROM products
        WHERE {w} AND price_now IS NOT NULL AND price_now >= 0
    """, tuple(p))
    prices = [r["price_now"] for r in rows if r["price_now"] is not None]
    if not prices:
        return []
    lo, hi = min(prices), max(prices)
    if hi - lo < 1e-9:
        hi = lo + 1.0
    width = (hi - lo) / bins
    counts = [0] * bins
    for price in prices:
        idx = min(int((price - lo) / width), bins - 1)
        counts[idx] += 1
    label_fmt = "${:,.0f}".format
    return [{
        "label": f"{label_fmt(lo + i * width)}–{label_fmt(lo + (i + 1) * width)}",
        "lo": round(lo + i * width, 2),
        "hi": round(lo + (i + 1) * width, 2),
        "count": counts[i],
    } for i in range(bins)]


def best_value(db, filters: Optional[dict] = None, limit: int = 10) -> list[dict[str, Any]]:
    w, p = _where(filters)
    return db.query(f"""
        SELECT display_name AS name, subcategory, brand, unit_price,
               unit_of_measure, price_now
        FROM products
        WHERE {w} AND unit_price IS NOT NULL AND unit_price > 0
        ORDER BY unit_price ASC
        LIMIT ?
    """, tuple(p) + (limit,))


def filters_meta(db) -> dict[str, Any]:
    cats = [r["category"] for r in db.query(
        "SELECT DISTINCT category FROM product_aisles ORDER BY category")]
    subs = [r["subcategory"] for r in db.query(
        "SELECT DISTINCT subcategory FROM products WHERE subcategory IS NOT NULL ORDER BY subcategory")]
    brands = [r["brand"] for r in db.query(
        "SELECT DISTINCT brand FROM products WHERE brand IS NOT NULL AND brand != '' ORDER BY brand")]
    promos = [r["promo_kind"] for r in db.query(
        "SELECT DISTINCT promo_kind FROM products WHERE promo_kind IS NOT NULL ORDER BY promo_kind")]
    return {"categories": cats, "subcategories": subs, "brands": brands, "promos": promos}
