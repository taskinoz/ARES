#!/usr/bin/env python3
"""Report which platform the textures in Titanfall 2 v7 RPaks were built for.

A texture asset's header carries a platform byte at +0x1c: 0 = PC, 8 = PS4.
The PS4 game streams only PS4-layout textures, so a PC pak copied into a PS4
mod shows black or corrupt textures. This tool reads the asset table of
decompressed, unpatched v7 RPaks and counts textures per platform, plus
materials and datatables (which load on either platform).

A pak is `ps4_ready` when it has textures, materials or datatables, and every
texture is PS4 layout. Compressed or patch paks are reported as unsupported:
decompress them first.

Ported from PS4 Northstar's runtime check (launcher/include/northstar_ps4/
mod_rpaks.h, InspectRpakTexturePlatforms), which uses the same rules.

usage:
  python tools/rpak_platform.py PAK.rpak [PAK.rpak ...] [--output report.json]
  python tools/rpak_platform.py --scan MODS_FOLDER [--require ps4]

Exit status is 1 if any pak could not be read, or with --require ps4/pc, if
any pak does not match.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

HEADER_SIZE = 0x58
SLAB_SIZE = 16
PAGE_SIZE = 12
POINTER_SIZE = 8
ASSET_SIZE = 72
MAX_TABLE_BYTES = 16 * 1024 * 1024
PLATFORMS = {0: 'pc', 8: 'ps4'}


class RpakError(ValueError):
    pass


def _u16(data, offset):
    return struct.unpack_from('<H', data, offset)[0]


def _u32(data, offset):
    return struct.unpack_from('<I', data, offset)[0]


def inspect_bytes(read, size):
    """Counts texture platforms. `read(offset, length)` returns bytes or raises."""
    if size < HEADER_SIZE:
        raise RpakError('file is smaller than an RPak header')
    header = read(0, HEADER_SIZE)
    if header[:4] != b'RPak':
        raise RpakError('not an RPak (bad magic)')
    version = _u16(header, 4)
    if version != 7:
        raise RpakError(f'RPak version {version}; only Titanfall 2 v7 is supported')
    flags = _u16(header, 6)
    if flags != 0:
        raise RpakError(f'flags {flags:#06x}: compressed or otherwise flagged pak; decompress it first')
    if _u16(header, 0x3e) != 0:
        raise RpakError('patch pak (patch index is not 0); inspect the base pak')

    counts = {
        'path': _u16(header, 0x38), 'slabs': _u16(header, 0x3a), 'pages': _u16(header, 0x3c),
        'pointers': _u32(header, 0x40), 'assets': _u32(header, 0x44),
        'uses': _u32(header, 0x48), 'dependents': _u32(header, 0x4c),
    }
    cursor = HEADER_SIZE

    def advance(count, width):
        nonlocal cursor
        cursor += count * width
        if cursor > size:
            raise RpakError('tables run past the end of the file')

    advance(counts['path'], 1)
    advance(counts['slabs'], SLAB_SIZE)
    pages_offset = cursor
    advance(counts['pages'], PAGE_SIZE)
    advance(counts['pointers'], POINTER_SIZE)
    assets_offset = cursor
    advance(counts['assets'], ASSET_SIZE)
    advance(counts['uses'], POINTER_SIZE)
    advance(counts['dependents'], 4)
    page_data = cursor
    if page_data > MAX_TABLE_BYTES:
        raise RpakError('tables are implausibly large')
    tables = read(0, page_data)

    page_offsets, page_sizes, position = [], [], page_data
    for i in range(counts['pages']):
        length = _u32(tables, pages_offset + i * PAGE_SIZE + 8)
        page_offsets.append(position)
        page_sizes.append(length)
        position += length
        if position > size:
            raise RpakError(f'page {i} runs past the end of the file')

    result = {'textures': 0, 'pc': 0, 'ps4': 0, 'other': 0, 'materials': 0, 'datatables': 0,
              'other_platform_values': []}
    for i in range(counts['assets']):
        asset = assets_offset + i * ASSET_SIZE
        kind = tables[asset + 68:asset + 72]
        if kind == b'matl':
            result['materials'] += 1
        elif kind == b'dtbl':
            result['datatables'] += 1
        if kind != b'txtr':
            continue
        page, offset, head_size = _u32(tables, asset + 16), _u32(tables, asset + 20), _u32(tables, asset + 60)
        if page >= counts['pages'] or head_size <= 0x1c:
            raise RpakError(f'texture asset {i} has a bad page or header size')
        if offset > page_sizes[page] or head_size > page_sizes[page] - offset:
            raise RpakError(f'texture asset {i} header runs past its page')
        platform = read(page_offsets[page] + offset + 0x1c, 1)[0]
        result['textures'] += 1
        name = PLATFORMS.get(platform)
        if name:
            result[name] += 1
        else:
            result['other'] += 1
            if platform not in result['other_platform_values']:
                result['other_platform_values'].append(platform)
    result['assets'] = counts['assets']
    result['ps4_ready'] = (result['textures'] + result['materials'] + result['datatables'] > 0 and
                           result['ps4'] == result['textures'] and not result['pc'] and not result['other'])
    result['pc_ready'] = (result['textures'] + result['materials'] + result['datatables'] > 0 and
                          result['pc'] == result['textures'] and not result['ps4'] and not result['other'])
    if result['textures'] == 0:
        result['platform'] = 'any'
    elif result['ps4'] == result['textures']:
        result['platform'] = 'ps4'
    elif result['pc'] == result['textures']:
        result['platform'] = 'pc'
    else:
        result['platform'] = 'mixed'
    return result


def inspect_file(path):
    path = Path(path)
    size = path.stat().st_size
    with path.open('rb') as handle:
        def read(offset, length):
            if offset < 0 or offset + length > size:
                raise RpakError('read past the end of the file')
            handle.seek(offset)
            data = handle.read(length)
            if len(data) != length:
                raise RpakError('short read')
            return data
        return inspect_bytes(read, size)


def inspect_data(data):
    def read(offset, length):
        if offset < 0 or offset + length > len(data):
            raise RpakError('read past the end of the data')
        return bytes(data[offset:offset + length])
    return inspect_bytes(read, len(data))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('paks', nargs='*', type=Path)
    parser.add_argument('--scan', type=Path, action='append', default=[],
                        help='Folder to search recursively for *.rpak (e.g. a mods folder)')
    parser.add_argument('--require', choices=['ps4', 'pc'],
                        help='Exit 1 unless every pak is ready for this platform')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    paks = list(args.paks)
    for folder in args.scan:
        paks += sorted(folder.rglob('*.rpak'))
    if not paks:
        parser.error('no paks given')
    rows, failed = [], False
    for pak in paks:
        row = {'path': str(pak)}
        try:
            row.update(inspect_file(pak))
        except (OSError, RpakError, struct.error) as error:
            row['error'] = str(error)
            failed = True
        if args.require and 'error' not in row and not row[f'{args.require}_ready']:
            failed = True
        rows.append(row)
    summary = {'paks': len(rows), 'errors': sum('error' in r for r in rows),
               'ps4_ready': sum(bool(r.get('ps4_ready')) for r in rows),
               'pc_ready': sum(bool(r.get('pc_ready')) for r in rows)}
    text = json.dumps({'summary': summary, 'paks': rows}, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
