# Agent Deck MCP Server

The CWI agent departments' shared reasoning layer: a read-only MCP server
(stdio transport) exposing the live **Agent Deck** product registry (18 SKUs)
and the verified **That Boy Hi Hat** 24-track catalog to any MCP-capable
agent — Claude, Cursor, VS Code Copilot, or another agent on Moltbook.

Every answer carries evidence tiers (`verified` / `owner_confirmed` /
`claimed_unverified`). Nothing is invented: tools only return what exists in
the snapshots under `data/`, which are byte-faithful copies of the live pages
at https://cumulativewebinc.github.io/cwi-learn/.

> There is **no quantum computing** in this stack. "Quantum infrastructure" in
> CWI copy means best-in-class machine-to-machine infrastructure — real HTTP
> APIs, JSON schemas, and MCP tooling.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # installs the mcp SDK
```

(`requirements.txt` pins `mcp<2` for the FastMCP API. A plain `pip install mcp`
installs v2, whose API changed.)

## Run

```bash
.venv/bin/python server.py          # stdio transport
.venv/bin/python test_server.py     # end-to-end test, all tools asserted
.venv/bin/python refresh_data.py    # refresh data/ from the live pages
```

To point at a different snapshot dir: `AGENT_DECK_DATA=/path/to/data .venv/bin/python server.py`

## Tools

| Tool | What it does |
|---|---|
| `catalog_lookup(query, limit=10)` | Search the 24-track catalog (title / artist / credits / mood notes). Returns track facts with evidence tier. |
| `momentum_score(track)` | Score a track's playlist momentum 0–100 from **verified signals only** (verified placement + position, lifetime plays, verified link, flagship note). Missing data scores 0 — never estimated. |
| `product_lookup(query="")` | All 18 Agent Deck SKUs: name, one-line purpose, live URL, department. Empty query lists all; text filters. SIGNAL SKIN includes its 4 configs (Zooted Bloom, Dark Luxe, Chrome Standard, Phantom Shift). |

### Example calls

```jsonc
// catalog_lookup
{"query": "zooted"}
→ {"count": 1, "results": [{"title": "Zooted Zone",
    "spotify_url": "https://open.spotify.com/track/0emH8ktA8x4DkOFLsG5xkW",
    "evidence_tier": "verified", "verified_placement": {"playlist": "New Rap Hits",
    "position": 30, ...}, "evidence": [...]}]}

// momentum_score
{"track": "Zooted Zone"}
→ {"score": 61, "grade": "High",
    "signals": [{"signal": "verified_playlist_placement", "points": 11,
                 "evidence_tier": "verified", ...},
                {"signal": "lifetime_spotify_plays", "points": 30,
                 "value": 307439, "observed": "2026-09-14", ...}, ...]}

// product_lookup
{"query": "sync"}
→ {"count": 4, "products": [{"name": "CWI-2 SYNCDECK",
    "purpose": "The Sync & Licensing department's draw-and-pitch kit ...",
    "product_url": "https://cumulativewebinc.github.io/cwi-learn/syncdeck/", ...}, ...]}
```

## Data sources + refresh cadence

`data/` holds snapshots of the live pages (see `data/SOURCES.md` for the
snapshot date). Refresh after any catalog/gear update — the live pages are
updated by the cwi-learn deploy workflow. Weekly refresh is a good default;
always refresh before cutting a release:

```bash
.venv/bin/python refresh_data.py
```

## Files

- `server.py` — the MCP server (3 read-only tools, stdio)
- `test_server.py` — boots the server over stdio, asserts every tool
- `refresh_data.py` — refetches live JSONs into `data/`
- `data/` — `catalog.json`, `gear.json`, `graph.json`, `kit.json`,
  `products.json` (derived SKU list), `SOURCES.md`
- `requirements.txt` — pinned `mcp<2`

## License

MIT — see `LICENSE`.
