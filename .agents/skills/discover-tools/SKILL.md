---
name: discover-tools
description: Discover game-compatible tools - the ARES local tools and the registered upstream repositories - and locate their authoritative instructions.
---

# Discover Tools

## Procedure
1. Identify the target game (`r1`, `tfo`, `r2`, `r5`).
2. Read `games/<target>/AGENTS.md`.
3. List the local tools: `python -m ares` (or `python -m ares --json`). These are
   standalone readers, comparisons, packaging and in-game harnesses; each has `--help`.
4. Search `registry/tools/` by `targets` and `capabilities` for upstream tools
   (compilers, map tools, converters); `integration.type: local-adapter` entries are
   the ARES tools above.
5. Open upstream instruction links before running an upstream tool.
