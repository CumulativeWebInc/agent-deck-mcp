"""End-to-end test for the Agent Deck MCP server v1.0.0 (stdio transport).

Boots the server over stdio, lists tools, invokes EVERY tool with realistic
queries, asserts outputs match the live data snapshots, and asserts that
bad input returns clean error objects (INVALID_INPUT / NOT_FOUND) rather
than tracebacks.
"""
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = str(HERE / ".venv" / "bin" / "python")
SERVER = str(HERE / "server.py")

# Independent ground truth, loaded from the same snapshots the server uses.
CATALOG = json.loads((HERE / "data" / "catalog.json").read_text())
PRODUCTS = json.loads((HERE / "data" / "products.json").read_text())["products"]
SKINS = json.loads((HERE / "data" / "skins.json").read_text())
LEDGER = json.loads((HERE / "data" / "ledger.json").read_text())


async def main():
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp import ClientSession

    params = StdioServerParameters(command=PYTHON, args=[SERVER])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = {t.name for t in tools.tools}
            expected = {"catalog_lookup", "momentum_score", "product_lookup",
                        "skin_config", "ledger_read"}
            assert expected <= names, f"missing tools: {expected - names}"
            print("tools ok:", sorted(names))
            # every tool has a description and a JSON schema
            for t in tools.tools:
                assert t.description and len(t.description) > 40, t.name
                assert t.inputSchema.get("type") == "object", t.name
            print("tool schemas ok: descriptions + JSON-schema inputs present")

            async def as_json(name, args):
                r = await s.call_tool(name, args)
                return json.loads(r.content[0].text)

            # ---- catalog_lookup ----
            cl = await as_json("catalog_lookup", {"query": "zooted"})
            assert cl["count"] >= 1 and cl["catalog_size"] == 24, cl
            z = next(r for r in cl["results"] if r["title"] == "Zooted Zone")
            assert z["evidence_tier"] == "verified"
            assert z["spotify_id"] == "0emH8ktA8x4DkOFLsG5xkW"
            assert z["spotify_url_verified"] is True
            vp = z["verified_placement"]
            assert vp["playlist"] == "New Rap Hits" and vp["position"] == 30, vp
            assert z["evidence"], "evidence missing"
            print("catalog_lookup ok: Zooted Zone verified, #30 New Rap Hits, evidence")

            cl2 = await as_json("catalog_lookup", {"query": "diabolique"})
            assert any(r["title"] == "Diabolique" for r in cl2["results"]), cl2
            print("catalog_lookup ok: 'diabolique' ->",
                  [r["title"] for r in cl2["results"]])

            cl3 = await as_json("catalog_lookup", {"query": "Nonexistent Song XYZ"})
            assert cl3["count"] == 0 and cl3["results"] == [], cl3
            print("catalog_lookup miss ok: count=0, empty results")

            # validation: empty query / bad limit
            e1 = await as_json("catalog_lookup", {"query": "   "})
            assert e1["error"]["code"] == "INVALID_INPUT", e1
            e2 = await as_json("catalog_lookup", {"query": "zooted", "limit": 99})
            assert e2["error"]["code"] == "INVALID_INPUT", e2
            print("catalog_lookup validation ok: INVALID_INPUT on empty query / bad limit")

            # ---- momentum_score ----
            ms = await as_json("momentum_score", {"track": "Zooted Zone"})
            assert "error" not in ms, ms
            sig = {g["signal"]: g for g in ms["signals"]}
            assert sig["verified_playlist_placement"]["points"] == 11, sig  # 40-(30-1)
            assert sig["lifetime_spotify_plays"]["value"] == 307439, sig
            assert sig["lifetime_spotify_plays"]["points"] == 30, sig
            assert sig["spotify_url_verified"]["points"] == 10, sig
            assert sig["flagship_catalog_note"]["points"] == 10, sig
            assert ms["score"] == 61 and ms["grade"] == "High", ms
            assert all(g["evidence_tier"] == "verified" for g in ms["signals"])
            print(f"momentum_score ok: Zooted Zone score={ms['score']} grade=High "
                  "(11+30+10+10, all verified)")

            ms_b = await as_json("momentum_score", {"track": "Diabolique"})
            assert ms_b["score"] >= 10, ms_b  # verified link + flagship at least
            assert all(g["evidence_tier"] == "verified" for g in ms_b["signals"])
            print(f"momentum_score ok: Diabolique score={ms_b['score']} "
                  f"grade={ms_b['grade']}")

            ms2 = await as_json("momentum_score", {"track": "Nonexistent Song XYZ"})
            assert ms2["error"]["code"] == "NOT_FOUND", ms2
            e3 = await as_json("momentum_score", {"track": ""})
            assert e3["error"]["code"] == "INVALID_INPUT", e3
            print("momentum_score errors ok: NOT_FOUND on miss, INVALID_INPUT on empty")

            # ---- product_lookup ----
            pl = await as_json("product_lookup", {})
            assert pl["sku_count"] == 18 and pl["page"]["total"] == 18, pl
            got = {p["name"] for p in pl["page"]["items"]}
            want = {"Signal Boy", "Gear Ledger", "CWI-1 Scoreboard Chip",
                    "Chain-of-Title Compass", "CWI-2 SYNCDECK",
                    "CWI-1 Prospect Scanner", "CWI Press Kit Cartridge",
                    "Radio Dial", "HYPE Cartridge", "SIGNAL SKIN",
                    "THE STREETLIGHT", "THE ALL-CLEAR", "THE FIRST SPIN",
                    "ONE-STOP", "COPY DESK", "THE FINAL CUT", "OPEN WAVE",
                    "THE TALLY"}
            assert want <= got, f"missing: {want - got}"
            for p in pl["page"]["items"]:
                assert p["purpose"] and len(p["purpose"]) > 20, p
                assert p["product_url"].startswith("https://"), p
            print("product_lookup ok: all 18 SKUs, purpose + live URL each")

            # pagination
            pg1 = await as_json("product_lookup", {"limit": 5, "offset": 0})
            pg2 = await as_json("product_lookup", {"limit": 5, "offset": 5})
            assert pg1["page"]["returned"] == 5 and pg1["page"]["has_more"] is True
            n1 = {p["name"] for p in pg1["page"]["items"]}
            n2 = {p["name"] for p in pg2["page"]["items"]}
            assert not (n1 & n2), "pages overlap"
            print("product_lookup pagination ok: 5+5 non-overlapping, has_more=True")

            # spot-check purpose text against snapshot
            live = {p["name"]: p for p in PRODUCTS}
            for p in pl["page"]["items"]:
                assert p["purpose"] == live[p["name"]]["purpose"], p["name"]
                assert p["product_url"] == live[p["name"]]["product_url"], p["name"]
            print("product_lookup spot-check ok: matches live snapshots exactly")

            pl2 = await as_json("product_lookup", {"query": "The First Spin"})
            assert len(pl2["page"]["items"]) == 1, pl2
            fs = pl2["page"]["items"][0]
            assert fs["name"] == "THE FIRST SPIN", fs
            assert fs["department"] == live["THE FIRST SPIN"]["department"], fs
            assert fs["product_url"] == live["THE FIRST SPIN"]["product_url"], fs
            print("product_lookup filter ok: 'The First Spin' ->",
                  fs["product_url"])

            e4 = await as_json("product_lookup", {"query": "x", "limit": 0})
            assert e4["error"]["code"] == "INVALID_INPUT", e4
            print("product_lookup validation ok: INVALID_INPUT on limit=0")

            # ---- skin_config ----
            sc = await as_json("skin_config", {})
            assert sc["count"] == 4, sc
            ids = [c["skin_id"] for c in sc["configs"]]
            assert ids == ["zooted-bloom", "dark-luxe", "chrome-standard",
                           "phantom-shift"], ids
            zb = next(c for c in sc["configs"] if c["skin_id"] == "zooted-bloom")
            live_zb = next(x for x in SKINS["skins"] if x["skin_id"] == "zooted-bloom")
            assert zb["palette"] == live_zb["palette"], "palette mismatch vs live"
            assert zb["palette"]["accent"] == "#a3ff5e", zb["palette"]
            assert sc["apply_instructions"], "apply instructions missing"
            assert "logo" in sc["brand_rule"].lower(), sc["brand_rule"]
            print("skin_config ok: 4 configs, zooted-bloom accent #a3ff5e "
                  "matches live, apply instructions present")

            sc1 = await as_json("skin_config", {"skin_id": "dark-luxe"})
            assert sc1["config"]["skin_name"] == "Dark Luxe"
            assert sc1["config"]["palette"]["accent"] == "#d4a017"
            print("skin_config ok: dark-luxe single config, accent #d4a017")

            e5 = await as_json("skin_config", {"skin_id": "neon-nope"})
            assert e5["error"]["code"] == "NOT_FOUND", e5
            assert "zooted-bloom" in e5["error"]["message"], e5
            print("skin_config validation ok: NOT_FOUND lists valid ids")

            # ---- ledger_read ----
            lr = await as_json("ledger_read", {"limit": 10})
            assert lr["entry_count"] == len(LEDGER) == 2, lr
            seqs = [e["seq"] for e in lr["entries"]]
            assert seqs == sorted(seqs), seqs
            assert all("hash" in e and "prev_hash" in e for e in lr["entries"])
            print(f"ledger_read ok: {lr['entry_count']} entries, hashes present")

            lrv = await as_json("ledger_read", {"limit": 10, "verify_chain": True})
            assert lrv["chain_verification"]["checked"] is True
            assert lrv["chain_verification"]["ok"] is True, lrv["chain_verification"]
            print("ledger_read ok: hash chain verifies (",
                  lrv["chain_verification"]["note"][:60], "...)", sep="")

            e6 = await as_json("ledger_read", {"limit": 0})
            assert e6["error"]["code"] == "INVALID_INPUT", e6
            # framework-level: pydantic coerces "yes"->True, so the call succeeds;
            # a truly wrong type (dict for int) yields a clean MCP error, no traceback
            r_bad = await s.call_tool("ledger_read", {"limit": {"a": 1}})
            assert r_bad.isError is True, r_bad
            assert "Traceback" not in r_bad.content[0].text, r_bad.content[0].text
            assert "validation error" in r_bad.content[0].text.lower(), r_bad.content[0].text
            print("ledger_read validation ok: INVALID_INPUT on limit=0; "
                  "clean MCP error (no traceback) on wrong-typed input")

    print("ALL AGENT DECK MCP TESTS PASSED")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
