"""Discover Woolworths sub-categories from the rendered category browse pages.

The sub-category list is rendered client-side as "category tiles" (only a real
browser can see them): each is an ``<a href="/shop/browse/<dept>/<slug>">`` whose
``<img src=".../categories/<NodeId>.jpg">`` carries the sub-category NodeId.
"""

from __future__ import annotations

import re

from .browser import ChromeMinter
from .config import load_config

# <a href="/shop/browse/freezer/ice-cream" ...><img alt="Ice Cream" ... categories/1_D04DE47.jpg ...>
_TILE_RE = re.compile(
    r'<a href="/shop/browse/[a-z0-9-]+/(?P<slug>[a-z0-9-]+)"[^>]*>'
    r'.*?<img[^>]*alt="(?P<name>[^"]+)"[^>]*?categories/(?P<node>[A-Za-z0-9_]+)\.jpg',
    re.S,
)


def extract_subcategory_tiles(html: str) -> list[tuple[str, str]]:
    """Return deduplicated [(name, node_id), ...] sub-category tiles in an HTML page."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for m in _TILE_RE.finditer(html):
        name = m.group("name").strip()
        node = m.group("node")
        if not name or not node or node in seen:
            continue
        seen.add(node)
        out.append((name, node))
    return out


def discover_subcategories() -> dict[str, list[tuple[str, str]]]:
    """Load each configured category's browse page and return {slug: [(name, node_id)]}."""
    cfg = load_config()
    base = cfg["scraper"]["base_url"]
    ua = cfg["scraper"]["user_agent"]
    minter = ChromeMinter(headless=True, user_agent=ua)
    result: dict[str, list[tuple[str, str]]] = {}
    try:
        for cat in cfg["categories"]:
            url = f"{base}/shop/browse/{cat['slug']}"
            html = minter.navigate_and_get_html(url, settle_timeout=120)
            result[cat["slug"]] = extract_subcategory_tiles(html)
    finally:
        minter.stop()
    return result


if __name__ == "__main__":
    import json
    tree = discover_subcategories()
    for slug, subs in tree.items():
        print(f"\n{slug}: {len(subs)} sub-categories")
        for name, node in subs:
            print(f"   {name:40} {node}")
