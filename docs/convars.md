# Console variables and commands for testing

What each engine exposes for runtime testing: cameras, clean captures, render
isolation, debug overlays, AI and bots, time and logging. Use it to choose
harness commands instead of guessing names across games: the three engines
share most debug convars but differ in the ones that matter (TFO has a
scriptable freecam; Titanfall 2 lacks `cvarlist` and `find`).

## How the lists were made

[`tools/convar_scan.py`](../tools/convar_scan.py) reads the game binaries
without launching anything. It finds the ConVar and ConCommand constructors by
the shape of their call sites, reads R1's inlined `server.dll` registrations,
and reads TFO's statically laid-out command objects.

| Game (build scanned) | Entries | Convars | Commands |
| --- | --- | --- | --- |
| R1: Titanfall 1 retail + R1Delta 3.0.5 | 3,731 | 3,048 | 683 |
| TFO: Titanfall Online (TFORevive) | 3,745 | 3,044 | 701 |
| R2: Titanfall 2 + Northstar 1.31.15 | 2,976 | 2,437 | 539 |

Accuracy was measured on R2 against the game's own answers (`help <name>` for
every candidate name, plus Northstar's `convar_find`; 3,167 entries):

- 2,872 of 2,976 scanned entries were confirmed in the game (96.5%); the rest are
  development-only or otherwise hidden from `help`.
- The scan finds 90% of what the game lists (2,747 of 3,041). The gap is convars that mods and
  Squirrel register at runtime (for example `ares_harness_*`) and a few
  registered outside the usual initialisers (`sv_cheats`, `noclip`,
  `setpos` and `script` exist in R2 but aren't in its scan).
- Defaults match the game's value for 97.6% of convars (2,278 of 2,335) and
  help text for 99.5% (1,476 of 1,484).
- Flag bits were checked against the game's flag names (`0x4000` = CHEAT for
  289 of 290 convars).

Binaries only show what is registered. A development-only or cheat convar can
still be unusable in a given build, so confirm anything a test relies on in the
game. Northstar answers `help <name>`; R1Delta answers `find` through its
control server (a long `find` sweep made R1Delta exit, so keep queries short);
TFO runs commands from the harness's `view_commands`.

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
but the game confirmed it.

### Cameras and views

| Name | Kind | R1 | TFO | R2 | Help |
| --- | --- | --- | --- | --- | --- |
| `freecam_enable` | command | — | yes | — |  |
| `freecam_disable` | command | — | yes | — |  |
| `freecam_setpos` | command | — | yes (cheat) | — | Move freecam to the specified origin. |
| `freecam_setang` | command | — | yes (cheat) | — | Rotate freecam to the specified angles. |
| `freecam_getpos` | command | — | yes (cheat) | — |  |
| `freecam_paused` | command | — | yes | — |  |
| `freecam` | command | — | yes | — |  |
| `thirdperson` | command | yes (cheat) | yes (cheat) | yes (cheat) | Switch to thirdperson camera. |
| `thirdpersonshoulder` | command | yes | yes | yes | Switch to thirdperson-shoulder camera. |
| `firstperson` | command | yes | yes | yes | Switch to firstperson camera. |
| `camortho` | command | yes (cheat) | yes (cheat) | yes (cheat) | Switch to orthographic camera. |
| `cam_command` | command | yes (cheat) | yes (cheat) | yes (cheat) | Tells camera to change modes |
| `cam_idealdist` | convar | yes (dev-only) | yes (dev-only) | in game¹ |  |
| `getpos` | command | yes | yes | yes | dump position and angles to the console |
| `getpos_exact` | command | yes | yes | — | dump origin and angles to the console |
| `getposvec` | command | yes | yes | yes | dump position and angles to the console in 'Vector( x, y, z ), Vector( pitch, yaw, roll )' format |
| `cl_showpos` | convar | yes | yes | yes | Draw current position at top of screen |

### Clean frames and capture

| Name | Kind | R1 | TFO | R2 | Help |
| --- | --- | --- | --- | --- | --- |
| `screenshot` | command | yes | yes | yes | Take a screenshot. |
| `jpeg` | command | yes | yes | yes | Take a jpeg screenshot:  jpeg <filename> <quality 1-100>. |
| `jpeg_quality` | convar | yes | yes | yes | jpeg screenshot quality. |
| `jpeg_path` | convar | — | yes | — | jpeg screenshot path. |
| `cl_screenshotname` | convar | yes | yes | yes | Custom Screenshot name |
| `screenshot_overview` | command | — | — | yes | Take an overview screenshot. |
| `devshots_screenshot` | command | yes | yes | yes | Used by the -makedevshots system to take a screenshot. For taking your own screenshots, use the 'screenshot' c |
| `cl_drawhud` | convar | yes (cheat) | yes (dev-only) | yes (cheat) | Enable the rendering of the hud |
| `hidehud` | convar | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `r_drawvgui` | convar | yes (cheat) | yes (cheat) | yes (cheat) | Enable the rendering of vgui panels |
| `r_drawviewmodel` | convar | yes (cheat) | yes (dev-only) | yes (cheat) |  |
| `envmap` | command | yes | yes | yes |  |
| `buildcubemaps` | command | yes | yes | yes | Rebuild cubemaps. |
| `mat_envmaptgasize` | convar | yes | yes | yes | Final envmap size for "envmap" console command; should be <= 128. |
| `host_framerate` | convar | yes | yes | in game¹ | Set to lock per-frame time elapse. |

### Render isolation

| Name | Kind | R1 | TFO | R2 | Help |
| --- | --- | --- | --- | --- | --- |
| `r_drawworld` | convar | yes (cheat) | yes (cheat) | yes (cheat) | Render the world (0 = none, 1 = opaque only, 2 = trans only, 3 = both). |
| `r_drawstaticprops` | convar | yes (cheat) | yes (cheat) | yes (cheat) | Toggle drawing of static props |
| `r_drawentities` | convar | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `r_drawothermodels` | convar | yes (cheat) | yes (cheat) | yes (cheat) | Enables drawing 'other' (C_BaseAnimating) models |
| `r_drawparticles` | convar | yes (cheat) | yes (cheat) | yes (cheat) | Enable/disable particle rendering |
| `r_drawdecals` | convar | yes (cheat) | yes (cheat) | yes (cheat) | Render decals. |
| `r_drawsky` | convar | — | — | yes (cheat) | Enable the rendering of sky |
| `r_drawskybox` | convar | yes (cheat) | yes (cheat) | — |  |
| `r_drawropes` | convar | yes (cheat) | yes (cheat) | — |  |
| `r_drawclipbrushes` | convar | yes (cheat) | yes (cheat) | — | Draw clip brushes (red=NPC+player, pink=player, purple=NPC) |
| `r_drawlightcache` | convar | yes (cheat) | yes (cheat) | — | 0: off |
| `r_drawlightinfo` | convar | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `r_lightmap` | convar | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `mat_fullbright` | convar | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `mat_drawflat` | convar | yes (cheat) | yes (cheat) | yes (cheat) |  |
| `mat_luxels` | convar | yes (cheat) | yes (cheat) | — |  |
| `mat_normals` | convar | yes (cheat) | yes (cheat) | — |  |
| `mat_showmiplevels` | convar | yes (cheat) | yes (cheat) | yes (cheat) | color-code miplevels 2: normalmaps, 1: everything else |
| `csm_enabled` | convar | yes | yes | yes | Set whether to render cascading shadow maps |
| `csm_debug_2d` | convar | yes (dev-only) | yes (dev-only) | yes (dev-only) |  |
| `vcollide_wireframe` | convar | yes (cheat) | yes (cheat) | — | Render physics collision models in wireframe |

### Entities, triggers and collision

| Name | Kind | R1 | TFO | R2 | Help |
| --- | --- | --- | --- | --- | --- |
| `showtriggers` | convar | yes (cheat) | yes (cheat) | yes (cheat) | Shows trigger brushes. Must be set while loading the map |
| `showtriggers_toggle` | command | yes (cheat) | yes (cheat) | yes (cheat) | Toggle show triggers |
| `ent_text` | command | yes (cheat) | yes (cheat) | yes (cheat) | Displays text debugging information about the given entity(ies) on top of the entity (See Overlay Text) |
| `ent_bbox` | command | yes (cheat) | yes (cheat) | yes (cheat) | Displays the movement bounding box for the given entity(ies) in orange.  Some entites will also display entity |
| `ent_absbox` | command | yes (cheat) | yes (cheat) | yes (cheat) | Displays the total bounding box for the given entity(s) in green.  Some entites will also display entity speci |
| `ent_pivot` | command | yes (cheat) | yes (cheat) | yes (cheat) | Displays the pivot for the given entity(ies). |
| `ent_messages` | command | yes (cheat) | yes (cheat) | yes (cheat) | Toggles input/output message display for the selected entity(ies).  The name of the entity will be displayed a |
| `ent_fire` | convar | yes (cheat) | yes (cheat) | in game¹ | Usage: |
| `ent_create` | command | yes (cheat) | yes (cheat) | in game¹ | Creates an entity of the given type where the player is looking. |
| `ent_remove` | command | yes (cheat) | yes (cheat) | yes (cheat) | Removes the given entity(s) |
| `sv_showhitboxes` | convar | yes (cheat) | yes (cheat) | yes (cheat) | Send server-side hitboxes for specified entity to client (NOTE:  this uses lots of bandwidth, use on listen se |
| `debug_draw_box_depth_test` | convar | yes (dev-only) | yes (dev-only) | yes (dev-only) | Toggle depth test for debug draw box functionality |
| `titan_step_damage_debug` | convar | yes | yes | yes | Draw debug box of titan step damage volume |

### AI and navigation

| Name | Kind | R1 | TFO | R2 | Help |
| --- | --- | --- | --- | --- | --- |
| `ai_debug_nodes` | convar | yes | yes | yes |  |
| `ai_debug_node_connect` | command | yes | yes | yes | Debug the attempted connection between two nodes |
| `ai_debug_los` | convar | yes (cheat) | yes (cheat) | in game¹ | NPC Line-Of-Sight debug mode. If 1, solid entities that block NPC LOC will be highlighted with white bounding  |
| `ai_debug_search_paths` | convar | yes | yes | yes |  |
| `ai_show_path_search_nodes` | convar | yes (dev-only) | yes (dev-only) | yes (dev-only) |  |
| `ai_show_hull_attacks` | convar | yes | yes | yes |  |
| `ai_debug_squads` | convar | yes | yes | yes |  |
| `ai_debug_enemies` | convar | yes | yes | yes |  |
| `ai_drawbattlelines` | convar | yes (cheat) | yes (cheat) | — |  |
| `ai_debug_auto_traverse` | convar | yes (cheat) | yes (cheat) | — |  |

### Bots

| Name | Kind | R1 | TFO | R2 | Help |
| --- | --- | --- | --- | --- | --- |
| `bot_loadout` | command | yes (cheat) | yes (cheat) | yes (cheat) | Override bot loadout |
| `bot_dontmove` | convar | yes (cheat) | yes (cheat) | — |  |
| `bot_follow` | convar | yes (cheat) | yes (cheat) | — | When on, bot will follow the player. |
| `bot_mimic` | convar | yes | yes | — | Bot uses usercmd of player by index. |
| `bot_kill` | command | yes (cheat) | yes (cheat) | — | <bot id>.  Kills bot. |
| `bot_equip` | command | yes (cheat) | yes (cheat) | — | Generate an item and have the bot equip it. |
| `bot_flipout` | convar | yes | yes | — | When on, all bots fire their guns. |
| `bot_lagOut` | convar | — | — | yes | Cause bots to lag out |

### Time, state and logging

| Name | Kind | R1 | TFO | R2 | Help |
| --- | --- | --- | --- | --- | --- |
| `host_timescale` | convar | yes (cheat) | yes (cheat) | yes (cheat) | Prescale the clock by this amount. |
| `phys_timescale` | convar | yes | yes | in game¹ | Scale time for physics |
| `sv_gravity` | convar | yes | yes | yes | World gravity. |
| `sv_pausable` | convar | yes | yes | yes | Whether the server is allowed to pause |
| `pause` | command | yes | yes | yes | Toggle the server pause state. |
| `unpause` | command | yes | yes | yes | Unpause the game. |
| `map` | command | yes | yes | yes | Start playing on specified map. |
| `changelevel` | command | yes | yes | yes | Change server to the specified map |
| `mp_gamemode` | convar | yes | yes | yes | Current game mode name |
| `developer` | convar | yes | yes | yes | Set developer message level |
| `condump` | command | yes | yes | yes | dump the text currently in the console to condumpXX.log |
| `con_logfile` | convar | yes | yes | in game¹ | Console output gets written to this file |
| `find` | command | yes | yes | — | Find commands, convars, and other settings with the specified string in their name/help text. |
| `help` | command | yes (dev-only) | yes (dev-only) | yes (dev-only) | Find help about a convar/concommand. |
| `convar_findByFlags` | command | yes (dev-only) | yes (dev-only) | yes (dev-only) | Find concommands by flags. |
| `weapon_reparse` | command | yes (cheat) | yes (cheat) | yes (cheat) | Reloads the weapon script files |
| `give` | command | yes (cheat) | yes (cheat) | yes (cheat) | Give weapon to player. |

## Regenerate

```powershell
python tools/convar_scan.py reports/convars/r2.json --game C:/Games/Titanfall2
python tools/convar_scan.py reports/convars/tfo.json --game "D:/Games/Titanfall Online"
python tools/convar_scan.py reports/convars/r1.json `
    $env:LOCALAPPDATA/R1Delta/app-3.0.5/r1delta/bin/server.dll --game D:/Games/Titanfall
```

Full lists stay in the ignored `reports/` folder; this page keeps only the
entries useful for tests. Scanned 2026-11-19.
