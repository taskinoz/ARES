---
name: optimise-tf2-map
description: Shrink and check a compiled or converted Titanfall 2 (BSP v37) map. Weld duplicated triangle-collision and sun-shadow positions, check the world drawing budget, and find visibility cells that hide entities. Use after a map build or conversion, when a map file is unexpectedly large, or before a release.
---

# Optimise a Titanfall 2 map

Tools are in `tools/` (standard library only, any map size). The welds rewrite
the BSP: pass `--output` to keep the input, or omit it to replace the map in
place. Work on a copy, never on an installed game file.

## Procedure

1. **Inspect first.** `python tools/inspect_bsp.py MAP.bsp`: `issues` must be
   empty. `python tools/validate_records.py MAP.bsp` too, when the map is
   under 256 MiB.
2. **Weld triangle collision.**
   `python tools/weld_tricoll.py MAP.bsp --output OUT.bsp`.
   - **When it helps:** when `collision_positions_before` is about 3 x the
     triangle count (retail: about 0.65).
   - **Unwelded headers:** `unwelded_headers` counts headers whose triangle
     flags don't follow the encoder's Z rule. Those keep their positions.
   - **Ordering:** if the generator sorted triangles along one axis, groups
     are long slabs. They weld poorly and give traces oversized boxes. Fix the
     ordering (Z-order or per mesh) at the source.
3. **Weld sun-shadow meshes.**
   `python tools/weld_shadow_meshes.py OUT.bsp`. Retail stores about 0.22
   positions per index; generated maps often store 1.0.
4. **Check the world budget.**
   `python tools/audit_tf2_budget.py OUT.bsp --engine engine.dll`. The limit
   is per frame (0x300000 visible indices). Welding doesn't change it; more
   scenery has to come from static props.
5. **Check visibility cells.** `python tools/cells_all_visible.py inspect OUT.bsp`.
   - If `split_without_portals` is true, the cells hide entities outside the
     camera's cell: ropes, and very likely players.
   - Unless portals are being written, run
     `python tools/cells_all_visible.py apply OUT.bsp`.
6. **Test in game.** Use the `run-harness` skill:
   - views at a few positions, to confirm sun shadows and world geometry are
     unchanged;
   - hull or trace checks, or `player` drops onto welded collision.
   Then run `accept-northstar-map` before any release.

## Reporting

Report each tool's JSON (positions before and after, bytes saved, unwelded
headers) and label it `static`. The tools decode every triangle and mesh again
before writing, so a written map matches the input's geometry; runtime
behaviour still needs the harness. Background:
`docs/research/tf2-map-rendering-and-visibility.md`.
