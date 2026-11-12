---
name: inspect-bsp
description: Statically inspect and validate Respawn BSP maps (Titanfall 1 v29, Titanfall 2 v37, Apex v47) and their RPak/VPK/STBSP packages with the ARES format tools. Use before any runtime test, to diagnose a map that crashes or misbehaves, or to compare a compiled map against a retail one.
---

# Inspect a Respawn BSP

The tools are in `tools/` (standard library only). Run them from the repository
root. They never modify inputs. `tools/README.md` lists every tool.

## Procedure

1. **Identify the file.** `python tools/inspect_bsp.py MAP.bsp`
   - `version_raw`: 29 = TF1/TFO, 37 = TF2, 47 = Apex.
   - `issues` must be empty: overlapping or out-of-range lumps make the map
     unusable.
   - External `.bsp_lump` files are listed per lump. Keep them next to the BSP
     when you copy or stage the map.
2. **Validate records (R1/R2).** `python tools/validate_records.py MAP.bsp`
   checks counts and cross-references between meshes, vertices, materials,
   collision and portals. Treat any `error` as a blocker before runtime testing.
3. **Targeted checks, as needed:**
   - Collision: `python tools/tricoll.py MAP.bsp --obj tri.obj` to decode the
     triangle collision; open the OBJ to compare it with the intended geometry.
   - Visibility/portals: `python tools/portals.py MAP.bsp --point X Y Z` to find
     which cell holds a point, and check portal topology.
   - Static props: `python tools/game_lump.py inspect MAP.bsp --placements`.
   - Lighting: `python tools/lighting.py inspect MAP.bsp --json lights.json`.
   - TF2 mesh budget: `python tools/audit_tf2_budget.py MAP.bsp --engine engine.dll`.
4. **Compare with retail.** Run the same command on a retail map of the same
   version, and diff the JSON. Most "is this field right?" questions are settled
   by what retail maps contain. Use the user's own game files; never commit
   or redistribute them.
5. **Then run the engine.** Static validity doesn't prove the engine accepts
   the map. Continue with the `run-harness` skill.

## Expected collision values

To predict a trace or hull result without the engine, use `tools/swept_box.py`
or `tools/swept_capsule.py` on the authored triangles. Then compare with the
harness's `TRACE`/`HULL` events and put the prediction in `expect`.

## Reporting

Quote the tool, the BSP path and version, and the relevant `issues`/counts.
Call the result `static` verification.
