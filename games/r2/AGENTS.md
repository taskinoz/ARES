# R2 agent guidance

Use R2-specific tools and confirm Northstar/runtime assumptions with upstream docs.

Applicable tool IDs:
- r2-model-compiler
- ps4-northstar
- apex-to-titanfall-2
- titanfall-2-custom-maps
- mrvn-radiant
- ares-model-readers
- ares-model-harness-northstar
- ares-map-harness-northstar
- ares-bsp-tools
- ares-tf2-map-edits
- ares-northstar-recipes
- ares-thunderstore-upload

Model tools (`ares/`): skills `inspect-respawn-model`, `test-northstar`. Model harness: `python -m ares.harness.northstar` (isolated Northstar profile).

Map tools: skill `inspect-bsp` (`tools/`, BSP v37, RPak v7, VPK, STBSP). Map harness: `python harnesses/adapters/northstar_harness.py` (isolated `R2AresHarness` profile; [guide](../../harnesses/docs/northstar.md)). Mod logic: skill `test-northstar-mod`. Skill `run-harness`.

Map optimisation and release: skills `optimise-tf2-map`, `add-tf2-prop-shadows`, `add-tf2-cubemaps`, `accept-northstar-map`, `publish-thunderstore`. Engine findings (cells cull entities, the per-frame world budget, CSM and cubemap layouts): [research note](../../docs/research/tf2-map-rendering-and-visibility.md).
