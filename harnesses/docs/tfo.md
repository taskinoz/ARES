# Titanfall Online harness

`harnesses/adapters/tfo_harness.py` loads a compiled Titanfall 1 map in
Titanfall Online (TFORevive), then runs traces, hulls, physics drops and view
captures.

```powershell
python harnesses/adapters/tfo_harness.py --game "D:/Games/Titanfall Online" `
    --maps BUILD_DIR --map mp_name --checks checks.json --output REPORT_DIR `
    --enable Titanfall1.Content.Client --enable Titanfall1.Content.Shared
```

`--enable` turns on installed content mods. The two Titanfall1 content mods
mount retail TF1 assets and maps; Colony (`mp_colony`) is a useful retail
reference.

## What it does

- Installs the map as the temporary mod `ARES.TF1Harness` and hooks
  TFORevive's `_mapspawn.nut`. It refuses to run if that folder already exists.
- Launches `TFO.exe --authToken ares-local-noauth -noauth`. The token is a
  required placeholder, not a credential.
- Logs `[ARES] TRACE/HULL/DROP/VIEW` lines to `Logs/tforevive.log` and parses
  them into `report.json`.
- Removes the mod and restores `Mods/enabledmods.json` afterwards.

## Checks

The [shared format](../README.md#shared-checks-format), plus physics drops:

| Key | Meaning |
| --- | --- |
| `drops` | `[[x, y, z]]`: spawn a physics prop at each point and log its height |
| `drop_models` | One `models/...mdl` per drop (default: rocket physics with grenade appearance) |
| `drop_wait` | Seconds before sampling (default 4) |
| `drop_sequential` | Test one prop at a time, destroying each after sampling |
| `drop_samples` | Log all props' positions every 0.2 s |
| `view_commands` | Console commands before views, e.g. `["thirdperson"]` |
| `expect.drop_z` | `[[index, min, max]]` expected resting heights |

A sampled height alone doesn't show that a body has settled, or that water
makes it float. Compare matching dry, wet and retail-map controls.

Final `DROP` events include `angles`, `bounds_mins` and `bounds_maxs`, as well
as origin and linear velocity. Both v29 adapters accept these additional ranges
in `expect`, each as `[[index, minimum, maximum]]`:

- `drop_speed`: magnitude of the entity-reported velocity. This can remain zero
  while a VPhysics body moves; it does not establish rest by itself.
- `drop_bounds_bottom`: lowest world Z of the model's rotated local bounding box.

For a box resting on its side, origin height changes while the bottom of the
rotated bounds stays near the supporting surface. The bounding box is **not**
the VPhysics contact mesh: curved models, rounded hulls and visual/physics bounds
can differ. A bounds check is a coarse support diagnostic, not exact collision
or buoyancy verification. Missing pose data fails these expectations; legacy
`drop_z` still compares the raw origin without changing its meaning.

Decode saved reports without launching the game:

```powershell
python harnesses/adapters/physics_observations.py REPORT_DIR/report.json --output REPORT_DIR/physics.json
```

For a rigid single-solid prop, pass its standalone `--phy FILE.phy` to project
the actual collision vertices instead of the visual box. Optional repeated
`--floor INDEX Z` checks require a physics-hull bottom within one unit of that
flat plane and entity-reported speed at most 0.1. Articulated/multi-solid models are
rejected. The report fingerprints the PHY; no game mesh is copied into ARES.
This tests the sampled pose's support, not friction, stacking, buoyancy or
every contact trajectory.

Both sequential and concurrent drops now honor `drop_samples`. Check sampled
translation independently of the velocity field:

```powershell
python harnesses/adapters/physics_observations.py REPORT_DIR/report.json --output REPORT_DIR/motion.json --motion 0 --motion-window 2 --max-translation 0.25
```

`--motion INDEX` requires samples spanning the tail window and rejects more
than the given maximum pairwise displacement. Missing, nonfinite, duplicate or
out-of-order samples fail the requested check. Reports also record tail position
ranges and peak interval-average speed. They do not measure angular rest or
motion between samples. Timestamps use the adapter's clock; these finite
differences are not instantaneous engine velocities. Without `--motion`, this
information is diagnostic and does not add a motion acceptance gate.

## Known behaviour

- **Offline spawning.** Offline sessions have no player data, so the hook falls
  back to the stock `pilot_male_fastest` settings file.
- **Startup failures are not map evidence.** `exited before loading the map`
  means TFO never emitted `UICodeCallback_LevelLoadingStarted`. Check the two
  causes in [Startup blockers](#startup-blockers) before changing a fixture.
  On a captured crash the harness closes only this launch's
  `crashpad_handler.exe` and `messagebox-win.exe`.
- **`-dev` crashes** at startup in the NVIDIA driver, so it isn't used.
- **Screenshots.** The engine's `screenshot` writes nothing and `PrintWindow`
  returns black, so the screen is read. Keep the window visible, and answer any
  Windows Firewall prompt for `TFO.exe` first.

## Startup blockers

Two launch failures look like map failures but are harness/environment issues.
Both were reproduced under compiler
`b0a8064905996b3b2790cee1df12fcf59aae212c9fc6b66301d6ca2370098110` with
one-hash TF1 fixtures. Retain the failing log/report; do not treat a pre-map
timeout as a compiler or BSP result.

### Wrong `--maps` depth

The adapter copies the `--maps` directory into the temporary mod's `maps/`
folder. Passing a build root whose BSP lives in `maps/` installs an empty map
directory. TFO stays on the loading screen about a quarter full, never emits
`UICodeCallback_LevelLoadingStarted`, and each attempt times out with no
traces. `r1_harness.py` already accepted both layouts; the TFO adapter now does
too, and fails with `missing compiled map: ...` before modifying `Mods/` or
`enabledmods.json`.

```powershell
python harnesses/adapters/tfo_harness.py --game "D:/Games/Titanfall Online" `
    --maps .local/respawn/my-build/maps --map mp_name --checks checks.json --output REPORT
# A build root also works when my-build/maps/mp_name.bsp exists:
python harnesses/adapters/tfo_harness.py --game "D:/Games/Titanfall Online" `
    --maps .local/respawn/my-build --map mp_name --checks checks.json --output REPORT
```

`test_map_source_accepts_maps_folder`, `test_map_source_accepts_build_root` and
`test_map_source_rejects_nested_wrong_map_before_mod_install` in
[`test_tfo_harness.py`](../adapters/test_tfo_harness.py) cover this.

### sentry-native 0.7.8 stack overflow

The installed `D:/Games/Titanfall Online/Bin/sentry.dll` is upstream
sentry-native 0.7.8 (`E`: SHA-256
`768f9a5f6ea8c8dd88e3b00c0c604fee09f745831b16de54397815623dda2c26`,
`sentry.native/0.7.8`). Its `DllMain` calls `SetThreadStackGuarantee()` for
every attaching thread. NVIDIA D3D worker threads already have small stacks;
the guarantee consumes the remainder and the worker overflows in
`nvwgf2umx.dll` before map load. Upstream made the auto-guarantee defensive in
0.8.4 ([issue #1193](https://github.com/getsentry/sentry-native/issues/1193),
[PR #1196](https://github.com/getsentry/sentry-native/pull/1196)); TFORevive
tracks it in [bugs#59](https://github.com/TFORevive/bugs/issues/59).

[`tfo_sentry_patch.py`](../adapters/tfo_sentry_patch.py) is a local, reversible
binary workaround. It verifies the installed hash, writes the original to
`<ARES>/.local/respawn/tfo-crash-patch/sentry-original-backup.dll`, replaces
the `DllMain` prologue at file offset `0x7c00` / RVA `0x8800` with
`b8 01 00 00 00 c3` (`mov eax, 1; ret`), and restores the DLL after `run`.
Patched SHA-256:
`f93c0d4be3ee78509f043bedecd3d58eed66492357194e1043434db74f813bf1`.

```powershell
python harnesses/adapters/tfo_sentry_patch.py --game "D:/Games/Titanfall Online" status
python harnesses/adapters/tfo_sentry_patch.py --game "D:/Games/Titanfall Online" apply
python harnesses/adapters/tfo_sentry_patch.py --game "D:/Games/Titanfall Online" revert
python harnesses/adapters/tfo_sentry_patch.py --game "D:/Games/Titanfall Online" run -- `
    python harnesses/adapters/tfo_harness.py --game "D:/Games/Titanfall Online" ...
```

Controlled A/B on the same compiler and replay BSP
`655c618aafb25241054a860f5f828bb377fec9f8cbce413f62a7223e9cfa5bcc`:

| Sentry DLL | Result |
| --- | --- |
| Stock 0.7.8 | Failed before map load, exit `3221225725`. Report `e3b2b51cec94857ce0011fceaf10a62d785bc5544ac6abe84239d1f974e7d13a`, log `4c20deecb06a25fa9a5463faa78285b0eed9e29ea601786c99980f7802dbd63b`. |
| Locally patched | Loaded and finished, 2 traces, 4 views, 0 errors. Report `1b535532075368b7794775aa1b8fce5a992a27013e1cfbc79d6e68b9edeb5d11`, log `4879d7ca1a8355287ac1aab872edf936909e20b359870dc6852704952b880083`. |

Other observed failures with the wrong `--maps` depth used the patched DLL and
still failed before level load; report hashes
`3845235e83d827c0145c72f916ad335685d7531ab95cc63bee48da9417fcf4e5`
(vertex) and `33cc744835ad5a04be22c082363ee6aecfd31798d9e0fa711c2ad25a2a0d9f9e`
(props). Corrected patched runs passed with reports
`1698edb8aac8a68129af934887cf63f20391c33fe6b917162f1b905e95021107` (ARES vertex),
`870bbaeae6a7359b07a17320783a6f602b2deeeec2f18abd339d9303138dcd7f` (props) and
`386e86de1073da2cc3f430e0f02842b21c754e71f04491f083d45071b8a84cae` (masks).
Full provenance:
`C:/Users/Tristan/GitHub/MRVN-Radiant/.local/respawn/tf1-tfo-closure/.local/respawn/tfo-crash-patch/report.json`
and `.../one-hash-native-replay/results.json`.

**Limits (`B`/`E`/`N`).** This is a third-party binary patch, not an upstream
TFORevive fix or a substitute for sentry-native 0.8.4+. It disables per-thread
stack guarantees, so crash reporting on tiny-stack threads is not guaranteed.
One driver, one GPU and a small number of sessions were tested. It does not
cover physics launch breadth, `sprp v12` package loads, image comparisons or
release deployment. The installed DLL is restored to stock after each `run`;
verify with `status` before and after a batch. Synthetic patch tests live in
[`test_tfo_sentry_patch.py`](../adapters/test_tfo_sentry_patch.py).

## View capture validation

Requested views are held against gravity during capture and log origin and eye
position. Each view must record one finite pose within one unit of the requested
player origin and produce a successful screenshot. TFO requires a capture from
this launch; pre-existing PNGs do not count. R1Delta holds use an ownership token,
a 60-second bound and cancellation after capture, including capture failures.
Inspect every screenshot: a passing pose/capture check does not prove rendering.
New view markers include `alive=true` and finite eye coordinates; missing or
false alive state fails validation even when the player origin matches. This
rejects poses recorded after death; screenshot/pose frame synchronization still
requires visual review.


Optional `trace_masks` and `hull_masks` arrays select one mask per corresponding
probe row: `playersolid`, `solid`, `shot` or `water`. Empty/omitted arrays retain
`playersolid`. Nonempty arrays must match the probe count. Values are mapped to
known engine constants, never interpolated as arbitrary script expressions.
These traces do not replace actual fired-projectile or titan gameplay tests.


`engine_screenshots: true` experimentally requests the game's `screenshot`
command, collecting a fresh uniquely named image and converting it to PNG.
Reports record `capture_methods` as `engine` or `window-fallback`. The option
is off by default: TFORevive.Core 135 crashed during both JPEG and screenshot
capture commands in native tests. R1Delta 3.0.5 passed three engine captures and prefers that path by default. Window
fallbacks can include desktop popups; inspect them before claiming visual parity.

### Freecam views

`"freecam": true` renders each view from TFO's client freecam instead of
moving the player: `freecam_enable`, then `freecam_setpos x y z` and
`freecam_setang pitch yaw 0` per view, with `cl_drawhud 0` and `r_drawvgui 0`
(the latter hides game-mode announcements and subtitles). The player stays
where it is, so views can't drift, die, or be blocked by out-of-bounds
triggers, and they work during the dropship intro. View events read
`VIEW i freecam=true pose=x,y,z,pitch,yaw`; the origin/alive checks don't apply.
The commands live in TFO's `client.dll` (found with `tools/convar_scan.py`);
R1 retail and Titanfall 2 lack them. Verified on retail Colony (TFORevive,
2026-11-19): two views from opposite directions, clean frames, exit 0. The pose
is applied as commanded; `freecam_getpos` prints nothing to `tforevive.log`, so
the exact camera position isn't read back.

```json
{"freecam": true, "views": [[1500, 0, 800, 20, 180], [-1500, 500, 900, 30, 0]]}
```

Every captured view is reviewed by
[`screenshots.py`](../adapters/screenshots.py): black or one-colour frames
fail, and near-duplicate views are listed in `frame_warnings`.


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


Core135's `game_state_dialog` routes CP dialogue through both legacy and shared
mode loaders, causing duplicate `RegisterHardpointConversations` registration.
The unpatched authored fixture and a retail Colony launch control fail before
harness probes. `"tfo_cp_dialogue_compat":true` is an explicit opt-in for a
bounded transform, and requires `mode_check.mode` to be `cp`. It adds CP to the
legacy switch so that the second include is skipped. The helper rejects
unsupported/already-fixed routing, invalid text and oversized sources. It
copies the transformed installed script only into the owned temporary harness
mod, with source/output hashes; installed Core files are not edited. Reports
include a non-null `compatibility` object when this intervention is enabled.
Such a run is not an unmodified-Core pass. Omit the flag when testing a Core
version that already fixes the routing. Deterministic script errors now stop
the harness promptly and are not retried as graphics startup failures.


The CP compatibility transform also registers five MFDP-only conversations only
when `GAMETYPE == MARKED_FOR_DEATH_PRO`; it does not bypass current-mode dialogue
assertions. Core135's supplied Hardpoint sound definition has a known commented
closing brace. Supply `--sound-file PATH/mp_hardpoints.txt --repair-hardpoint-sound`
to stage a repaired copy. Unknown malformed variants fail closed. The original
file and installed Core remain unchanged; source/output hashes and definition
counts appear in `report.compatibility.sound_definitions`.

`--sound-file` can be repeated for up to 32 explicit UTF-8 sound-definition files
(4 MiB each, 16 MiB total), whose names must already occur as active audio entries
in Core's manifest. Linked, duplicate, malformed or unsupported sources fail
before staging. Repair requires explicit CP mode and supplied `mp_hardpoints.txt`.
This validates syntax and references, not wave payloads or playback. The final
three-point initialization fixture passes with these reported interventions;
unmodified Core does not. Capture, scoring and other modes remain separate gates.


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
