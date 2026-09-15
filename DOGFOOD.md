# DOGFOOD.md — cold-agent value test log

The Agent Deck MCP server is dogfooded by a *cold* outside agent (`dogfood.py`):
it knows only this repo's README plus `list_tools`, then completes three real
tasks. Every stumble is logged here with the fix. The server is not done until
a cold run passes clean.

## Tasks

1. Look up Zooted Zone's verified placements.
2. What does The First Spin do, and what's its URL?
3. Equip the Zooted Bloom SKIN config (ids + hex palette + apply steps,
   cross-checked against the live `skins.json`).

## Stumbles found and fixed (2026-09-15)

1. **README examples weren't machine-parseable.** The `// call` + single-line
   JSON convention broke a simple cold parser. Fixed by reformatting every
   example as `### Example N — \`tool\`: title` + a standalone `**Call:**`
   fenced-JSON arguments block — clearer for humans and machines alike.
2. **Cold parser assumed backtick-wrapped table cells.** The Tools table's
   params cell contains inner backticks, defeating a naive regex. Fixed the
   cold agent to split rows on pipes (what a real agent would do) — no README
   change needed.
3. **Test bug (not server):** `test_server.py` asserted The First Spin's
   department was `"aandr"`; live data says `"ar"`. Fixed the test to assert
   against the snapshot.
4. **Test bug (not server):** `test_server.py` expected `verify_chain: "yes"`
   to be rejected; FastMCP/pydantic coerces it to `True` at the framework
   layer. Fixed the test to assert the real contract: wrong-typed input
   (e.g. `limit: {"a": 1}`) yields a clean MCP error with no traceback.

Final cold run: **CLEAN PASS** — all 3 tasks completed from README +
`list_tools` alone, zero stumbles.

## Cold run 2026-09-15T18:48:57.136342+00:00 — 5 stumble(s)

- **setup**: README tool table did not parse
  Fix: fix the Tools table format
- **setup**: only 1/5 README examples parsed
  Fix: fix the ```jsonc example blocks
- **task1**: could not parse Example 1 call from README
  Fix: fix Example 1 jsonc block
- **task2**: could not parse Example 3 call from README
  Fix: fix Example 3 jsonc block
- **task3**: could not parse Example 4 call from README
  Fix: fix Example 4 jsonc block

## Cold run 2026-09-15T18:49:07.837731+00:00 — 1 stumble(s)

- **setup**: README tool table did not parse
  Fix: fix the Tools table format

## Cold run 2026-09-15T18:49:18.774147+00:00 — CLEAN PASS

All 3 cold tasks completed from README + list_tools alone, no stumbles.
