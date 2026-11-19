---
name: accept-northstar-map
description: Run release acceptance on a Titanfall 2 / Northstar map mod in the game. Probes every spawn in Pilots vs Pilots and Free For All, respawns both teams, fires a weapon, goes through postmatch to the lobby and reloads after a stock map, with clean logs. Use before publishing or installing a new map version.
---

# Accept a Northstar map for release

Requirements:
- Titanfall 2 with Northstar (`--game` or `$ARES_R2_GAME`).
- A visible desktop.
- The packaged map mod, with `mod/maps/<map>.bsp`.

The recipe runs in the harness's own profile and never touches the player's
mods.

## Procedure

1. **Check the map statically.** Use the `inspect-bsp` and
   `optimise-tf2-map` skills.
2. **Run the recipe.**

   ```powershell
   python harnesses/recipes/northstar_acceptance.py --mod MAP_MOD --mod SHARED_UI_MOD `
       --map mp_name --output reports/mp_name-acceptance
   ```

   - **Dependencies:** include every mod the map needs (a shared UI or atlas
     pack). A missing dependency shows up as a load timeout or a script error.
   - **Modes:** `--modes` sets them (default `ps ffa`). Use only modes the map
     supports; CTF needs flag entities.
3. **Read `result.json`.** `status: success` means every check passed:
   - all pilot spawns have floor and pilot clearance, and all Titan spawns
     have Titan clearance;
   - both teams respawned and the weapon fired;
   - postmatch reached `mp_lobby`;
   - the map reloaded after a stock map;
   - no script errors;
   - no crash dumps (any `crash/nsdump*.dmp` written during the run fails it).

   `report.json` lists failed spawn origins. Look at `reload.png`.
4. **If a load times out,** retry once. Under heavy CPU or disk load a load
   can exceed the harness timeout. Check the cause in `nslog.txt` before
   calling the map broken.

## Reporting

Report it as `runtime` verification, single client. It does not certify
multiplayer, dedicated servers, AI or modes it didn't run. Publishing:
`publish-thunderstore`.
