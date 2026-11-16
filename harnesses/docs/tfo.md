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
- **Flaky starts.** The first launch often logs `attempt 1: exited before
  loading the map, retrying`. The retry usually succeeds (`--attempts`,
  default 3). On a captured crash the harness closes only this launch's
  `crashpad_handler.exe` and `messagebox-win.exe`.
- **`-dev` crashes** at startup in the NVIDIA driver, so it isn't used.
- **Screenshots.** The engine's `screenshot` writes nothing and `PrintWindow`
  returns black, so the screen is read. Keep the window visible, and answer any
  Windows Firewall prompt for `TFO.exe` first.

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
