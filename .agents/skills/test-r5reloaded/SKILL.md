---
name: test-r5reloaded
description: Package Apex (S3) models with RePak and test them in an isolated R5Reloaded copy - spawning, sequences, attachments, trace collision, physics drops and ragdolls - with the ARES harness. Use to get runtime evidence for R5 models.
---

# Test models in R5Reloaded

Windows only. Needs the user's own R5Reloaded install and a separately installed RePak.
Nothing from the game is bundled or copied out.

## 1. Build runtime assets

Compile with `--external-assets` (model, rig, one sequence asset per sequence, `.phy`
when there is physics) and bind every material to an RPak asset GUID, for example with
taskinoz/r5-model-compiler:

```
r5studiomdl --target s3 --external-assets --material-guid <material>=<guid> -o out\box.rmdl box.qc
```

## 2. Package

```
python -m ares.r5.rpak --target s3 --repak <repak.exe> --out out\pak --name my_models out\box.rmdl
```

It checks the asset set, the rig, every sequence asset and the PHY's size and checksum
against the model, then writes `my_models.rpak`, the mandatory `.starpak` and
`my_models.report.json`. Add test expectations to that report (below).

## 3. Run

```
python -m ares.harness.r5reloaded --game <R5R folder> --runtime <new folder, same drive> --pak out\pak\my_models.rpak [--collision] [--keep-open]
```

- `--runtime` must be a separate folder on the same volume: large assets are hard links or
  junctions, configs/scripts/mods are copied. Never point it at the installed game.
- The harness refuses to start next to another game process, uses offline settings and a
  loopback SDK netconsole, spawns every model, plays each non-reference sequence, samples
  movement and optional `probe` attachments, and takes screenshots.
- Report: `<runtime>\r5c-report.json` (with netconsole and script logs beside it). Exit
  code nonzero on a failure. Convert with `python -m ares.result r5reloaded <report>`.

## Collision expectations (`--collision`)

Per model in the package report (and `collision_controls` for installed retail models):

- `collision_traces`: `[[dx, dy, expected_top_or_null], ...]` ordinary traces (`TraceLine`,
  shot mask) onto a `SOLID_VPHYSICS` prop_dynamic placed 240 units up.
- `high_detail_traces`: same, with `TraceLineHighDetail`.
- `physics_drops`: `[[null_or_placed_model_path, expected_rest_height], ...]`: prop_physics
  dropped 160 units onto a level spot found by a ground search.
- `ragdoll: true`: the prop must switch to a ragdoll (`BecomeRagdoll`).

Compute expected heights from the compiled BVH (`ares.r5.bvh54`); at angles 0, BVH
coordinates are world offsets from the prop. Avoid points on edges where either level
would be right.

## What R5R does (v2.6.52, measured)

- Ordinary traces of a prop_dynamic read its physics-hull BVH entry and miss models
  without one (retail too); `TraceLineHighDetail` reads the trace-mesh entry.
  `TRACE_MASK_SHOT` also hits hitboxes; use `TRACE_MASK_SOLID` to isolate collision.
- Traces report the model's `$surfaceprop`, not the BVH surface table.
- A prop_physics needs a `prop_data` keyvalue or the game deletes it. Retail models
  always have `mdlkeyvalue{prop_data{base "..."}}`.
- A jointed model becomes a ragdoll only with an `ACT_DIERAGDOLL` sequence; an empty
  (clip-less) one crashes BecomeRagdoll (divide by zero) in a RePak build, so it must carry
  a one-frame clip. The sequence named `ref` must stay empty.
- Ragdolls are client-side: the server only sees its entity replaced; there is no server
  `prop_ragdoll`, and client ragdolls are not found by `GetClientEntArrayBySignifier`.
  Ragdoll motion is not script-measurable.
- Squirrel: global declarations go at the top of a script; a function has a limited number
  of locals ("Too many locals"), so generated probes call helpers.
- After a crash, close the test runtime's `crashmsg.exe` before the next run.

Report runtime verification only for what the run checked; screenshots need review.
