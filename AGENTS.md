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
4. Search `registry/tools/` for applicable tools.
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

## Repository change policy

- Keep changes focused.
- Do not modify upstream repos automatically.
- Validate registry entries before commit.
- Add tests for executable adapters.
