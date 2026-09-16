# Agent Deck MCP Server — v1.0.0

The CWI agent departments' shared reasoning layer: a **read-only** MCP server
(stdio transport) exposing the live **Agent Deck** product registry (25 SKUs)
and the verified **That Boy Hi Hat** 24-track catalog to any MCP-capable
agent — Claude, Cursor, VS Code Copilot, or another agent on the network.

Every answer carries evidence tiers (`verified` / `owner_confirmed` /
`claimed_unverified`). Nothing is invented: tools only return what exists in
the snapshots under `data/`, which are byte-faithful copies of the live pages
at https://cumulativewebinc.github.io/cwi-learn/.

> There is **no quantum computing** in this stack. "Quantum infrastructure" in
> CWI copy means best-in-class machine-to-machine infrastructure — real HTTP
> APIs, JSON schemas, and MCP tooling.

## Install (3 steps)

```bash
git clone https://github.com/CumulativeWebInc/agent-deck-mcp.git
cd agent-deck-mcp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Step 3 only needs the `mcp` SDK (`requirements.txt` pins `mcp<2` for the
FastMCP API; a bare `pip install mcp` installs v2, whose API changed).

## Run

```bash
.venv/bin/python server.py            # stdio transport — connect your MCP client to this
.venv/bin/python test_server.py      # end-to-end test: boots the server, asserts all 5 tools
.venv/bin/python refresh_data.py     # refresh data/ snapshots from the live pages
```

Claude Desktop / MCP client config (stdio):

```json
{
  "mcpServers": {
    "agent-deck": {
      "command": "/path/to/agent-deck-mcp/.venv/bin/python",
      "args": ["/path/to/agent-deck-mcp/server.py"]
    }
  }
}
```

## Tools (5)

| # | Tool | Parameters | What it returns |
|---|---|---|---|
| 1 | `catalog_lookup` | `query` (string, required), `limit` (int 1–24, default 10) | Track facts with evidence tier |
| 2 | `momentum_score` | `track` (string, required: title or Spotify ID) | 0–100 momentum score from verified signals |
| 3 | `product_lookup` | `query` (string, default ""), `limit` (int 1–50, default 18), `offset` (int, default 0) | Paginated SKU list: name, purpose, live URL |
| 4 | `skin_config` | `skin_id` (string, default "" = all 4) | SKIN configs: ids, hex palettes, apply steps |
| 5 | `ledger_read` | `limit` (int 1–100, default 10), `verify_chain` (bool, default false) | Gear Ledger entries + optional hash-chain check |

### Example 1 — `catalog_lookup`: look up a track's verified placements

**Call:**
```json
{
  "query": "Zooted Zone"
}
```

**Response** (trimmed):
```json
{
  "count": 1,
  "results": [{
    "title": "Zooted Zone",
    "spotify_url": "https://open.spotify.com/track/0emH8ktA8x4DkOFLsG5xkW",
    "spotify_url_verified": true,
    "evidence_tier": "verified",
    "verified_placement": {
      "playlist": "New Rap Hits",
      "position": 30,
      "playlist_followers_at_acceptance": 673,
      "scan_date": "2026-09-15",
      "playlist_url": "https://open.spotify.com/playlist/5zhnSpZqKRRaOvRMWuT0bL"
    },
    "evidence": [{"claim": "Track identity and link", "status": "verified"}]
  }]
}
```

### Example 2 — `momentum_score`: score a track's momentum

**Call:**
```json
{
  "track": "Zooted Zone"
}
```

**Response** (trimmed):
```json
{
  "track": "Zooted Zone",
  "score": 61,
  "grade": "High",
  "signals": [
    {"signal": "verified_playlist_placement", "points": 11,
     "evidence_tier": "verified",
     "detail": {"playlist": "New Rap Hits", "position": 30}},
    {"signal": "lifetime_spotify_plays", "points": 30,
     "evidence_tier": "verified", "value": 307439, "observed": "2026-09-14"},
    {"signal": "spotify_url_verified", "points": 10, "evidence_tier": "verified"},
    {"signal": "flagship_catalog_note", "points": 10, "evidence_tier": "verified"}
  ],
  "formula": "placement (40 - (position-1), floor 0) + plays (1 pt per 10k, cap 30) + verified link (10) + flagship note (10); cap 100."
}
```

Formula is transparent and every signal is labeled `verified`. Missing data
scores 0 — never estimated.

### Example 3 — `product_lookup`: find what a product does

**Call:**
```json
{
  "query": "The First Spin"
}
```

**Response** (trimmed):
```json
{
  "sku_count": 18,
  "page": {"total": 1, "items": [{
    "name": "THE FIRST SPIN",
    "purpose": "The A&R department's machine-native demo-evaluation protocol: ...",
    "product_url": "https://cumulativewebinc.github.io/cwi-learn/first-spin/",
    "department": "ar",
    "version": "1.0.0"
  }]}
}
```

Empty `query` lists all 25 SKUs (paginated via `limit`/`offset`).

### Example 4 — `skin_config`: get a SKIN config (equip Zooted Bloom)

**Call:**
```json
{
  "skin_id": "zooted-bloom"
}
```

**Response** (trimmed):
```json
{
  "config": {
    "skin_id": "zooted-bloom",
    "skin_name": "Zooted Bloom",
    "palette": {"accent": "#a3ff5e", "body": "#231b3a", "screen": "#0b1f10",
                "text": "#f2ecff"}
  },
  "apply_instructions": [
    "Fetch the skin pack: GET https://cumulativewebinc.github.io/cwi-learn/skin/skins.json",
    "Pick a built-in skin by skin_id (zooted-bloom, dark-luxe, chrome-standard, phantom-shift) — or author your own against .../skin-schema.json",
    "Apply the skin's token block to your Signal Boy presentation layer. ...",
    "Brand rule: the CWI logo badge ships on every skin. Never remove the logo lockup."
  ]
}
```

Valid ids: `zooted-bloom`, `dark-luxe`, `chrome-standard`, `phantom-shift`.
Omit `skin_id` to list all four.

### Example 5 — `ledger_read`: read the Gear Ledger

**Call:**
```json
{
  "limit": 5,
  "verify_chain": true
}
```

**Response** (trimmed):
```json
{
  "ledger": "Gear Ledger — Agent Deck provenance chain",
  "entry_count": 2,
  "entries": [{"seq": 0, "ts": "2026-09-15T15:10:00Z", "gear": "cwi-1-walkman",
               "event": "minted", "from_agent": "Cumulative Web Inc",
               "to_agent": "KingCode (MUSE_CWI)", "prev_hash": "GENESIS",
               "hash": "d5cb65..."}],
  "chain_verification": {"checked": true, "ok": true,
    "note": "All 2 entries link correctly (prev_hash matches previous hash; genesis = GENESIS)."}
}
```

`verify_chain` checks hash linkage only (each `prev_hash` matches the
previous entry's `hash`); it does not recompute digests.

## Errors

Bad input never raises to the caller — you get a clean error object:

```jsonc
{"error": {"code": "INVALID_INPUT", "message": "'limit' must be between 1 and 24, got 99."}}
{"error": {"code": "NOT_FOUND", "message": "No track matching 'xyz' in the 24-track verified catalog. Use catalog_lookup to find a valid title."}}
{"error": {"code": "DATA_MISSING", "message": "Snapshot data is missing or unreadable. Run refresh_data.py to rebuild ./data/ from the live pages."}}
```

| Code | Meaning |
|---|---|
| `INVALID_INPUT` | Parameter wrong type, empty, or out of range — fix the argument and retry |
| `NOT_FOUND` | No match — use a lookup tool to find a valid identifier |
| `DATA_MISSING` | Snapshot unreadable — run `refresh_data.py` |

## Data sources + refresh cadence

`data/` snapshots (see `data/SOURCES.md` for the snapshot date):

| File | Source |
|---|---|
| `catalog.json`, `gear.json`, `graph.json`, `kit.json` | `https://cumulativewebinc.github.io/cwi-learn/<file>` |
| `products.json` | derived: each gear item's live `item_card_url` description |
| `skins.json` | `https://cumulativewebinc.github.io/cwi-learn/skin/skins.json` |
| `skin_apply.json` | derived: SKIN item card `equip_instructions` |
| `ledger.json` | `https://cumulativewebinc.github.io/cwi-learn/agents/ledger.json` |

Refresh after any catalog/gear update (the live pages update via the
cwi-learn deploy workflow). Weekly refresh is a good default; always refresh
before cutting a release: `.venv/bin/python refresh_data.py`

## Files

- `server.py` — the MCP server, v1.0.0 (5 read-only tools, stdio)
- `test_server.py` — boots the server over stdio, asserts every tool + error paths
- `dogfood.py` — cold-agent value test (see `DOGFOOD.md`)
- `refresh_data.py` — refetches live JSONs into `data/`
- `server.json` — registry metadata
- `data/` — snapshots + `SOURCES.md`
- `requirements.txt` — pinned `mcp<2`

## License

MIT — see `LICENSE`.
