---
name: validate-r5-collision
description: Check and compare Apex Legends (S0-S3) physics (PHY) and trace collision (BVH) of a rebuilt or converted model against the original, with fixed limits. Use when compiling, converting or porting R5 models with collision.
---

# Validate R5 collision

Two structures carry an R5 model's collision:

- **PHY** (`.phy` beside the `.rmdl`): convex solids for physics (prop_physics, ragdolls).
- **BVH** (inside the `.rmdl`, studiohdr 0x214): what traces hit. Entries: a trace mesh
  (static props), the physics hull (rigid props), or one per solid (jointed models).

## Compare a rebuild with the original

```
python -m ares.r5.compare_phy54 original.phy rebuilt.phy --target s3
python -m ares.r5.compare_bvh54 original.rmdl rebuilt.rmdl
```

Both print JSON and exit nonzero on an issue.

- PHY limits: vertices and bounds 0.0001 in; centroids, radii and centres 0.0001 of the
  hull/solid size; inertia 0.0001 of its largest component; keyvalues 0.00001 relative.
- BVH: entry roles and the 0x1F0 box (0.0001 in); a valid rebuilt tree; the rebuilt
  trace mesh must equal its own LOD 0 render triangles; against the original, trace
  triangles and quads (either diagonal) within 1.5 packing steps plus the original's
  measured offset (`retail_gap`, at most 0.001 in), hull vertex sets within 1.5 steps
  and enclosed volume within 0.1%.
- Never widen a limit to make a model pass. Explain each remaining difference.

## Known causes of differences

- Retail defects: a hull whose stored centre lies outside it (tablet_mini), a hull that
  is not closed (w_bloodhound_axe). Check the original with `phy54.check_hull` first.
- Bent hull faces: retail splits some non-planar faces along the other diagonal
  (wood_gib01c), changing the volume slightly.
- A rigid model with an embedded first animation is posed by its frame 0. The native
  rotation step (0.00019175 rad) cannot store 90 degrees exactly, so a rebuild from
  decoded data can differ by about 5e-5 rad times the radius.

## Format facts for interpretation

- Leaf types: 3 list, 4/5 triangles (float/packed), 6/7 parallelogram quads whose fourth
  corner is b + c - a (often not stored). Leaf headers address vertices in 1024-vertex
  pages.
- The BVH per-leaf surface table holds surface-property indices; R5R reports the model's
  `$surfaceprop` instead, so it does not affect behaviour.

Static checks do not prove runtime behaviour: confirm with `test-r5reloaded`.
