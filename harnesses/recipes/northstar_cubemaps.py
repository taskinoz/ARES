#!/usr/bin/env python3
"""Capture the six cubemap views at each planned origin of a Northstar map, for tools/cubemaps.py write.

Input is `tools/cubemaps.py plan` output. In-between origins marked floor_snap
are dropped onto the first surface below them (a server trace from 512 above)
plus 72 units. For each origin the camera looks along +X, +Y, -X, -Y, up and
down at fov 106.26, which is 90 degrees vertically at 16:9 because Titanfall's
fov is the 4:3 horizontal angle. The player is held there for streaming.

The HUD is RUI, which camera mode doesn't hide, so `rui_drawEnable 0` is set
for the captures and restored afterwards. The output is the plan with each
origin's final position and screenshot paths, ready for `cubemaps.py write`.

Copyright (c) 2026 taskinoz. MIT licence. From taskinoz/apex-to-titanfall-2
build_cubemaps.py. Verified on Northstar 1.31.14 for six maps (5-7 cubemaps, 42
views each run).

  python harnesses/recipes/northstar_cubemaps.py --game C:/Games/Titanfall2 --mod path/to/MyMap \\
      --map mp_name --plan cubemaps.json --output reports/mp_name-cubemaps
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'harnesses' / 'adapters'))
from northstar_harness import Session  # noqa: E402

VIEWS = {'px': (0, 0), 'py': (0, 90), 'nx': (0, 180), 'ny': (0, 270), 'pz': (-90, 0), 'nz': (90, 0)}
FOV = 106.26
EYE = 72.0


def capture(game, mods, map_name, plan, output, mode='tdm', settle=20, maps=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    plan = json.loads(Path(plan).read_text()) if not isinstance(plan, dict) else plan
    with Session(game, output, mods=mods, maps=maps, map_name=map_name if maps else None) as s:
        s.load(map_name, mode)
        time.sleep(settle)
        s.run('ui', 'console', command='rui_drawEnable 0')
        try:
            for i, o in enumerate(plan['origins']):
                x, y, z = o['origin']
                if o.get('floor_snap'):
                    hit = s.run('server', 'trace', px=float(x), py=float(y), pz=float(z + 512),
                                ex=float(x), ey=float(y), ez=float(z - 2048))['data']
                    if hit['fraction'] < 1 and not hit['startSolid']:
                        z = hit['end'][2] + EYE
                o['origin'] = [x, y, round(z, 1)]
                o['shots'] = {}
                for name, (pitch, yaw) in VIEWS.items():
                    pose = dict(px=float(x), py=float(y), pz=float(z), pitch=float(pitch), yaw=float(yaw), roll=0.0)
                    s.run('ui', 'clear_ui')
                    s.run('server', 'camera_follow', **dict(pose, pz=float(z) - 64))
                    s.run('client', 'camera', fov=FOV, **pose)
                    time.sleep(3 if name == 'px' else 1.5)
                    path = output / f'cubemap{i}-{name}.png'
                    if not s.capture(path):
                        raise RuntimeError(f'capture failed: {path.name}')
                    o['shots'][name] = str(path)
        finally:
            s.run('ui', 'console', command='rui_drawEnable 1')
        errors = s.script_errors()
    if errors:
        raise RuntimeError('script errors during capture: ' + errors[0])
    (output / 'cubemaps.json').write_text(json.dumps(plan, indent=2))
    return plan


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--game', default=os.environ.get('ARES_R2_GAME'))
    p.add_argument('--mod', action='append', default=[], help='mod folder to install (repeatable)')
    p.add_argument('--maps', help='a loose build folder with <map>.bsp instead of a mod')
    p.add_argument('--map', required=True)
    p.add_argument('--mode', default='tdm')
    p.add_argument('--plan', required=True, help='tools/cubemaps.py plan output')
    p.add_argument('--settle', type=float, default=20)
    p.add_argument('--output', required=True)
    a = p.parse_args(argv)
    if not a.game:
        p.error('--game or ARES_R2_GAME is required')
    plan = capture(a.game, a.mod, a.map, a.plan, a.output, a.mode, a.settle, a.maps)
    print(json.dumps({'cubemaps': len(plan['origins']), 'config': str(Path(a.output) / 'cubemaps.json')}, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
