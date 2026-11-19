# Console variables and commands for testing

What each engine exposes for runtime testing: cameras, clean captures, render
isolation, debug overlays, AI and bots, time and logging. Use it to choose
harness commands instead of guessing names across games. The engines share
most debug convars but differ in the ones that matter: TFO has a scriptable
freecam, Titanfall 2 lacks `cvarlist` and `find`, and Apex has Recast navmesh
debug drawing and `script` commands but no freecam.

## How the lists were made

[`tools/convar_scan.py`](../tools/convar_scan.py) reads the game binaries
without launching anything, so it is safe on fragile builds and also finds
development-only convars that retail hides. No per-build byte signatures are
used; it recognises how each engine lays out a registration:

- a call to a ConVar or ConCommand constructor, recognised by the shape of its
  arguments at 20+ call sites (direct calls, or calls through a pointer as in
  the legacy R5Reloaded SDK);
- constructors the compiler inlined: the name, help and flags are stored
  straight into the object (R1's `server.dll`, every Apex `r5apex.exe`, and the
  legacy SDK's heap-built ConCommands);
- ConCommands laid out as initialised data (TFO's `client.dll`, Apex).

| Game (build scanned) | Entries | Convars | Commands |
| --- | --- | --- | --- |
| R1: Titanfall 1 retail + R1Delta 3.0.5 | 3,741 | 3,054 | 687 |
| TFO: Titanfall Online (TFORevive) | 3,857 | 3,096 | 761 |
| R2: Titanfall 2 + Northstar 1.31.15 | 3,012 | 2,453 | 559 |
| R5: Apex Season 0 and Season 1 (same `r5apex.exe`) | 3,345 | 2,753 | 592 |
| R5: Apex Season 2 (unpacked) | 3,329 | 2,736 | 593 |
| R5: Apex Season 3 (`r5apex.exe`, `r5apex_ds.exe`) | 3,410 | 2,812 | 598 |
| R5: R5Reloaded SDK 2.3 (the harness's install) | 3,577 | 2,941 | 636 |
| R5: R5Reloaded 2.6.52 (launcher `R5R Library/LIVE`) | 3,650 | 2,988 | 662 |

Accuracy was measured on R2 against the game's own answers (`help <name>` for
every candidate name, plus Northstar's `convar_find`; 3,167 entries):

- 2,908 of 3,012 scanned entries were confirmed in the game (96.5%); the rest are
  development-only or otherwise hidden from `help`.
- The scan finds 92% of what the game lists (2,908 of 3,167). The gap is convars that mods and
  Squirrel register at runtime (for example `ares_harness_*`) and a few
  registered outside the usual initialisers (`sv_cheats`, `noclip`,
  `setpos` and `script` exist in R2 but aren't in its scan).
- Defaults match the game's value for 97.6% of convars (2,294 of 2,351). Help
  text matches for all 1,505 convars that have it once multi-line help is
  compared by its first line (the game's `help` prints only that).
- Flag bits were checked against the game's flag names (`0x4000` = CHEAT for
  289 of 290 convars). The remaining bit names come from r5sdk's
  `tier1/iconvar.h`.

Known false entries: six CPU-dispatch descriptors in `tforevive.dll`
(`haswell`, `westmere`, `icelake`, `fallback`, `unsupported`,
`best_supported_detector`) have exactly a convar's shape.

Binaries only show what is registered. A development-only or cheat convar can
still be unusable in a given build, so confirm anything a test relies on in the
game. Northstar answers `help <name>`; R1Delta answers `find` through its
control server (a long `find` sweep made R1Delta exit, so keep queries short);
TFO runs commands from the harness's `view_commands`, and TFORevive adds
`cvarlist`, `get_cvar` and `set_cvar`. Every build also registers the
development-only `convar_list`, not yet tried in game.

## Apex builds

- Seasons 0 and 1 are the same `r5apex.exe`, byte for byte.
- Season 2's `platform/r5apex[original].exe` is still Origin-encrypted
  (`.text` and `.data` at 8 bits/byte, an `.ooa` section), so only the
  unpacked `r5apex.exe` can be scanned. Season 3's `r5apex.exe`,
  `r5apex_ds.exe` and the separately unpacked copy give the same 3,410 entries.
- S0 to S2: 8 added (`crash_test`, `error_test`, `particles_cull_all`), 24
  removed (the `cam_pitchlock_*` camera set). S2 to S3: 154 added (`bhit_*`,
  `bullet_trace_test_*`, the `cam_pitchlock_*` set back), 73 removed.
- R5Reloaded runs the Season 3 engine (3,411 entries in its `r5apex.exe`)
  plus its SDK DLLs. SDK 2.3 adds 172 entries (`bhit`, `navmesh_debug_*`,
  `reload_playlists`); 2.6.52 renames and extends them (`navmesh_draw_*`,
  `playlist_reload`) for 146 added and 73 removed against 2.3. Use the column
  for the SDK the test runs on.
- No Apex build has the TFO freecam commands; only `freecam_swallowButtonInput`
  is registered. `thirdperson_override`, `stream_freeze_camera` and
  `getpos_bind` are the camera controls it has.

## Verified in game

| Use | Command | Where | Result |
| --- | --- | --- | --- |
| Named engine screenshot | `screenshot <name>`, `jpeg <name>` | R2 (Northstar 1.31.15) | Writes `r2/screenshots/<name>.tga` / `.jpg`; used by the Northstar harness |
| Clean frame | `cl_drawhud 0` | R2 | Removes the HUD and the pre-match loadout overlay |
| Free camera | `freecam_enable`, `freecam_setpos`, `freecam_setang` | TFO (Colony) | Renders any pose without moving the player; used by `"freecam": true` |
| Clean frame | `cl_drawhud 0` + `r_drawvgui 0` | TFO | Also hides game-mode announcements and subtitles |
| Discovery | `help <name>`, `convar_find <text>` | R2 | Works; `cvarlist` and `find` are unknown commands |
| Discovery | `find <text>` | R1Delta 3.0.5 | Works over the control server; `cvarlist` output isn't captured |

TFO's engine `screenshot` crashed TFORevive in earlier tests, so the TFO
harness still captures the window by default (see the
[TFO harness guide](../harnesses/docs/tfo.md)).

## Testing-relevant entries

"cheat" needs `sv_cheats 1`; "dev-only" is FCVAR_DEVELOPMENTONLY, hidden from
retail `help`/`find` (Northstar lists many of these anyway). "—" means the scan
didn't find it in that game's binaries; ¹ "in game" means R2's scan missed it
but the game confirmed it. R5R 2.3 and R5R 2.6 include the SDK DLLs; the
retail seasons are close to the 2.3 engine column without the SDK entries.

### Cameras and views

| Name | Kind | R1 | TFO | R2 | R5 | Help |
| --- | --- | --- | --- | --- | --- | --- |
| `freecam_enable` | command | — | yes | — | — | — |  |
| `freecam_disable` | command | — | yes | — | — | — |  |
| `freecam_setpos` | command | — | yes (cheat) | — | — | — | Move freecam to the specified origin. |
| `freecam_setang` | command | — | yes (cheat) | — | — | — | Rotate freecam to the specified angles. |
| `freecam_getpos` | command | — | yes (cheat) | — | — | — |  |
| `freecam_paused` | command | — | yes | — | — | — |  |
| `freecam` | command | — | yes | — | — | — |  |
| `thirdperson` | command | yes (cheat) | yes (cheat) | yes (cheat) | — | — | Switch to thirdperson camera. |
| `thirdpersonshoulder` | command | yes | yes | yes | — | — | Switch to thirdperson-shoulder camera. |
| `firstperson` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) | Switch to firstperson camera. |
| `camortho` | command | yes (cheat) | yes (cheat) | yes (cheat) | — | — | Switch to orthographic camera. |
| `cam_command` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Tells camera to change modes |
| `cam_idealdist` | convar | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) |  |
| `getpos` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) | dump position and angles to the console |
| `getpos_exact` | command | yes | yes | — | — | — | dump origin and angles to the console |
| `getposvec` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) | dump position and angles to the console in 'Vector( x, y, z ), Vector( pitch, yaw, roll )' format |
| `cl_showpos` | convar | yes | yes | yes | yes | yes | Draw current position at top of screen |
| `thirdperson_override` | convar | — | — | — | yes (cheat) | yes (cheat) | Set to -1 to stop overriding. Set to 0 to force first person, 1 to force third person |
| `thirdperson_mayamode` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Switch to thirdperson Maya-like camera controls. |
| `cam_collision` | convar | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | When in thirdperson and cam_collision is set to 1, an attempt is made to keep the camera from passing though w |
| `stream_freeze_camera` | convar | — | — | yes | yes (dev-only) | yes (dev-only) | Freezes camera for purposes of streaming map textures. |
| `getpos_bind` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) | Binds the given key to a setpos/setang command of your current position. |

### Clean frames and capture

| Name | Kind | R1 | TFO | R2 | R5 | Help |
| --- | --- | --- | --- | --- | --- | --- |
| `screenshot` | command | yes | yes | yes | yes | yes | Take a screenshot. |
| `jpeg` | command | yes | yes | yes | yes | yes | Take a jpeg screenshot:  jpeg <filename> <quality 1-100>. |
| `jpeg_quality` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) | jpeg screenshot quality. |
| `jpeg_path` | convar | — | yes | — | — | — | jpeg screenshot path. |
| `cl_screenshotname` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) | Custom Screenshot name |
| `screenshot_overview` | command | — | — | yes | — | — | Take an overview screenshot. |
| `devshots_screenshot` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) | Used by the -makedevshots system to take a screenshot. For taking your own screenshots, use the 'screenshot' c |
| `cl_drawhud` | convar | yes (cheat) | yes (dev-only) | yes (cheat) | yes (cheat) | yes (cheat) | Enable the rendering of the hud |
| `hidehud` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `r_drawvgui` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Enable the rendering of vgui panels |
| `r_drawviewmodel` | convar | yes (cheat) | yes (dev-only) | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `envmap` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) |  |
| `buildcubemaps` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) | Rebuild cubemaps. |
| `mat_envmaptgasize` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) | Final envmap size for "envmap" console command; should be <= 128. |
| `host_framerate` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) | Set to lock per-frame time elapse. |

### Render isolation

| Name | Kind | R1 | TFO | R2 | R5 | Help |
| --- | --- | --- | --- | --- | --- | --- |
| `r_drawworld` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Render the world (0 = none, 1 = opaque only, 2 = trans only, 3 = both). |
| `r_drawstaticprops` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Toggle drawing of static props |
| `r_drawentities` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | 0: don't draw; 1: draw normal; 2: draw bones; 3: draw hulls |
| `r_drawothermodels` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | 0=Off, 1=Normal, 2=Wireframe |
| `r_drawparticles` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Enable/disable particle rendering |
| `r_drawdecals` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Render decals. |
| `r_drawsky` | convar | — | — | yes (cheat) | yes (cheat) | yes (cheat) | Enable the rendering of sky |
| `r_drawskybox` | convar | yes (cheat) | yes (cheat) | — | — | — |  |
| `r_drawropes` | convar | yes (cheat) | yes (cheat) | — | — | — |  |
| `r_drawclipbrushes` | convar | yes (cheat) | yes (cheat) | — | — | — | Draw clip brushes (red=NPC+player, pink=player, purple=NPC) |
| `r_drawlightcache` | convar | yes (cheat) | yes (cheat) | — | — | — | 0: off 1: draw light cache entries 2: draw rays 5: only draw models containing the substring set in r_lightcac |
| `r_drawlightinfo` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `r_lightmap` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `mat_fullbright` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `mat_drawflat` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `mat_luxels` | convar | yes (cheat) | yes (cheat) | — | — | — |  |
| `mat_normals` | convar | yes (cheat) | yes (cheat) | — | — | — |  |
| `mat_showmiplevels` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | color-code miplevels 2: normalmaps, 1: everything else |
| `csm_enabled` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) | Set whether to render cascading shadow maps |
| `csm_debug_2d` | convar | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) |  |
| `vcollide_wireframe` | convar | yes (cheat) | yes (cheat) | — | — | — | Render physics collision models in wireframe |
| `r_drawWorldMeshes` | convar | — | — | — | yes (dev-only, cheat) | yes (dev-only, cheat) | Render world meshes. |
| `r_drawmodelstatsoverlay` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Draws information for static props and other models |
| `r_visualizetraces` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `r_visualizetraces_duration` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) |  |

### Entities, triggers and collision

| Name | Kind | R1 | TFO | R2 | R5 | Help |
| --- | --- | --- | --- | --- | --- | --- |
| `showtriggers` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Shows trigger brushes |
| `showtriggers_toggle` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Toggle show triggers |
| `ent_text` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Displays text debugging information about the given entity(ies) on top of the entity (See Overlay Text) 	Argum |
| `ent_bbox` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Displays the movement bounding box for the given entity(ies) in orange.  Some entites will also display entity |
| `ent_absbox` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Displays the total bounding box for the given entity(s) in green.  Some entites will also display entity speci |
| `ent_pivot` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Displays the pivot for the given entity(ies). 	(y=up=green, z=forward=blue, x=left=red).  	Arguments:   	{enti |
| `ent_messages` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Toggles input/output message display for the selected entity(ies).  The name of the entity will be displayed a |
| `ent_fire` | convar | yes (cheat) | yes (cheat) | in game¹ | — | — | Usage:    ent_fire <target> [action] [value] [delay] |
| `ent_create` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Creates an entity of the given type where the player is looking. |
| `ent_remove` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Removes the given entity(s) 	Arguments:   	{entity_name} / {class_name} / no argument picks what player is loo |
| `sv_showhitboxes` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Send server-side hitboxes for specified entity to client (NOTE:  this uses lots of bandwidth, use on listen se |
| `debug_draw_box_depth_test` | convar | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | Toggle depth test for debug draw box functionality |
| `titan_step_damage_debug` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) | Draw debug box of titan step damage volume |
| `ent_text_radius` | command | — | — | yes (cheat) | yes (cheat) | yes (cheat) | Displays text debugging information about the given entity(ies) on top of the entity (See Overlay Text) 	Argum |
| `showtriggers_distance` | convar | — | — | — | yes (cheat) | yes (cheat) | Sets the distance from the player that triggers can be shown at. |
| `bhit` | command | — | — | — | yes (dev-only) | yes (dev-only) | Bullet-hit trajectory debug. |
| `bhit_enable` | convar | — | — | — | yes (dev-only) | yes (dev-only) | Enables bhit commands from the client |

### AI and navigation

| Name | Kind | R1 | TFO | R2 | R5 | Help |
| --- | --- | --- | --- | --- | --- | --- |
| `ai_debug_nodes` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) |  |
| `ai_debug_node_connect` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) | Debug the attempted connection between two nodes |
| `ai_debug_los` | convar | yes (cheat) | yes (cheat) | in game¹ | yes (cheat) | yes (cheat) | NPC Line-Of-Sight debug mode. If 1, solid entities that block NPC LOC will be highlighted with white bounding  |
| `ai_debug_search_paths` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) |  |
| `ai_show_path_search_nodes` | convar | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) |  |
| `ai_show_hull_attacks` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) |  |
| `ai_debug_squads` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) |  |
| `ai_debug_enemies` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) |  |
| `ai_drawbattlelines` | convar | yes (cheat) | yes (cheat) | — | — | — |  |
| `ai_debug_auto_traverse` | convar | yes (cheat) | yes (cheat) | — | — | — |  |
| `navmesh_draw_enable` | convar | — | — | — | — | yes (dev-only) | Enable the debug drawing of the NavMesh |
| `navmesh_draw_poly_faces` | convar | — | — | — | — | yes (dev-only) | Draws the polygon faces of the NavMesh tiles |
| `navmesh_draw_off_mesh_connections` | convar | — | — | — | — | yes (dev-only) | Draws the off-mesh connections of the NavMesh |
| `navmesh_draw_traverse_portals` | convar | — | — | — | — | yes (dev-only) | Draws the traversal network connecting the polygons of the NavMesh |
| `navmesh_draw_range` | convar | — | — | — | — | yes (dev-only) | Only draw tiles within this distance from our camera |
| `navmesh_debug_type` | convar | — | — | — | yes (dev-only) | — | NavMesh debug draw hull index. |
| `navmesh_draw_poly_bounds` | convar | — | — | — | yes (dev-only) | — | Draws the bounds of the NavMesh polys. |
| `navmesh_hotswap` | command | — | — | — | yes (dev-only) | yes (dev-only) | Hot swap the NavMesh for all hulls. |
| `ai_script_nodes_draw_range` | convar | — | — | — | yes (dev-only) | yes (dev-only) | Debug draw AIN script nodes ranging from shift index to this cvar. |
| `BuildAINFile` | command | — | yes | yes | yes (dev-only) | yes (dev-only) | Build and Save the AI Node Graph (restarts map) |
| `dump_ainet_to_disk` | command | — | yes | — | — | — | Dumps the currently loaded AINet to disk |

### Bots

| Name | Kind | R1 | TFO | R2 | R5 | Help |
| --- | --- | --- | --- | --- | --- | --- |
| `bot_loadout` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Override bot loadout |
| `bot_dontmove` | convar | yes (cheat) | yes (cheat) | — | — | — |  |
| `bot_follow` | convar | yes (cheat) | yes (cheat) | — | — | — | When on, bot will follow the player. |
| `bot_mimic` | convar | yes | yes | — | — | — | Bot uses usercmd of player by index. |
| `bot_kill` | command | yes (cheat) | yes (cheat) | — | — | — | <bot id>.  Kills bot. |
| `bot_equip` | command | yes (cheat) | yes (cheat) | — | — | — | Generate an item and have the bot equip it. 	Format: bot_equip <bot name> <item name> |
| `bot_flipout` | convar | yes | yes | — | — | — | When on, all bots fire their guns. |
| `bot_lagOut` | convar | — | — | yes | yes (dev-only) | yes (dev-only) | Cause bots to lag out |

### Time, state and logging

| Name | Kind | R1 | TFO | R2 | R5 | Help |
| --- | --- | --- | --- | --- | --- | --- |
| `host_timescale` | convar | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Prescale the clock by this amount. |
| `phys_timescale` | convar | yes | yes | in game¹ | yes (dev-only) | yes (dev-only) | Scale time for physics |
| `sv_gravity` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) | World gravity. |
| `sv_pausable` | convar | yes | yes | yes | yes (cheat) | yes (cheat) | Whether the server is allowed to pause |
| `pause` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) | Toggle the server pause state. |
| `unpause` | command | yes | yes | yes | — | — | Unpause the game. |
| `map` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) | Start playing on specified map. |
| `changelevel` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) | Change server to the specified map |
| `mp_gamemode` | convar | yes | yes | yes | yes (dev-only) | yes (dev-only) | Game mode name |
| `developer` | convar | yes | yes | yes | yes | yes | Set developer message level |
| `condump` | command | yes | yes | yes | — | — | dump the text currently in the console to condumpXX.log |
| `con_logfile` | convar | yes | yes | in game¹ | yes (dev-only) | yes (dev-only) | Console output gets written to this file |
| `find` | command | yes | yes | — | — | — | Find commands, convars, and other settings with the specified string in their name/help text. |
| `help` | command | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | Find help about a convar/concommand. |
| `convar_findByFlags` | command | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | Find concommands by flags. |
| `weapon_reparse` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Reloads the weapon script files |
| `give` | command | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | yes (cheat) | Give weapon to player. |
| `sv_cheats` | convar | yes | yes | in game¹ | yes | yes | Allow cheats on server |
| `script` | command | — | yes | in game¹ | yes (cheat) | yes (dev-only, cheat) | Execute Squirrel code in server context |
| `script_client` | command | — | — | in game¹ | yes (cheat) | yes (dev-only, cheat) | Run input code as CLIENT script on the VM. |
| `script_ui` | command | — | — | in game¹ | yes (cheat) | yes (dev-only, cheat) | Run input code as UI script on the VM. |
| `playlist_reload` | command | — | — | — | — | yes | Reloads the playlists file |
| `reload_playlists` | command | — | — | — | yes | — | Reloads the playlists file. |
| `launchplaylist` | command | yes | yes | yes | yes (dev-only) | yes (dev-only) | Launch the current playlist |
| `cvarlist` | command | — | yes | — | — | — | Lists all cvars |
| `convar_list` | command | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | yes (dev-only) | Show the list of convars/concommands. |
| `get_cvar` | command | — | yes | — | — | — | Print cvar's value |
| `reload_mods` | command | — | yes | in game¹ | — | — | Reloads TFORevive mods |

## Regenerate

```powershell
python tools/convar_scan.py reports/convars/r2-northstar/scan.json --game C:/Games/Titanfall2
python tools/convar_scan.py reports/convars/tfo/scan.json --game "D:/Games/Titanfall Online"
python tools/convar_scan.py reports/convars/r1-r1delta/scan.json `
    $env:LOCALAPPDATA/R1Delta/app-3.0.5/r1delta/bin/*.dll --game D:/Games/Titanfall
python tools/convar_scan.py reports/convars/r5-s3/scan.json "F:/Games/Apex Detours/Apex s3/r5apex.exe"
python tools/convar_scan.py reports/convars/r5reloaded/scan.json `
    "F:/Games/Apex Detours/R5Reloaded/r5apex.exe" "F:/Games/Apex Detours/R5Reloaded/gamesdk.dll" `
    "F:/Games/Apex Detours/R5Reloaded/dedicated.dll" "F:/Games/Apex Detours/R5Reloaded/bin/x64_retail/client.dll"
```

Each Apex executable takes about two minutes. Full lists stay in the ignored
`reports/` folder; this page keeps only the entries useful for tests. Scanned
2026-11-19.
