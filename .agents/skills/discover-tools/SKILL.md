---
name: discover-tools
description: Discover ARES tools and upstream runtime, scripting and navigation sources by game and capability. Use to select a compiler, harness, runtime fork or Recast tool without assuming cross-fork compatibility.
---

# Discover Tools

## Procedure
1. Identify the target game (`r1`, `tfo`, `r2`, `r5`).
2. Read `games/<target>/AGENTS.md`.
3. List the local tools: `python -m ares` (or `python -m ares --json`). These are
   standalone readers, comparisons, packaging and in-game harnesses; each has `--help`.
4. Query the registry with `python scripts/discover-tools.py --game r2 --json`.
   Use `--capability runtime-source` for runtime implementations and
   `--capability navmesh-generation` for Recast candidates. Repeated capability
   flags require all listed capabilities. `--integration local-adapter` selects
   ARES tools; `external-repository` selects upstream sources.
5. Read the matching entry's `verification.notes`, source commit and documentation
   before choosing a tool. JSON output includes these fields; a catalogue match is
   not a runtime-compatibility claim. See `docs/runtime-sources.md` for fork routing.
6. Open upstream instructions before running an upstream tool. Pin the actual
   revision used; never replace an installed runtime merely to match a registry entry.
