# Ion (Titanfall 2) isolated harness and MCP client

Ion is a Titanfall 2 / Northstar fork. `harnesses/adapters/ion_harness.py`
stages a **separate runtime folder**, launches that copy with the ARES map
harness mod, and starts Ion's embedded MCP server for state and log capture.
Its MCP client is also usable on its own as `python -m ares.harness.ion_mcp`.

Native ARES validation now exists for stock `mp_glitch`/`tdm` on Ion 1.31.15
(2026-11-24, `reports/ion-runtime-20261124/run4`). The MCP protocol, tools and
command name were confirmed from
`r2ion/IonLauncher@ae960ecc405b81e2eae307e9c0e318388daa39ea`. Other maps,
mods, gamemodes and visual review remain unvalidated. Keep Ion evidence
separate from Northstar evidence.

## What is isolated

The adapter never writes to the existing game or Northstar install. By default
it creates a sibling folder such as `C:\Games\Titanfall2-Ion`.

- Base game files are hard-linked, so staging a ~70 GB install costs little
  space. The source and runtime must be on the same volume.
- `r2/cfg` and `r2/screenshots` are real copies; game writes cannot reach the
  original install.
- Only Ion's own files are copied from the release folder. Existing
  `R2Northstar` mods, packages, profiles and backups are **not migrated**: Ion
  supplies its own core mods, and Northstar mods are not assumed compatible.
- The runtime carries `.ares-ion-runtime` with the source paths and Ion
  version. An unmarked folder, or one prepared from different sources, is
  refused. The ARES profile is `R2AresIon`, never `R2Northstar`.
- Before launch, the adapter copies Ion's `Northstar.dll` and `plugins/`
  into `R2AresIon`. IonLauncher checks `<profile>/Northstar.dll` before the
  install root; without that copy it loads the source install's Northstar DLL
  and Ion's `NSIsVanilla()` built-in is missing. The DiscordRPC plugin supplies
  `ClearJoinSecret()` for Ion's UI scripts.
- The map, user mods and harness mod are staged by the existing
  `northstar_harness.Session` under `R2AresIon`; owned files are removed and
  `enabledmods.json` restored after the run. The isolated runtime itself is
  kept for reuse.

## Prepare only (no game launch)

Use this first to check paths and prove the original install is untouched:

```powershell
python harnesses/adapters/ion_harness.py `
  --game C:/Games/Titanfall2 `
  --ion C:/Users/Tristan/Downloads/Ion.release.v1.31.15 `
  --prepare-only
```

The command prints the runtime path and writes `ares-ion-release.json` with
SHA-256 hashes of the launcher, `Northstar.dll` and the client mod manifest.
Use `--runtime` to choose a different folder. Do not point it at an existing
install or profile.

## Run checks

```powershell
python harnesses/adapters/ion_harness.py `
  --game C:/Games/Titanfall2 `
  --ion C:/Users/Tristan/Downloads/Ion.release.v1.31.15 `
  --maps BUILD_DIR --map mp_name --mode tdm `
  --checks checks.json --output reports/mp_name-ion
```

`checks.json` uses the shared format documented in
[harnesses/README.md](../README.md#shared-checks-format). The adapter adds the
Ion MCP state, tool list and log tail to `report.json`, and writes
`result.json` with `tool: ion_harness` and `target: r2`. A result is labelled
`runtime` only when the game launched and the checks finished; MCP reachability
itself is an extra check, not proof of map correctness.

Before launching, list running processes and choose free ports. The adapter
uses `--hostport 37044` (Northstar's harness uses 37040) and starts MCP on
`--mcp-port 8766` (Ion's default 8765 is avoided, as is R1Delta's default).
Never stop a game or server you did not start. Use `--no-mcp` to skip both the
start command and the MCP observation if the port is unavailable.

## MCP client

Ion embeds a loopback-only Streamable HTTP MCP server in `Northstar.dll`. Start
it in game with `+mcp_start_http PORT` or `mcp_start_http PORT`; the adapter
does this automatically. Protocol version is `2025-06-18`. The server requires
an `initialize` handshake, returns an `Mcp-Session-Id`, and exposes
`execute_squirrel`, `execute_console_command`, `get_game_state`,
`search_script_functions` and `get_console_log`. A bare client can connect to
an already running game:

```powershell
python -m ares.harness.ion_mcp --port 8766 health
python -m ares.harness.ion_mcp --port 8766 tools
python -m ares.harness.ion_mcp --port 8766 state
python -m ares.harness.ion_mcp --port 8766 console "map mp_glitch"
python -m ares.harness.ion_mcp --port 8766 squirrel server "printl(GetMapName())"
python -m ares.harness.ion_mcp --port 8766 search GetMapName
```

`GET /health` is a readiness probe; JSON-RPC requests go to `POST /` and the
client closes its session with `DELETE /`. Origins other than localhost are
rejected by the game. The client uses only the Python standard library.

## Caveats

- Ion's scripts use `NSIsVanilla()` for runtime switching. Do not assume a
  Northstar-only Squirrel hook or build-time `VANILLA` branch behaves the
  same; recheck UI, client and server initialization on Ion.
- A successful static check or MCP handshake does **not** prove map rendering,
  lighting or gameplay. Review every captured frame yourself.
- If the runtime preparation fails, inspect the isolated folder before reusing
  it. A failed first preparation is removed; a marked runtime is reused.
- Ion's release and launcher revisions differ. Record the exact release hash
  in any result you publish.
- One exploratory `spawn_probe` at `[0, 0, 500]` reported `floor=False`,
  `pilot=True`, `titan=False`; it is not part of the verified checks and needs
  separate follow-up. Trace and mode checks matched the Northstar baseline.

## Verification record

- 2026-11-24: source inspected at `r2ion/IonLauncher@ae960ecc`; protocol,
  tools, command and session behaviour confirmed. Offline tests cover the
  MCP client handshake, isolated staging/ownership and profile DLL/plugin
  staging.
- 2026-11-24: **native** Ion 1.31.15, runtime `C:/Games/Titanfall2-Ion`,
  profile `R2AresIon`, stock `mp_glitch`/`tdm`: map loaded, checks finished,
  trace hit Z `768.03125`, mode check ran, MCP reachable with all five tools
  and state `In Game: Yes`, `Current Map: mp_glitch`; no script errors, crash
  dumps or port/process leftovers. Evidence:
  `reports/ion-runtime-20261124/run4/`. No view capture, custom map, mod,
  gamemode or Ion-only gameplay path was exercised.
