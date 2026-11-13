#!/usr/bin/env python3
"""Weld a Titanfall 2 map's sun-shadow (CSM) meshes so each opaque mesh stores each position once (stdlib only).

Shadow meshes are a separate copy of the world the sun's cascaded shadows draw.
Map builds often write three positions per triangle: converted maps stored
2.66-2.96M shadow positions where mp_homestead stores 86,042 for 384,819
indices. Welding cut them to 0.61-0.71M, 24-28 MB per map, and lets the GPU
reuse shaded vertices in the shadow passes.

Format: SHADOW_MESHES (0x7F) `<2I2h` is first position, triangle count, opaque
and material sort. Indices (0x7E, uint16) follow the previous meshes' and are
local to the first position: opaque meshes index 0x7C (12-byte positions),
alpha meshes (opaque 0) index 0x7D and are left alone. Shadow environments
(0x05) address meshes by number, which doesn't change. The index lump keeps its
length, triangle order and winding; every mesh is decoded again and compared
before writing.

Copyright (c) 2026 taskinoz. MIT licence. From taskinoz/apex-to-titanfall-2
weld_shadow_meshes.py (numpy there; pure Python here).

  python tools/weld_shadow_meshes.py MAP.bsp [--output OUT.bsp]   (default: in place)
"""
import argparse
import json
import struct
import sys
from array import array

from bsp_edit import read_lumps, replace_in_place, replace_lumps

MESH = struct.Struct('<2I2h')


def weld(lumps):
    """Replacement lumps 0x7C, 0x7E, 0x7F and a report."""
    pos, idx = lumps[0x7C], array('H', lumps[0x7E])
    meshes = [list(m) for m in MESH.iter_unpack(lumps[0x7F])]
    out, at = bytearray(), 0
    for m in meshes:
        first, count, opaque = m[:3]
        if opaque:
            slots = {}
            base = len(out) // 12
            for k in range(at, at + 3 * count):
                key = pos[12 * (first + idx[k]):12 * (first + idx[k]) + 12]
                local = slots.get(key)
                if local is None:
                    local = slots[key] = len(slots)
                    out += key
                idx[k] = local
            if len(slots) > 65536:
                raise ValueError('a welded shadow mesh needs more than 65,536 positions')
            m[0] = base
        at += 3 * count
    if at != len(idx):
        raise ValueError('shadow mesh triangles do not cover the index lump')
    old_idx = array('H', lumps[0x7E])
    at = 0
    for old, m in zip(MESH.iter_unpack(lumps[0x7F]), meshes):
        if m[2]:
            for k in range(at, at + 3 * m[1]):
                if pos[12 * (old[0] + old_idx[k]):12 * (old[0] + old_idx[k]) + 12] != \
                        out[12 * (m[0] + idx[k]):12 * (m[0] + idx[k]) + 12]:
                    raise AssertionError('a shadow mesh does not decode to its triangles')
        at += 3 * m[1]
    changes = {0x7C: bytes(out), 0x7E: idx.tobytes(), 0x7F: b''.join(MESH.pack(*m) for m in meshes)}
    return changes, dict(shadow_meshes=len(meshes), positions_before=len(pos) // 12, positions_after=len(out) // 12,
                         indices=len(idx), bytes_saved=len(pos) - len(out))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('bsp')
    p.add_argument('--output', help='write here instead of replacing the input')
    a = p.parse_args(argv)
    changes, report = weld(read_lumps(a.bsp, (0x7C, 0x7E, 0x7F)))
    if a.output:
        replace_lumps(a.bsp, a.output, changes)
    else:
        replace_in_place(a.bsp, changes, '.shadow')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
