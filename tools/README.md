# Format tools

Offline readers, validators and small writers for Respawn map formats. They
check a compiled or retail map **before** any game is launched. They use only
the Python 3.10+ standard library and don't modify inputs. Every tool prints
its options with `--help` and writes JSON to stdout, or to `--output`.

They import each other by module name, so run them by path from the
repository root (`python tools/inspect_bsp.py ...`). To import them from your
own script, put `tools/` on `sys.path`.

| BSP versions | Game |
| --- | --- |
| 29 | Titanfall 1 / Titanfall Online (R1) |
| 37 | Titanfall 2 (R2) |
| 47 | Apex Legends (R5) |

## Inspect and validate

| Tool | Does | Example |
| --- | --- | --- |
| `inspect_bsp.py` | Header, lump table, overlaps, external `.bsp_lump` files and entity headers | `python tools/inspect_bsp.py map.bsp --hash` |
| `validate_records.py` | Cross-lump record counts and references for R1/R2 (meshes, vertices, materials, collision, portals) | `python tools/validate_records.py map.bsp` |
| `tricoll.py` | Decodes triangle collision, checks ranges and bevel chains, exports OBJ | `python tools/tricoll.py map.bsp --obj tri.obj` |
| `portals.py` | Cell/portal topology; locates the cell that holds a point | `python tools/portals.py map.bsp --point 0 0 64` |
| `game_lump.py` | GAME_LUMP (static props) inspection and relocation | `python tools/game_lump.py inspect map.bsp --placements` |
| `lighting.py` | Light entities and lightmap inspection; writes authored point lights | `python tools/lighting.py inspect map.bsp --json lights.json` |
| `audit_tf2_budget.py` | World mesh index budget against a hashed `engine.dll` | `python tools/audit_tf2_budget.py map.bsp --engine engine.dll` |

`issues` lists in the output are findings, not proof the engine will accept or
reject the map. Confirm with a [harness](../harnesses/README.md).

## Recover and rebuild

| Tool | Does |
| --- | --- |
| `decompile_bsp.py` | Exports a TF2 scene to an editable project and rebuilds it byte-identically (`export`, `rebuild`). Its experimental `compile` needs MRVN-Radiant's `remap` |
| `recover_collision_map.py` | Recovers collision brushes from v29/v37 maps as a partial Radiant `.map` |
| `bake_direct.py` | Offline direct-light reference bake (diagnostic, not an engine bake) |
| `extract_maps.py` | Extracts sample maps from game VPKs through a supplied `tf2vpk` executable |

## Packages and assets

| Tool | Does |
| --- | --- |
| `pack_vpk.py` | Writes an uncompressed Titanfall 2 VPK 2.3 (small test packages) |
| `stbsp.py` | Reads and writes TF2 STBSP v8.0 material catalogues |
| `rpak.py` | Reads decompressed TF2 v7 RPaks (asset table, v12 materials) |
| `rpak_apex.py` | Reads unpatched, decompressed Apex S3 v8 RPaks |

## Collision oracles

`swept_box.py` and `swept_capsule.py` are independent maths references for
sweeping an axis-aligned box or a vertical capsule through triangles. They give
the expected trace result without engine code. Compare their answers against
harness `HULL` events.

## Data

`data/lump_names.json` holds the R1/R2/R5 lump names. It's a snapshot of
MRVN-Radiant's `lump_names.h`; the names follow that compiler's definitions.

## Tests

```powershell
python -m unittest discover -s tools -p "test_*.py"
```

The tests build synthetic BSPs and need no game files.

## Provenance

These tools were written in [taskinoz/MRVN-Radiant](https://github.com/taskinoz/MRVN-Radiant)
(`tools/respawn`, commit `53fd030`) and moved here so they can be reused
without the map editor. Format research and sources are cited in each module's
docstring. The cited notes are in that repository's `docs/respawn/` folder. The
map converters and the `remap` compiler regression suite stay in MRVN-Radiant.
