"""Bounded v54 AIN sidecar framing checks, not graph semantics or CRC validation.

Copyright (C) 2026 MRVN-Radiant contributors. GPL-2.0-or-later.
"""
import math
from pathlib import Path
import stat
import struct

MAX_BYTES = 64 * 1024 * 1024


def linked(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def navigation_graph(bsp):
    """Return an optional matching graph's bytes after checking basic framing.

    Tail semantics, native script version and entity CRC remain engine checks.
    Read before staging so a rejected graph cannot leave an owned addon behind.
    """
    bsp = Path(bsp)
    folder = bsp.parent / 'graphs'
    if not folder.exists() and not folder.is_symlink():
        return None
    if linked(folder) or not folder.is_dir():
        raise ValueError('refusing linked or non-directory AIN folder')
    name = bsp.stem + '.ain'
    matches = [p for p in folder.iterdir() if p.name.casefold() == name.casefold()]
    if not matches:
        return None
    if len(matches) != 1 or matches[0].name != name:
        raise ValueError('ambiguous or case-aliased AIN sidecar')
    path = matches[0]
    if linked(path) or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('refusing linked or non-file AIN sidecar')
    if not 24 <= path.stat().st_size <= MAX_BYTES:
        raise ValueError('AIN sidecar size outside bounds')
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or len(data) < 24:
        raise ValueError('AIN sidecar size outside bounds')
    version, revision, _, nodes = struct.unpack_from('<4I', data)
    with bsp.open('rb') as stream:
        header = stream.read(12)
    if len(header) != 12 or header[:4] != b'rBSP' or struct.unpack_from('<I', header, 4)[0] != 29:
        raise ValueError('AIN sidecars require a v29 BSP')
    if version != 54 or revision != struct.unpack_from('<I', header, 8)[0]:
        raise ValueError('AIN version or map revision mismatch')
    if not 1 <= nodes <= 32767:
        raise ValueError('AIN node count outside bounds')
    offset = 16 + nodes * 68
    if offset + 8 > len(data):
        raise ValueError('truncated AIN node block')
    for index in range(nodes):
        if not all(math.isfinite(v) for v in struct.unpack_from('<9f', data, 16 + index * 68)):
            raise ValueError('nonfinite AIN node geometry')
    links = struct.unpack_from('<I', data, offset)[0]
    if links > 1_000_000 or offset + 4 + links * 10 + 4 > len(data):
        raise ValueError('truncated or oversized AIN link block')
    seen = set()
    for index in range(links):
        src, dst = struct.unpack_from('<hh', data, offset + 4 + index * 10)
        edge = tuple(sorted((src, dst)))
        if not (0 <= src < nodes and 0 <= dst < nodes) or src == dst or edge in seen:
            raise ValueError('invalid or duplicate AIN link endpoints')
        seen.add(edge)
    return data
