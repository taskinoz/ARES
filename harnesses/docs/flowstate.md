# R5Flowstate (Apex S21) harness

`harnesses/adapters/flowstate_harness.py` renders map views in R5Flowstate, the
Apex Legends bridge that runs a Season 21 client (`r5apex_dx12.exe`) against a
Season 3 dedicated server (`r5apex_ds.exe`). It starts both, moves Flowstate's
own client script camera to each view, hides the HUD, takes named engine
screenshots and reviews the frames. It is the only ARES harness that renders
Apex; the [R5Reloaded harness](r5reloaded.md) is dedicated-server only.

## What it touches

- **The install is read only.** Every run uses an isolated copy (`--runtime`)
  on the same drive. Assets, executables and scripts are hard links, so the copy
  takes almost no space and builds in seconds. `cfg`, `platform/cfg`, `mods`,
  `LiveAPI`, `r2` and `bin` are real copies, so anything the game writes (configs,
  logs, screenshots, demos) lands in the copy. A marker file stops it reusing a
  folder it didn't create.
- **A per-run mod goes into the copy only:** `mods/ARES-Harness` (id
  `ARES.Harness`, realm `client`), listed in the copy's `mods.vdf`.
- **Saved Games.** The S21 client keeps `settings.cfg`, `videoconfig.txt` and
  `profile.cfg` in `Saved Games/Respawn/Apex_s30`, shared with normal play. The
  harness backs up the existing `.cfg`/`.txt` files, restores them after the run
  and lists any it created (`profile_files_created`).
- **Processes.** It stops only the client and server it started.

## Run

```powershell
python harnesses/adapters/flowstate_harness.py --game "C:/Games/Flowstate" `
    --runtime "C:/Games/.ares-flowstate" --map mp_rr_canyonlands_staging_mu1 `
    --playlist survival_dev --checks views.json --output reports/flowstate-run
```

`views.json`:

```json
{"views": [[x, y, z, pitch, yaw], ...], "hide_hud": true, "relative_to_spawn": false,
 "server_commands": ["host_timescale 1"]}
```

- `relative_to_spawn: true` treats each origin as an offset from where the local
  player spawned. Use it on a map whose coordinates you don't know yet; the report's
  `player` field (from the server) gives the spawn pose for absolute views.
- `server_commands` run on the dedicated server over RCON after the map loads
  (one command each; no `;` or line breaks).
- `cubemap_balls: true` places `mdl/dev/envballs.rmdl` (the `weapon_cubemap`
  view model: spheres plus grey and colour charts in S30) as a client-side prop
  in front of the camera at every view, as Flowstate's own art viewer does, so
  the frames show what the map's cubemaps reflect. Giving `weapon_cubemap`
  itself doesn't work here: the S30 weapon HUD looks the weapon up as survival
  loot (`SURVIVAL_Loot_GetLootDataByRef`), the lookup fails, and the client
  disconnects with "There was a problem processing game logic". Server scripts
  over RCON also need typed locals (`entity p = ...`); `local p` fails with
  "Cannot call ... without compile-time type checking".
- `--prepare-only` builds the copy and the mod without launching. `--keep-open`
  leaves the game running (it then skips the Saved Games restore).

The report (`report.json`) has `events`, `errors`, `screenshots`, `player`,
`frames` and `frame_warnings` (shared frame review: black or single-colour frames
fail, near-duplicates warn), `finished`, and both exit codes. Exit code 0 means
every view was captured and nothing failed.

## How it works

1. **Server.** `r5apex_ds.exe -dedicated -port P -offline +sv_cheats 1
   +sv_rcon_sendlogs 1 +launchplaylist PLAYLIST +map MAP`, with the launcher's
   loopback RCON session: `FROM_R5F_LAUNCHER=1`, a fresh `R5F_LOCAL_RCON` password
   and `R5F_LOCAL_RCON_PORT` in its environment only (never on the command line).
   That session listens on the IPv6 loopback, sends frames unencrypted and accepts
   any registered command, rate-limited to 20 a second.
2. **Readiness.** The harness subscribes to the server console over RCON and sends
   `script printt( "ARES_FS SERVER map=" + GetMapName() )` every few seconds; the
   echo only comes back once the map's server scripts run.
3. **Client.** `r5apex_dx12.exe -offline -dev -windowed -width 1280 -height 720
   +connect 127.0.0.1:P`.
4. **Views.** On local player spawn the mod calls `CreateWorldCrawlerCamera()`,
   then for each view `SetWorldCrawlerCameraPositionAndAngles()` and
   `screenshot <token>_<n>`. The camera is a client-side point camera from
   Flowstate's `cl_utility_camera.nut`, so the player never moves and the
   bridge's unrelayed `roamingcam` message is not needed.
5. **HUD.** `cl_drawhud 0` does not reach the S21 RUI HUD. The mod calls
   Flowstate's `DevHud_ClientSet( true )`, which sets the cinematic flags that hide
   the main and permanent HUD and the obituary, and restores it afterwards.
6. **Collection.** Screenshots land in the copy's `r2/screenshots/` as TGA and are
   converted to PNG. Client script prints are not written to any log file, so
   progress comes from the screenshot files and from the server (the `player` pose
   is read with a server script over RCON).

## Netconsole framing

Each frame is `'RCon'` magic and length (big-endian), then a protobuf envelope
`{header{seqNr, sessionId}, data}`. Sequence numbers start at 1 and rise by one,
and the session id stays fixed for the connection; the server rejects anything
else. `data` is `netcon.request` (type 0 exec, 1 auth, 2 console log), and exec
takes the command name as `requestMsg` and the whole line as `requestVal`. This
differs from the legacy SDK 2.3 encoder in `r5_harness.py`, and from the R5R 2.6
`NetConsole` in `ares/harness/r5reloaded.py`, which sends a new session id per frame.

## Verified

2026-11-20, R5Flowstate SDK `R5FlowstateSDK005`, Firing Range
(`mp_rr_canyonlands_staging_mu1`, playlist `survival_dev`): three spawn-relative
views captured as engine screenshots with the HUD hidden, frame review clean,
player pose read over RCON, Saved Games restored, exit 0.

Not covered yet: other maps and modes, absolute map views at scale, LiveAPI events,
and renderer or lighting checks beyond the frame review.
