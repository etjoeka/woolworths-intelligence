"""Dynamic dashboard server for Coles Intelligence.

A dependency-free (stdlib) HTTP server that serves the single-page dashboard and a
small JSON API backed by the SQLite database.

Endpoints:
  GET /                 -> dashboard (index.html)
  GET /static/...       -> static assets
  GET /api/overview     -> summary + aggregations for the charts
  GET /api/products     -> filtered / paginated product table
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from woolworths_intel.analyst import (best_value, brand_top, category_stats, filters_meta,
                                 overview, price_histogram, promo_breakdown,
                                 subcategory_stats, _where)
from woolworths_intel.config import PACKAGE_ROOT, load_config, resolve_path
from woolworths_intel.db import Database

STATIC_DIR = PACKAGE_ROOT / "dashboard" / "static"
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}


class DashboardHandler(BaseHTTPRequestHandler):
    db: Database = None  # set by server factory

    def log_message(self, fmt, *args):  # quiet
        pass

    # -- routing -------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            if route in ("/", "/index.html"):
                self._serve_file("index.html")
            elif route.startswith("/static/"):
                self._serve_file(route[len("/static/"):])
            elif route == "/api/overview":
                self._send_json(self._overview(parse_qs(parsed.query)))
            elif route == "/api/products":
                self._send_json(self._products(parse_qs(parsed.query)))
            elif route == "/api/health":
                self._send_json({"ok": True, "products": self.db.count_products()})
            else:
                self.send_error(404)
        except Exception as exc:  # pragma: no cover - defensive
            self.send_error(500, str(exc))

    # -- helpers -------------------------------------------------------------
    def _serve_file(self, rel: str):
        path = (STATIC_DIR / rel).resolve()
        if not str(path).startswith(str(STATIC_DIR.resolve())):
            self.send_error(403)
            return
        if not path.is_file():
            self.send_error(404)
            return
        ext = os.path.splitext(path)[1].lower()
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        # Always revalidate so the latest JS/CSS reaches the browser
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # -- API -------------------------------------------------------------
    def _parse_filters(self, qs: dict) -> dict:
        """Extract the shared filter params from a query string."""
        def one(k, default=None):
            v = qs.get(k)
            return v[0] if v else default

        filters = {}
        for k in ("category", "subcategory", "brand", "promo", "on_special",
                  "search", "min_price", "max_price"):
            v = one(k)
            if v not in (None, ""):
                filters[k] = v
        return filters

    def _overview(self, qs: dict):
        filters = self._parse_filters(qs)
        return {
            "summary": overview(self.db, filters),
            "categories": category_stats(self.db),
            "subcategories": subcategory_stats(self.db, filters),
            "promo": promo_breakdown(self.db, filters),
            "brands": brand_top(self.db, filters),
            "histogram": price_histogram(self.db, filters),
            "best_value": best_value(self.db, filters),
            "filters": filters_meta(self.db),
        }

    def _products(self, qs: dict):
        def one(k, default=None):
            v = qs.get(k)
            return v[0] if v else default

        filters = self._parse_filters(qs)
        where_cond, params = _where(filters)
        where_sql = f"WHERE {where_cond}"

        sort = one("sort", "price_asc")
        limit = min(int(one("limit", "50") or 50), 500)
        offset = max(int(one("offset", "0") or 0), 0)

        total = self.db.query(f"SELECT COUNT(*) AS n FROM products {where_sql}", tuple(params))[0]["n"]

        sort_map = {
            "price_asc": "price_now ASC NULLS LAST",
            "price_desc": "price_now DESC NULLS LAST",
            "name_asc": "display_name COLLATE NOCASE ASC",
            "discount_desc": "discount_percent DESC NULLS LAST",
            "unit_asc": "unit_price ASC NULLS LAST",
        }
        order = sort_map.get(sort, sort_map["price_asc"])

        rows = self.db.query(
            f"""SELECT sku_id, display_name, brand, category, subcategory, aisle, size,
                       price_now, price_was, save_amount, discount_percent,
                       unit_price, unit_of_measure, promo_kind, special_type,
                       offer_description, price_description, image_url, product_url,
                       available, availability_type
                FROM products {where_sql}
                ORDER BY {order} LIMIT ? OFFSET ?""",
            tuple(params) + (limit, offset),
        )
        return {"total": total, "limit": limit, "offset": offset, "rows": rows}


def serve(db_path: str | None = None, host: str = "127.0.0.1", port: int = 8777):
    cfg = load_config()
    dcfg = cfg.get("dashboard", {})
    host = host or dcfg.get("host", "127.0.0.1")
    port = port or dcfg.get("port", 8777)

    DashboardHandler.db = Database(
        str(db_path or resolve_path(cfg["storage"]["db_path"]))
    )
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Coles Intelligence dashboard -> http://{host}:{port}")
    return server


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()
    srv = serve(args.db, args.host, args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
