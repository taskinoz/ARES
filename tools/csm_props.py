#!/usr/bin/env python3
"""Inspect a Titanfall 2 map's cascaded-shadow (CSM) object tree, or list its static props in it (stdlib only).

Map builds commonly write an empty CSM tree: 0x63 holds one inverted root per
shadow environment and 0x64 is empty, so static props never cast real-time sun
shadows. They only shadow the baked lightmaps, not players, and not each other
near the camera. Retail lists them: mp_homestead's gameplay environment has
5,162 nodes over 6,833 of its 16,146 props, with at most 24 direct references
per node.

Layout (MRVN-Radiant docs/respawn/RESPAWN_TF2_LUMPS.md, checked on Homestead):
- **Nodes (0x63):** the cell AABB node layout `<3f2BH3f2H`, with mins, child
  count, direct refs, subtree refs, maxs, first child and first ref. Boxes are
  in light space: z = -sun, x = normalize(sun.y, -sun.x, 0), y = z x x, where
  sun is the shadow environment's normal.
- **Check:** 6,809 of Homestead's 6,833 referenced prop origins lie inside
  their node's box with that basis, against 5 with the sun negated.
- **References (0x64):** uint16 object ids in the OBJ_REFERENCES namespace.
  Static prop k is (LEVEL_INFO first sky mesh + 63 & ~63) + k.
- **Ownership:** a shadow environment (0x05 `<6i3f`) owns nodes and references
  [first, last).

`add` builds a binary tree for environment 0 from each chosen prop's model
bounds, read from `.mdl` files (--models), a JSON map (--bounds), or a sphere
of --default-radius. Props whose model matches --exclude (grass and ground
cover by default) or whose world radius is under --min-radius are left out.

Copyright (c) 2026 taskinoz. MIT licence. From taskinoz/apex-to-titanfall-2
add_csm_props.py. Verified in game on Thunderdome (3,344 casters): the skull and
rocks shade themselves on the side away from the sun.

  python tools/csm_props.py inspect MAP.bsp
  python tools/csm_props.py add MAP.bsp --models MOD/mod [--output OUT.bsp]
"""
import argparse
import json
import math
import re
import struct
import sys
from pathlib import Path

from bsp_edit import read_lumps, replace_in_place, replace_lumps
from game_lump import inspect_game_lump

NODE = struct.Struct('<3f2BH3f2H')
ENV = struct.Struct('<6i3f')
LEAF = 16
EXCLUDE = r'grass|flower|clump|fern|weed|moss|ivy|ground_?cover|pebble'


def light_basis(sun):
    z = [-v for v in sun]
    x = [sun[1], -sun[0], 0.0]
    n = math.hypot(*x) or 1.0
    x = [v / n for v in x]
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    return x, y, z


def angle_matrix(pitch, yaw, roll):
    """Source AngleMatrix: columns forward, left, up."""
    sp, cp = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))
    sy, cy = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
    sr, cr = math.sin(math.radians(roll)), math.cos(math.radians(roll))
    return ((cp * cy, sr * sp * cy - cr * sy, cr * sp * cy + sr * sy),
            (cp * sy, sr * sp * sy + cr * cy, cr * sp * sy - sr * cy),
            (-sp, sr * cp, cr * cp))


def model_bounds(models_dir):
    """{model path as stored in sprp (lower case): (mins, maxs)} from .mdl view bounds."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ares.r2.mdl53 import HDR_FIELDS, unpack_fields
    out = {}
    root = Path(models_dir)
    for mdl in root.rglob('*.mdl'):
        hdr, _ = unpack_fields(HDR_FIELDS, mdl.read_bytes()[:0x2CC], 0)
        lo, hi = hdr['view_bbmin'], hdr['view_bbmax']
        if all(a == 0 for a in lo + hi):
            lo, hi = hdr['hull_min'], hdr['hull_max']
        out[mdl.relative_to(root).as_posix().lower()] = (lo, hi)
    return out


def tree(boxes, ids):
    """Median-split binary tree; each subtree's references are contiguous."""
    nodes, refs = [None], []

    def emit(index, members):
        lo = [min(boxes[m][0][k] for m in members) for k in range(3)]
        hi = [max(boxes[m][1][k] for m in members) for k in range(3)]
        first = len(refs)
        if len(members) <= LEAF:
            refs.extend(ids[m] for m in members)
            nodes[index] = NODE.pack(*lo, 0, len(members), len(members), *hi, 0, first)
            return
        centre = {m: [(boxes[m][0][k] + boxes[m][1][k]) / 2 for k in range(3)] for m in members}
        axis = max(range(3), key=lambda k: max(c[k] for c in centre.values()) - min(c[k] for c in centre.values()))
        members = sorted(members, key=lambda m: centre[m][axis])
        left = len(nodes)
        nodes.extend([None, None])
        nodes[index] = NODE.pack(*lo, 2, 0, len(members), *hi, left, first)
        mid = len(members) // 2
        emit(left, members[:mid])
        emit(left + 1, members[mid:])
    emit(0, list(range(len(ids))))
    return nodes, refs


def inspect(path):
    l = read_lumps(path, (5, 0x63, 0x64, 0x7B))
    envs = [ENV.unpack_from(l[5], i) for i in range(0, len(l[5]), ENV.size)]
    first_sky = struct.unpack_from('<4I', l[0x7B])[2]
    return dict(environments=[dict(nodes=[e[0], e[3]], references=[e[1], e[4]], shadow_meshes=[e[2], e[5]],
                                   sun=[round(v, 4) for v in e[6:]]) for e in envs],
                nodes=len(l[0x63]) // NODE.size, references=len(l[0x64]) // 2,
                prop_object_base=(first_sky + 63) & ~63)


def add(path, bounds, default_radius, exclude, min_radius):
    l = read_lumps(path, (5, 0x63, 0x64, 0x7B))
    envs = [list(ENV.unpack_from(l[5], i)) for i in range(0, len(l[5]), ENV.size)]
    if l[0x64] or any(e[3] - e[0] != 1 for e in envs) or len(l[0x63]) != NODE.size * len(envs):
        raise ValueError('expected one empty CSM root per shadow environment (this map already lists objects)')
    sprp = next((e for e in inspect_game_lump(path, include_props=True)['entries'] if e.get('placements') is not None), None)
    if sprp is None:
        raise ValueError('no sprp v13 static props')
    base = (struct.unpack_from('<4I', l[0x7B])[2] + 63) & ~63
    if base + sprp['placement_count'] > 65536:
        raise ValueError('static prop object ids exceed uint16')
    basis = light_basis(envs[0][6:])
    pattern = re.compile(exclude, re.I)
    boxes, ids, skipped = [], [], dict(excluded=0, small=0, default_bounds=0)
    for p in sprp['placements']:
        name = p['model'].replace('\\', '/').lower()
        if pattern.search(name):
            skipped['excluded'] += 1
            continue
        key = name[len('models/'):] if name.startswith('models/') else name
        lo, hi = bounds.get(name) or bounds.get(key) or (None, None)
        if lo is None:
            skipped['default_bounds'] += 1
            lo, hi = [-default_radius] * 3, [default_radius] * 3
        corners = [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
        if max(math.sqrt(sum(v * v for v in c)) for c in corners) * p['scale'] < min_radius:
            skipped['small'] += 1
            continue
        m = angle_matrix(*p['angles_raw'])
        world = [[sum(m[r][k] * c[k] for k in range(3)) * p['scale'] + p['origin'][r] for r in range(3)] for c in corners]
        light = [[sum(axis[k] * w[k] for k in range(3)) for axis in basis] for w in world]
        boxes.append(([min(v[k] for v in light) - 1 for k in range(3)], [max(v[k] for v in light) + 1 for k in range(3)]))
        ids.append(base + p['index'])
    if not ids:
        raise ValueError('no props chosen')
    nodes, refs = tree(boxes, ids)
    empty = [l[0x63][NODE.size * i:NODE.size * (i + 1)] for i in range(1, len(envs))]
    envs[0][0], envs[0][1], envs[0][3], envs[0][4] = 0, 0, len(nodes), len(refs)
    for i, e in enumerate(envs[1:]):
        e[0], e[1], e[3], e[4] = len(nodes) + i, len(refs), len(nodes) + i + 1, len(refs)
    changes = {0x63: b''.join(nodes + empty), 0x64: struct.pack(f'<{len(refs)}H', *refs),
               5: b''.join(ENV.pack(*e) for e in envs)}
    return changes, dict(casters=len(refs), nodes=len(nodes), skipped=skipped, sun=envs[0][6:], prop_object_base=base)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    i = sub.add_parser('inspect')
    i.add_argument('bsp')
    a_ = sub.add_parser('add')
    a_.add_argument('bsp')
    a_.add_argument('--models', help='folder holding the props\' .mdl files as models/... (a mod\'s mod/ folder)')
    a_.add_argument('--bounds', help='JSON {model path: [[minx,miny,minz],[maxx,maxy,maxz]]}, model space')
    a_.add_argument('--default-radius', type=float, default=64.0, help='bounds for models with none (default 64)')
    a_.add_argument('--exclude', default=EXCLUDE, help=f'model regex left out (default {EXCLUDE!r})')
    a_.add_argument('--min-radius', type=float, default=48.0, help='skip props smaller than this (default 48)')
    a_.add_argument('--output', help='write here instead of replacing the input')
    a = p.parse_args(argv)
    if a.command == 'inspect':
        print(json.dumps(inspect(a.bsp), indent=2))
        return 0
    bounds = {}
    if a.models:
        root = Path(a.models)
        bounds.update({('models/' + k if not k.startswith('models/') else k): v
                       for k, v in model_bounds(root / 'models' if (root / 'models').is_dir() else root).items()})
    if a.bounds:
        bounds.update({k.lower(): v for k, v in json.loads(Path(a.bounds).read_text()).items()})
    changes, report = add(a.bsp, bounds, a.default_radius, a.exclude, a.min_radius)
    if a.output:
        replace_lumps(a.bsp, a.output, changes)
    else:
        replace_in_place(a.bsp, changes, '.csm')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
