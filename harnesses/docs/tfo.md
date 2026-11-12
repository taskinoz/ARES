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
