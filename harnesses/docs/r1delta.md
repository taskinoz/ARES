# R1Delta (Titanfall 1) harness

`harnesses/adapters/r1_harness.py` tests maps in R1Delta unattended. It uses
the TFO harness's checks, event lines and report, so the two TF1 runtimes
compare line for line.

```powershell
python harnesses/adapters/r1_harness.py --maps BUILD_DIR --map mp_name `
    --checks checks.json --output REPORT_DIR
```

Omit `--maps` to test a retail map. `--game` defaults to R1Delta's registry
`InstallPath` (`HKCU\Software\R1Delta`), and `--r1delta` defaults to the newest
`%LOCALAPPDATA%/R1Delta/app-*`.

## How it works

- **Control.** R1Delta ships a JSON-RPC (MCP) server, registered with `-usemcp`
  and started by `+mcp_start_http PORT` on 127.0.0.1. The harness launches
  `app-*/Titanfall.exe` the way R1Delta's own launcher does
  (`FROM_DELTA_LAUNCHER`, `ContentId`, DLL folders on `PATH`, game folder as
  the working directory). It loads the map, waits for the local player, then
  runs server Squirrel in batches and reads the printed results. The source
  checked was R1Delta v3.0.4 (`engine/mcp_server.cpp`).
- **Script calls.** R1Delta gives a script 2 s to reach the engine thread. The
  first call after a map load always misses, but still runs later. The harness
  retries, so every script is idempotent, and drop spawning is guarded by a
  run token.
- **Staging.** A compiled map becomes an owned addon `ARES.TF1Harness.<id>` in
  `r1/addons` with only its `.bsp`, `.bsp_lump` and `.ent` files, listed in
  `addonlist.txt`. Cleanup removes exactly that addon and entry. Drop models are
  precached by an addon `scripts/vscripts/test/myscript.nut`. The harness
  refuses to overwrite an existing one.

## Requirements for a compiled map

- **`info_intermission`.** R1Delta's gametype script puts each connecting player
  at one. Without it the match never starts. TFO doesn't need it.
- **Coordinates within ±16384.** R1Delta refuses larger maps ("Map coordinate
  extents are too large!!"), which TFO loads.
- **Drop models.** `models/containers/barrel.mdl` is the default. Most TF1 model
  files live in per-map VPKs, so on a custom map a prop loads without
  `prop_data` and is deleted on spawn. Pass the model's loose files with
  `--model-files DIR`. A distributed TF1 map must ship the models it uses.
  Small models such as `crate.mdl` are made client-side, so they never spawn
  from the harness.
- **Material dependencies.** `--material-files DIR` stages an explicit loose
  tree containing `materials/**/*.vmt` and `materials/**/*.vtf` in the owned
  addon. Supply the material's complete texture, cubemap and bottom-material
  dependencies. Linked paths, empty trees and other file types are rejected.
  This stages supplied files; it does not discover or convert dependencies.
- **Paused server.** On maps without a match intro, the loadout menu pauses
  the server and physics stops. The harness sends `unpause nomsg` once the
  player exists.

Prop samples and final drops include orientation and local model bounds.
`expect.drop_speed` and `expect.drop_bounds_bottom` use the shared
[TFO diagnostics](tfo.md#checks). A rotated model's origin can rest well above
the plane; use the bounds diagnostic alongside poses, not as an exact contact
mesh measurement. `drop_sequential: true` isolates each body, waits and reports
it under its original index, then destroys it before spawning the next body.

## Recorded results

`GetVelocity()` can report zero while a VPhysics prop's sampled origin changes.
The legacy `drop_speed` check therefore measures entity-reported velocity, not
proof of body rest. With `drop_samples: true`, use `physics_observations.py
REPORT/report.json --output REPORT/motion.json --motion INDEX` to require at
most 0.25 units of sampled translation over a two-second tail window. See the
[TFO motion diagnostics](tfo.md) for options and limitations. This does not test
angular motion or events between samples.

Retail Angel City (16 traces, 16 barrels) passed, with every barrel resting on
its traced floor. On a compiled closed-solid bevel map, all 5,148 traces and
hull sweeps matched TFO within 0.001 unit.

## View capture validation

Requested views are held against gravity during capture and log origin and eye
position. Each view must record one finite pose within one unit of the requested
player origin and produce a successful screenshot. TFO requires a capture from
this launch; pre-existing PNGs do not count. R1Delta holds use an ownership token,
a 60-second bound and cancellation after capture, including capture failures.
The freshly launched local R1 game enables `sv_cheats` and toggles noclip for
the capture phase, then toggles it off in cleanup. Ray/hull and prop-drop checks
run before this phase with normal physics. Noclip prevents between-tick gravity
drift that per-frame SetOrigin alone did not eliminate. The game exits after
the run; this adapter does not attach to an existing player session.
Inspect every screenshot: a passing pose/capture check does not prove rendering.
New reports also require `alive=true` and finite eye coordinates for each view.
A correct server origin can coexist with a death/spectator camera; dead players
and older markers without an alive state fail current view validation.


Optional `trace_masks` and `hull_masks` arrays select one mask per corresponding
probe row: `playersolid`, `solid`, `shot` or `water`. Empty/omitted arrays retain
`playersolid`. Nonempty arrays must match the probe count. Values are mapped to
known engine constants, never interpolated as arbitrary script expressions.
These traces do not replace actual fired-projectile or titan gameplay tests.


`engine_screenshots: true` experimentally requests the game's `screenshot`
command, collecting a fresh uniquely named image and converting it to PNG.
Reports record `capture_methods` as `engine` or `window-fallback`. The option
is on by default for R1 after three verified internal captures on R1Delta 3.0.5.
Set it to false to force window capture. TFO keeps it off: Core 135 crashed
during both JPEG and screenshot commands. Window
fallbacks can include desktop popups; inspect them before claiming visual parity.


Water requires compiled shader caches loaded through the map VPK in the native
control. Loose shader files in an addon did not restore it. MRVN-Radiant's
`tools/respawn/pack_tf1_shaders.py` writes a shader-only VPK from explicitly
supplied `shaders/fxc/*.vcs`; it includes no retail caches. Stage such packages
only with owned isolated filenames and cleanup. This adapter's material-tree
option does not stage shaders or map VPKs automatically.


Before installing a custom v29 map, the adapter checks embedded `01*`
ENTITY_PARTITIONS declarations and requires each named `map_partition.ent`
sidecar to exist locally, be nonempty and not be linked. Missing spawn sidecars
can otherwise leave a map on its loading screen. This is a packaging preflight,
not entity-syntax or gameplay validation. Other BSP versions and external
partition-table overrides are outside this check.


## Authored trigger output probes

Both v29 adapters accept `triggers` in checks.json:

```json
{"triggers":[{"targetname":"ares_trigger",
 "points":[[-300,0,1],[0,0,1],[300,0,1]],
 "counts":[[0,0],[1,0],[1,1]],"wait":1,"tolerance":16}]}
```

Each point resets the living player's origin/velocity, waits (0.1..5 seconds),
then samples cumulative `OnStartTouch` and `OnEndTouch` counts. The adapter
requires one result per point, the exact counts, an alive player and a finite
origin within `tolerance` units per axis (default 16; allowed 0.01..64).
At most 16 uniquely named triggers and 2..16 points per trigger are allowed;
coordinates stay within ?16384. Start outside the volume, then enter and leave.
Avoid overlapping triggers and other players: callbacks count player touches.
A missing target, missing/duplicate result, wrong counts, death or wrong pose
fails the run. Use a unique targetname for each authored trigger.

This is controlled repositioning, not normal walking, objective/mode validation
or network testing. MRVN-Radiant's `prepare_tf1_triggers.py` creates original
axis-aligned and rotated fixtures without game assets.


`spawn_probe` checks the actual initial spawn before any trigger/drop/view
repositioning. For example, `"spawn_probe":{"origins":[[-400,0,0]],"tolerance":2}`
requires exactly one result, an alive player on team 2 or 3 and a finite origin
within the tolerance per axis of at least one allowed position. Optional `team`
requires 2 or 3 specifically. Default tolerance is 4 (allowed 0.01..64); up to
64 allowed origins stay within ?16384. This samples one initial spawn, not
respawn choice, all teams, mode selection, objective entities or multiplayer.


## Native atlas support probe

`"titans":[{"origin":[0,500,256],"team":2,"floor_z":0}]` creates a native
atlas NPC on a large floor, then samples it five times at one-second intervals.
The adapters select `titan_atlas` in R1Delta and `titan_atlas_tier0` in TFO;
these script setting names are not interchangeable. The NPC is destroyed after
the samples, including a caught script failure. R1 setup is guarded against
control-call retries. Script errors, missing/duplicate samples, dead/non-titan
entities, nonfinite or invalid bounds, an XY displacement from the requested
spawn greater than `tolerance`, or a bounding-box bottom away from `floor_z`
fail. Default tolerance is 1 (allowed 0.01..8). `max_translation` (default 0.25,
allowed 0.01..8) bounds pairwise sampled displacement independently of reported
velocity. Velocity is diagnostic, not proof of rest.

At most eight sequential probes are allowed; `samples` is 2..10 (default 5)
and `wait` is 0.25..2 seconds per sample (default 1). Choose a friendly team to
avoid combat moving or killing the probe. This tests sampled native NPC support
on the supplied surface, not titan piloting, traversal, combat, AI navigation,
curved surfaces or movement between samples. MRVN-Radiant's
`prepare_tf1_triggers.py --titans` adds this probe to its original fixture.
