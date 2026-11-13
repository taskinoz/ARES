---
name: add-tf2-prop-shadows
description: Make a Titanfall 2 map's static props cast real-time sun (cascaded) shadows by listing them in the CSM object tree. Use when a map's props shadow the baked lightmaps but not players or each other (the CSM tree, lumps 0x63/0x64, is empty).
---

# Add static props to a Titanfall 2 map's sun shadows

Work on a copy of the map. The tool is `tools/csm_props.py`, standard library
only.

## Procedure

1. **Inspect.** `python tools/csm_props.py inspect MAP.bsp`.
   - `references` 0 with one node per environment means no prop casts
     real-time sun shadows.
   - Note `prop_object_base`: static prop k is object id base + k.
2. **Provide bounds.** Choose one:
   - **Shipped models:** `--models MOD/mod` reads each `.mdl`'s view bounds.
     Use this for a mod that ships its props.
   - **Your own list:** `--bounds bounds.json`, as
     `{"models/x.mdl": [[minx,miny,minz],[maxx,maxy,maxz]]}`.
   - **Fallback:** anything without bounds gets a sphere of `--default-radius`.
3. **Add.** `python tools/csm_props.py add MAP.bsp --models MOD/mod --output OUT.bsp`.
   - Ground cover (`--exclude`, grass/flowers by default) and props under
     `--min-radius` are left out. Retail grass doesn't cast either.
   - Retail Homestead lists about 42% of its props.
4. **Verify in game.** Use the `run-harness` skill:
   - views with the sun behind large props, before and after; props should
     now shade the ground and each other;
   - the frame rate, which is not yet measured. Then run
     `accept-northstar-map`.

## Notes

The light-space basis was checked on retail Homestead; see
`docs/research/tf2-map-rendering-and-visibility.md`. The tool refuses maps that
already list CSM objects.
