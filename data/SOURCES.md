# Data sources

Snapshot date: 2026-09-15

All snapshots are fetched from the live Agent Deck pages at https://cumulativewebinc.github.io/cwi-learn/ :

| File | Source URL |
|---|---|
| `catalog.json` | https://cumulativewebinc.github.io/cwi-learn/catalog.json |
| `gear.json` | https://cumulativewebinc.github.io/cwi-learn/gear.json |
| `graph.json` | https://cumulativewebinc.github.io/cwi-learn/graph.json |
| `kit.json` | https://cumulativewebinc.github.io/cwi-learn/kit.json |
| `products.json` | derived from `gear.json` items' `item_card_url` values |
| `skins.json` | https://cumulativewebinc.github.io/cwi-learn/skin/skins.json |
| `ledger.json` | https://cumulativewebinc.github.io/cwi-learn/agents/ledger.json |
| `skin_apply.json` | derived from the SKIN item card `equip_instructions` |

## Refresh cadence

Re-run `.venv/bin/python refresh_data.py` after any catalog/gear update (the live pages are updated by the cwi-learn deploy workflow). Weekly refresh is a good default; always refresh before cutting a release.

## Evidence policy

Snapshots are byte-faithful copies of the live pages (plus `products.json`, which copies each item card's own `description` field verbatim). No values are invented in the snapshot step.
