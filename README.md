# Woolworths Intelligence

A replica of the **Coles Intelligence** market-intelligence system, built for
[Woolworths Australia](https://www.woolworths.com.au). It scrapes retail pricing
and promotional activity for three categories — **Freezer**, **Pantry**, and
**Pet** — limited to **Woolworths Supermarkets** products only (third-party
"Everyday Market" items excluded), stores the result in SQLite, and serves a
dynamic dashboard.

## Results (2026-11-07)

| Category | SKUs (Woolworths Supermarkets only) |
| --- | --- |
| Freezer | 1,182 |
| Pantry | 5,244 |
| Pet | 876 |
| **Total** | **7,301** |

> Pet is the striking case: the raw category lists ~39,900 items, but ~39,000 of
> those are third-party "Everyday Market" listings. Filtering to Woolworths
> Supermarkets leaves 876 real supermarket pet SKUs.

Snapshot highlights: 7,301 SKUs · 869 brands · 1,410 on special (19.3%) ·
avg price $6.91 · promo mix 5,808 regular / 1,360 price cuts / 133 half-price.

## How it works

1. **Akamai challenge** is solved once in headless Chrome (harvesting `_abck` /
   `bm_sz` cookies), which are then reused by `requests`.
2. **Category API** — `POST /apis/ui/browse/category` with a category `NodeId`
   returns paginated JSON (`Bundles[].Products[]`, `TotalRecordCount`).
3. **Marketplace filter** — products with `IsMarketProduct: true` are dropped,
   so only Woolworths Supermarkets items remain. Stall-based pagination stops
   once no new non-market product appears for `stall_pages` pages.

Category NodeIds:

| Category | NodeId |
| --- | --- |
| Freezer | `1_ACA2FC2` |
| Pantry | `1_39FD49C` |
| Pet | `1_61D6FEB` |

## Quick start

```bash
cd woolworths-intel
.venv/bin/python run.py scrape          # scrape Freezer/Pantry/Pet
.venv/bin/python run.py dashboard --port 8780   # open http://127.0.0.1:8780/
.venv/bin/python run.py report          # console summary
.venv/bin/python scripts/export_static.py   # build a static site (data/exports/site/)
```

## Dashboard

Same feature set as the Coles dashboard: KPI cards, price-distribution bar
chart, promotional-mix doughnut, sub-category/brand bar charts, an aisle
selector, brand/promo/search filters, and **dynamic chart scoping** (every chart
and KPI re-computes from the current catalogue selection, with a "Charts reflect
N selected SKUs" indicator).

## Notes & limitations

* **Sub-categories**: not populated in this build — products are tagged at the
  top level (Freezer/Pantry/Pet). Brand/promo/search filters and dynamic charts
  are fully functional.
* **Point-in-time snapshot** — prices/promos change; re-run `scrape` to refresh.
* **Responsible use** — respect `rate_limit` in `config.yaml` and Woolworths'
  terms of service.
* No barcodes are surfaced in the dashboard (the API does return `Barcode`, but
  the product model used here mirrors the Coles schema).

## Project layout

```
woolworths-intel/
├── run.py                  # CLI (scrape / report / export / dashboard)
├── config.yaml             # categories, NodeIds, rate limits, marketplace filter
├── woolworths_intel/       # fetcher (Akamai + API), parser, transform, db, analyst, browser
├── agents/orchestrator.py  # Planner/Crawler/Enricher/Analyst pipeline
├── dashboard/              # stdlib server + single-page app (reused from Coles)
└── data/                   # woolworths.db, cookies.json, exports/
```
