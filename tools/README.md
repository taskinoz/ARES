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

For v29, record validation also checks water heights/material indices, world
light strides and finite fields, lightmap dimensions and SKY/RTL plane lengths,
probe-reference indices, static-prop probe indices and probe-tree ranges/cycles.
These layouts are scoped to v29; v37 lighting uses different records. Passing
them establishes selected structural consistency, not shader or gameplay parity.

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

## PS4 modules, ports and save data

| Tool | Does | Example |
| --- | --- | --- |
| `prx_inspect.py` | Decrypted PS4 module (`.prx`, `eboot.bin`) or x86-64 ELF: segments, VA/file-offset conversion, string search, rip-relative code xrefs, vtables with relocations applied, byte patterns, disassembly (with capstone) | `python tools/prx_inspect.py xrefs engine.prx --string echo --exact` |
| `rpak_platform.py` | Counts PC and PS4 texture layouts in TF2 v7 RPaks; a PC pak in a PS4 mod renders black | `python tools/rpak_platform.py --scan mods --require ps4` |
| `pdef.py` | Persistence definition (`.pdef`) size, field offsets and diffs | `python tools/pdef.py diff old.pdef new.pdef` |

Module addresses are module-relative VAs (`engine+0x1234`); PS4 load addresses
change every run. Skill: `reverse-engineer-prx`. Runtime checks on PS4 go
through the [shadPS4 and GoldHEN adapters](../harnesses/README.md).

## Edit and optimise Titanfall 2 maps

These write maps of any size: `bsp_edit.py` streams lumps instead of loading
the map. Each takes `--output OUT.bsp`, or replaces the input in place. Each
decodes what it wrote and compares it with the input before saving. They are
MIT licensed, from [taskinoz/apex-to-titanfall-2](https://github.com/taskinoz/apex-to-titanfall-2).
Background: [the research note](../docs/research/tf2-map-rendering-and-visibility.md).

| Tool | Does |
| --- | --- |
| `bsp_edit.py` | Reads lumps from and replaces lumps in v29/v37 BSPs, moving the GAME_LUMP directory offsets with it |
| `weld_tricoll.py` | Stores each triangle-collision position once per header. A converted map went from 19.96M to 5.76M positions; retail is about 0.65 per triangle |
| `weld_shadow_meshes.py` | Stores each sun-shadow mesh position once, saving 24-28 MB on converted arenas |
| `csm_props.py` | Inspects the cascaded-shadow object tree, or lists static props in it so they cast real-time sun shadows (bounds from `.mdl` files) |
| `cubemaps.py` | Plans cubemap origins, inspects a map's cubemaps, and writes in-game-captured faces as BC6H VTF, pakfile and per-mesh assignments (Pillow and `texconv`) |
| `cells_all_visible.py` | Finds visibility cells without portals, which hide entities outside the camera's cell, and sends every point to the all-visible cell |

Skills: `optimise-tf2-map`, `add-tf2-prop-shadows`, `add-tf2-cubemaps`.

## Publishing

`thunderstore_upload.py check` validates a Thunderstore package's layout
offline. `upload` publishes it with Thunderstore's multipart, background-validated
protocol; the token comes from `$TCLI_AUTH_TOKEN`. Skill: `publish-thunderstore`.

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

`rpak_platform.py` ports PS4 Northstar's runtime check
(`launcher/include/northstar_ps4/mod_rpaks.h`); `prx_inspect.py` and `pdef.py`
generalise that project's reverse-engineering and save-data scripts.
The map edit tools and `thunderstore_upload.py` come from
[taskinoz/apex-to-titanfall-2](https://github.com/taskinoz/apex-to-titanfall-2) (MIT).
The others were written in [taskinoz/MRVN-Radiant](https://github.com/taskinoz/MRVN-Radiant)
(`tools/respawn`, commit `53fd030`) and moved here so they can be reused
without the map editor. Format research and sources are cited in each module's
docstring. The cited notes are in that repository's `docs/respawn/` folder. The
map converters and the `remap` compiler regression suite stay in MRVN-Radiant.


The v29 record validator also checks occlusion and opaque/alpha shadow vertex
streams, mesh-local shadow indices and cumulative triangle ranges, texture name
string offsets/references, and PHYSICS_COLLIDE model/solid/keydata framing.
These are structural checks; IVP trees, fluid semantics, CSM object namespaces
and runtime lighting/physics behavior require separate validation.

The v29 record validator also checks embedded entity KeyValues and declared
`ENTITIES01` partition syntax through `entity_text.py`. It honors the default
external partition table and rejects unsafe/case-alias names, missing or linked
files, malformed blocks and data after NUL. Counts establish syntax coverage,
not gameplay correctness.
