#!/usr/bin/env python3
"""Command-line entry point for Woolworths Intelligence.

Usage:
  python run.py scrape [--slug frozen]     # run the agentic crawl pipeline
  python run.py report                     # print a summary from the DB
  python run.py export [--dir data/exports] # export CSVs
  python run.py dashboard [--port 8777]    # serve the dashboard
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from woolworths_intel.config import load_config, resolve_path
from woolworths_intel.db import Database

MELBOURNE = ZoneInfo("Australia/Melbourne")


def cmd_scrape(cfg, args):
    from agents.orchestrator import Orchestrator
    orch = Orchestrator(cfg)
    try:
        reports = orch.run(slugs=args.slug, skip_existing=args.skip_existing)
    finally:
        orch.close()
    print("\n=== Scrape report ===")
    for r in reports:
        cov = f"{r['coverage_pct']}%" if r["coverage_pct"] is not None else "n/a"
        print(f"  {r['slug']}: found {r['found']} / expected {r['expected']} "
              f"({cov}) across {r['pages']} pages")
    db = Database(str(resolve_path(cfg["storage"]["db_path"])))
    print(f"\nDatabase now holds {db.count_products()} unique SKUs.")
    db.close()


def cmd_report(cfg, args):
    from woolworths_intel.analyst import overview, promo_breakdown, subcategory_stats
    db = Database(str(resolve_path(cfg["storage"]["db_path"])))
    s = overview(db)
    print("=== Woolworths Intelligence — summary ===")
    for k, v in s.items():
        print(f"  {k:<18} {v}")
    print("\n=== Promotional mix ===")
    for p in promo_breakdown(db):
        print(f"  {p['kind']:<20} {p['count']}")
    print("\n=== Sub-categories ===")
    for r in subcategory_stats(db):
        print(f"  {r['name']:<30} SKUs={r['skus']:<4} avg=${r['avg_price']} "
              f"on-special={r['on_special']}")
    db.close()


def cmd_export(cfg, args):
    out_dir = args.dir or resolve_path(cfg["storage"]["export_dir"])
    os.makedirs(out_dir, exist_ok=True)
    db = Database(str(resolve_path(cfg["storage"]["db_path"])))
    products = db.query("SELECT * FROM products ORDER BY subcategory, brand, display_name")
    cats = db.query("SELECT * FROM categories ORDER BY category_slug, name")

    p_path = os.path.join(out_dir, "products.csv")
    with open(p_path, "w", newline="", encoding="utf-8") as fh:
        if products:
            w = csv.DictWriter(fh, fieldnames=list(products[0].keys()))
            w.writeheader()
            w.writerows(products)
    c_path = os.path.join(out_dir, "categories.csv")
    with open(c_path, "w", newline="", encoding="utf-8") as fh:
        if cats:
            w = csv.DictWriter(fh, fieldnames=list(cats[0].keys()))
            w.writeheader()
            w.writerows(cats)
    print(f"Exported {len(products)} products -> {p_path}")
    print(f"Exported {len(cats)} sub-categories -> {c_path}")
    db.close()


def cmd_dashboard(cfg, args):
    from dashboard.server import serve
    srv = serve(args.db, args.host, args.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def cmd_enrich(cfg, args):
    from agents.orchestrator import Orchestrator
    orch = Orchestrator(cfg)
    try:
        tagged = orch.enrich_subcategories()
    finally:
        orch.close()
    total = sum(tagged.values())
    print(f"\nSub-category enrichment complete: {total} product tags across {len(tagged)} sub-categories.")


def main():
    ap = argparse.ArgumentParser(description="Woolworths Intelligence")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("scrape", help="run the crawl pipeline")
    sp.add_argument("--slug", nargs="*", default=None, help="category slugs to crawl")
    sp.add_argument("--skip-existing", action="store_true",
                    help="skip categories that already have data in the DB")
    sp.set_defaults(func=cmd_scrape)

    rp = sub.add_parser("report", help="print DB summary")
    rp.set_defaults(func=cmd_report)

    ep = sub.add_parser("export", help="export CSVs")
    ep.add_argument("--dir", default=None)
    ep.set_defaults(func=cmd_export)

    enp = sub.add_parser("enrich", help="discover + tag sub-categories")
    enp.set_defaults(func=cmd_enrich)

    dp = sub.add_parser("dashboard", help="serve the dashboard")
    dp.add_argument("--db", default=None)
    dp.add_argument("--host", default=None)
    dp.add_argument("--port", type=int, default=None)
    dp.set_defaults(func=cmd_dashboard)

    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    cfg = load_config()
    args.func(cfg, args)


if __name__ == "__main__":
    main()
