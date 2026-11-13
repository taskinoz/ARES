# Titanfall 2 map rendering, lighting and visibility findings

Evidence from converting six Apex Legends arenas to Titanfall 2 / Northstar
(taskinoz/apex-to-titanfall-2, October-November 2026), checked against retail
`mp_homestead` and `mp_colony02` and MRVN-Radiant's
`docs/respawn/RESPAWN_TF2_LUMPS.md`. The runtime results come from Northstar 1.31.14,
single client, Windows 11.

## Verified

### Visibility cells cull entities, not just world objects

A map split into cells with no portals hides every entity outside the camera's
cell.
- **Ropes:** on a converted Thermal Station (12 cells, no portals),
  `move_rope`/`keyframe_rope` ropes in another cell were not drawn from cell 4.
  The same map with its cell BSP (0x6A) pointed at the all-visible cell drew
  them.
- **Players:** these are entities too, so a player in another cell is very
  likely invisible. This was not tested directly: spawning a static-prop model
  as a dynamic prop stalled the server, and dropped weapons ended up behind
  geometry.
- **Practice:** keep one all-visible cell (`tools/cells_all_visible.py`)
  until cells have portals. Retail maps connect cells with portals; Homestead
  has 1,305.

### The world drawing limit is per frame, and shadow meshes and props are outside it

engine.dll stops world mesh submission past 0x300000 indices, about 1.05M
triangles, of the meshes visible that frame (`tools/audit_tf2_budget.py`).
Shadow meshes and static props use other paths:
- welding shadow meshes frees no scenery budget;
- more scenery means static props, which draw outside the budget.

### Sun-shadow (CSM) geometry

- **Layout:** SHADOW_MESHES (0x7F `<2I2h`) is first position, triangle count,
  opaque and material sort. Indices (0x7E, uint16) are local to the first
  position and follow the previous meshes'.
- **Retail:** Homestead stores 86,042 positions for 384,819 indices.
- **Converted maps:** three per triangle, 2.66-2.96M positions.
- **Welding** (`tools/weld_shadow_meshes.py`): down to 0.61-0.71M positions.
  The six maps loaded and drew their sun shadows unchanged.
- **Triangle collision** follows the same pattern. Homestead stores 432,219
  positions for 662,080 triangles, and welding a converted map's collision
  (`tools/weld_tricoll.py`) took it from 19.96M to 5.76M positions and its BSP
  from 930 to 759 MB. Player drops at ten spots landed at the same heights as
  before.

### Static props in the cascaded shadow map

The CSM tree (0x63, cell AABB node layout) holds static props; 0x64 lists their
object ids.
- **Basis:** boxes are in light space, with z = -sun and
  x = normalize(sun.y, -sun.x, 0), where sun is the shadow environment's normal.
- **Check:** 6,809 of Homestead's 6,833 referenced prop origins fall inside
  their node's box with that basis, against 5 with the sun negated.
- **Result:** listing 3,344 props on a converted Thunderdome
  (`tools/csm_props.py`) made the skull and rocks shade themselves and the
  ground in real time.

### Cubemaps

- **Retail:** Homestead has 4 and Colony 7.
- **Writer:** the MRVN layout (`tools/cubemaps.py`) loaded on six maps:
  - BC6H VTF 7.5 in a stored `XZP1 0` pakfile;
  - a per-mesh cubemap byte;
  - material sorts storing cubemap 0.
- **Face orientation:** faces captured in game and resampled with MRVN's D3D
  face mapping join along shared edges.
- **Effect:** subtle. Shaded rock, grass and metal pick up reflected light.
- **Capture details:**
  - fov 106.26 is 90 degrees vertically at 16:9, because the fov is the 4:3
    horizontal angle;
  - `rui_drawEnable 0` hides the HUD, which camera mode doesn't.

### Baked sun

- **Lightmap content:** the lightmaps store sun *visibility* (RTL B channel 0).
  The engine shades the sun at run time from the sun world light and the
  shadow environment normal.
- **Changing the sun:** update the world light, the shadow environment and
  `light_environment`, then re-bake channel 0 (and the probes' sun visibility
  byte).
- **Bake check:** re-baking with a map's existing sun reproduced its installed
  sun visibility on 98.6% of 6.29M texels, within 8/255.

## Harness notes

- Northstar's `script` console command splits on `;`. A vector literal
  starting with a negative (`<-5,...>`) parses as the `<-` operator, so write
  `< -5, ... >`.
- `CreatePropDynamic` with a model that is only loaded as a static prop
  stalled the listen server.
- The release acceptance spawn count must include Titan spawns. Drop-Off has 48
  pilot and 12 Titan spawns.

## Not verified

- The frame-rate cost of static props in the CSM.
- The meaning of the cubemap `CMA` resource (MRVN writes 1.0 for gameplay
  cubemaps).
- Whether retail assigns cubemaps by visibility rather than nearest distance.
