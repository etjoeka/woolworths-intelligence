# Woolworths Intelligence

An **agentic market-intelligence system** that scrapes source data from
[Coles Supermarkets](https://www.coles.com.au), captures **retail pricing** and
**promotional activity**, stores it in a local database, and presents it in a
**dynamic dashboard**. It ships pre-loaded with **every Coles aisle** — ~30,000
SKUs across 17 top-level categories (Fruit & Vegetables, Meat & Seafood, Pantry,
Dairy, Bakery, Drinks, Health & Beauty, Frozen, Liquor, and more).

---

## What it does

1. **Scrapes** Coles product data (price, unit price, "was" price, promo type,
   multi-buy offers, availability, brand, category, image) for every SKU in a
   category.
2. **Classifies** promotions (Half price, Price cut, Multi-buy, Online-only,
   Regular) and computes derived metrics (discount %, savings).
3. **Stores** a clean, queryable snapshot in SQLite (raw source JSON optional,
   off by default to keep the ~30k-SKU database compact).
4. **Analyses** the market — price distribution, sub-category economics, brand
   leaderboard, promo mix, best unit value.
5. **Presents** it all in an interactive dashboard (KPIs, charts, filterable
   catalogue).

---

## Results snapshot (all categories, 2026-11-07)

> **Status: 12 of 17 aisles crawled** (the five overlapping "aggregator" aisles —
> Pantry, Health & Dietary, International Foods, Chips & Snacks, Drinks — are
> pending). Resume with `.venv/bin/python run.py scrape --skip-existing`.

| Metric | Value |
| --- | --- |
| SKUs captured | **16,638 unique** (12 aisles) |
| Aisles | 12 (Frozen 1,283 · Health & Beauty 4,555 · Liquor 2,317 · Dairy 2,275 · …) |
| Brands | 2,492 |
| Sub-categories | 153 |
| On special | 5,059 (30.4%) |
| Avg. price | $16.18 |
| Avg. discount on specials | 30.7% |
| Total savings across specials | $22,267 |
| Promo mix | 11,579 regular · 2,902 price cuts · 1,173 multi-buy · 773 half price |

---

## Architecture

The pipeline is decomposed into **cooperating agent roles**, coordinated by an
orchestrator (see [`agents/orchestrator.py`](agents/orchestrator.py)):

```
┌────────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐
│  Planner   │──▶│  Crawler │──▶│ Enricher  │──▶│ Analyst  │
│ (plan)     │   │ (fetch & │   │ (normalise│   │ (validate│
│            │   │  parse)  │   │  classify)│   │  + store)│
└────────────┘   └──────────┘   └───────────┘   └──────────┘
```

* **Planner** — reads `config.yaml` and builds the crawl plan (categories →
  page sequence).
* **Crawler** — fetches browse pages, parses the embedded product payload,
  self-paginates until full coverage, and sweeps sub-categories to guarantee the
  complete SKU union. Handles anti-bot cookie refresh automatically.
* **Enricher** — normalizes each SKU, classifies promotions, computes discount %
  and display name.
* **Analyst** — validates coverage, persists to SQLite, and produces dashboard
  aggregations.

Each role is autonomous in its own task loop (the crawler decides when it has
finished paginating; the fetcher decides when to re-solve the bot challenge).

### How the scraping works

Coles' storefront is a Next.js app behind **Imperva/Incapsula** bot protection.
Plain HTTP clients are served a JS challenge. The scraper therefore:

1. Launches a real **headless Chrome** via the Chrome DevTools Protocol
   ([`coles_intel/browser.py`](coles_intel/browser.py)), lets it solve the
   challenge once, and harvests the resulting cookies
   (`reese84`, `incap_ses_*`, `visid_incap_*`, `nlbi_*`).
2. Reuses those cookies in a `requests` session
   ([`coles_intel/fetcher.py`](coles_intel/fetcher.py)) for fast, polite
   pagination — re-minting only if a block is detected.

Each browse page embeds its full data as JSON in a
`<script id="__NEXT_DATA__">` tag; [`coles_intel/parser.py`](coles_intel/parser.py)
parses that directly (more reliable and richer than scraping rendered tiles),
yielding every product's price, unit price, "was" price, promo type, multi-buy
details, brand, category hierarchy, availability and image.

---

## Quick start

```bash
cd coles-intel

# 1. (already done in this workspace, but for a fresh clone:)
#    python3 -m venv --system-site-packages .venv
#    .venv/bin/pip install -r requirements.txt

# 2. Scrape every aisle (17 categories, ~30k SKUs)
.venv/bin/python run.py scrape
#    use --skip-existing to resume an interrupted crawl without redoing aisles

# 3. View the dashboard
.venv/bin/python run.py dashboard --port 8777
# open http://127.0.0.1:8777/
```

Other commands:

```bash
.venv/bin/python run.py report                 # print a console summary
.venv/bin/python run.py export --dir data/exports   # export CSVs
```

---

## Public hosting (expose online)

To make the dashboard reachable from the public internet without a cloud account,
use a Cloudflare quick tunnel:

```bash
# 1. Start the dashboard (if not already running)
.venv/bin/python run.py dashboard --port 8777 &

# 2. Download cloudflared (macOS arm64) and start a tunnel
mkdir -p .tools && cd .tools
curl -sL -o cloudflared.tgz \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz
tar -xzf cloudflared.tgz && chmod +x cloudflared
nohup ./cloudflared tunnel --url http://127.0.0.1:8777 --no-autoupdate \
  > /tmp/cloudflared.log 2>&1 &

# 3. Read the public URL from the log
grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/cloudflared.log
```

The account-less quick tunnel has **no uptime guarantee** and the URL changes on
restart. For a **permanent URL**, use one of the prepared paths below.

## Permanent hosting (prepared, pick one)

Every permanent option needs a free account you control — the build artifacts
are already made.

### A. Static site (simplest — Netlify / Cloudflare Pages / GitHub Pages)

The whole dashboard is baked into a self-contained, backend-free folder:

```bash
.venv/bin/python scripts/export_static.py   # -> data/exports/site/
```

Upload/deploy `data/exports/site/` to any static host:
* **Netlify** — drag the `site` folder onto https://app.netlify.com/drop →
  permanent `https://<name>.netlify.app`.
* **Cloudflare Pages** — dashboard "Create project → Direct Upload" → drag the
  folder → permanent `https://<name>.pages.dev`.
* **GitHub Pages** — push the folder to a repo and enable Pages → `https://<user>.github.io/<repo>/`.

### B. Container on Render / Railway / Fly (live API + refreshable)

A `Dockerfile` and `render.yaml` are included and ship the pre-scraped DB:

* **Render** — push this repo to GitHub, then Render → *New > Blueprint* →
  select `render.yaml` → permanent `https://coles-intelligence.onrender.com`.
* **Railway / Fly.io** — point them at the `Dockerfile`; bind port from `$PORT`.

### C. Named Cloudflare tunnel on a domain you own

Requires a Cloudflare account and a domain on Cloudflare; gives a permanent URL
on your own domain and keeps using this Mac as the origin:

```bash
cloudflared tunnel login
cloudflared tunnel create coles
cloudflared tunnel route dns coles coles.example.com
cloudflared tunnel run --url http://127.0.0.1:8777 coles
```

---

## Configuration

All knobs live in [`config.yaml`](config.yaml):

* `scraper.rate_limit` — pacing between requests, retry/backoff.
* `scraper.browser` — headless mode, challenge settle timeout, cookie TTL.
* `scraper.crawl_subcategories` — also sweep every sub-category (on by default;
  required because some aisles, e.g. Pantry, don't surface their full SKU set on
  the top-level browse — only in their sub-categories).
* `scraper.max_pages_per_category` — page cap (Pantry is ~130 pages).
* `categories` — the crawl plan: every Coles aisle with its slug + display name.
* `storage.keep_raw_json` — retain per-SKU source JSON (defaults off for size).

---

## Data model

SQLite (`data/coles.db`):

* `products` — one row per SKU: identity, category taxonomy (`category` = aisle,
  `subcategory` = mid-level, `aisle` = fine), pricing (`price_now`, `price_was`,
  `unit_price`, `save_amount`, `save_percent`), promotion (`promotion_type`,
  `special_type`, `promo_kind`, `offer_description`, multi-buy fields),
  availability, image/product URLs, scrape provenance, and optional `raw_json`.
* `categories` — sub-category taxonomy discovered at crawl time.
* `scrape_runs` — crawl metadata (coverage, pages, timestamps).

Exports in `data/exports/` (`products.csv`, `categories.csv`).

---

## Notes & limitations (please read)

* **Bot protection.** Coles uses Imperva; a headless browser must be available
  (Google Chrome) to mint the initial cookie. This works reliably but is subject
  to change by Coles. If you get blocked, wait a few minutes and re-run — the
  fetcher re-solves the challenge automatically.
* **Point-in-time snapshot.** Prices and promos change frequently; re-run
  `scrape` to refresh (upserts by SKU id keep the latest snapshot).
* **Responsible use.** Respect `rate_limit` settings and Coles' terms of
  service. This is for personal/research use.
* **Sub-category tagging** uses Coles' own online hierarchy
  (`onlineHeirs.category`). A SKU cross-listed in several aisles keeps the aisle
  it was first scraped under (stable primary aisle); prices/promos still refresh.
* **No barcodes.** Coles' browse payload exposes product ids, not EAN/GTIN.
* A handful of SKUs (e.g. some seafood) are listed as unavailable with no price;
  these are captured with `available = 0`.
* **Tobacco** is excluded (age-gated; the browse page returns no products without
  verification).

---

## Project layout

```
coles-intel/
├── run.py                  # CLI entry (scrape / report / export / dashboard)
├── config.yaml             # crawl plan + settings
├── requirements.txt
├── coles_intel/            # core package
│   ├── browser.py          # Chrome CDP cookie minter (Imperva bypass)
│   ├── fetcher.py          # requests session + block handling
│   ├── parser.py           # __NEXT_DATA__ -> Product records
│   ├── models.py           # dataclasses
│   ├── transform.py        # promo classification + derived metrics
│   ├── analyst.py          # SQL aggregations for the dashboard
│   ├── db.py               # SQLite schema + upserts
│   └── config.py
├── agents/                 # agentic orchestration (Planner/Crawler/Enricher/Analyst)
│   └── orchestrator.py
├── dashboard/              # stdlib HTTP server + single-page app
│   ├── server.py
│   └── static/             # index.html, app.js, style.css, vendor/chart.umd.js
└── data/                   # coles.db, cookies.json, exports/
```
