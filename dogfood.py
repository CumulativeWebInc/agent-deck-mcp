"""DOGFOOD: cold outside-agent value test for the Agent Deck MCP server.

This script pretends to be an agent that has NEVER seen this codebase.
It may use ONLY:
  1. README.md (parsed as plain text — tool names, params, example calls)
  2. list_tools from the live server over stdio

It then completes three real tasks and asserts the answers. If anything
stumbles — a tool name in the README that doesn't match list_tools, an
example call that fails, a missing field, a bad error — the stumble is
logged to DOGFOOD.md and the script exits nonzero. Fix the server/README
and re-run until a cold agent succeeds on the first try.
"""
import asyncio
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = str(HERE / ".venv" / "bin" / "python")
SERVER = str(HERE / "server.py")
README = (HERE / "README.md").read_text(encoding="utf-8")
DOGFOOD_LOG = HERE / "DOGFOOD.md"

stumbles = []


def log_stumble(task, what, fix_hint):
    stumbles.append({"task": task, "what": what, "fix_hint": fix_hint})


# --- cold parsing of the README ------------------------------------------------
def parse_tool_table(readme):
    """Tool names from the '## Tools' markdown table (split on pipes)."""
    tools = {}
    for line in readme.splitlines():
        parts = [p.strip() for p in line.split("|")]
        # ['', '1', '`catalog_lookup`', '`query` ...', 'Track facts ...', '']
        if len(parts) == 6 and parts[1].isdigit():
            name = parts[2].strip("`")
            if re.fullmatch(r"\w+", name):
                tools[name] = {"params": parts[3], "desc": parts[4]}
    return tools


def parse_examples(readme):
    """Map '### Example N — `tool`: title' -> arguments JSON from the Call block."""
    examples = {}
    for m in re.finditer(r"### Example \d+ — `(\w+)`: (.+?)\n(.*?)(?=\n### |\n## |\Z)",
                         readme, re.S):
        tool, title, body = m.group(1), m.group(2).strip(), m.group(3)
        cm = re.search(r"\*\*Call:\*\*\s*```json\n(.*?)```", body, re.S)
        if not cm:
            examples[title] = {"tool": tool, "parse_error": "no **Call:** json block"}
            continue
        try:
            examples[title] = {"tool": tool, "arguments": json.loads(cm.group(1))}
        except Exception as e:
            examples[title] = {"tool": tool, "parse_error": str(e)}
    return examples


async def main():
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp import ClientSession

    table = parse_tool_table(README)
    examples = parse_examples(README)
    if not table:
        log_stumble("setup", "README tool table did not parse", "fix the Tools table format")
    if len(examples) < 5:
        log_stumble("setup", f"only {len(examples)}/5 README examples parsed",
                    "fix the ```jsonc example blocks")

    params = StdioServerParameters(command=PYTHON, args=[SERVER])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            live = {t.name: t for t in (await s.list_tools()).tools}

            # cold check: every README tool name must exist on the server
            for name in table:
                if name not in live:
                    log_stumble("setup",
                                f"README lists tool '{name}' but list_tools has {sorted(live)}",
                                "align README tool names with server")

            async def call(tool, args):
                r = await s.call_tool(tool, args)
                if r.isError:
                    return {"_mcp_error": r.content[0].text}
                return json.loads(r.content[0].text)

            # --- Task 1: look up Zooted Zone's verified placements ---
            ex = examples.get("look up a track's verified placements", {})
            if ex.get("parse_error") or "tool" not in ex:
                log_stumble("task1", "could not parse Example 1 call from README",
                            "fix Example 1 jsonc block")
            else:
                args = dict(ex["arguments"]); args["query"] = "Zooted Zone"
                res = await call(ex["tool"], args)
                if "_mcp_error" in res or "error" in res:
                    log_stumble("task1", f"catalog call failed: {res}",
                                "check tool name/params in README vs server")
                else:
                    hits = [r for r in res.get("results", [])
                            if r.get("title") == "Zooted Zone"]
                    if not hits:
                        log_stumble("task1", "Zooted Zone not in results",
                                    "catalog_lookup must match title case-insensitively")
                    else:
                        z = hits[0]
                        vp = z.get("verified_placement") or {}
                        if (vp.get("playlist") != "New Rap Hits"
                                or vp.get("position") != 30
                                or z.get("evidence_tier") != "verified"):
                            log_stumble("task1",
                                        f"placement facts wrong: {vp}, tier={z.get('evidence_tier')}",
                                        "verified_placement must carry playlist+position+tier")
                        else:
                            print("task1 ok: Zooted Zone -> New Rap Hits #30, tier verified")

            # --- Task 2: what does The First Spin do + its URL ---
            ex = examples.get("find what a product does", {})
            if ex.get("parse_error") or "tool" not in ex:
                log_stumble("task2", "could not parse Example 3 call from README",
                            "fix Example 3 jsonc block")
            else:
                args = dict(ex["arguments"]); args["query"] = "The First Spin"
                res = await call(ex["tool"], args)
                if "_mcp_error" in res or "error" in res:
                    log_stumble("task2", f"product call failed: {res}",
                                "check tool name/params in README vs server")
                else:
                    items = res.get("page", {}).get("items", [])
                    fs = next((p for p in items if "FIRST SPIN" in p.get("name", "")), None)
                    if not fs or not fs.get("purpose") or not str(fs.get("product_url", "")).startswith("https://"):
                        log_stumble("task2", f"First Spin purpose/URL missing: {fs}",
                                    "product_lookup items must include purpose + product_url")
                    else:
                        print(f"task2 ok: The First Spin -> {fs['product_url']}")
                        print(f"  purpose: {fs['purpose'][:80]}...")

            # --- Task 3: equip the Zooted Bloom SKIN config ---
            ex = examples.get("get a SKIN config (equip Zooted Bloom)", {})
            if ex.get("parse_error") or "tool" not in ex:
                log_stumble("task3", "could not parse Example 4 call from README",
                            "fix Example 4 jsonc block")
            else:
                args = dict(ex["arguments"]); args["skin_id"] = "zooted-bloom"
                res = await call(ex["tool"], args)
                if "_mcp_error" in res or "error" in res:
                    log_stumble("task3", f"skin call failed: {res}",
                                "check tool name/params in README vs server")
                else:
                    cfg = res.get("config") or {}
                    pal = cfg.get("palette") or {}
                    steps = res.get("apply_instructions") or []
                    hexes = [v for v in pal.values() if isinstance(v, str)]
                    if cfg.get("skin_id") != "zooted-bloom" or not hexes:
                        log_stumble("task3", f"skin config incomplete: {cfg}",
                                    "skin_config must return skin_id + palette hex codes")
                    elif not steps or not any("logo" in st.lower() for st in steps):
                        log_stumble("task3", "apply instructions missing or lack brand rule",
                                    "skin_config must include apply_instructions + logo brand rule")
                    else:
                        # cold cross-check: fetch the live skins.json URL from the
                        # README data-sources table and compare the palette
                        mu = re.search(r"`skins\.json` \| `(https://[^`]+)`", README)
                        if not mu:
                            log_stumble("task3", "skins.json URL not found in README",
                                        "data sources table must list skins.json URL")
                        else:
                            live_skins = json.load(urllib.request.urlopen(mu.group(1), timeout=20))
                            live_zb = next(x for x in live_skins["skins"]
                                           if x["skin_id"] == "zooted-bloom")
                            if pal != live_zb["palette"]:
                                log_stumble("task3", "palette does not match live skins.json",
                                            "refresh data/skins.json from the live page")
                            else:
                                print(f"task3 ok: zooted-bloom equipped — "
                                      f"accent {pal.get('accent')}, {len(pal)} tokens, "
                                      f"palette matches live source, {len(steps)} apply steps")

    if stumbles:
        with open(DOGFOOD_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n## Cold run {datetime.now(timezone.utc).isoformat()} — "
                    f"{len(stumbles)} stumble(s)\n\n")
            for st in stumbles:
                f.write(f"- **{st['task']}**: {st['what']}\n  Fix: {st['fix_hint']}\n")
        print(f"\nDOGFOOD FAILED: {len(stumbles)} stumble(s) logged to DOGFOOD.md")
        for st in stumbles:
            print(" -", st["task"], ":", st["what"])
        return 1
    with open(DOGFOOD_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n## Cold run {datetime.now(timezone.utc).isoformat()} — CLEAN PASS\n\n"
                "All 3 cold tasks completed from README + list_tools alone, "
                "no stumbles.\n")
    print("\nDOGFOOD PASSED: cold agent completed all 3 tasks from README alone")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
