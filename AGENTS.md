# ARES — Agent Instructions

ARES is a central repository for AI-assisted development, research, modding, and testing across Respawn Source-engine games.

## Supported targets

- R1: Titanfall 1 / R1Delta
- TFO: Titanfall Online
- R2: Titanfall 2 / Northstar
- R5: Apex Legends / R5Reloaded

Do not assume binary, asset, scripting, or protocol compatibility between targets.

## Agent startup procedure

1. Read this file.
2. Identify target game and requested operation.
3. Read `games/<target>/AGENTS.md`.
4. List the local tools (`python -m ares` for model tools; `tools/` and
   `harnesses/adapters/` for map tools) and search `registry/tools/` for applicable tools.
5. Read the selected registry entry.
6. Consult upstream AGENTS/README/skills/harness documentation.
7. Load only relevant ARES skill docs.
8. Confirm available test environment.
9. Execute and validate.

## Source of truth

- ARES owns cross-project conventions.
- Upstream repositories own implementation details.
- Upstream instructions take precedence inside their repository.
- ARES safety and verification requirements still apply.
- Report conflicting instructions instead of guessing.

## Execution and safety rules

- Inspect scripts before execution.
- Do not execute unknown binaries blindly.
- Use isolated output locations for generated artifacts.
- Do not modify installed game files without explicit permission.
- Never expose credentials or private game assets.
- Do not bypass anti-cheat or authentication controls.

## Validation requirements

Always report:

- target and environment
- tool and version/commit
- commands executed
- tests performed
- artifacts produced
- failures and limitations

Verification labels:

- verified
- partially verified
- experimental
- untested

Do not report runtime validation when only static/tool-level checks were performed.

## Local tools

- `ares/` (model tools and model harnesses): standard library only, run from the
  repository root with `python -m <module>`. Its files are vendored from the compiler
  repositories: change them upstream and refresh with `scripts/vendor-upstream.py`
  (`ares/result.py`, `ares/__main__.py` and the package `__init__.py` files are ARES's
  own). Report harness outcomes through `python -m ares.result`.
- Map tools and map harnesses: check maps statically with `tools/` (skill `inspect-bsp`),
  then in game with `harnesses/adapters/` (skill `run-harness`; Northstar mods: `test-northstar-mod`).
  Optimise Titanfall 2 maps with the `tools/` writers (skills `optimise-tf2-map`, `add-tf2-prop-shadows`,
  `add-tf2-cubemaps`). Before a release, run `harnesses/recipes/northstar_acceptance.py` (skill
  `accept-northstar-map`), then `publish-thunderstore`.
  Guides are in `harnesses/docs/`. Harnesses stage only owned files in isolated profiles
  and restore everything afterwards. Never stop a game or server process you didn't
  start: a Northstar dedicated server may be running (the map harness uses `--hostport 37040`).
- Edit skills in `.agents/skills/`, then run `python scripts/sync-agent-skills.py`.
- Never commit game files. Test fixtures are small models compiled from the compilers'
  own examples (`tests/fixtures/models`).

## Repository change policy

- Keep changes focused.
- Do not modify upstream repos automatically.
- Validate registry entries before commit.
- Add tests for executable adapters.
