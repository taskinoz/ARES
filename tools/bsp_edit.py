#!/usr/bin/env python3
"""Read lumps from, and replace lumps in, a Titanfall 1/2 BSP of any size (stdlib only).

The other writers in this folder hold the whole map in memory and stop at 256 MiB.
Converted maps are often several times larger, so this streams: every lump is
copied in index order to a 16-byte aligned offset, replaced lumps take their new
bytes, and the GAME_LUMP (35) directory's absolute offsets are moved with it.
Lumps nothing references are not dropped, so the output is the input with the
replacements and no other change. Maps with external .bsp_lump files or encoded
(FourCC) lumps are refused.

Copyright (c) 2026 taskinoz. MIT licence (see LICENSE). From
taskinoz/apex-to-titanfall-2 compact_preview_bsp.py, where it rewrote 600-930 MB
Titanfall 2 maps.

  python tools/bsp_edit.py lumps MAP.bsp                   lump table as JSON
  python tools/bsp_edit.py copy MAP.bsp OUT.bsp --replace 0x7C=positions.bin
"""
import argparse
import json
import os
import struct
import sys
from pathlib import Path

from inspect_bsp import FormatError, HEADER_SIZE

GAME_LUMP = 35
VERSIONS = (29, 37)
CHUNK = 1 << 24


def header(path):
    """(raw header bytes, [(offset, length, version, fourcc)] for the 128 lumps)."""
    with Path(path).open('rb') as stream:
        raw = stream.read(HEADER_SIZE)
    if len(raw) != HEADER_SIZE or raw[:4] != b'rBSP':
        raise FormatError('not a little-endian rBSP file')
    version = struct.unpack_from('<I', raw, 4)[0]
    if version not in VERSIONS:
        raise FormatError(f'BSP version {version} is not supported (29 or 37)')
    return raw, [struct.unpack_from('<4I', raw, 16 + 16 * i) for i in range(128)]


def check_plain(path, entries):
    path = Path(path)
    if any(path.with_name(f'{path.name}.{i:04x}.bsp_lump').exists() or
           path.with_name(f'{path.name}.{i:04X}.bsp_lump').exists() for i in range(128)):
        raise FormatError('maps with external .bsp_lump files are not supported')
    if any(e[3] and e[1] for e in entries):
        raise FormatError('encoded (FourCC) lumps are not supported')


def read_lumps(path, ids):
    """{index: bytes} for the requested lumps."""
    _, entries = header(path)
    check_plain(path, entries)
    out = {}
    with Path(path).open('rb') as stream:
        for i in ids:
            offset, length = entries[i][:2]
            stream.seek(offset)
            out[i] = stream.read(length)
            if len(out[i]) != length:
                raise FormatError(f'lump {i} extends past the end of the file')
    return out


def relocate_game_lump(data, old_base, new_base):
    """GAME_LUMP bytes whose directory offsets are moved from old_base to new_base."""
    if not data:
        return data
    data = bytearray(data)
    count = struct.unpack_from('<I', data, 0)[0]
    if 4 + 16 * count > len(data):
        raise FormatError('GAME_LUMP directory exceeds the lump')
    for k in range(count):
        at = 4 + 16 * k + 8
        offset = struct.unpack_from('<I', data, at)[0]
        if offset:
            struct.pack_into('<I', data, at, offset - old_base + new_base)
    return bytes(data)


def replace_lumps(source, output, changes):
    """Write output: source with `changes` ({index: bytes}) replacing those lumps. Returns the new lump table."""
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError('write to a new file, then replace the source')
    if GAME_LUMP in changes:
        raise ValueError('replacing GAME_LUMP is not supported here; edit its placements in place instead')
    raw, entries = header(source)
    check_plain(source, entries)
    head = bytearray(raw)
    with source.open('rb') as inp, output.open('xb') as out:
        out.write(head)
        for i, (offset, length, version, fourcc) in enumerate(entries):
            out.write(bytes(-out.tell() % 16))
            start = out.tell()
            if i in changes:
                payload = changes[i]
                out.write(payload)
                length = len(payload)
            elif i == GAME_LUMP and length:
                inp.seek(offset)
                out.write(relocate_game_lump(inp.read(length), offset, start))
            elif length:
                inp.seek(offset)
                left = length
                while left:
                    chunk = inp.read(min(CHUNK, left))
                    if not chunk:
                        raise FormatError(f'lump {i} extends past the end of the file')
                    out.write(chunk)
                    left -= len(chunk)
            struct.pack_into('<4I', head, 16 + 16 * i, start, length, version, fourcc)
        out.seek(0)
        out.write(head)
    return [struct.unpack_from('<4I', head, 16 + 16 * i) for i in range(128)]


def replace_in_place(path, changes, suffix='.edit'):
    """replace_lumps into a temporary file next to path, then swap it in."""
    path = Path(path)
    temp = path.with_name(path.name + suffix)
    if temp.exists():
        raise FileExistsError(f'{temp} exists; remove it first')
    try:
        replace_lumps(path, temp, changes)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    lumps = sub.add_parser('lumps', help='print the lump table')
    lumps.add_argument('bsp')
    copy = sub.add_parser('copy', help='copy a BSP, replacing lumps with file contents')
    copy.add_argument('bsp')
    copy.add_argument('output')
    copy.add_argument('--replace', action='append', default=[], metavar='INDEX=FILE')
    a = p.parse_args(argv)
    if a.command == 'lumps':
        _, entries = header(a.bsp)
        rows = [dict(index=i, offset=e[0], length=e[1], version=e[2], fourcc=e[3]) for i, e in enumerate(entries) if e[1]]
        print(json.dumps(rows, indent=1))
        return 0
    changes = {}
    for item in a.replace:
        index, _, file = item.partition('=')
        changes[int(index, 0)] = Path(file).read_bytes()
    replace_lumps(a.bsp, a.output, changes)
    print(json.dumps({'output': a.output, 'replaced': sorted(changes)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
