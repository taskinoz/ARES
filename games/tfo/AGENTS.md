# TFO agent guidance

Applicable tool IDs:
- r1-model-compiler
- mrvn-radiant (mapping workflows)
- ares-model-readers
- ares-model-harness-tfo
- ares-map-harness-tfo
- ares-bsp-tools

Treat dedicated/client harness expectations as tool-specific and upstream-defined.

Model tools (`ares/`): skills `inspect-respawn-model`, `test-titanfall1`. Model harness: `python -m ares.harness.tfo` (TFORevive; `--prepare-only` is a tool-level check, not runtime).

Map tools: skill `inspect-bsp` (`tools/`, BSP v29). Map harness: `python harnesses/adapters/tfo_harness.py` (TFORevive; [guide](../../harnesses/docs/tfo.md)). Enable `Titanfall1.Content.*` for retail assets. Skill `run-harness`.
