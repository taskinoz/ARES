---
name: test-northstar-mod
description: Test a Titanfall 2 Northstar gameplay mod or gamemode (scripts, timers, records, HUD, triggers) in the real game with the ARES Northstar Session API, using an isolated profile and an instrumented copy of the mod. Use when a mod's behaviour must be verified natively rather than by reading Squirrel code.
---

# Test a Northstar mod in game

For map-only checks, use the `run-harness` skill. This skill is for mod logic
that needs several phases, injected test code, or saved-file checks.

## Rules

- Work only in the harness profile (default `R2AresHarness`). Never edit
  `R2Northstar`, a dedicated server profile, or the mod's source folder.
- Instrument a **copy** of the mod in a scratch folder. Pass the copy with
  `mods=[...]`; the Session installs it as an owned folder and removes it.
- Back up and restore anything the mod writes, e.g.
  `<profile>/save_data/<Mod>/`. The Session restores only `enabledmods.json`
  and the mods it installed.
- Exactly one version of each mod identity may be enabled. Northstar disables
  all copies of a duplicated mod, and the gamemode then silently falls back to
  `tdm`.

## Procedure

1. **Read the mod.** Find its `mod.json` `Name`/`Version`, its gamemode or
   playlist name, its ConVars, and the functions you want to exercise.
2. **Inject a test function** into the copy. Call it with `thread` from the
   mod's init or gamemode setup. Inside it:
   - wait for the state you need (`while ( GetPlayerArray().len() == 0 ) wait 0.1`);
   - assert with a helper that `throw`s, so a failure shows up as a `SCRIPT ERROR`;
   - `printl( "[ModTest] ..." )` for values you want in the log;
   - signal phases with `SetConVarString( "ares_harness_generation", "phase-ready" )`.
3. **Drive it from Python:**

```python
import sys; sys.path.insert(0, 'harnesses/adapters')
from northstar_harness import Session

with Session(GAME, 'reports/mymod', mods=[INSTRUMENTED_COPY]) as s:
    s.load('mp_glitch', 'mymode')
    s.wait_state('ui', lambda st: st.get('generation') == 'phase1-ready', 120, 'phase 1')
    s.run('ui', 'console', command='+jump'); s.run('ui', 'console', command='-jump')
    s.capture('reports/mymod/hud.png')
    log = s.log_text()
    assert '[ModTest] phase1 passed' in log and not s.script_errors()
```

   To test across map loads or ConVar settings, call `s.load(...)` again in
   the same session. Each load is a fresh server VM.
4. **Check persistent output** (saved JSON, leaderboard requests) after the
   phases, then restore the backups in a `finally`.
5. **Look at the captures** before you report HUD or menu results.

## Reporting

List each phase and its observed values, and say which behaviour was exercised
natively and which was only inferred from code. Give the log lines that prove
each assertion ran.
