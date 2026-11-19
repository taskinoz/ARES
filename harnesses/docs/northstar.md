# Northstar (Titanfall 2) harness

`harnesses/adapters/northstar_harness.py` loads a map in a Titanfall 2 client
running Northstar, then drives it through the bundled
[`ARES.MapHarness`](../adapters/northstar/ARES.MapHarness) mod. The mod polls a
loopback HTTP controller from the UI, client and server Squirrel VMs and
executes jobs. It does nothing unless the game is started with
`-allowlocalhttp`, `ares_harness_enabled 1` and a token. On the server it
switches off master-server reporting while the harness is active.

## Isolation and recovery

The harness accepts only a new profile or an existing ARES-owned profile, never
an arbitrary player/dedicated profile. Dot/device/trailing-dot names and
redirected profile, mod, enabled-state or lock paths are rejected. Do not add an
ownership marker to an existing player profile to bypass the check.

An exclusive `.ares-session.lock` records the controller process PID and an
ownership token. Concurrent sessions must use different profiles. An interrupted
run may leave a lock: inspect its PID and confirm the owning session/game has
ended before manually removing it. Never remove a live session's lock or stop a
game/server you did not launch. `prepare()` rolls back partial mod copies on
failure; `close()` is idempotent and closed sessions cannot be reused.

The loopback controller requires a bearer token, known endpoint, JSON object and
a body no larger than 64 KiB. The early server initialization hook now requires
the token and HTTP opt-ins before changing local-server settings. These changes
have offline regression coverage, and the opted-in guard path was verified
natively on Northstar 1.31.15 (`mp_glitch`, 2026-11-18).

Ion and Prime are source references, not validated adapter replacements. See
[runtime source routing](../../docs/runtime-sources.md).

## Requirements

- Windows, Titanfall 2 with Northstar installed (`NorthstarLauncher.exe` in the
  game folder). It was tested with Northstar 1.31.15.
- Python 3.10+. Pillow is needed only for view captures.
- A visible desktop session for view captures.

## Run checks on a map

```powershell
# A compiled map: <map>.bsp plus any .ent / .bsp_lump files
python harnesses/adapters/northstar_harness.py --game C:/Games/Titanfall2 `
    --maps BUILD_DIR --map mp_name --mode tdm --checks checks.json --output REPORT_DIR

# A packaged mod (map, paks, scripts), or a stock map with no extra mod
python harnesses/adapters/northstar_harness.py --game C:/Games/Titanfall2 `
    --mod path/to/My.MapMod --map mp_name --checks checks.json --output REPORT_DIR
```

`--game` defaults to `$ARES_R2_GAME`. Useful options:

| Option | Meaning |
| --- | --- |
| `--mode` | Gamemode passed to `mp_gamemode` (`tdm`, `ffa`, or a mod's own, e.g. `surf`) |
| `--mod DIR` | Install this mod folder for the run (repeatable) |
| `--enable NAME` | Enable a mod already installed in the harness profile |
| `--profile` | Isolated profile folder (default `R2AresHarness`, created from the core mods) |
| `--hostport` | Listen-server port (default 37040, so it stays off a dedicated server on 37015) |

`checks.json` uses the [shared format](../README.md#shared-checks-format), plus
these keys:

| Key | Meaning |
| --- | --- |
| `settle` | Seconds to wait after the client is ready (default 20; the pre-match loadout overlay covers views for about 15 s) |
| `console` | UI console commands to run before the checks |
| `spawn_probe` | Points: each gets floor, pilot (32×32×72) and titan (200×200×400) clearance |
| `mode_check` | `true` records spawn, objective, out-of-bounds and hazard entity counts |
| `thirdperson` | `true` treats views as the player's feet position, in third person |

Line and hull traces use `TRACE_MASK_SOLID_BRUSHONLY`.

Outputs in `REPORT_DIR`: `report.json` (events, spawn/mode data), `result.json`
([contract](../contracts/result.schema.json)), `nslog.txt` and `view<i>.png`.
The harness token is replaced with `<redacted>` in the copied `nslog.txt`. Crash
dumps (`nsdump*.dmp`) that Northstar writes to the profile during the run are
copied to `crash/` and listed in `report.json` `crash_dumps`; older dumps are
ignored. The exit code is 0 only when the map loaded, every check ran, and no
script error, crash dump or expectation failed. A server script error stops waiting jobs within a
second and is reported. The command doesn't wait for a timeout.

## Scripted, multi-phase tests

For gameplay mods (timers, records, menus), import the classes and script the
phases yourself:

```python
import sys; sys.path.insert(0, 'harnesses/adapters')
from northstar_harness import Session

with Session('C:/Games/Titanfall2', 'reports/surf', mods=['path/to/MRVN.Surf']) as s:
    s.load('mp_coliseum', 'surf')
    s.run('server', 'player', px=0.0, py=0.0, pz=64.0, pitch=0.0, yaw=90.0, roll=0.0, freeze=True)
    s.run('ui', 'console', command='+jump')
    s.capture('reports/surf/jump.png')
    assert not s.script_errors()
```

Jobs by VM:

| VM | Operations |
| --- | --- |
| `ui` | `load` (map, mode), `console` (command), `screenshot`, `clear_ui`, `status` |
| `client` | `camera` (px, py, pz, pitch, yaw, roll, fov), `camera_clear`, `status` |
| `server` | `trace`, `hull`, `player`, `respawn` (team), `spawn_probe` (points), `mode_check`, `camera_follow`, `camera_restore`, `status` |

To check a mod's internal state, copy it into a scratch folder, add a test
function that `printl`s marker lines or sets `ares_harness_generation` to a
phase name, and pass the copy with `--mod`/`mods=`. `Session.wait_state('ui',
lambda s: s.get('generation') == 'phase-ready', 60, 'phase')` waits for that
phase. Never instrument the released mod folder itself.

## Pitfalls

- **Duplicate mod versions.** If two versions of a mod identity are enabled,
  Northstar logs `Mod 'X' has several versions enabled, disabling them all`
  and loads neither. The harness enables exactly one version per identity in
  its own profile. Check for this first when a gamemode doesn't register
  (the log shows `GAMETYPE: tdm` instead of yours).
- **Loose BSP staging.** `--maps` stages only `.bsp/.ent/.bsp_lump`. A map whose
  spawns or materials come from a level script or RPak needs `--mod` with the
  packaged mod. For example, a bare `mp_mrvn_triportal` failed under TDM with
  `getrandom(): Array is empty`, while its full mod passed.
- **Local loads.** The UI disconnects before every `load`. Replacing a connected
  local server directly can crash the client.

## Verification record

Verified on 12 November 2026 (Northstar 1.31.15, Windows 11). The
`R2Surf` dedicated server ran on the same PC throughout:

- `mp_glitch` / `tdm`, no extra mods: trace, hull, entity counts and one view
  passed; finished in 53 s.
- `MRVN.TriPortalTest` via `--mod`: native results matched the earlier manual
  run exactly. The ray ended at z 16.0336 (fraction 0.879832), the hull at
  z 16.6359 (fraction 0.876820), and the divider wall at x = -8.
- Bare `--maps` staging of the same map: reported the TDM spawn script error
  and failed in 31 s. Cleanup restored the profile in every run.
