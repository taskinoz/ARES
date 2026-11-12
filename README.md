# ARES — Agent Research & Evaluation System

ARES is an agent-first, documentation-driven repository for discovering and orchestrating tooling across Respawn Source-engine game ecosystems.

## Supported targets

- R1: Titanfall 1 / R1Delta
- TFO: Titanfall Online
- R2: Titanfall 2 / Northstar
- R5: Apex Legends / R5Reloaded

## Principles

1. One source of truth: upstream repositories own implementation details.
2. Agent discoverability: `AGENTS.md` is the canonical entry point.
3. Cross-game awareness: target compatibility must be explicit.
4. Reusable skills: focused workflows in `.agents/skills/`.
5. Progressive integration: start with docs/registry before adapters.
6. Traceable research: record evidence and verification state.

## Repository layout

- `games/`: target-specific instructions and constraints.
- `registry/`: machine-readable tool catalogue and schema.
- `.agents/skills/`: reusable, task-scoped skill documents.
- `docs/`: architecture, conventions, compatibility, workflows.
- `harnesses/`: shared contracts and future adapter surface.
- `scripts/`: validation and discovery utilities.
- `tests/`: repository script tests.

## Initial integrated repositories

- https://github.com/taskinoz/r1-model-compiler
- https://github.com/taskinoz/r2-model-compiler
- https://github.com/taskinoz/PS4-Northstar
- https://github.com/taskinoz/apex-to-titanfall-2
- https://github.com/taskinoz/Titanfall-2-Custom-Maps
- https://github.com/taskinoz/MRVN-Radiant

See `registry/tools/` for metadata, support boundaries, and verification state.

## Getting started

1. Read `AGENTS.md`.
2. Open `games/<target>/AGENTS.md`.
3. Discover tools in `registry/tools/`.
4. Validate registry data:
   - `python scripts/validate-registry.py`
5. Run focused tests:
   - `python -m unittest discover -s tests -p "test_*.py"`

## Contributing

- Keep changes small and auditable.
- Do not claim unverified runtime support.
- Prefer links to upstream instructions over copied content.
- Update registry verification fields when new evidence is gathered.

See `CONTRIBUTING.md` for details.
