---
name: run-harness
description: Load a map or mod in a real Respawn game (Titanfall 2/Northstar or Ion, Titanfall Online, R1Delta, R5Reloaded, R5Flowstate) and run traces, spawn probes, physics drops and screenshots through the ARES harnesses. Use when a map, mod or conversion must be proven to work in the engine, not only to parse.
---

# Run a runtime harness

The harnesses are in `harnesses/adapters/`. The guides in `harnesses/docs/`
hold the full option lists; read the guide for your target before the first run.

## 1. Pick the adapter

| Target | Command | Guide |
| --- | --- | --- |
| Titanfall 2 / Northstar | `python harnesses/adapters/northstar_harness.py` | `harnesses/docs/northstar.md` |
| Titanfall 2 / Ion (isolated runtime; stock `mp_glitch` verified 24 Nov 2026) | `python harnesses/adapters/ion_harness.py` | `harnesses/docs/ion.md` |
| Titanfall Online | `python harnesses/adapters/tfo_harness.py` | `harnesses/docs/tfo.md` |
| Titanfall 1 / R1Delta | `python harnesses/adapters/r1_harness.py` | `harnesses/docs/r1delta.md` |
| Apex / R5Reloaded | `python harnesses/adapters/r5_harness.py` + `r5_harnessctl.py` | `harnesses/docs/r5reloaded.md` |
| Apex S21 / R5Flowstate (rendered views, screenshots) | `python harnesses/adapters/flowstate_harness.py` | `harnesses/docs/flowstate.md` |

These are **map and mod** harnesses. For compiled or converted **models**, use
the `ares` package instead (`python -m ares` lists everything):

| Target | Model harness | Skill |
| --- | --- | --- |
| R5 / R5Reloaded | `python -m ares.harness.r5reloaded` (package first with `python -m ares.r5.rpak`) | `test-r5reloaded` |
| R2 / Northstar | `python -m ares.harness.northstar` | `test-northstar` |
| TFO | `python -m ares.harness.tfo` | `test-titanfall1` |
| R1 / R1Delta | `python -m ares.harness.r1delta` (+ `r1delta_mcp`, `r1delta_compare`) | `test-titanfall1` |

Ion's embedded MCP server also has a standalone client:
`python -m ares.harness.ion_mcp --help`. It connects to an already running game
over loopback HTTP and is not a substitute for a native harness run.

To convert a model-harness report to the result contract, run
`python -m ares.result <r5reloaded|northstar|tfo|r1delta|r1delta-compare> report.json --out result.json`.
It never upgrades verification: prepared-only runs are `tool`, and unreviewed
screenshots are `partial`.

## 2. Check the environment first

- Identify the runtime fork and exact build, not only the game. The Northstar
  adapter is not verified for Ion or Prime; Ion has its own isolated adapter with
  a native stock `mp_glitch` check (other Ion coverage is unvalidated), and Prime
  remains a source reference. R5Reloaded SDK 2.3 evidence does not cover Valkyrie
  or later Apex seasons. Consult
  `docs/runtime-sources.md` before adapting hooks or protocols. Stop at static
  checks if no matching runtime is available.
- Confirm the game folder exists. Ask the user for it if it's unknown; don't
  search whole drives. Ask for the exact install folder and runtime/executable
  location for R1Delta, TFO, Northstar, Ion, R5Reloaded or R5Flowstate; do not
  assume a common drive or folder. Northstar: `$ARES_R2_GAME`, or the folder
  that holds `NorthstarLauncher.exe`. Ion also needs `$ARES_ION_RELEASE` and a
  separate `$ARES_ION_RUNTIME` (default `C:/Games/Titanfall2-Ion` for the
  reported install).
- List running game processes (`Get-CimInstance Win32_Process` for
  `NorthstarLauncher.exe`, `Titanfall2.exe`, `TFO.exe`, `Titanfall.exe`, `r5apex*`).
  **Never stop a process you didn't start.** A dedicated server may be serving
  players. Northstar runs alongside one with `-multiple` and `--hostport 37040`;
  Ion uses `--hostport 37044` and starts MCP on loopback port 8766.
- Run the static checks from the `inspect-bsp` skill first. They are cheaper
  and they explain many runtime failures.
- Northstar refuses existing profiles without its ownership marker. Choose a new
  isolated profile rather than marking a player/server profile as harness-owned.
  Ion also refuses unmarked runtimes and never migrates the existing
  `R2Northstar` mods/packages; use its default separate runtime copy. Failed
  preparation rolls back staged files; do not reuse a closed Session.

## 3. Write checks.json

Start small: one downward trace where you know the floor height, plus one view.

```json
{"traces": [[0, 0, 512, 0, 0, -512]],
 "views": [[0, 0, 600, 45, 0]],
 "expect": {"trace_z": [[0, 63.9, 64.1]]}}
```

Northstar and Ion also accept `spawn_probe`, `mode_check`, `settle`, `console`
and `thirdperson`; Ion additionally records MCP state and a log tail.
TFO/R1Delta accept `drops`, `drop_models`, `drop_wait`, initial `spawn_probe`
authored `triggers` output checks, native atlas `titans` support probes and
explicit `mode_check` initialization checks. See their guides for the v29 schemas;
Northstar's `spawn_probe` schema differs. Trigger checks use controlled repositioning,
not normal traversal.

Views: Northstar and Ion capture with the engine's `screenshot` command and hide the
HUD by default (`engine_screenshots`, `hide_hud`). In TFO prefer
`"freecam": true`: the camera, not the player, is placed, so views can't drift
or die. Every view is reviewed; black or one-colour frames fail and
near-duplicates appear in `frame_warnings`. Before using a console command in a
check, look it up in [the convar reference](../../../docs/convars.md): names
and availability differ between R1, TFO, R2 and Apex/R5Reloaded.

## 4. Run and read the result

```powershell
python harnesses/adapters/northstar_harness.py --game C:/Games/Titanfall2 `
    --maps BUILD_DIR --map mp_name --mode tdm --checks checks.json --output reports/mp_name

# Ion: stage a separate runtime first, then run the same checks against it
python harnesses/adapters/ion_harness.py --game C:/Games/Titanfall2 `
    --ion C:/Users/Tristan/Downloads/Ion.release.v1.31.15 --prepare-only
python harnesses/adapters/ion_harness.py --game C:/Games/Titanfall2 `
    --ion C:/Users/Tristan/Downloads/Ion.release.v1.31.15 `
    --maps BUILD_DIR --map mp_name --checks checks.json --output reports/mp_name-ion
```

- Exit code 0 means loaded, finished and no failures. Otherwise read
  `report.json` `errors` first, then the copied game log (`nslog.txt`,
  `tforevive.log`).
- Look at every `view*.png` yourself before claiming visual correctness. The
  automatic review only rejects blank frames; `capture_methods` says whether
  each came from the engine or a desktop grab.
- `result.json` (Northstar and Ion) follows `harnesses/contracts/result.schema.json`.
  Ion's result records its version, isolated runtime and MCP observation; the
  native stock-map run is in `harnesses/docs/ion.md`, with broader Ion coverage
  still unvalidated.

## 5. Report

State the target, the game/mod versions, the exact command, the checks and
their observed values, the artifacts, and what was **not** verified (e.g.
"collision verified at 3 points; lighting not checked"). Label the result
`runtime` only for the behaviour that was actually exercised.

## Common failures

| Symptom | Likely cause |
| --- | --- |
| Northstar runs `GAMETYPE: tdm` instead of your mode | Two versions of a mod enabled, or the mode's mod not installed (`--mod`) |
| Ion result says `Ion MCP reachable: false` | MCP port busy, `mcp_start_http` not accepted, or the game exited; check `report.json` `mcp.error` and the copied log |
| `getrandom(): Array is empty` | No spawn points for the mode; stage the full mod rather than a loose BSP |
| TFO `attempt 1: exited before loading the map` | Normal flaky start; the harness retries |
| R1Delta match never starts | Map lacks `info_intermission` |
| R1Delta drops never appear | Model not in the map's VPK; pass `--model-files` |
| Black or wrong screenshot | Window hidden or covered (firewall prompt, other window) |


TFO Core135 CP has a duplicate dialogue-registration fault reproduced by authored
and retail launch controls. See the TFO guide for the explicit temporary
`tfo_cp_dialogue_compat` intervention. Reports label it; do not call a patched
run an unmodified-Core pass. Never edit installed Core scripts for this test.

Core135 CP additionally needs the supplied Hardpoint sound definitions repaired
at one known commented brace. Use the TFO guide's explicit sound-file/repair
options; never silence dialogue assertions. Hashes and intervention metadata
must remain in the report. Initialization does not certify capture or scoring.

The v29 `cp_capture` option tests natural neutral-point capture and team scoring;
it never sets match state or ownership. See the guides for limits and required
TFO interventions. Do not promote one capture/hold to whole-mode or match parity.


The v29 `navigation_probe` tests one sampled native grunt route with a supplied
matching graph. See the runtime guides for graph framing limits, CRC/export
caveats and explicit NPC controls. Node count/connectivity alone is not a route
pass. Final arrival/hold and living floor/optional obstacle samples must pass;
this does not establish general AI, continuous swept collision or combat parity.
