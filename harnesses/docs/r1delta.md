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
- **Paused server.** On maps without a match intro, the loadout menu pauses
  the server and physics stops. The harness sends `unpause nomsg` once the
  player exists.

## Recorded results

Retail Angel City (16 traces, 16 barrels) passed, with every barrel resting on
its traced floor. On a compiled closed-solid bevel map, all 5,148 traces and
hull sweeps matched TFO within 0.001 unit.
