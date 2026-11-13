# shadPS4 harness

`harnesses/adapters/shadps4_harness.py` tests PS4 games and mods in the
[shadPS4](https://github.com/shadps4-emu/shadPS4) emulator unattended. It is not
tied to a game: you choose the log lines that mean success and failure, and a
step script drives the menus. It was built for PS4 Northstar (Titanfall 2,
CUSA04013) and works for any title shadPS4 runs.

```powershell
$env:ARES_SHADPS4_EXE = 'C:\path\to\shadPS4.exe'
$env:ARES_PS4_EBOOT  = 'D:\PS4\CUSA04013\eboot.bin'
python harnesses/adapters/shadps4_harness.py boot `
    --success 'lifecycle callbacks loaded' --steps steps.json --capture-end `
    --output reports/shadps4-boot
```

It writes `report.json` (events, module bases, matched line),
`shad-new-lines.log` (only the lines this run added), screenshots, and
`result.json` in the [result schema](../contracts/result.schema.json).
It exits 0 only when the success pattern matched and every step check passed.

## Commands

| Command | Does |
| --- | --- |
| `boot` | Launches `shadPS4 --game EBOOT --log-append`, follows the log from its current end, stops at the first success or failure match, a timeout, or emulator exit. Runs `--steps` after success. Stops the emulator unless `--keep-running` |
| `modules --log LOG` | Module load addresses from shadPS4's `Loading module X to 0x…` lines |
| `pad cross down cross` | Presses buttons in the running window, in order |
| `capture --out x.png` | Saves the game window (PrintWindow works while it is covered) and reports `mean`, `max`, `black` |
| `peek --module engine --offset 0x3818688 --log LOG` | Reads guest memory as hex, u32, i32, f32, u64 and string |

`pad`, `capture` and `peek` are Windows only; `boot` and `modules` run anywhere.

## Step scripts

Steps run in order after the success pattern; any failure-pattern line stops
the run.

```json
[
  {"name": "menu", "wait": "main menu ready", "timeout": 90},
  {"key": "cross"},
  {"key": "down", "times": 2, "gap_ms": 500},
  {"sleep": 3},
  {"capture": "lobby.png", "expect": "not-black"},
  {"peek": {"module": "engine", "offset": "0x3818688", "length": 4}, "expect_u32": 2}
]
```

| Key | Meaning |
| --- | --- |
| `wait` | Regex that must appear in new log lines within `timeout` seconds (default 60) |
| `key`, `times`, `hold_ms`, `gap_ms` | Pad button press. Buttons: `cross circle square triangle up down left right l1 r1 l2 r2 l3 r3 options touchpad lstick_* rstick_*` |
| `sleep` | Seconds |
| `capture`, `expect` | Plain file name ending `.png`; `expect` is `black` or `not-black` |
| `peek`, `expect_u32` | `{"module", "offset", "length"}` or `{"address"}`; optional u32 check |

## How it works

- **Log.** shadPS4 writes `user/log/shad_log.txt` beside a portable install,
  otherwise `%APPDATA%\shadPS4\log` (or the platform equivalent); pass `--log`
  if yours is elsewhere. The follower starts at the file's current end and
  survives truncation, so a multi-GB log costs nothing.
- **Default failure pattern:** `SIGSEGV`, `access violation`, `guest crash`,
  `Unhandled exception`, `[Debug] <Critical>`, `Unreachable code`. Pass
  `--failure ""` to disable it, or your own regex.
- **Pad input** posts `WM_KEYDOWN`/`WM_KEYUP` to the window through shadPS4's
  default keyboard mapping (`input_config/default.ini`), so focus isn't needed.
  A custom mapping needs matching keys. Text can't be typed into the PS4
  on-screen keyboard this way.
- **Memory.** Guest memory is host memory in the shadPS4 process, so a guest
  address is read with `ReadProcessMemory`. Module bases come from the log. The
  adapter only reads; it refuses address 0 (a missing base).
- **Black screens.** `black` is true when the sampled mean brightness is under
  8 and nothing is brighter than 64. Loading screens and fades are briefly
  black, so wait or sleep before an `expect`.

## Safety

- `boot` refuses to start while another shadPS4 is running (`--allow-running`
  overrides). It stops only the process it launched.
- Stopping is a forced terminate. shadPS4 can leave a corrupt pipeline cache
  after a forced stop; if later boots misbehave, clear the title's shader cache.
  Have the game disconnect from servers before the run ends.
- The adapter doesn't modify game files. Deploying a mod or plugin into the
  game folder is your build's job; ask the owner first.
- Measure stability over 8+ boots, never one.

## Tests

```powershell
python -m unittest harnesses/adapters/test_ps4_harnesses.py
```
