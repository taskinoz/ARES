# ARES — Agent Research & Evaluation System

[![AI: AI-built agent tooling](.github/badges/ai-generated.svg)](AI.md)
[![Skill available](.github/badges/skill-available.svg)](.agents/skills/)

ARES is an agent-first, documentation-driven repository for discovering and orchestrating tooling across Respawn Source-engine game ecosystems.

## Supported targets

- R1: Titanfall 1 / R1Delta
- TFO: Titanfall Online
- R2: Titanfall 2 / Northstar
- R5: Apex Legends / R5Reloaded

### TF1 / R1Delta and TFO compatibility

MRVN-Radiant currently uses one BSP v29 compiler target for both games:
`remap -game titanfallonline`. ARES tests the runtimes separately. R1Delta needs
an intermission camera, has a smaller coordinate limit, and mounts different
content; a successful TFO run does not establish R1Delta compatibility.

Paired collision and rigid-prop support samples pass. One freshly compiled TFO
water room renders underwater geometry/fog; R1Delta water surface rendering
remains open. R1 capture cameras now use noclip after normal physics probes to
prevent gravity drift. Complete lighting, collision, buoyancy, asset packaging,
gameplay/navigation and human release acceptance are still required. See the
[TF1/TFO compatibility log](docs/tf1-tfo-compatibility.md) for evidence and gaps.

Current compiler follow-up corrects v29 mesh vertex-type and material-sort span
metadata against five retail maps. R1 uniquely named UnlitGeneric controls draw
both water surfaces from staged files, while native Water materials on the same
BSP still fail visually. This isolates the staging/visibility control without
claiming Water shader compatibility.

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
- `.agents/skills/`: reusable, task-scoped skill documents (mirrored into
  `.claude/skills/` by `scripts/sync-agent-skills.py`).
- `ares/`: standalone model tools and in-game model harnesses (Python package).
- `tools/`, `harnesses/adapters/`, `harnesses/recipes/`: map tools, map harnesses and multi-step game procedures (see below).
- `docs/`: architecture, conventions, compatibility, workflows.
- `harnesses/`: the result contract, map adapters and their guides.
- `scripts/`: validation, discovery and upstream-refresh utilities.
- `tests/`: tests for the scripts and the `ares` package, with small compiled fixtures.

## Model tools and harnesses (`ares/`)

Standard library only, Python 3.10+. Run from the repository root; `python -m ares`
lists every tool and `python -m <module> --help` documents it.

| Target | Read and check | In-game harness |
| --- | --- | --- |
| R1 / R1Delta | `ares.r1.mdl52`, `ares.source.ivp_phy` | `ares.harness.r1delta` (+ `r1delta_mcp`, `r1delta_compare`) |
| TFO | `ares.r1.mdl52`, `ares.r2.mdl53`, `ares.source.ivp_phy` | `ares.harness.tfo` |
| R2 / Northstar | `ares.r2.mdl53`, `ares.source.ivp_phy` | `ares.harness.northstar` |
| R5 / R5Reloaded | `ares.r5.mdl54`, `ares.r5.phy54`, `ares.r5.bvh54`, `ares.r5.compare_phy54`, `ares.r5.compare_bvh54` | `ares.r5.rpak` then `ares.harness.r5reloaded` |

`python -m ares.result <kind> report.json` converts a model-harness report into the
ARES result contract (`harnesses/contracts/result.schema.json`). The tools are
vendored from taskinoz/r1-, r2- and r5-model-compiler; `ares/SOURCES.json` records
each file's origin and commit, and `scripts/vendor-upstream.py` refreshes them.
Skills: `inspect-respawn-model`, `validate-r5-collision`, `test-r5reloaded`,
`test-northstar`, `test-titanfall1`, `compile-model`, `run-harness`.

## Map tools and harnesses

Check a map statically first, then test it in the game.

- [`tools/`](tools/README.md): standard-library readers and validators for
  Respawn BSP v29/v37/v47 (`inspect_bsp`, `validate_records`, `tricoll`,
  `portals`, `game_lump`, `lighting`, `audit_tf2_budget`), plus RPak readers,
  VPK/STBSP writers and swept-collision oracles. Skill: `inspect-bsp`.
- [`harnesses/adapters/`](harnesses/README.md): runtime harnesses for maps and mods.
- [`harnesses/recipes/`](harnesses/recipes/README.md): Northstar release acceptance and cubemap capture, built on the harness.

  | Target | Harness | Guide |
  | --- | --- | --- |
  | R2 / Northstar | `northstar_harness.py` (run in game from ARES, 12 Nov 2026) | [northstar.md](harnesses/docs/northstar.md) |
  | TFO | `tfo_harness.py` | [tfo.md](harnesses/docs/tfo.md) |
  | R1 / R1Delta | `r1_harness.py` | [r1delta.md](harnesses/docs/r1delta.md) |
  | R5 / R5Reloaded | `r5_harness.py`, `r5_harnessctl.py`, `r5_harness_smoke.py` | [r5reloaded.md](harnesses/docs/r5reloaded.md) |

  Skills: `run-harness`, `test-northstar-mod`, `build-map`.

```powershell
python tools/inspect_bsp.py BUILD/mp_name.bsp
python harnesses/adapters/northstar_harness.py --game C:/Games/Titanfall2 `
    --maps BUILD --map mp_name --mode tdm --checks checks.json --output reports/mp_name
```


## PS4 ports and consoles

For porting Respawn games and mods to PS4 (built for PS4 Northstar, Titanfall 2
CUSA04013). The adapters work with any PS4 title.

- [`tools/`](tools/README.md): `prx_inspect` (decrypted PRX/eboot: strings,
  code xrefs, relocated vtables, disassembly), `rpak_platform` (PC vs PS4
  texture layout in RPaks), `pdef` (persistence layout). Skill: `reverse-engineer-prx`.
- [`shadps4_harness.py`](harnesses/docs/shadps4.md): boot in the shadPS4
  emulator with log patterns, pad input, captures and memory reads. Skill: `test-shadps4`.
- [`goldhen.py`](harnesses/docs/goldhen.md): deploy to a real GoldHEN PS4 over
  FTP, enable plugins, record the kernel log and summarise crashes. Skill:
  `deploy-goldhen-plugin`.

## Initial integrated repositories

- https://github.com/taskinoz/r1-model-compiler
- https://github.com/taskinoz/r2-model-compiler
- https://github.com/taskinoz/r5-model-compiler (private)
- https://github.com/taskinoz/PS4-Northstar
- https://github.com/taskinoz/apex-to-titanfall-2
- https://github.com/taskinoz/Titanfall-2-Custom-Maps
- https://github.com/taskinoz/MRVN-Radiant

See `registry/tools/` for metadata, support boundaries, and verification state.

## Getting started

1. Read `AGENTS.md`.
2. Open `games/<target>/AGENTS.md`.
3. Discover tools in `registry/tools/`.
4. List the local tools: `python -m ares` (model tools); see the map tools section.
5. Validate registry data:
   - `python scripts/validate-registry.py`
6. Run the tests:
   - `python -m unittest discover -s tests -p "test_*.py"`
   - `python -m unittest discover -s tools -p "test_*.py"`
   - `python -m unittest discover -s harnesses/adapters -p "test_*.py"`
   - `python -m unittest discover -s harnesses/recipes -p "test_*.py"`
   - `python scripts/sync-agent-skills.py --check`

## Contributing

- Keep changes small and auditable.
- Do not claim unverified runtime support.
- Prefer links to upstream instructions over copied content.
- Update registry verification fields when new evidence is gathered.

See `CONTRIBUTING.md` for details.

## Licence and AI disclosure

MIT (see [LICENSE](LICENSE)), except files whose header says GPL-2.0-or-later:
the map tools in `tools/` and the map harnesses in `harnesses/adapters/`, which
came from [taskinoz/MRVN-Radiant](https://github.com/taskinoz/MRVN-Radiant).
`ares/` and `tests/` are MIT; their provenance is in `ares/SOURCES.json`.
ARES was written with AI; see [AI.md](AI.md) for what was generated and for the
human-built projects it depends on.
