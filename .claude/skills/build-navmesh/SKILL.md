---
name: build-navmesh
description: Select and validate Recast navigation workflows for Titanfall 2 or Apex maps. Use when baking or investigating navmeshes, coordinate transforms, agent bounds or game-specific navigation export; not for TF1/TFO node graphs.
---

# Build and validate navigation

1. Identify the game, runtime fork, exact build and intended agent (pilot, titan,
   NPC). Read `games/<target>/AGENTS.md`. TF1/TFO `.ain` graph probes are a separate
   workflow documented in their runtime guides, not a Recast export path.
2. Run `python scripts/discover-tools.py --game <r2|r5> --capability navmesh-generation --json`.
   Read the selected entry, then that checkout's README/build instructions. Sources:
   `Mauler125/recastnavigation` (R2/R5 candidate) and `r-ex/r2recast` (R2 candidate).
   Both are discovery integrations, not ARES-verified bakers or exporters.
3. Inspect the geometry exporter and game loader before baking. Establish the
   coordinate basis (XYZ versus XZY), handedness, winding, units, map origin and
   scale with a small asymmetric reference. Record agent radius/height, step,
   slope, cell size and tile settings. Never infer these from a fork's name.
4. Build and bake only with the documented upstream command into isolated output.
   Record source commit, input hashes and bake settings. Do not invent CLI flags
   or treat generic Detour output as a game-loadable navigation file.
5. Compare exported version, framing, bounds, polygon/tile counts and off-mesh
   links with a matching-build reference. Run map static checks (`inspect-bsp`)
   separately; a valid BSP does not validate its navigation data.
6. If a matching runtime and explicit staging permission are available, use
   `run-harness` for map loading and target-specific native path queries or NPC
   routes supported by that runtime. Include reachable, unreachable, narrow,
   stepped and disconnected controls. Node counts or a viewer screenshot alone
   are not a route pass. Otherwise report static/tool-level evidence only.

Report artifacts, build/format identity, coordinate/agent settings, tested routes
and unresolved exporter/runtime gaps. Do not claim general AI or combat parity.
