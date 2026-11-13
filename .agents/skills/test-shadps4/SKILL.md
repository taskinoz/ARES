---
name: test-shadps4
description: Boot a PS4 game or mod in the shadPS4 emulator and prove it reached a state, with log patterns, pad input, screenshots, black-screen checks and guest memory reads, using the ARES shadPS4 adapter. Use to test a PS4 port, plugin or mod change (e.g. PS4 Northstar), to reproduce a crash or black screen, or to read a live value at module+offset.
---

# Test in shadPS4

Adapter: `harnesses/adapters/shadps4_harness.py`. Guide:
`harnesses/docs/shadps4.md`. Run from the repository root.

## Before you start

1. Check what's running: `tasklist | findstr /i shadps4` (or `pgrep shadPS4`).
   Never stop a shadPS4 you didn't start. `boot` refuses to run beside one.
2. Know the build. Record the shadPS4 version and the SHA-256 of any module you
   changed (`python tools/prx_inspect.py info MODULE`).
3. Deploying files into the game folder changes the user's install. Ask first,
   and keep a backup of anything you replace.

## Procedure

1. **Pick the patterns.** Success is the earliest log line that proves what you
   are testing (e.g. your plugin's "ready" line). Look at a previous
   `shad-new-lines.log` for real lines. Don't guess. Keep the default failure
   pattern unless it matches harmless lines in this game.
2. **Boot.**
   ```powershell
   python harnesses/adapters/shadps4_harness.py boot --shadps4 SHADPS4.exe `
       --eboot GAME\eboot.bin --success 'REGEX' --timeout 180 `
       --capture-end --output reports/shadps4/RUN
   ```
3. **Drive menus** with `--steps steps.json`: `wait` for a log line, press a
   `key`, `sleep`, `capture` with `"expect": "not-black"`, `peek` a value with
   `expect_u32`. Real menu flows beat shortcuts: a command-line or script
   shortcut can fail where the real flow works, and mislead a whole bisect.
4. **Inspect a running game** with `--keep-running`, then `pad`, `capture` and
   `peek --module NAME --offset 0x… --log reports/shadps4/RUN/shad-new-lines.log`.
   Close the game yourself when done (from the game, or stop the PID the report
   lists).
5. **Read results.** `result.json` status, then `report.json` events and
   `shad-new-lines.log`. Look at screenshots yourself; `black: false` only means
   something is drawn.

## Pitfalls

- Boot behaviour varies run to run. Judge stability over 8+ boots.
- Compare against the unmodified game under the same emulator build before you
  blame your change.
- Leftover test mods in the game's mod folder change behaviour; remove what you
  added.
- Pad keys are posted through shadPS4's default keyboard map. Text can't be
  typed into the PS4 on-screen keyboard.
- A forced stop can corrupt shadPS4's pipeline cache.

## Reporting

Quote the eboot, shadPS4 build, patterns, `result.json` status and the matched
line. Call it `runtime` verification for what the steps checked only.
