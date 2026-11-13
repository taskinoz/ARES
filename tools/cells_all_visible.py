#!/usr/bin/env python3
"""Send every point of a Titanfall 2 map to its all-visible cell, so its cells cull nothing (stdlib only).

Titanfall 2 culls entities by cell as well as world objects. A map split into
cells with no portals between them hides every entity outside the camera's
cell: on a converted Thermal Station, ropes (move_rope/keyframe_rope) in another
cell were not drawn, and this change brought them back. Players are entities
too. Retail maps connect their cells with portals; a map whose cells have none
should keep one all-visible cell until portals are written.

Only the cell BSP (0x6A) changes. It becomes one leaf that points at the last
cell, which in the layout tools/portals.py reads is the all-visible cell whose
access tree holds every object. Check that with `inspect` first.

Copyright (c) 2026 taskinoz. MIT licence. From taskinoz/apex-to-titanfall-2
disable_visibility_cells.py.

  python tools/cells_all_visible.py inspect MAP.bsp
  python tools/cells_all_visible.py apply MAP.bsp [--cell N] [--output OUT.bsp]
"""
import argparse
import json
import struct
import sys

from bsp_edit import read_lumps, replace_in_place, replace_lumps

NODE = struct.Struct('<3f2BH3f2H')


def inspect(path):
    l = read_lumps(path, (0x6A, 0x6B, 0x6C, 0x77, 0x78))
    cells = len(l[0x6B]) // 8
    roots = [NODE.unpack_from(l[0x77], NODE.size * c) for c in range(min(cells, len(l[0x77]) // NODE.size))]
    return dict(cells=cells, cell_bsp_nodes=len(l[0x6A]) // 8, portals=len(l[0x6C]) // 12,
                object_references=len(l[0x78]) // 2,
                subtree_references_per_cell=[r[5] for r in roots],
                split_without_portals=cells > 1 and not l[0x6C] and len(l[0x6A]) > 8)


def apply(path, cell=None):
    info = inspect(path)
    cell = info['cells'] - 1 if cell is None else cell
    if not 0 <= cell < info['cells']:
        raise ValueError('cell out of range')
    if info['subtree_references_per_cell'][cell] != max(info['subtree_references_per_cell']):
        raise ValueError(f'cell {cell} does not reference the most objects; pass the all-visible cell with --cell')
    return {0x6A: struct.pack('<iI', -1, cell)}, dict(info, every_point_in_cell=cell)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    i = sub.add_parser('inspect')
    i.add_argument('bsp')
    ap = sub.add_parser('apply')
    ap.add_argument('bsp')
    ap.add_argument('--cell', type=int)
    ap.add_argument('--output')
    a = p.parse_args(argv)
    if a.command == 'inspect':
        print(json.dumps(inspect(a.bsp), indent=2))
        return 0
    changes, report = apply(a.bsp, a.cell)
    if a.output:
        replace_lumps(a.bsp, a.output, changes)
    else:
        replace_in_place(a.bsp, changes, '.cells')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
