"""End-to-end test for the Agent Deck MCP server (stdio transport)."""
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = str(HERE / ".venv" / "bin" / "python")
SERVER = str(HERE / "server.py")


async def main():
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp import ClientSession

    params = StdioServerParameters(command=PYTHON, args=[SERVER])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = {t.name for t in tools.tools}
            expected = {"catalog_lookup", "momentum_score", "product_lookup"}
            assert expected <= names, f"missing tools: {expected - names}"
            print("tools ok:", sorted(names))

            def call(name, args):
                return s.call_tool(name, args)

            async def as_json(name, args):
                r = await call(name, args)
                return json.loads(r.content[0].text)

            # catalog_lookup: real query
            cl = await as_json("catalog_lookup", {"query": "zooted"})
            assert cl["count"] >= 1, cl
            z = cl["results"][0]
            assert z["title"] == "Zooted Zone", z
            assert z["evidence_tier"] == "verified", z
            assert z["spotify_url"].startswith("https://open.spotify.com/track/"), z
            assert z["evidence"], "evidence missing"
            print("catalog_lookup ok: Zooted Zone, tier=verified, evidence attached")

            # catalog_lookup: producer/mood search hits graph notes
            cl2 = await as_json("catalog_lookup", {"query": "hybrid"})
            assert cl2["count"] >= 1, cl2
            print("catalog_lookup ok: producer search ->",
                  [r["title"] for r in cl2["results"]])

            # catalog_lookup: miss is honest
            cl3 = await as_json("catalog_lookup", {"query": "Nonexistent Song XYZ"})
            assert cl3["count"] == 0, cl3
            print("catalog_lookup miss ok: count=0")

            # momentum_score: Zooted Zone has placement + plays + link + flagship
            ms = await as_json("momentum_score", {"track": "Zooted Zone"})
            assert ms["found"] is True, ms
            assert ms["score"] > 0, ms
            tiers = {sg["evidence_tier"] for sg in ms["signals"]}
            assert tiers <= {"verified"}, tiers
            sig_names = {sg["signal"] for sg in ms["signals"]}
            assert "verified_playlist_placement" in sig_names, sig_names
            assert "lifetime_spotify_plays" in sig_names, sig_names
            plays = next(sg for sg in ms["signals"]
                         if sg["signal"] == "lifetime_spotify_plays")
            assert plays["value"] == 307439, plays
            assert ms["grade"] in {"High", "Medium", "Low", "Emerging"}, ms
            print(f"momentum_score ok: Zooted Zone score={ms['score']} "
                  f"grade={ms['grade']} (plays=307439 verified)")

            # momentum_score: miss is honest
            ms2 = await as_json("momentum_score", {"track": "Nonexistent Song XYZ"})
            assert ms2["found"] is False, ms2
            print("momentum_score miss ok: found=False")

            # product_lookup: all 18 SKUs
            pl = await as_json("product_lookup", {})
            assert pl["sku_count"] == 18, pl
            assert pl["count"] == 18, pl
            names18 = {p["name"] for p in pl["products"]}
            for want in ("Signal Boy", "SIGNAL SKIN", "HYPE Cartridge",
                         "Gear Ledger", "Chain-of-Title Compass", "CWI-2 SYNCDECK",
                         "Radio Dial", "THE TALLY"):
                assert want in names18, f"missing product {want}"
            for p in pl["products"]:
                assert p["purpose"] and p["product_url"].startswith("https://"), p
            skin = next(p for p in pl["products"] if p["name"] == "SIGNAL SKIN")
            configs = [c["name"] for c in skin["configs"]]
            assert configs == ["Zooted Bloom", "Dark Luxe", "Chrome Standard",
                               "Phantom Shift"], configs
            print("product_lookup ok: 18 SKUs, all with purpose + live URL, "
                  "SKIN configs verified")

            # product_lookup: filtered query
            pl2 = await as_json("product_lookup", {"query": "sync"})
            assert any(p["name"] == "CWI-2 SYNCDECK" for p in pl2["products"]), pl2
            print("product_lookup filter ok: sync ->",
                  [p["name"] for p in pl2["products"]])

    print("ALL AGENT DECK MCP TESTS PASSED")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
