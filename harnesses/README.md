# Harnesses

Runtime harnesses load a map (and optionally mods) in a real Respawn game,
run checks inside the game's own scripting VM, and write a machine-readable
report. They let an agent prove a compiled map or mod works in the engine, not
only that a file parses.

All adapters live in [`adapters/`](adapters/) as standalone Python 3.10+ scripts.
Each prints its options with `--help`.

| Target | Adapter | Game control | Guide |
| --- | --- | --- | --- |
| R2: Titanfall 2 / Northstar | `northstar_harness.py` | Loopback HTTP; `ARES.MapHarness` mod polls it | [northstar.md](docs/northstar.md) |
| TFO: Titanfall Online | `tfo_harness.py` | Temporary mod with a `_mapspawn` hook; reads `tforevive.log` | [tfo.md](docs/tfo.md) |
| R1: Titanfall 1 / R1Delta | `r1_harness.py` | R1Delta's built-in JSON-RPC (MCP) server | [r1delta.md](docs/r1delta.md) |
| R5: Apex / R5Reloaded SDK 2.3 | `r5_harness.py`, `r5_harnessctl.py`, `r5_harness_smoke.py` | Native protobuf netconsole behind an HTTP controller | [r5reloaded.md](docs/r5reloaded.md) |

PS4 adapters work for any title, not only one engine. They don't use the shared
checks format; success and failure are log patterns you supply.

| Platform | Adapter | Control | Guide |
| --- | --- | --- | --- |
| PS4 in shadPS4 | `shadps4_harness.py` | Log patterns, posted pad keys, window capture, guest memory reads | [shadps4.md](docs/shadps4.md) |
| Real PS4 with GoldHEN | `goldhen.py` | FTP deploy, `plugins.ini`, kernel log recorder and crash summary | [goldhen.md](docs/goldhen.md) |

## Shared checks format

The TFO, R1Delta and Northstar adapters accept the same core `checks.json`
keys and print the same event lines, so results from different engines compare
line for line:

```json
{
  "traces": [[0, 0, 4000, 0, 0, -4000]],
  "hulls": [[0, 0, 4000, 0, 0, -4000, -16, -16, 0, 16, 16, 72]],
  "views": [[0, 0, 1500, 60, 0]],
  "expect": {"trace_z": [[0, 767.9, 768.1]], "hull_z": [[0, 767.9, 768.1]]}
}
```

```text
TRACE 0 fraction=0.403996 end=768.03125 solid=False normal=<0.0, 0.0, 1.0>
HULL 0 fraction=0.403996 end=768.03125 solid=False normal=<0.0, 0.0, 1.0>
VIEW 0 captured=True
```

`expect` rows are `[check index, minimum Z, maximum Z]`. A failed expectation
makes the command exit non-zero. Each adapter adds its own keys: physics drops
for TFO and R1Delta, and spawn probes, entity counts and settle time for
Northstar. Only Northstar rejects keys it doesn't support.

## Lifecycle and safety

Every adapter follows the same lifecycle (see [the contract](../docs/harness-contract.md)):

1. **Prepare.** Stage the map/mods in an isolated place: a separate Northstar
   profile, a temporary TFO mod or R1Delta addon, or an owned R5 playlist copy.
   Staged folders carry an owner marker. A folder the harness doesn't own is
   never overwritten.
2. **Execute.** Launch the game with loopback-only control and a random token.
3. **Validate.** Run checks, capture views, scan logs for script errors.
4. **Report.** Write `report.json` (raw events) and, for Northstar,
   `result.json` in the [result schema](contracts/result.schema.json).
5. **Cleanup.** Quit the game, remove owned files and restore
   `enabledmods.json`/`addonlist.txt` byte for byte, even after failures.

Rules for agents:

- Don't touch the player's main profile (`R2Northstar`) or any dedicated server
  profile. Use the adapter's default isolated profile.
- Check what's running before you launch. A dedicated server may own the default
  port 37015; the Northstar adapter listens on `--hostport 37040`.
- View captures read the screen. The game window must stay visible and
  unobstructed while views are captured.
- A harness run is **runtime** verification only for what it checked. Traces
  passing doesn't prove lighting, materials or client rendering.

## Tests

The adapter unit tests need no game install:

```powershell
python -m unittest discover -s harnesses/adapters -p "test_*.py"
python -m unittest discover -s harnesses/recipes -p "test_*.py"
```
