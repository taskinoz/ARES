#!/usr/bin/env python3
"""Weld a Titanfall 2 map's triangle collision so each header stores each position once (stdlib only).

Generated triangle collision often writes three fresh positions per triangle.
Respawn's mp_homestead stores 432,219 positions for 662,080 triangles (0.65 per
triangle); a converted map that wrote three per triangle stored 19.96M, and
welding cut them to 5.76M and the BSP by 170 MB.

Format (TRICOLL_HEADERS 0x45 `<6h4i4f`: [3] vertex count, [4] triangle count,
[6] first position, [7] first triangle word): each triangle word (0x42) holds
its first vertex as a 10-bit index from the header's first position and the
other two as 7-bit forward deltas; bits 28-29 name the lowest-Z vertex and bit
30 which of the other two is highest. So positions can be shared inside a
header as long as each triangle's indices span at most 127.

Each header is welded on exact float32 equality, in first-use order. If that
leaves a triangle spanning more than 127, the header is welded again, emitting
a position again once its last copy is more than 125 back. Triangles are
rotated (keeping winding) to put their lowest index first, and their Z bits are
recomputed. A header whose words don't follow that bit rule keeps its
positions. Lump 0x3 is rebuilt as the positions the render vertices
(0x47-0x4B) use, in their old order, then the welded collision positions;
render vertices are re-pointed and unused positions dropped. Every triangle and
render vertex is decoded again and compared with the original before writing.

Copyright (c) 2026 taskinoz. MIT licence. From taskinoz/apex-to-titanfall-2
weld_collision_vertices.py (numpy there; pure Python here).

  python tools/weld_tricoll.py MAP.bsp [--output OUT.bsp]   (default: in place)
"""
import argparse
import json
import struct
import sys
from array import array
from pathlib import Path

from bsp_edit import read_lumps, replace_in_place, replace_lumps

HEADER = struct.Struct('<6h4i4f')
STRIDE = {0x47: 20, 0x48: 36, 0x49: 44, 0x4A: 28, 0x4B: 92}  # render vertex lumps; position index first
SPAN = 127
OPTIONS = ((1, 2), (0, 2), (1, 0))  # the other pair, for each lowest-Z vertex


def decode(word):
    i0 = word & 1023
    return i0, i0 + (word >> 10 & 127), i0 + (word >> 17 & 127)


def z_bits(zs):
    """Bits 28-30 of a triangle word for vertex heights zs (first lowest and highest win ties)."""
    low = min(range(3), key=lambda k: zs[k])
    high = max(range(3), key=lambda k: zs[k])
    pick = 1 if high == OPTIONS[low][1] and low != high else 0
    return (low | pick << 2) << 28


def weld_header(keys):
    """keys: 3n position byte strings. Returns (positions to keep, per-triangle local index triples)."""
    # Plain first-use sharing, when every triangle's indices then span at most SPAN ...
    slots, keep = {}, []
    for k in keys:
        if k not in slots:
            slots[k] = len(keep)
            keep.append(k)
    local = [[slots[k] for k in keys[3 * t:3 * t + 3]] for t in range(len(keys) // 3)]
    if all(max(tri) - min(tri) <= SPAN for tri in local):
        return keep, local
    # ... otherwise emit a position again once its last copy is too far back.
    slots, keep, local = {}, [], []
    for t in range(len(keys) // 3):
        tri = []
        for k in keys[3 * t:3 * t + 3]:
            i = slots.get(k)
            if i is None or len(keep) - i > SPAN - 2:  # leaves room for two new positions after it
                i = slots[k] = len(keep)
                keep.append(k)
            tri.append(i)
        local.append(tri)
    return keep, local


def weld(lumps):
    """Replacement lumps and a report, from {3, 0x42, 0x45, 0x47..0x4B: bytes}."""
    pos = lumps[3]
    count = len(pos) // 12
    key = lambda i: pos[12 * i:12 * i + 12]
    words = array('I', lumps[0x42])
    used = bytearray(count)
    render = {}
    for lump, stride in STRIDE.items():
        data = lumps.get(lump, b'')
        if len(data) % stride:
            raise ValueError(f'lump {lump:#x} is not whole {stride}-byte records')
        render[lump] = [struct.unpack_from('<I', data, at)[0] for at in range(0, len(data), stride)]
        for i in render[lump]:
            used[i] = 1
    remap = array('I', bytes(4 * count))
    out = bytearray()
    for i in range(count):
        if used[i]:
            remap[i] = len(out) // 12
            out += key(i)
    render_positions = len(out) // 12
    headers = bytearray(lumps[0x45])
    unwelded = before = 0
    for at in range(0, len(headers), HEADER.size):
        h = list(HEADER.unpack_from(headers, at))
        tris, base, first = h[4], h[6], h[7]
        before += h[3]
        idx = [decode(words[first + t]) for t in range(tris)]
        keys = [key(base + v) for tri in idx for v in tri]
        zs = [[struct.unpack_from('<f', k, 8)[0] for k in keys[3 * t:3 * t + 3]] for t in range(tris)]
        if any(words[first + t] & 0x8F000000 or words[first + t] & 0x70000000 != z_bits(zs[t]) for t in range(tris)):
            h[6] = len(out) // 12
            out += pos[12 * base:12 * (base + h[3])]
            unwelded += 1
        else:
            keep, local = weld_header(keys)
            for t, tri in enumerate(local):
                r = tri.index(min(tri))  # rotate, keeping winding, so the lowest index is first
                tri = tri[r:] + tri[:r]
                z = zs[t][r:] + zs[t][:r]
                words[first + t] = tri[0] | (tri[1] - tri[0]) << 10 | (tri[2] - tri[0]) << 17 | z_bits(z)
            h[3], h[6] = len(keep), len(out) // 12
            out += b''.join(keep)
        HEADER.pack_into(headers, at, *h)
    # Decode everything again from the new lumps.
    for at in range(0, len(headers), HEADER.size):
        old, new = HEADER.unpack_from(lumps[0x45], at), HEADER.unpack_from(headers, at)
        old_words = array('I', lumps[0x42][4 * old[7]:4 * (old[7] + old[4])])
        for t in range(old[4]):
            a = [pos[12 * (old[6] + v):12 * (old[6] + v) + 12] for v in decode(old_words[t])]
            n = decode(words[new[7] + t])
            if max(n) >= new[3]:
                raise AssertionError(f'header {at // HEADER.size}: index outside its positions')
            b = [bytes(out[12 * (new[6] + v):12 * (new[6] + v) + 12]) for v in n]
            if b not in (a, a[1:] + a[:1], a[2:] + a[:2]):  # the same triangle, same winding
                raise AssertionError(f'header {at // HEADER.size} triangle {t} changed')
    changes = {3: bytes(out), 0x42: words.tobytes(), 0x45: bytes(headers)}
    for lump, stride in STRIDE.items():
        data = bytearray(lumps.get(lump, b''))
        for n, at in enumerate(range(0, len(data), stride)):
            struct.pack_into('<I', data, at, remap[render[lump][n]])
            if out[12 * remap[render[lump][n]]:12 * remap[render[lump][n]] + 12] != key(render[lump][n]):
                raise AssertionError(f'render vertex lump {lump:#x} moved')
        if data:
            changes[lump] = bytes(data)
    report = dict(positions_before=count, positions_after=len(out) // 12, render_positions=render_positions,
                  collision_positions_before=before, collision_positions_after=len(out) // 12 - render_positions,
                  headers=len(headers) // HEADER.size, unwelded_headers=unwelded, bytes_saved=len(pos) - len(out))
    return changes, report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('bsp')
    p.add_argument('--output', help='write here instead of replacing the input')
    a = p.parse_args(argv)
    lumps = read_lumps(a.bsp, (3, 0x42, 0x45, *STRIDE))
    changes, report = weld(lumps)
    if a.output:
        replace_lumps(a.bsp, a.output, changes)
    else:
        replace_in_place(a.bsp, changes, '.weld')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
