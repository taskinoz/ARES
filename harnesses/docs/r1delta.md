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


## Explicit mode and Hardpoint initialization

`"mode_check":{"mode":"cp","hardpoints":3}` selects `mp_gamemode cp` before
loading the map, then requires both `GameRules.GetGameMode()` and `GAMETYPE`
to report `cp`. The optional CP-only `hardpoints` count requires exactly that
many native objectives (1..32), a successful initialization flag, unique IDs
0..count-1 and a valid terminal for each. Other modes can use `{"mode":"tdm"}`
without objective checks; accepted mode identifiers do not imply that every
engine mode/alias works. A fallback mode, duplicate/missing results or incomplete
objectives fails. R1 caches the observation before reading it, guarding against
MCP retries emitting duplicate sets.

MRVN-Radiant's `prepare_tf1_objectives.py --remap PATH --output NEW_DIR` creates
an original Hardpoint room with three triggers, terminals, four assault points
per objective and pilot spawns. It references the base-game terminal model;
retail assets are not bundled. Initialization is not capture/scoring, team
respawn selection, AI navigation or multiplayer acceptance.


## Natural Hardpoint capture and team scoring

With `mode_check.mode` set to `cp`, use:

```json
"cp_capture":{"targetname":"ares_cp_a","origin":[-600,-90,1]}
```

The probe waits up to `ready_wait` seconds (default 30; 0..30) for the match to
reach Playing naturally, requires a neutral objective, then places the player
once inside the authored trigger. It never sets match state, ownership, progress
or scores. It takes `samples` observations (default 10; 2..20) separated by
`wait` seconds (default 2; 0.25..5), at most 60 sampling seconds total.

Every sample must be unique, alive, touching the native trigger and within
`tolerance` units per axis of the requested position (default 4; 0.01..16).
Capture direction must agree with the player's team, ownership must remain
friendly once captured and team scores cannot decrease. The final objective
must be friendly with at least `min_score` new team points (default 1; 1..100).
Missing/dead/outside samples, a non-neutral start, native script errors or a match
that does not start fail. R1 guards its asynchronous sampler against MCP retries.

MRVN-Radiant's `prepare_tf1_objectives.py --capture` emits this check. One neutral
capture/hold passes in both runtimes, gaining five team points in each final run.
TFO requires the explicitly reported Core135 dialogue/sound compatibility setup
above. This is not contested capture, recapture, combat, respawn, AI-navigation,
network or human-match acceptance. Initial placement is controlled; approach
movement is covered by a separate straight-walk diagnostic.


## Native grunt navigation sample

`navigation_probe` accepts a start, goal, expected node count and floor height:

```json
{"navigation_probe":{"start":[-400,0,1],"goal":[400,0,0],"nodes":8,
 "floor_z":0,"samples":12,"wait":1,"radius":24,
 "forbidden_box":[[-64,-144,-1],[64,144,192]]}}
```

Supply the map's matching `maps/graphs/<map>.ain` beside its BSP/sidecars.
R1 now stages that exact graph in its owned addon; TFO includes it in the owned
mod. Both adapters preflight matching v54 graph size, map revision, finite node
geometry and link framing. They do not certify tail semantics, script version
or entity CRC. Native graph header/CRC acceptance is a separate gate.

The probe waits naturally for Playing (at most 90 seconds), explicitly enables
NPCs, spawns one friendly native grunt, disables movement-start animations and
squad following, and gives it `SendAIToAssaultPoint`. It never sets the NPC's
position after spawning. Reports require a living start pose within two units,
expected nodes and at least two reachable neighbors, exactly one living finite
pose per sample, sampled floor height within two units, and the last two poses
within the goal radius. Optional `forbidden_box` excludes sampled origins in an
axis-aligned volume; expand it for the desired hull clearance. It does not
certify every intervening frame, swept collision, animation appearance, combat,
other NPC hulls or dynamic/repeated routes. R1 setup is guarded against MCP
retries. Failures to build/load a graph must not be called navigation passes.

MRVN-Radiant's `tools/respawn/prepare_tf1_navigation.py` generates original floor,
pillar and node geometry plus checks; it generates no AIN or retail assets.
The native R1Delta 3.0.5 `updateain` builder needs its initialization hook enabled
at launch (the local control uses `-r1delta_build_ain_no_existing`). Without it,
it partially changes connectivity then fails its unknown-node-tail allocation.
Use an explicit new private output filename with `updateain`; never use its
`legacy` mode on installed graphs. The native exporter writes CRC zero without
an existing source graph. MRVN-Radiant now has a scoped public exporter:
`tools/respawn/build_tf1_navigation.py --ares ../ARES --maps MAPS --map NAME --output NEW_DIR`.
Run it from that checkout with the pinned engine/server profile. It requests the
explicit `build_navigation` session flag, exports to a new directory and uses
`tf1_navigation_crc.py` to calculate the CRC offline. Ordinary launches do not
enable that flag. External/compressed layouts and ambiguous selected text fail;
tail/script semantics and correctness after geometry edits remain separate.

Original and changed-pillar/node fixtures pass both runtimes' fresh route checks.
Independent owned R1/TFO observations confirm the changed graph's file and
expected CRC both equal 1916430116. No integrity check was disabled. Export is
separate from route and full gameplay acceptance. MRVN-Radiant's
`RESPAWN_TF1_NAVIGATION.md` records hashes, commands, evidence and limits.

### Repeated native navigation legs

Optional `navigation_probe.round_trips` accepts integers 0..3. Zero preserves
the existing one-way events; a positive value requests that many goal/return
pairs on the same NPC. Total sampled time must be at most 180 seconds.
`NAVIGATION LEG N START/SAMPLE` events are indexed and checked independently:
living floor/obstacle poses, initial/leg-start positions and final two arrival/
hold poses. One successful leg does not establish later legs.

Two round trips (four legs, 48 movement samples) pass in both runtimes on the
changed-pillar fixture with the native-exported graph. Returns finish within
the configured 24-unit radius. Controls still enable NPCs and disable movement
starts/squad following; no NPC repositioning follows spawn. This is repeated
human-hull static routing, not dynamic obstacles, default AI or combat.

### Native atlas navigation

`navigation_probe.actor` accepts `grunt` (default) or `atlas`.
Atlas uses native `CreateSpawnNPCTitanTemplate`/`SpawnNPCTitan` with R1's
`titan_atlas` or TFO's `titan_atlas_tier0` settings, and queries
`HULL_TITAN` connectivity. Its required actor event verifies native titan type
and finite ordered bounds larger than the human hull. Floor checks include the
recorded minimum Z. Expand `forbidden_box` for the larger actor.

Final paired runs pass one atlas goal/return pair with 20 movement samples per
leg and bounds (-60,-60,0)..(60,60,235). Arrival facing is unspecified through the
goal helper's `null` angle parameter. The earlier TFO control forcing facing
(0,0,0) reaches the return area but fails its hold; it remains documented in
MRVN-Radiant's navigation checkpoint. Radius, clearance and hold criteria were
not relaxed. Piloting, combat, other titan types, default AI, dynamic obstacles
and fixed-facing behavior remain open.
