"""Agent Deck MCP Server v1.0.0 — the CWI agent departments' shared reasoning layer.

Read-only MCP server (stdio transport) exposing the live Agent Deck product
registry (25 SKUs) and the verified That Boy Hi Hat 24-track catalog to any
MCP-capable agent — Claude, Cursor, VS Code Copilot, or another agent.

Evidence tiers on every answer: verified | owner_confirmed |
claimed_unverified. Nothing is invented: tools only return what exists in the
snapshots under ./data/ (byte-faithful copies of the live pages at
https://cumulativewebinc.github.io/cwi-learn/ — refresh with refresh_data.py).

Design notes (MCP best practices):
- Tools are stateless: every call loads from the snapshot files, no sessions.
- Lists are paginated (limit/offset) wherever they can grow.
- Errors are explicit JSON objects with a code, never a stack trace:
  INVALID_INPUT (bad parameter), NOT_FOUND (no match), DATA_MISSING
  (snapshot absent or malformed).

Run:
    .venv/bin/python server.py          # stdio transport
    .venv/bin/python test_server.py     # end-to-end test, all tools asserted
    .venv/bin/python refresh_data.py    # refresh data/ from the live pages
    AGENT_DECK_DATA=/path/to/data .venv/bin/python server.py

Note: there is NO quantum computing in this stack. "Quantum infrastructure"
in CWI copy means best-in-class machine-to-machine infrastructure.
"""
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

SERVER_VERSION = "1.0.0"
DATA = Path(os.environ.get("AGENT_DECK_DATA", str(Path(__file__).resolve().parent / "data")))


def _load(name):
    try:
        with open(DATA / name, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


CATALOG = _load("catalog.json")
GEAR = _load("gear.json")
GRAPH = _load("graph.json")
PRODUCTS_DOC = _load("products.json")
SKINS_DOC = _load("skins.json")
SKIN_APPLY = _load("skin_apply.json")
LEDGER = _load("ledger.json")

mcp = FastMCP("agent-deck")

# --------------------------------------------------------------------------
# Error helpers — callers always get a clean error object, never a traceback.
# --------------------------------------------------------------------------

def _err(code, message):
    return {"error": {"code": code, "message": message}}


def _need_data(*docs):
    if any(d is None for d in docs):
        return _err("DATA_MISSING",
                    "Snapshot data is missing or unreadable. "
                    "Run refresh_data.py to rebuild ./data/ from the live pages.")
    return None


def _need_str(value, name, allow_empty=False):
    if not isinstance(value, str):
        return _err("INVALID_INPUT",
                    f"'{name}' must be a string, got {type(value).__name__}.")
    if not allow_empty and not value.strip():
        return _err("INVALID_INPUT", f"'{name}' must not be empty.")
    return None


def _need_int(value, name, lo, hi):
    if isinstance(value, bool) or not isinstance(value, int):
        return _err("INVALID_INPUT",
                    f"'{name}' must be an integer, got {type(value).__name__}.")
    if not (lo <= value <= hi):
        return _err("INVALID_INPUT",
                    f"'{name}' must be between {lo} and {hi}, got {value}.")
    return None


def _paginate(items, limit, offset):
    total = len(items)
    page = items[offset:offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "returned": len(page),
        "has_more": offset + limit < total,
        "items": page,
    }


# --------------------------------------------------------------------------
# Catalog helpers
# --------------------------------------------------------------------------

def _track_nodes():
    return [n for n in (GRAPH or {}).get("nodes", []) if n["type"] == "track"]


def _track_by_name():
    return {n["name"].lower(): n for n in _track_nodes()}


def _track_by_spotify():
    return {
        n["attrs"].get("spotify_id", "").lower(): n
        for n in _track_nodes() if n["attrs"].get("spotify_id")
    }


def _catalog_track_map():
    return {t["title"]: t for t in (CATALOG or {}).get("tracks", [])}


def _placements():
    return (CATALOG or {}).get("verified_placements", [])


def _track_facts(node):
    attrs = node.get("attrs", {})
    cat = _catalog_track_map().get(node["name"], {})
    placement = None
    for p in _placements():
        pos = p.get("verification", {}).get("positions", {}).get(node["name"])
        if pos is not None:
            placement = {
                "playlist": p["playlist"],
                "position": pos,
                "playlist_followers_at_acceptance": p.get("playlist_followers_at_acceptance"),
                "verified_by": p.get("verification", {}).get("method"),
                "scan_date": p.get("verification", {}).get("scan_date"),
                "playlist_url": p.get("playlist_url"),
            }
    return {
        "title": node["name"],
        "artist": attrs.get("performed_by", "That Boy Hi Hat"),
        "spotify_url": attrs.get("spotify_url"),
        "spotify_id": attrs.get("spotify_id"),
        "spotify_url_verified": bool(cat.get("spotify_url_verified")),
        "evidence_tier": node.get("status"),
        "ai_learning_set_position": attrs.get("ai_learning_set_position"),
        "explicit_per_spotify_metadata": attrs.get("explicit_per_spotify_metadata"),
        "notes": attrs.get("notes", ""),
        "verified_placement": placement,
        "evidence": [
            {"claim": e.get("claim"), "source": e.get("source"),
             "observed": e.get("observed"), "status": e.get("status")}
            for e in node.get("evidence", [])
        ],
    }


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

@mcp.tool()
def catalog_lookup(query: str, limit: int = 10) -> dict:
    """Search the 24-track That Boy Hi Hat catalog.

    Matches against title, artist, credits and mood/notes text, e.g.
    {"query": "zooted"} or {"query": "hybrid", "limit": 5}.
    Returns track facts with an evidence tier per track
    (verified | owner_confirmed). Empty result means no match — never a guess.
    """
    try:
        for bad in (_need_data(CATALOG, GRAPH),
                    _need_str(query, "query"),
                    _need_int(limit, "limit", 1, 24)):
            if bad:
                return bad
        q = query.strip().lower()
        hits = []
        for n in _track_nodes():
            text = " ".join(str(v) for v in (
                n.get("name"), n.get("id"), json.dumps(n.get("attrs", {})))).lower()
            if q in text:
                hits.append(_track_facts(n))
            if len(hits) >= limit:
                break
        return {
            "query": query, "count": len(hits),
            "catalog_size": len(_track_nodes()), "results": hits,
            "policy": "Track facts come from the verified knowledge graph. "
                      "Evidence tier is the per-node status.",
        }
    except Exception as e:  # never leak a traceback to the caller
        return _err("DATA_MISSING", f"catalog_lookup failed: {e}")


def _find_track(identifier):
    key = identifier.strip().lower()
    by_name, by_spotify = _track_by_name(), _track_by_spotify()
    if key in by_name:
        return by_name[key]
    if key in by_spotify:
        return by_spotify[key]
    for name, node in by_name.items():
        if key in name:
            return node
    return None


@mcp.tool()
def momentum_score(track: str) -> dict:
    """Score one track's playlist momentum 0-100 from VERIFIED signals only.

    Example: {"track": "Zooted Zone"}. Accepts a title or Spotify track ID.
    Signals (each with observed date): verified playlist placement + position,
    lifetime Spotify plays, verified Spotify link, flagship catalog note.
    Missing signal data scores 0 — never estimated or filled in.
    """
    try:
        for bad in (_need_data(CATALOG, GRAPH), _need_str(track, "track")):
            if bad:
                return bad
        node = _find_track(track)
        if node is None:
            return _err("NOT_FOUND",
                        f"No track matching '{track}' in the 24-track verified catalog. "
                        "Use catalog_lookup to find a valid title.")
        name = node["name"]
        signals = []
        score = 0

        placement_pts, placement_detail = 0, None
        for p in _placements():
            pos = p.get("verification", {}).get("positions", {}).get(name)
            if pos is not None:
                placement_pts = max(placement_pts, max(0, 40 - (pos - 1)))
                placement_detail = {
                    "playlist": p["playlist"], "position": pos,
                    "playlist_followers_at_acceptance": p.get("playlist_followers_at_acceptance"),
                    "scan": p.get("verification", {}).get("method"),
                    "scan_date": p.get("verification", {}).get("scan_date"),
                }
        if placement_pts:
            score += placement_pts
            signals.append({"signal": "verified_playlist_placement",
                            "points": placement_pts, "evidence_tier": "verified",
                            "detail": placement_detail})

        metrics = {m["metric"]: m for m in (CATALOG or {}).get("metrics", [])}
        pm = metrics.get("lifetime_spotify_plays")
        if pm and str(pm.get("track", "")).lower() == name.lower():
            pts = min(30, int(pm["value"] // 10000))
            score += pts
            signals.append({"signal": "lifetime_spotify_plays", "points": pts,
                            "evidence_tier": "verified", "value": pm["value"],
                            "observed": pm.get("observed"), "note": pm.get("note")})

        if _catalog_track_map().get(name, {}).get("spotify_url_verified"):
            score += 10
            signals.append({"signal": "spotify_url_verified", "points": 10,
                            "evidence_tier": "verified",
                            "url": _catalog_track_map()[name].get("spotify_url")})

        if "flagship" in (node.get("attrs", {}).get("notes", "") or "").lower():
            score += 10
            signals.append({"signal": "flagship_catalog_note", "points": 10,
                            "evidence_tier": "verified"})

        ml = metrics.get("monthly_listeners")
        context = ({
            "artist_monthly_listeners": ml.get("value"), "observed": ml.get("observed"),
            "evidence_tier": "verified",
            "note": "Artist-level; applies to every track equally, not counted in score.",
        } if ml else None)

        score = min(100, score)
        grade = ("High" if score >= 50 else "Medium" if score >= 25
                 else "Low" if score >= 10 else "Emerging")
        return {
            "track": name, "score": score, "grade": grade,
            "formula": "placement (40 - (position-1), floor 0) + "
                       "plays (1 pt per 10k lifetime plays, cap 30) + "
                       "verified link (10) + flagship note (10); cap 100.",
            "signals": signals, "artist_context": context,
            "policy": "Verified signals only. Missing signal data scores 0 — "
                      "never estimated or filled in.",
        }
    except Exception as e:
        return _err("DATA_MISSING", f"momentum_score failed: {e}")


def _slim_product(p):
    out = {
        "name": p["name"], "purpose": p["purpose"],
        "product_url": p["product_url"], "item_card_url": p["item_card_url"],
        "department": p["department"], "category": p["category"],
        "version": p["version"], "updated": p["updated"],
    }
    if "configs" in p:
        out["skin_configs"] = [c["name"] for c in p["configs"]]
    return out


@mcp.tool()
def product_lookup(query: str = "", limit: int = 18, offset: int = 0) -> dict:
    """List Agent Deck products: name, one-line purpose, live URL, department.

    Empty query lists all 25 SKUs (paginated); text filters on name/purpose,
    e.g. {"query": "sync"} or {"query": "The First Spin"}.
    SIGNAL SKIN entries include its 4 config names; full configs live in
    the skin_config tool.
    """
    try:
        for bad in (_need_data(PRODUCTS_DOC),
                    _need_str(query, "query", allow_empty=True),
                    _need_int(limit, "limit", 1, 50),
                    _need_int(offset, "offset", 0, 1000)):
            if bad:
                return bad
        products = PRODUCTS_DOC["products"]
        q = query.strip().lower()
        items = ([_slim_product(p) for p in products]
                 if not q else
                 [_slim_product(p) for p in products
                  if q in p["name"].lower() or q in p["purpose"].lower()])
        page = _paginate(items, limit, offset)
        return {
            "query": query or None, "sku_count": len(products),
            "registry": "Agent Deck — CWI Agent Gear Registry",
            "registry_version": (GEAR or {}).get("version"),
            "page": page,
        }
    except Exception as e:
        return _err("DATA_MISSING", f"product_lookup failed: {e}")


def _skin_entry(s):
    return {
        "skin_id": s["skin_id"], "skin_name": s["skin_name"],
        "season": s.get("season"), "skin_version": s.get("skin_version"),
        "inspired_by": s.get("inspired_by"),
        "palette": s.get("palette", {}),
        "background_treatment": s.get("background_treatment", {}),
        "dpad_glow": s.get("dpad_glow", {}),
        "track_accent_treatment": s.get("track_accent_treatment", {}),
        "typography_accents": s.get("typography_accents", {}),
        "logo_lockup": s.get("logo_lockup", {}),
    }


@mcp.tool()
def skin_config(skin_id: str = "") -> dict:
    """SIGNAL SKIN configs for Signal Boy: ids + full token sets (hex palettes).

    Empty skin_id lists all 4 verified configs (Zooted Bloom, Dark Luxe,
    Chrome Standard, Phantom Shift). Pass a skin_id for one full config, e.g.
    {"skin_id": "zooted-bloom"}. Includes the apply instructions so an agent
    can "equip" a skin: fetch skins.json, pick a skin_id, apply the token
    block to the Signal Boy presentation layer. Brand rule: the CWI logo
    badge ships on every skin — never remove the logo lockup.
    """
    try:
        for bad in (_need_data(SKINS_DOC, SKIN_APPLY),
                    _need_str(skin_id, "skin_id", allow_empty=True)):
            if bad:
                return bad
        skins = SKINS_DOC.get("skins", [])
        sid = skin_id.strip().lower()
        if not sid:
            return {
                "count": len(skins),
                "configs": [_skin_entry(s) for s in skins],
                "apply_instructions": SKIN_APPLY.get("apply_instructions", []),
                "schema_url": SKIN_APPLY.get("schema_url"),
                "skins_url": SKIN_APPLY.get("skins_url"),
                "brand_rule": SKIN_APPLY.get("brand_rule"),
            }
        match = next((s for s in skins if s.get("skin_id") == sid), None)
        if match is None:
            valid = [s.get("skin_id") for s in skins]
            return _err("NOT_FOUND",
                        f"Unknown skin_id '{skin_id}'. Valid ids: {', '.join(valid)}.")
        return {
            "config": _skin_entry(match),
            "apply_instructions": SKIN_APPLY.get("apply_instructions", []),
            "schema_url": SKIN_APPLY.get("schema_url"),
            "brand_rule": SKIN_APPLY.get("brand_rule"),
        }
    except Exception as e:
        return _err("DATA_MISSING", f"skin_config failed: {e}")


@mcp.tool()
def ledger_read(limit: int = 10, verify_chain: bool = False) -> dict:
    """Read the Gear Ledger: the hash-chained provenance log of Agent Deck
    gear events (mints, announcements, equipment transfers).

    Example: {"limit": 5} for the latest 5 entries, or
    {"limit": 10, "verify_chain": true} to also check that every entry's
    prev_hash matches the previous entry's hash (genesis entry has
    prev_hash "GENESIS"). verify_chain checks hash linkage only — it does
    not recompute digests.
    """
    try:
        for bad in (_need_data(LEDGER),
                    _need_int(limit, "limit", 1, 100)):
            if bad:
                return bad
        if not isinstance(verify_chain, bool):
            return _err("INVALID_INPUT",
                        f"'verify_chain' must be true or false, "
                        f"got {type(verify_chain).__name__}.")
        entries = LEDGER if isinstance(LEDGER, list) else []
        entries = sorted(entries, key=lambda e: e.get("seq", 0))
        chain_ok, chain_note = None, None
        if verify_chain and entries:
            chain_ok = True
            for i, e in enumerate(entries):
                want = "GENESIS" if i == 0 else entries[i - 1].get("hash")
                if e.get("prev_hash") != want:
                    chain_ok = False
                    chain_note = (f"Break at seq {e.get('seq')}: prev_hash "
                                  f"{e.get('prev_hash')} != {want}")
                    break
            if chain_ok:
                chain_note = (f"All {len(entries)} entries link correctly "
                              "(prev_hash matches previous hash; genesis = GENESIS).")
        latest = entries[-limit:] if limit <= len(entries) else entries
        return {
            "ledger": "Gear Ledger — Agent Deck provenance chain",
            "entry_count": len(entries),
            "entries": latest,
            "chain_verification": ({"checked": True, "ok": chain_ok,
                                    "note": chain_note}
                                   if verify_chain else {"checked": False}),
            "live_source": "https://cumulativewebinc.github.io/cwi-learn/agents/ledger.json",
        }
    except Exception as e:
        return _err("DATA_MISSING", f"ledger_read failed: {e}")


if __name__ == "__main__":
    mcp.run(transport="stdio")
