"""Agent Deck MCP Server — the CWI agent departments' shared reasoning layer.

Exposes the live Agent Deck product registry and the verified That Boy Hi Hat
catalog as read-only MCP tools over stdio. Every answer carries evidence tiers
(verified | owner_confirmed | claimed_unverified); nothing is invented.

Data lives in ./data/ (snapshots of the live pages at
https://cumulativewebinc.github.io/cwi-learn/ — refresh with refresh_data.py).

Run:
    .venv/bin/python server.py            # stdio transport
    AGENT_DECK_DATA=/path/to/data .venv/bin/python server.py

Note: there is NO quantum computing in this stack. "Quantum infrastructure"
here means best-in-class machine-to-machine infrastructure.
"""
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DATA = Path(os.environ.get("AGENT_DECK_DATA", str(Path(__file__).resolve().parent / "data")))


def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


CATALOG = _load("catalog.json")
GEAR = _load("gear.json")
GRAPH = _load("graph.json")
PRODUCTS = _load("products.json")["products"]

TRACK_NODES = [n for n in GRAPH["nodes"] if n["type"] == "track"]
TRACK_BY_NAME = {n["name"].lower(): n for n in TRACK_NODES}
TRACK_BY_SPOTIFY = {
    n["attrs"].get("spotify_id", "").lower(): n
    for n in TRACK_NODES
    if n["attrs"].get("spotify_id")
}

PLACEMENTS = CATALOG.get("verified_placements", [])
METRICS = {m["metric"]: m for m in CATALOG.get("metrics", [])}

mcp = FastMCP("agent-deck")


def _track_facts(node):
    attrs = node.get("attrs", {})
    placement = None
    for p in PLACEMENTS:
        pos = p.get("verification", {}).get("positions", {}).get(node["name"])
        if pos is not None:
            placement = {
                "playlist": p["playlist"],
                "position": pos,
                "playlist_followers_at_acceptance": p.get("playlist_followers_at_acceptance"),
                "verified_by": p.get("verification", {}).get("method"),
                "scan_date": p.get("verification", {}).get("scan_date"),
            }
    return {
        "title": node["name"],
        "artist": attrs.get("performed_by", "That Boy Hi Hat"),
        "spotify_url": attrs.get("spotify_url"),
        "spotify_id": attrs.get("spotify_id"),
        "spotify_url_verified": CATALOG_TRACK_MAP.get(node["name"], {}).get(
            "spotify_url_verified", False
        ),
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


CATALOG_TRACK_MAP = {t["title"]: t for t in CATALOG.get("tracks", [])}


@mcp.tool()
def catalog_lookup(query: str, limit: int = 10) -> dict:
    """Search the 24-track That Boy Hi Hat catalog (title, artist, credits, mood
    notes). Returns track facts with evidence tier. No invented data."""
    q = query.strip().lower()
    limit = max(1, min(limit, 24))
    hits = []
    for n in TRACK_NODES:
        text = " ".join(
            str(v)
            for v in (n.get("name"), n.get("id"), json.dumps(n.get("attrs", {})))
        ).lower()
        if q in text:
            hits.append(_track_facts(n))
        if len(hits) >= limit:
            break
    return {
        "query": query,
        "count": len(hits),
        "catalog_size": len(TRACK_NODES),
        "results": hits,
        "policy": "Track facts come from the verified knowledge graph. "
                  "Evidence tier is per-node status (verified | owner_confirmed).",
    }


def _find_track(identifier):
    key = identifier.strip().lower()
    if key in TRACK_BY_NAME:
        return TRACK_BY_NAME[key]
    if key in TRACK_BY_SPOTIFY:
        return TRACK_BY_SPOTIFY[key]
    for name, node in TRACK_BY_NAME.items():
        if key in name:
            return node
    return None


@mcp.tool()
def momentum_score(track: str) -> dict:
    """Score a track's playlist momentum 0-100 from VERIFIED signals only.

    Signals (with observed dates): verified playlist placement + position,
    lifetime Spotify plays, artist monthly listeners, verified Spotify link,
    flagship status in the graph notes. Never invented numbers.
    """
    node = _find_track(track)
    if node is None:
        return {
            "found": False,
            "track": track,
            "policy": "Only the 24 tracks in the verified catalog can be scored.",
        }
    name = node["name"]
    signals = []
    score = 0

    # Verified playlist placement (max 40): higher position = higher score.
    placement_pts = 0
    placement_detail = None
    for p in PLACEMENTS:
        pos = p.get("verification", {}).get("positions", {}).get(name)
        if pos is not None:
            placement_pts = max(placement_pts, max(0, 40 - (pos - 1)))
            placement_detail = {
                "playlist": p["playlist"],
                "position": pos,
                "playlist_followers_at_acceptance": p.get("playlist_followers_at_acceptance"),
                "scan": p.get("verification", {}).get("method"),
                "scan_date": p.get("verification", {}).get("scan_date"),
            }
    if placement_pts:
        score += placement_pts
        signals.append({
            "signal": "verified_playlist_placement",
            "points": placement_pts,
            "evidence_tier": "verified",
            "detail": placement_detail,
        })

    # Lifetime plays (max 30, ~1 pt per 10k plays, capped).
    plays = None
    plays_metric = METRICS.get("lifetime_spotify_plays")
    if plays_metric and plays_metric.get("track", "").lower() == name.lower():
        plays = plays_metric["value"]
        pts = min(30, int(plays // 10000))
        score += pts
        signals.append({
            "signal": "lifetime_spotify_plays",
            "points": pts,
            "evidence_tier": "verified",
            "value": plays,
            "observed": plays_metric.get("observed"),
            "note": plays_metric.get("note"),
        })

    # Verified Spotify link (10).
    cat_track = CATALOG_TRACK_MAP.get(name, {})
    if cat_track.get("spotify_url_verified"):
        score += 10
        signals.append({
            "signal": "spotify_url_verified", "points": 10,
            "evidence_tier": "verified",
            "url": cat_track.get("spotify_url"),
        })

    # Flagship status in graph notes (10).
    if "flagship" in (node.get("attrs", {}).get("notes", "") or "").lower():
        score += 10
        signals.append({
            "signal": "flagship_catalog_note", "points": 10,
            "evidence_tier": "verified",
        })

    # Artist-level monthly listeners: context, not track points.
    listeners = METRICS.get("monthly_listeners")
    context = None
    if listeners:
        context = {
            "artist_monthly_listeners": listeners.get("value"),
            "observed": listeners.get("observed"),
            "evidence_tier": "verified",
            "note": "Artist-level; applies to every track equally, not counted in score.",
        }

    score = min(100, score)
    grade = (
        "High" if score >= 50 else "Medium" if score >= 25
        else "Low" if score >= 10 else "Emerging"
    )
    return {
        "found": True,
        "track": name,
        "score": score,
        "grade": grade,
        "formula": "placement (40 - (position-1), floor 0) + "
                   "plays (1 per 10k lifetime plays, cap 30) + "
                   "verified link (10) + flagship note (10); cap 100.",
        "signals": signals,
        "artist_context": context,
        "policy": "Verified signals only. Missing signal data scores 0 — "
                  "never estimated or filled in.",
    }


def _slim_product(p):
    out = {
        "name": p["name"],
        "purpose": p["purpose"],
        "product_url": p["product_url"],
        "item_card_url": p["item_card_url"],
        "department": p["department"],
        "category": p["category"],
        "version": p["version"],
        "updated": p["updated"],
    }
    if "configs" in p:
        out["configs"] = p["configs"]
    return out


@mcp.tool()
def product_lookup(query: str = "") -> dict:
    """Every Agent Deck product: name, one-line purpose, live URL.
    Empty query lists all 18 SKUs; pass text to filter (name/purpose).
    SIGNAL SKIN includes its 4 configs."""
    q = query.strip().lower()
    if not q:
        items = [_slim_product(p) for p in PRODUCTS]
    else:
        items = [
            _slim_product(p) for p in PRODUCTS
            if q in p["name"].lower() or q in p["purpose"].lower()
        ]
    return {
        "query": query or None,
        "count": len(items),
        "sku_count": len(PRODUCTS),
        "registry": "Agent Deck — CWI Agent Gear Registry",
        "products": items,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
