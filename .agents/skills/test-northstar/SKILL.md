---
name: test-northstar
description: Load compiled Titanfall 2 models in the game through Northstar with the ARES harness - spawn, sequences, attachments, root motion, physics drops, NPC ragdolls and screenshots. Use to get runtime evidence for R2 models.
---

# Test models in Titanfall 2 (Northstar)

Needs the user's Titanfall 2 install with Northstar. Set `TITANFALL2_DIR` or pass `--game`.

```
python -m ares.harness.northstar --report out\report.json out\model.mdl=models/r2c_test/model.mdl
```

Each argument is `local file = game path`. The harness creates an isolated profile
(`R2ModelTest`) with the core Northstar mods and a generated mod that precaches each
model, spawns it as a `prop_dynamic` in front of the player, plays `--sequence`, takes a
screenshot (`<game>\r2\screenshots\*.tga`) and quits. It exits nonzero on a missing spawn,
a script error or a timeout. Convert the report with
`python -m ares.result northstar out\report.json`.

## Options

- `--pose-attachments a,b`: log those attachments' origin and angles.
- `--probe-attachment` with `--probe-times`: sample one attachment during playback.
- `--motion seq1,seq2`: play with `Anim_PlayWithRefPoint` and sample origin/yaw (root motion).
- `--physics`: drop physics props and log their fall; `--npc --ragdoll`: death ragdolls.
- `--extra-file local=gamepath`: mount a non-model file (for example a weapon script).
- `--no-animation`: spawn without a sequence (viewmodels have no `idle`).

## Lessons

- Compare against the original side by side: mount retail and rebuilt copies under
  different paths and compare attachment poses. This found a rebuilt weapon lying on its
  side (lost delta flags) when byte diffs matched.
- Model i is offset by `(i - (n-1)/2) * spacing + lateral` along the player's right;
  `--lateral -110 --spacing 100` keeps two models clear of the viewmodel.
- Server queries miss client-only effects: `GetAttachmentOrigin` ignores procedural
  bones; check those visually against a control without them.
- Viewmodels: mount a rebuilt `ptpov_*.mdl` over its retail path so the default loadout
  uses it; its report "fails" on the missing `idle` sequence but the screenshot is valid.
- Squirrel: `foreach` over an array literal does not compile (use a typed variable);
  `ClientCommand()` exists only in the UI VM.
- "Authentication Failed" when launching straight into a map: the generated server script
  sets `ns_auth_allow_insecure`. `NO_GAMESERVER_RESPONSE` errors are harmless.
