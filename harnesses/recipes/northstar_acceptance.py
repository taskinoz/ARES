#!/usr/bin/env python3
"""Release acceptance for a Northstar map mod: what a map must pass before it is published.

For each mode (default Pilots vs Pilots and Free For All):
1. Load the map.
2. Read every spawn point from the packaged BSP's entities, and probe each for
   floor and clearance: pilot for pilot spawns, Titan for Titan spawns.
3. Respawn on both teams (team modes) and fire the weapon.

Then it plays out the rest of a session:
1. Postmatch, which must return to the lobby.
2. Load a stock map, then the mod's map again.
3. Capture a view after the reload.

It fails on any script error, failed probe, crash or timeout. This is the
procedure the Apex-to-Titanfall-2 ports used for every release (Thunderdome,
Thermal Station, Drop-Off, Overflow, Party Crasher, Firing Range; Northstar
1.31.14, November 2026).

It runs in the harness's own profile through northstar_harness.Session, so the
player's profile is untouched. It is single-client: it does not certify
multiplayer, dedicated servers or AI.

Copyright (c) 2026 taskinoz. MIT licence. From taskinoz/apex-to-titanfall-2
release_map.py and release_thunderdome.py.

  python harnesses/recipes/northstar_acceptance.py --game C:/Games/Titanfall2 \\
      --mod path/to/MyMap --map mp_name --output reports/mp_name-acceptance
"""
import argparse
import json
import re
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'harnesses' / 'adapters'))
from northstar_harness import Session  # noqa: E402

PILOT = ('info_spawnpoint_human_start', 'info_spawnpoint_human')
TITAN = ('info_spawnpoint_titan_start', 'info_spawnpoint_titan')


def spawn_points(bsp):
    """{classname: [[x, y, z]]} for pilot and Titan spawns in the BSP's entity lump (plus <map>_spawn.ent if present)."""
    with Path(bsp).open('rb') as f:
        head = f.read(16 + 16)
        offset, length = struct.unpack_from('<2I', head, 16)
        f.seek(offset)
        text = f.read(length).decode('latin-1')
    for ent in Path(bsp).parent.glob(Path(bsp).stem + '_*.ent'):
        text += ent.read_text('latin-1')
    out = {c: [] for c in PILOT + TITAN}
    for block in re.findall(r'\{([^{}]*)\}', text):
        kv = dict(re.findall(r'"([^"]*)" "([^"]*)"', block))
        if kv.get('classname') in out and 'origin' in kv:
            out[kv['classname']].append([float(v) for v in kv['origin'].split()])
    return out


def alive(s, level):
    end = time.monotonic() + 30
    while time.monotonic() < end:
        c = s.controller.state('client')
        if c.get('level') == level and c.get('alive') and c.get('health', 0) > 0:
            return c
        time.sleep(0.5)
    raise RuntimeError(f'no living player on {level}')


def accept(game, mods, map_name, output, modes=('ps', 'ffa'), stock='mp_coliseum', settle=20):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    bsp = next((m / 'mod' / 'maps' / f'{map_name}.bsp' for m in map(Path, mods)
                if (m / 'mod' / 'maps' / f'{map_name}.bsp').is_file()), None)
    if bsp is None:
        raise FileNotFoundError(f'no mod/maps/{map_name}.bsp in the given mods')
    spawns = spawn_points(bsp)
    report = dict(map=map_name, modes={}, checks=[], errors=[], screenshots=[])
    check = lambda name, ok: report['checks'].append({'name': name, 'passed': bool(ok)})
    started = time.time()
    with Session(game, output, mods=mods) as s:
        for mode in modes:
            s.load(map_name, mode)
            time.sleep(settle)
            alive(s, map_name)
            data = s.run('server', 'mode_check')['data']
            probes = {}
            for kind, classes, need in (('pilot', PILOT, 'pilot'), ('titan', TITAN, 'titan')):
                points = [p for c in classes for p in spawns[c]]
                if points:
                    results = s.run('server', 'spawn_probe', points=points, timeout=120)['data']
                    bad = [r['origin'] for r in results if not (r['floor'] and r[need])]
                    probes[kind] = dict(points=len(points), failed=bad)
                    check(f'{mode}: all {len(points)} {kind} spawns have floor and {need} clearance', not bad)
            check(f'{mode}: map has pilot spawns', sum(len(spawns[c]) for c in PILOT) > 0)
            if mode != 'ffa':
                for team in (2, 3):
                    s.run('server', 'respawn', team=team)
                    alive(s, map_name)
                check(f'{mode}: both teams respawn', True)
            s.run('ui', 'console', command='+attack')
            time.sleep(0.35)
            s.run('ui', 'console', command='-attack')
            time.sleep(1)
            alive(s, map_name)
            check(f'{mode}: weapon fire', True)
            report['modes'][mode] = dict(entities=data['entities'], probes=probes)
        s.run('ui', 'console', command='script SetGameState( eGameState.Postmatch )')
        s.wait_state('ui', lambda st: st.get('level') == 'mp_lobby' and st.get('ready'), 120, 'postmatch lobby')
        check('postmatch returns to the lobby', True)
        s.load(stock, 'ps')
        time.sleep(5)
        s.load(map_name, modes[0])
        time.sleep(settle)
        alive(s, map_name)
        check(f'reload after {stock}', True)
        shot = output / 'reload.png'
        if s.capture(shot):
            report['screenshots'].append(shot.name)
        errors = s.script_errors()
        report['errors'] += errors
        check('no script errors', not errors)
    passed = all(c['passed'] for c in report['checks']) and not report['errors']
    (output / 'report.json').write_text(json.dumps(report, indent=2))
    result = {'schema_version': '1.0', 'tool': 'northstar_acceptance', 'target': 'r2',
              'operation': f'map-acceptance:{map_name}:{"+".join(modes)}',
              'status': 'success' if passed else 'failure', 'verification': 'runtime',
              'duration_ms': int((time.time() - started) * 1000),
              'artifacts': [{'path': n, 'type': 'screenshot'} for n in report['screenshots']] +
                           [{'path': 'report.json', 'type': 'report'}, {'path': 'nslog.txt', 'type': 'log'}],
              'checks': report['checks'], 'errors': report['errors']}
    (output / 'result.json').write_text(json.dumps(result, indent=2))
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--game', default=None, help='Titanfall 2 folder with NorthstarLauncher.exe (default $ARES_R2_GAME)')
    p.add_argument('--mod', action='append', required=True, help='mod folder to install (repeatable; the map mod first)')
    p.add_argument('--map', required=True)
    p.add_argument('--modes', nargs='+', default=['ps', 'ffa'])
    p.add_argument('--stock-map', default='mp_coliseum')
    p.add_argument('--settle', type=float, default=20)
    p.add_argument('--output', required=True)
    a = p.parse_args(argv)
    import os
    game = a.game or os.environ.get('ARES_R2_GAME')
    if not game:
        p.error('--game or ARES_R2_GAME is required')
    try:
        result = accept(game, a.mod, a.map, a.output, tuple(a.modes), a.stock_map, a.settle)
    except Exception as e:  # report the failure as a result, then exit non-zero
        Path(a.output).mkdir(parents=True, exist_ok=True)
        result = {'schema_version': '1.0', 'tool': 'northstar_acceptance', 'target': 'r2',
                  'operation': f'map-acceptance:{a.map}', 'status': 'failure', 'verification': 'runtime',
                  'duration_ms': 0, 'artifacts': [], 'checks': [], 'errors': [f'{type(e).__name__}: {e}']}
        (Path(a.output) / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'errors': result['errors']}, indent=2))
    return 0 if result['status'] == 'success' else 1


if __name__ == '__main__':
    sys.exit(main())
