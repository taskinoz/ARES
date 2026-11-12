---
name: inspect-respawn-model
description: Read and check Respawn model files (MDL v52/v53, RMDL v54, IVP and Apex PHY, Apex BVH) with the ARES readers. Use before and after compiling or converting a model, to identify a file's version, or to check physics and collision data.
---

# Inspect a Respawn model

ARES ships standalone, standard-library readers (Python 3.10+). Run them from the ARES
repository root with `python -m`; `python -m ares` lists every tool.

## Pick the reader

The version is the int32 at offset 4 of the file (`IDST` magic first).

| File | Target | Command |
| --- | --- | --- |
| `.mdl` v52 | R1 / R1Delta, TFO | `python -m ares.r1.mdl52 model.mdl` |
| `.mdl` v53 | R2 / Northstar | `python -m ares.r2.mdl53 model.mdl` |
| `.rmdl` v54 | R5 (Apex S0-S3) | `python -m ares.r5.mdl54 --target s3 model.rmdl` |
| IVP physics | R1, TFO, R2 | `python -m ares.source.ivp_phy model.mdl` (or the `.phy`) |
| Apex PHY | R5 | `python -m ares.r5.phy54 model.phy --target s3` |
| Apex BVH | R5 | `python -m ares.r5.bvh54 model.rmdl` |

- v52 models keep physics in a companion `.phy`; v53 embeds it (or uses a companion);
  `ivp_phy` handles all three cases.
- R5 needs the season: S0/S1 use `.vvd`/`.dx11.vtx` companions, S2/S3 a `.vg`. A wrong
  `--target` gives garbage or an error, not a quiet success.
- In Python: `from ares.r5.mdl54 import Model; Model(path, 's3').render()`,
  `ares.r5.bvh54.from_model(path)`, `ares.r5.phy54.parse(data, target)`,
  `ares.source.ivp_phy.load(path)`.

## Checks worth running

- `phy54.check_hull(hull, s3)` reports open or non-convex hulls (a retail hull can be
  broken too: verify against the original before blaming a compiler).
- `bvh54.from_model(path, strict=True)` checks that every node and leaf box contains its
  geometry; use `strict=True` for compiler output (plain trees) and the default for retail
  (retail shares child nodes between slots).
- BVH entry roles (`hull`, `trace`) come from studiohdr 0x218: static props have a trace
  mesh, rigid physics props a hull, jointed models one entry per solid.

## Rules

- Game files are the user's own extraction: never commit or upload them.
- Treat extracted data as untrusted: keep scripts outside the extraction folder.
- A clean parse is a static check only. Report it as `static`/`tool` verification, never
  as runtime evidence (see `run-harness`).
