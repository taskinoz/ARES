# R1 agent guidance

Use R1/TFO-specific tooling only.

Applicable tool IDs:
- r1-model-compiler
- ares-model-readers
- ares-model-harness-r1delta

Validation expectations:
- Distinguish static compile checks from in-game R1Delta/TFO validation.
- ares-map-harness-r1delta
- ares-bsp-tools

Model tools (`ares/`): skills `inspect-respawn-model`, `test-titanfall1`. Model harness: `python -m ares.harness.r1delta` (prepare/collect/cleanup), `ares.harness.r1delta_mcp` for unattended R1Delta, `ares.harness.r1delta_compare` for retail-versus-rebuilt pairs.

Map tools: skill `inspect-bsp` (`tools/`, BSP v29). Map harness: `python harnesses/adapters/r1_harness.py` (R1Delta, via its MCP server; [guide](../../harnesses/docs/r1delta.md)). Compiled maps need `info_intermission` and coordinates within ±16384. Skill `run-harness`.
