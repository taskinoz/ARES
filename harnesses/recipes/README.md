# Harness recipes

Multi-step game tests built on the [adapters](../adapters). A recipe runs a
whole procedure in one isolated harness session and writes `report.json` and
`result.json` in the [result contract](../contracts/result.schema.json), like
the adapters do. Like them, recipes stage only owned files and restore the
profile afterwards.

| Recipe | Target | Does |
| --- | --- | --- |
| `northstar_acceptance.py` | R2 / Northstar | Release acceptance for a map mod. In each mode: every pilot and Titan spawn gets a floor and clearance probe, both teams respawn and the weapon fires. Then postmatch must reach the lobby, and the map must reload after a stock map, with clean logs |
| `northstar_cubemaps.py` | R2 / Northstar | Captures six HUD-free views at each cubemap origin from `tools/cubemaps.py plan`, ready for `tools/cubemaps.py write` |

```powershell
python harnesses/recipes/northstar_acceptance.py --game C:/Games/Titanfall2 `
    --mod path/to/MyMap --mod path/to/SharedUI --map mp_name --output reports/acceptance
```

`--mod` takes the map mod and any mod it depends on (a shared UI pack, for
example). The acceptance recipe is single-client: it does not certify
multiplayer, dedicated servers or AI. Skills: `accept-northstar-map`,
`add-tf2-cubemaps`.

`test_recipes.py` covers the offline parts; the game runs are listed in each
recipe's docstring and in its registry entry.
