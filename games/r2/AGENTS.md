# R2 agent guidance

Use R2-specific tools and confirm Northstar/runtime assumptions with upstream docs.

Runtime forks and navigation sources: [routing guide](../../docs/runtime-sources.md).
Ion and Prime are discovery references, not validated substitutes for the
Northstar harness. For Recast work, use skill `build-navmesh` and registry entries
`recast-respawn` / `r2recast`; their game exports are not yet ARES-verified.

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
- ares-ps4-module-tools
- ares-shadps4-harness
- ares-goldhen-tools

Model tools (`ares/`): skills `inspect-respawn-model`, `test-northstar`. Model harness: `python -m ares.harness.northstar` (isolated Northstar profile).

Map tools: skill `inspect-bsp` (`tools/`, BSP v37, RPak v7, VPK, STBSP). Map harness: `python harnesses/adapters/northstar_harness.py` (isolated `R2AresHarness` profile; [guide](../../harnesses/docs/northstar.md)). Mod logic: skill `test-northstar-mod`. Skill `run-harness`.

Map optimisation and release: skills `optimise-tf2-map`, `add-tf2-prop-shadows`, `add-tf2-cubemaps`, `accept-northstar-map`, `publish-thunderstore`. Engine findings (cells cull entities, the per-frame world budget, CSM and cubemap layouts): [research note](../../docs/research/tf2-map-rendering-and-visibility.md).

PS4 (CUSA04013, PS4 Northstar): skills `reverse-engineer-prx` (`tools/prx_inspect.py`, `rpak_platform.py`, `pdef.py`), `test-shadps4` (`harnesses/adapters/shadps4_harness.py`, [guide](../../harnesses/docs/shadps4.md)) and `deploy-goldhen-plugin` (`harnesses/adapters/goldhen.py`, [guide](../../harnesses/docs/goldhen.md)). PS4 addresses are module-relative and only valid for the module hash they were found in.
