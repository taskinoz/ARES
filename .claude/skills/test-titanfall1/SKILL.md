---
name: test-titanfall1
description: Runtime-test MDL v52 models in Titanfall Online (TFORevive) and in original Titanfall through R1Delta - staging, telemetry, collision and physics probes, retail-versus-rebuilt comparison - with the ARES harnesses. Use to get runtime evidence for R1 and TFO models.
---

# Test models in Titanfall Online and R1Delta

Both games load MDL v52. **Mount each model at its `$modelname` path** (`models/` + the
name stored in the MDL): the client finds the `.vvd`/`.dx11.vtx` through that name, so a
model mounted elsewhere precaches and collides but draws nothing. Both harnesses reject
other paths. Use a new `$modelname` per compile to avoid the engine's model cache.

## Titanfall Online (TFORevive)

```
python -m ares.harness.tfo --game <TFO folder> --report out\tfo.json [--sequence=] [--attachment probe] [--physics] out\box.mdl=models/r1c_examples/box.mdl
```

- Stages a temporary mod and a temporary copy of the core map-spawn script; never edits
  the core mod; removes its mod afterwards (`--keep-mod` to keep it).
- `--prepare-only` validates staging without launching (always `passed: false`, a
  tool-level result). `--dedicated` is server-only (no rendering claim). `--cwd-bin` for
  builds that expect `Bin` as the working folder. `--mount-only` stages included models.
- Startup crashes are retried (`--attempts`) only when the test script logged nothing;
  the harness closes the crash handler dialogs its launch started.
- Offline sessions have no loadout; the script falls back to `pilot_male_fastest`.
  The engine `screenshot` command leaves no file, so the harness captures the window.
- Only one TFO instance can run, and other tools share `Mods/` and the log.

## Original Titanfall (R1Delta)

Manual (any running R1Delta):

```
python -m ares.harness.r1delta prepare --game <Titanfall folder> --session out\delta.json out\box.mdl=models/r1c_examples/box.mdl
# run the printed `exec r1c_<run-id>` in the local match console
python -m ares.harness.r1delta collect --session out\delta.json --report out\delta-report.json
python -m ares.harness.r1delta cleanup --session out\delta.json
```

Unattended: start `r1delta.exe -usemcp +mcp_start_http` (add `-multiple` and a free
`+hostport` if another Respawn game runs), then drive it with
`python -m ares.harness.r1delta_mcp` (`state`, `console "map mp_fracture"`,
`squirrel server "..."`, `log`). Compare originals and rebuilds side by side with
`python -m ares.harness.r1delta_compare --pairs pairs.json --report out\compare.json`.

- A collected report passes the server telemetry before the screenshots are reviewed;
  that is a `partial` result until a person reviews them.
- Script commands need `developer 1` and `sv_cheats 1` (the generated cfg sets them);
  use `IncludeFile`, not `IncludeScript`. `ServerCommand("screenshot")` and `condump` work;
  `ClientCommand` screenshots do not export.
- `Anim_Play` then `Anim_SetInitialTime(t)` sets an exact time; move a noclip camera with
  `setpos`. `map mp_box` does not load a match: use `mp_fracture`.
- Viewmodels and zero-bounds characters are not drawn as world props; weapon world models,
  gibs and projectiles are not spawnable prop_physics.

Convert reports with `python -m ares.result tfo|r1delta|r1delta-compare <report>`.
