# R5 agent guidance

Applicable tool IDs:
- apex-to-titanfall-2
- mrvn-radiant
- r5-model-compiler
- ares-model-readers
- ares-r5-collision
- ares-rpak-packager
- ares-model-harness-r5reloaded
- ares-map-harness-r5reloaded
- ares-bsp-tools

Do not claim full runtime parity with R2 or R1 toolchains.

Model tools (`ares/`): skills `inspect-respawn-model`, `test-r5reloaded`. Model harness: package with `python -m ares.r5.rpak`, run `python -m ares.harness.r5reloaded`; check collision with `validate-r5-collision`.

Map tools: skill `inspect-bsp` (`tools/`, BSP v47, Apex RPak v8). Map harness: `python harnesses/adapters/r5_harness.py` + `r5_harnessctl.py` (SDK 2.3 dedicated; [guide](../../harnesses/docs/r5reloaded.md)). Server-side only; it does not check rendering. Skill `run-harness`.
