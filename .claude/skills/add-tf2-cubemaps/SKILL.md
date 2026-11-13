---
name: add-tf2-cubemaps
description: Give a Titanfall 2 map reflection cubemaps captured in the game itself. Plan the origins, capture six HUD-free views per origin through the Northstar harness, then write the BC6H VTF, pakfile and per-mesh assignments. Use when a compiled or converted map has no cubemaps (metal and wet surfaces reflect nothing).
---

# Add reflection cubemaps to a Titanfall 2 map

Requires the following:
- Titanfall 2 with Northstar (`--game` or `$ARES_R2_GAME`), and a visible
  desktop for captures.
- Pillow.
- DirectXTex `texconv.exe` (`--texconv` or `$ARES_TEXCONV`).

Work on a copy of the map mod.

## Procedure

1. **Check.** `python tools/cubemaps.py inspect MOD/mod/maps/MAP.bsp`. An empty
   `cubemaps` list and `meshes_per_cubemap` all `-1` means the map has none.
   The writer refuses a map that already has cubemaps or a pakfile.
2. **Plan.**
   `python tools/cubemaps.py plan MOD/mod/maps/MAP.bsp --output plan.json`.
   - **Default placement:** one cubemap in each team base (the two spawn
     clusters) and three between them.
   - **Hand placement:** for a map with other key areas, edit `origins` by
     hand. Keep them in open, playable space; 1-127 cubemaps.
3. **Capture.** Run the recipe:

   ```powershell
   python harnesses/recipes/northstar_cubemaps.py --mod MOD --mod DEPENDENCY `
       --map MAP --plan plan.json --output reports/cubemaps
   ```

   - **What it does:** drops the in-between origins onto the floor, hides the
     RUI HUD, and captures +X, +Y, -X, -Y, up and down at fov 106.26 per origin.
   - **Check the PNGs:** they must show the world, with no HUD, menu or
     loading screen.
4. **Write.** Run
   `python tools/cubemaps.py write MOD/mod/maps/MAP.bsp reports/cubemaps/cubemaps.json --texconv texconv.exe`.
   It adds lumps 0x28 and 0x2A, the mesh cubemap bytes and the material sort
   values.
5. **Verify in game.**
   - Use the `run-harness` views on metal or wet surfaces, before and after.
     The effect is subtle: shaded surfaces pick up reflected light.
   - Then run `accept-northstar-map`.

## Notes

- Retail maps have 4-7 cubemaps. Each costs about 0.5 MB in the pakfile.
- The `CMA` value (1.0) and nearest-distance assignment follow MRVN-Radiant.
  Retail's exact rules are unresolved; see
  `docs/research/tf2-map-rendering-and-visibility.md`.
