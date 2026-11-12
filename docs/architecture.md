# Architecture

ARES separates:

- `registry/`: what tools exist.
- `games/`: where each tool applies.
- `.agents/skills/`: how to execute a class of task (mirrored into `.claude/skills/`).
- `harnesses/`: common execution and reporting contracts, plus the map adapters.
- `ares/`: standalone model tools and model harnesses, vendored from the compiler
  repositories (`ares/SOURCES.json`, refreshed by `scripts/vendor-upstream.py`).
  `ares/result.py` maps each model harness report onto the result contract.
- `tools/`: offline map format tools (BSP, RPak, VPK, STBSP readers and validators,
  swept-collision oracles), standard library only. Moved from MRVN-Radiant `tools/respawn`.
- `harnesses/adapters/`: runtime map/mod harnesses for Northstar, TFO, R1Delta and
  R5Reloaded, with guides in `harnesses/docs/`. `northstar_harness.py` writes the result
  contract (`result.json`) directly.

Upstream repositories stay the source of truth for implementation. Vendored code is
changed upstream first and then refreshed, so the two never drift silently
(`scripts/vendor-upstream.py --check` reports drift).
