---
name: build-map
description: Build or convert a Respawn map and verify it with a static-then-runtime loop. Use when compiling a .map with MRVN-Radiant's remap, converting another game's map, or iterating on a map fix until it works in game.
---

# Build and verify a map

ARES doesn't compile maps. The compiler (`remap`) and the converters live in
[taskinoz/MRVN-Radiant](https://github.com/taskinoz/MRVN-Radiant); finished map
ports and their build recipes live in
[taskinoz/Titanfall-2-Custom-Maps](https://github.com/taskinoz/Titanfall-2-Custom-Maps).
Read their `AGENTS.md`/README for the build command, and follow those
instructions inside those repositories.

## Loop

1. **Build** with the upstream command into an isolated output folder, never
   into a game install.
2. **Static gate** (`inspect-bsp` skill): `inspect_bsp.py` reports no issues, and
   `validate_records.py` reports no errors. Fix the build before going further.
3. **Runtime gate** (`run-harness` skill): load the map in its target game.
   Use traces at known floor heights, spawn probes at the spawn points, and
   views of the areas you changed.
4. **Compare** with the previous build or a retail reference: the same checks
   and the same view positions. Differences that appear only in the HUD mean
   the world is unchanged.
5. **Repeat** until both gates pass, then report what each gate showed.

## Target notes

- TF2 maps need their materials/RPaks and any level scripts. Stage the
  packaged mod with `--mod`, not only the BSP, when spawns or materials come
  from the mod.
- TF1 maps need `info_intermission` for R1Delta and must stay within ±16384
  units. TFO tolerates both.
- Apex maps need the server VPK (`englishserver_<map>.bsp.pak000_dir.vpk`) for
  dedicated R5Reloaded.
