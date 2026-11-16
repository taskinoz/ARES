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
