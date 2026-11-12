# Skills

Mirrored from `.agents/skills/` by `scripts/sync-agent-skills.py`.
Edit the canonical copies there, then run the script.

- [build-map](build-map/SKILL.md): Build or convert a Respawn map and verify it with a static-then-runtime loop. Use when compiling a .map with MRVN-Radiant's remap, converting another game's map, or iterating on a map fix until it works in game.
- [compile-model](compile-model/SKILL.md): Compile models with the registered Respawn compilers and validate the output with ARES readers and harnesses.
- [convert-assets](convert-assets/SKILL.md): Convert assets across supported workflows while preserving provenance.
- [discover-tools](discover-tools/SKILL.md): Discover game-compatible tools - the ARES local tools and the registered upstream repositories - and locate their authoritative instructions.
- [inspect-bsp](inspect-bsp/SKILL.md): Statically inspect and validate Respawn BSP maps (Titanfall 1 v29, Titanfall 2 v37, Apex v47) and their RPak/VPK/STBSP packages with the ARES format tools. Use before any runtime test, to diagnose a map that crashes or misbehaves, or to compare a compiled map against a retail one.
- [inspect-respawn-model](inspect-respawn-model/SKILL.md): Read and check Respawn model files (MDL v52/v53, RMDL v54, IVP and Apex PHY, Apex BVH) with the ARES readers. Use before and after compiling or converting a model, to identify a file's version, or to check physics and collision data.
- [research-engine](research-engine/SKILL.md): Investigate engine behaviour and document evidence-backed findings.
- [run-harness](run-harness/SKILL.md): Load a map or mod in a real Respawn game (Titanfall 2/Northstar, Titanfall Online, R1Delta, R5Reloaded) and run traces, spawn probes, physics drops and screenshots through the ARES harnesses. Use when a map, mod or conversion must be proven to work in the engine, not only to parse.
- [test-northstar](test-northstar/SKILL.md): Load compiled Titanfall 2 models in the game through Northstar with the ARES harness - spawn, sequences, attachments, root motion, physics drops, NPC ragdolls and screenshots. Use to get runtime evidence for R2 models.
- [test-northstar-mod](test-northstar-mod/SKILL.md): Test a Titanfall 2 Northstar gameplay mod or gamemode (scripts, timers, records, HUD, triggers) in the real game with the ARES Northstar Session API, using an isolated profile and an instrumented copy of the mod. Use when a mod's behaviour must be verified natively rather than by reading Squirrel code.
- [test-r5reloaded](test-r5reloaded/SKILL.md): Package Apex (S3) models with RePak and test them in an isolated R5Reloaded copy - spawning, sequences, attachments, trace collision, physics drops and ragdolls - with the ARES harness. Use to get runtime evidence for R5 models.
- [test-titanfall1](test-titanfall1/SKILL.md): Runtime-test MDL v52 models in Titanfall Online (TFORevive) and in original Titanfall through R1Delta - staging, telemetry, collision and physics probes, retail-versus-rebuilt comparison - with the ARES harnesses. Use to get runtime evidence for R1 and TFO models.
- [validate-r5-collision](validate-r5-collision/SKILL.md): Check and compare Apex Legends (S0-S3) physics (PHY) and trace collision (BVH) of a rebuilt or converted model against the original, with fixed limits. Use when compiling, converting or porting R5 models with collision.
