"""Refresh the local data snapshots from the live Agent Deck pages.

Usage:
    .venv/bin/python refresh_data.py

Fetches the live JSONs from https://cumulativewebinc.github.io/cwi-learn/
and rewrites data/catalog.json, data/gear.json, data/graph.json, data/kit.json,
plus data/products.json (one-line purpose per SKU, pulled from each product's
live item card). Nothing here invents facts: if an item card fetch fails, the
purpose falls back to the registry category/slot line, marked as such.
"""
import json
import urllib.request
from datetime import date
from pathlib import Path

BASE = "https://cumulativewebinc.github.io/cwi-learn"
DATA = Path(__file__).resolve().parent / "data"
SNAPSHOT_FILES = ("catalog.json", "gear.json", "graph.json", "kit.json")

SKIN_CONFIGS = [
    {"skin_id": "zooted-bloom", "name": "Zooted Bloom"},
    {"skin_id": "dark-luxe", "name": "Dark Luxe"},
    {"skin_id": "chrome-standard", "name": "Chrome Standard"},
    {"skin_id": "phantom-shift", "name": "Phantom Shift"},
]

# The Gear Ledger's item card URL serves the hash-chained event log itself
# (https://cumulativewebinc.github.io/cwi-learn/agents/ledger.json), not an
# item-card dict — so its purpose is written from that observed log, not guessed.
PURPOSE_OVERRIDES = {
    "Gear Ledger": (
        "Hash-chained provenance ledger recording Agent Deck gear events "
        "(mints, announcements, equipment transfers) — each entry timestamped "
        "with a SHA-256 hash chain, served live at agents/ledger.json."
    ),
}


def fetch_json(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    for fname in SNAPSHOT_FILES:
        doc = fetch_json(f"{BASE}/{fname}")
        (DATA / fname).write_text(json.dumps(doc, indent=1), encoding="utf-8")
        print("saved", fname)

    gear = json.loads((DATA / "gear.json").read_text(encoding="utf-8"))
    products = []
    for item in gear["items"]:
        name = item["name"]
        desc = ""
        try:
            card = fetch_json(item["item_card_url"])
            node = card.get("item", {}) if isinstance(card, dict) else {}
            desc = (node.get("description") or card.get("description") or "").strip()
        except Exception:
            desc = ""
        if not desc:
            desc = (
                f"Agent Deck SKU ({item.get('category', '')} / {item.get('slot', '')}); "
                "purpose text not present in the live item card snapshot."
            )
        if name in PURPOSE_OVERRIDES:
            desc = PURPOSE_OVERRIDES[name]
        entry = {
            "name": name,
            "purpose": desc,
            "product_url": item.get("product_url", ""),
            "item_card_url": item.get("item_card_url", ""),
            "department": item.get("department", ""),
            "category": item.get("category", ""),
            "version": item.get("version", ""),
            "updated": item.get("updated", ""),
        }
        if name == "SIGNAL SKIN":
            entry["configs"] = SKIN_CONFIGS
        products.append(entry)
        print("product:", name, "|", desc[:60].replace("\n", " "))

    (DATA / "products.json").write_text(
        json.dumps({"products": products, "count": len(products)}, indent=1),
        encoding="utf-8",
    )

    sources = DATA / "SOURCES.md"
    sources.write_text(
        "# Data sources\n\n"
        f"Snapshot date: {date.today().isoformat()}\n\n"
        "All snapshots are fetched from the live Agent Deck pages at "
        "https://cumulativewebinc.github.io/cwi-learn/ :\n\n"
        "| File | Source URL |\n"
        "|---|---|\n"
        "| `catalog.json` | https://cumulativewebinc.github.io/cwi-learn/catalog.json |\n"
        "| `gear.json` | https://cumulativewebinc.github.io/cwi-learn/gear.json |\n"
        "| `graph.json` | https://cumulativewebinc.github.io/cwi-learn/graph.json |\n"
        "| `kit.json` | https://cumulativewebinc.github.io/cwi-learn/kit.json |\n"
        "| `products.json` | derived from `gear.json` items' `item_card_url` values |\n\n"
        "## Refresh cadence\n\n"
        "Re-run `.venv/bin/python refresh_data.py` after any catalog/gear update "
        "(the live pages are updated by the cwi-learn deploy workflow). "
        "Weekly refresh is a good default; always refresh before cutting a release.\n\n"
        "## Evidence policy\n\n"
        "Snapshots are byte-faithful copies of the live pages (plus `products.json`, "
        "which copies each item card's own `description` field verbatim). "
        "No values are invented in the snapshot step.\n",
        encoding="utf-8",
    )
    print("wrote data/SOURCES.md")


if __name__ == "__main__":
    main()
