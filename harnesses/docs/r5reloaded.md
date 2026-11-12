# R5Reloaded (Apex) harness

`harnesses/adapters/r5_harness.py` controls an installed R5Reloaded SDK 2.3
through its native legacy protobuf netconsole. It launches the dedicated
executable without a window, loads maps, selects modes and playlists, and runs
console/Squirrel commands. It returns structured readiness results over local
HTTP. There is no injected DLL and no third-party Python dependency.

This tests server loading, scripts and collision. It does **not** certify client
rendering, lighting or sky; check those visually in a rendered client.

## Start the controller

```powershell
python harnesses/adapters/r5_harness.py --game "F:/Games/R5Reloaded" --state-dir reports/r5-harness
```

HTTP binds to `127.0.0.1:39300` and the netconsole to `[::1]:37025`. Use
`--port` and `--game-port` for a second controller. The controller writes
`connection.json` with the bearer token. `r5_harnessctl.py` reads it, so the
token never appears in shell history:

```powershell
$c = 'reports/r5-harness/connection.json'
python harnesses/adapters/r5_harnessctl.py --connection $c boot '{"mode":"dedicated","playlist_file":"PLAYLIST_FILE.txt"}'
python harnesses/adapters/r5_harnessctl.py --connection $c load '{"map":"MAP","playlist":"PLAYLIST","gamemode":"tdm"}'
python harnesses/adapters/r5_harnessctl.py --connection $c command '{"text":"status"}'
python harnesses/adapters/r5_harnessctl.py --connection $c state
python harnesses/adapters/r5_harnessctl.py --connection $c stop
```

Use the playlist file and playlist names your SDK install actually has. The
defaults in the scripts (`playlists_mrvn_coliseum.txt`) come from the original
Coliseum port test. `boot` also accepts `"mode":"client"`, but dedicated mode is
the verified unattended path.

## Repeatable smoke check

```powershell
python harnesses/adapters/r5_harness_smoke.py --connection $c --map MAP `
    --playlist PLAYLIST --gamemode tdm --report reports/r5-smoke.json --boot --reload
```

Each load must observe a **new SERVER VM**, followed by a Squirrel probe that
reports the requested map, the generated playlist, the actual mode and
`EntitiesDidLoad=true`. `--reload` loads a second time in the same process.
`--coliseum-checks` applies only to `mp_mrvn_coliseum_s3`.

## HTTP interface

All requests need `Authorization: Bearer <token>`. Bodies are JSON objects of
at most 32 KiB, with no CORS.

| Method | Endpoint | Body / result |
| --- | --- | --- |
| POST | `/boot` | `mode`, `playlist_file`, optional `timeout` |
| POST | `/load` | `map`, `playlist`, `gamemode`, optional `timeout` |
| POST | `/command` | `text`, optional `timeout` |
| GET | `/state` | PID, liveness, exit code, console state, last load, crash header |
| GET | `/events` | Latest 100 filtered native events |
| POST | `/stop` | Quit gracefully, then terminate only this controller's child |

`/load` creates the temporary playlist `ares_harness_run`, inheriting from the
requested one. As a result, `GetCurrentPlaylistName()` reports
`ares_harness_run`. Stock playlist and config files are never edited, and the
temporary copies are removed on stop.

## Notes

- The SDK 2.3 command is `reload_playlists`. The newer SDK's `playlist_reload`
  isn't interchangeable.
- Legacy RCON frames are a big-endian 32-bit size plus a protobuf message, with
  no encrypted envelope.
- Dedicated R5 mounts `englishserver_<map>.bsp.pak000_dir.vpk` and its server
  chunk. Loose BSP files weren't enough to load a map.
- Events exclude password, token and network-key lines. Raw engine output stays
  in the state directory.

Verified 28 October 2026: dedicated Coliseum boot and reload each created a
fresh server VM, and eight collision probes matched source fractions within
0.0001. The same process switched mode `tdm` → `fs_dm`, then loaded
`mp_rr_arena_composite`.
