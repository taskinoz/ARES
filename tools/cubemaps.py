#!/usr/bin/env python3
"""Plan, inspect and write reflection cubemaps for a Titanfall 2 map (stdlib; Pillow and texconv for `write`).

Map builds often write none: CUBEMAPS (0x2A) and PAKFILE (0x28) are empty and
every mesh's cubemap byte is -1. mp_homestead has 4 and mp_colony02 has 7.
Without them, metal, glass and wet surfaces have nothing to reflect.

Layout (MRVN-Radiant titanfall2_cubemaps.cpp and docs/respawn/RESPAWN_TF2_LUMPS.md,
read from six retail maps):

- **CUBEMAPS (0x2A):** `<3iI` per cubemap, the integer origin and a zero.
- **MESHES (0x50):** byte 11 is the mesh's cubemap. Lit meshes take the nearest
  one; unlit meshes (vertex flags 0x400) take -1.
- **MATERIAL_SORTS (0x52):** every retail sort stores cubemap 0 (bytes 4-5).
- **PAKFILE (0x28):** a stored ZIP whose comment is `XZP1 0` padded to 32
  bytes. It holds `materials/maps/<map>/cubemaps.hdr.vtf`:
  - VTF 7.5, 256x256 faces, flags 0x420C, format 66 (BC6H unsigned), 9 mips,
    one frame per cubemap;
  - data is mips smallest first, then frames, then the six faces in D3D order
    (+X, -X, +Y, -Y, +Z, -Z), sampled with Source world vectors;
  - resources: `0` (image offset), `CMA` (one float per cubemap, meaning
    unresolved; 1.0 for gameplay cubemaps) and `CRC` (0).

The faces come from the game itself. `harnesses/recipes/northstar_cubemaps.py`
captures six views per origin, with the RUI HUD off and fov 106.26, which is 90
degrees vertically at 16:9 because Titanfall's fov is the 4:3 horizontal angle.
`write` resamples each face texel from the view facing it most directly,
linearises sRGB, and compresses to BC6H with DirectXTex `texconv` (--texconv or
$ARES_TEXCONV).

Copyright (c) 2026 taskinoz. MIT licence. From taskinoz/apex-to-titanfall-2
build_cubemaps.py. Verified on Northstar 1.31.14: six maps load with 5-7
cubemaps, and in comparison shots shaded rock, grass and metal pick up
reflected light.

  python tools/cubemaps.py inspect MAP.bsp
  python tools/cubemaps.py plan MAP.bsp --output cubemaps.json [--between 3]
  python tools/cubemaps.py write MAP.bsp cubemaps.json --texconv texconv.exe [--output OUT.bsp]
  python tools/cubemaps.py faces MAP.bsp --output DIR [--mip 2] [--raw]

`faces` decodes the compiled cubemaps.hdr.vtf of a Titanfall 2 or Apex map
(retail, texconv or MRVN-Radiant output) to PNG strips, faces +X -X +Y -Y +Z -Z.
To see them in game, use the Northstar harness checks key `cubemap_weapon`.
"""
import argparse
import io
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from bsp_edit import read_lumps, replace_in_place, replace_lumps

FACE = 256
MIPS = 9
EYE = 72.0
VIEWS = {'px': (0, 0), 'py': (0, 90), 'nx': (0, 180), 'ny': (0, 270), 'pz': (-90, 0), 'nz': (90, 0)}  # pitch, yaw
MESH = struct.Struct('<I3H6b2h2BHI')


def entities(path):
    text = read_lumps(path, (0,))[0].decode('latin-1')
    return [dict(re.findall(r'"([^"]*)" "([^"]*)"', block)) for block in re.findall(r'\{([^{}]*)\}', text)]


def plan(path, between=3):
    """Origins: the two team bases (spawn clusters, at spawn height + EYE) and `between` points on the line joining
    them, at the average spawn height + EYE. The capture recipe drops each in-between point onto the floor below."""
    spawns = [[float(v) for v in e['origin'].split()] for e in entities(path)
              if e.get('classname', '').startswith('info_spawnpoint_human') and 'origin' in e]
    if len(spawns) < 2:
        raise ValueError('need at least two human spawn points; pass origins by hand')
    dist = lambda p, q: math.dist(p, q)
    mean = [sum(c) / len(spawns) for c in zip(*spawns)]
    a = max(spawns, key=lambda p: dist(p, mean))
    b = max(spawns, key=lambda p: dist(p, a))
    for _ in range(20):  # two-means
        near_a = [p for p in spawns if dist(p, a) <= dist(p, b)]
        near_b = [p for p in spawns if dist(p, a) > dist(p, b)] or [b]
        a, b = [sum(c) / len(near_a) for c in zip(*near_a)], [sum(c) / len(near_b) for c in zip(*near_b)]
    origins = []
    for k in range(between + 2):
        t = k / (between + 1)
        o = [a[i] + (b[i] - a[i]) * t for i in range(3)]
        o[2] += EYE
        origins.append(dict(origin=[round(v) for v in o], floor_snap=0 < t < 1))
    return dict(map=Path(path).stem, origins=origins, fov=106.26)


def face_direction(face, u, v):
    """MRVN FaceDirection: D3D cube faces with Source world vectors (u, v in [-1, 1], v down)."""
    d = [(1, -v, -u), (-1, -v, u), (u, 1, v), (u, -1, -v), (u, -v, 1), (-u, -v, -1)][face]
    n = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    return d[0] / n, d[1] / n, d[2] / n


def basis(pitch, yaw):
    p, y = math.radians(pitch), math.radians(yaw)
    f = (math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), -math.sin(p))
    r = (math.sin(y), -math.cos(y), 0.0)
    u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
    return f, r, u


def faces(shots):
    """Six FACE x FACE linear-light faces [[(r, g, b)]] from {view name: screenshot path}."""
    from PIL import Image
    images = {}
    for name, path in shots.items():
        im = Image.open(path).convert('RGB')
        images[name] = (im.size, im.load())
    (w, h) = next(iter(images.values()))[0]
    focal = (h / 2) / math.tan(math.radians(45))  # the views are 90 degrees vertically
    lut = [(c / 255) ** 2.2 for c in range(256)]
    frames = {n: basis(*VIEWS[n]) for n in images}
    out = []
    for face in range(6):
        rows = []
        for y in range(FACE):
            row = []
            for x in range(FACE):
                d = face_direction(face, (x + .5) / FACE * 2 - 1, (y + .5) / FACE * 2 - 1)
                best = max(frames, key=lambda n: sum(a * b for a, b in zip(frames[n][0], d)))
                f, r, u = frames[best]
                along = sum(a * b for a, b in zip(f, d))
                px = int(w / 2 + focal * sum(a * b for a, b in zip(r, d)) / along)
                py = int(h / 2 - focal * sum(a * b for a, b in zip(u, d)) / along)
                c = images[best][1][min(max(px, 0), w - 1), min(max(py, 0), h - 1)]
                row.append((lut[c[0]], lut[c[1]], lut[c[2]]))
            rows.append(row)
        out.append(rows)
    return out


def bc6h(cube, texconv, work):
    """[face][mip] BC6H blocks (mips largest first) from a float16 cubemap DDS compressed by texconv."""
    src = Path(work) / 'cube.dds'
    head = struct.pack('<4s7I44x2I4s5I', b'DDS ', 124, 0x1007, FACE, FACE, FACE * 8, 0, 1, 32, 4, b'DX10', 0, 0, 0, 0, 0)
    head += struct.pack('<5I', 0x1000, 0x200 | 0xFC00, 0, 0, 0)
    head += struct.pack('<5I', 10, 3, 0x4, 1, 0)  # R16G16B16A16_FLOAT, 2D, TEXTURECUBE, one cube
    body = bytearray()
    for face in cube:
        for row in face:
            body += b''.join(struct.pack('<4e', *c, 1.0) for c in row)
    src.write_bytes(head + body)
    out = Path(work) / 'bc6h'
    out.mkdir(exist_ok=True)
    subprocess.run([str(texconv), '-nologo', '-y', '-m', str(MIPS), '-f', 'BC6H_UF16', '-o', str(out), str(src)],
                   check=True, capture_output=True)
    data = (out / src.name).read_bytes()
    at, result = 148, []
    for _ in range(6):
        mips = []
        for m in range(MIPS):
            n = max(1, (FACE >> m) // 4) ** 2 * 16
            mips.append(data[at:at + n])
            at += n
        result.append(mips)
    if at != len(data):
        raise ValueError('unexpected BC6H cubemap size from texconv')
    return result


def vtf(cubes, cma):
    frames = len(cubes)
    v = bytearray(b'VTF\0')
    v += struct.pack('<3I2HI2HI3fIfiBiBBH', 7, 5, 104, FACE, FACE, 0x420C, frames, 0, 0, .2, .2, .2, 0, 1.0, 66,
                     MIPS, -1, 0, 0, 1)
    v += bytes(3) + struct.pack('<I', 3) + bytes(8)
    v += b'0\0\0\0' + struct.pack('<I', 104 + (4 + 4 * frames if frames > 1 else 0))
    v += (b'CMA\0' + struct.pack('<I', 104)) if frames > 1 else (b'CMA\x02' + struct.pack('<f', cma[0]))
    v += b'CRC\x02' + struct.pack('<I', 0)
    assert len(v) == 104
    if frames > 1:
        v += struct.pack(f'<I{frames}f', 4 * frames, *cma)
    for mip in reversed(range(MIPS)):
        for cube in cubes:
            for face in range(6):
                v += cube[face][mip]
    return bytes(v)


def pakfile(name, data):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as z:
        z.comment = b'XZP1 0'.ljust(32, b'\0')
        z.writestr(zipfile.ZipInfo(name), data)
    return buf.getvalue()


def assign(lumps, origins):
    """Meshes with each lit mesh's nearest cubemap at byte 11, and material sorts storing cubemap 0."""
    meshes = bytearray(lumps[0x50])
    centres = [struct.unpack_from('<3f', lumps[0x51], i) for i in range(0, len(lumps[0x51]), 32)]
    assigned = 0
    for m, c in enumerate(centres):
        if struct.unpack_from('<I', meshes, m * MESH.size + 24)[0] & 0x600 == 0x400:
            continue
        struct.pack_into('<b', meshes, m * MESH.size + 11, min(range(len(origins)), key=lambda k: math.dist(origins[k], c)))
        assigned += 1
    sorts = bytearray(lumps[0x52])
    for at in range(0, len(sorts), 12):
        struct.pack_into('<h', sorts, at + 4, 0)
    return bytes(meshes), bytes(sorts), assigned


def write(path, cfg, texconv):
    origins = [o['origin'] for o in cfg['origins']]
    if not 1 <= len(origins) <= 127:
        raise ValueError('1-127 cubemaps')
    lumps = read_lumps(path, (0x28, 0x2A, 0x50, 0x51, 0x52))
    if lumps[0x28] or lumps[0x2A]:
        raise ValueError('the map already has cubemaps or a pakfile')
    cubes = []
    with tempfile.TemporaryDirectory() as work:
        for i, o in enumerate(cfg['origins']):
            cubes.append(bc6h(faces({n: o['shots'][n] for n in VIEWS}), texconv, work))
    meshes, sorts, assigned = assign(lumps, origins)
    name = f'materials/maps/{Path(path).stem}/cubemaps.hdr.vtf'
    changes = {0x28: pakfile(name, vtf(cubes, [1.0] * len(cubes))), 0x50: meshes, 0x52: sorts,
               0x2A: b''.join(struct.pack('<3iI', *[round(v) for v in o], 0) for o in origins)}
    return changes, dict(cubemaps=len(origins), meshes_assigned=assigned, pakfile_bytes=len(changes[0x28]), texture=name)


def inspect(path):
    l = read_lumps(path, (0x28, 0x2A, 0x50))
    files = zipfile.ZipFile(io.BytesIO(l[0x28])).namelist() if l[0x28] else []
    counts = {}
    for at in range(0, len(l[0x50]), MESH.size):
        c = struct.unpack_from('<b', l[0x50], at + 11)[0]
        counts[c] = counts.get(c, 0) + 1
    return dict(cubemaps=[list(struct.unpack_from('<3i', l[0x2A], i)) for i in range(0, len(l[0x2A]), 16)],
                pakfile_files=files, meshes_per_cubemap={str(k): v for k, v in sorted(counts.items())})


def pakfile_vtf(path):
    """(name, bytes) of the cubemaps.hdr.vtf in a BSP's PAKFILE, embedded or in a .0028.bsp_lump file."""
    path = Path(path)
    with path.open('rb') as stream:
        head = stream.read(16 + 128 * 16)
        if head[:4] != b'rBSP':
            raise ValueError(f'{path}: not an rBSP file')
        offset, length = struct.unpack_from('<ii', head, 16 + 0x28 * 16)
        stream.seek(offset)
        data = stream.read(length)
    external = path.with_name(path.name + '.0028.bsp_lump')
    if external.is_file():
        data = external.read_bytes()
    if not data:
        raise ValueError(f'{path}: the PAKFILE is empty (no compiled cubemaps)')
    pak = zipfile.ZipFile(io.BytesIO(data))
    names = [n for n in pak.namelist() if n.lower().endswith('cubemaps.hdr.vtf')]
    if not names:
        raise ValueError(f'{path}: the PAKFILE has no cubemaps.hdr.vtf')
    return names[0], pak.read(names[0])


def decode_faces(data, mip=0):
    """[cubemap][face] RGB images (faces +X, -X, +Y, -Y, +Z, -Z) of one mip of a BC6H cubemap VTF.

    Pillow (10.1 or later) decodes every BC6H mode, clamped to 8 bits, so this
    reads retail, texconv-written and MRVN-Radiant cubemaps alike."""
    from PIL import Image  # optional dependency, only for this command
    if data[:4] != b'VTF\0':
        raise ValueError('not a VTF file')
    width, height, _, frames = struct.unpack_from('<HHIH', data, 16)
    fmt, mips = struct.unpack_from('<iB', data, 52)
    if fmt != 66 or width != height:
        raise ValueError(f'expected a square BC6H (format 66) cubemap, got format {fmt} {width}x{height}')
    if not 0 <= mip < mips:
        raise ValueError(f'mip {mip} is outside 0-{mips - 1}')
    offset = None
    for r in range(struct.unpack_from('<I', data, 68)[0]):
        tag, value = data[80 + 8 * r:84 + 8 * r], struct.unpack_from('<I', data, 84 + 8 * r)[0]
        if tag[:1] == b'0':
            offset = value
    if offset is None:
        raise ValueError('VTF has no image resource')

    def face_bytes(m):
        return max(1, (max(width >> m, 1) + 3) // 4) ** 2 * 16

    for m in range(mips - 1, mip, -1):  # mips are stored smallest first
        offset += frames * 6 * face_bytes(m)
    size, n = max(width >> mip, 1), face_bytes(mip)
    blocks = max(size, 4)
    dds = (struct.pack('<4s7I44x2I4s5I', b'DDS ', 124, 0x1007, blocks, blocks, n, 0, 1, 32, 4, b'DX10', 0, 0, 0, 0, 0)
           + struct.pack('<5I', 0x1000, 0, 0, 0, 0) + struct.pack('<5I', 95, 3, 0, 1, 0))  # BC6H_UF16, 2D
    cubes = []
    for frame in range(frames):
        cube = []
        for face in range(6):
            start = offset + (frame * 6 + face) * n
            if start + n > len(data):
                raise ValueError('VTF image data is shorter than its header says')
            image = Image.open(io.BytesIO(dds + data[start:start + n]))
            image.load()
            cube.append(image.convert('RGB').crop((0, 0, size, size)))
        cubes.append(cube)
    return cubes


def write_faces(path, output, mip=0, normalise=True):
    """Write one PNG strip per cubemap (six faces side by side) and return statistics."""
    from PIL import Image
    name, data = pakfile_vtf(path)
    cubes = decode_faces(data, mip)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = {'vtf': name, 'mip': mip, 'cubemaps': []}
    for i, cube in enumerate(cubes):
        size = cube[0].width
        strip = Image.new('RGB', (size * 6, size))
        for f, face in enumerate(cube):
            strip.paste(face, (f * size, 0))
        values = list(strip.getdata())
        peak = max(max(p) for p in values)
        mean = sum(sum(p) for p in values) / (3 * len(values))
        if normalise and 0 < peak < 255:
            # Dark cubemaps decode to a few grey levels; stretch them for viewing.
            strip = strip.point(lambda v, k=255 / peak: min(255, round(v * k)))
        target = output / f'cubemap{i}.png'
        strip.save(target)
        report['cubemaps'].append({'png': str(target), 'mean': round(mean, 2), 'max': peak})
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='command', required=True)
    i = sub.add_parser('inspect')
    i.add_argument('bsp')
    pl = sub.add_parser('plan')
    pl.add_argument('bsp')
    pl.add_argument('--between', type=int, default=3)
    pl.add_argument('--output', required=True)
    w = sub.add_parser('write')
    w.add_argument('bsp')
    w.add_argument('config', help='plan output with each origin\'s "shots" filled in by the capture recipe')
    w.add_argument('--texconv', default=os.environ.get('ARES_TEXCONV'))
    w.add_argument('--output', help='write here instead of replacing the input')
    fc = sub.add_parser('faces', help='decode the compiled cubemaps to PNG strips (needs Pillow 10.1+)')
    fc.add_argument('bsp')
    fc.add_argument('--output', required=True, help='folder for cubemap<N>.png')
    fc.add_argument('--mip', type=int, default=2, help='0 is 256x256; the default 2 is 64x64')
    fc.add_argument('--raw', action='store_true', help='do not stretch dark cubemaps for viewing')
    a = p.parse_args(argv)
    if a.command == 'inspect':
        print(json.dumps(inspect(a.bsp), indent=2))
    elif a.command == 'faces':
        print(json.dumps(write_faces(a.bsp, a.output, a.mip, not a.raw), indent=2))
    elif a.command == 'plan':
        Path(a.output).write_text(json.dumps(plan(a.bsp, a.between), indent=2) + '\n')
        print(Path(a.output).read_text())
    else:
        if not a.texconv:
            p.error('--texconv (or ARES_TEXCONV) is required to compress BC6H faces')
        changes, report = write(a.bsp, json.loads(Path(a.config).read_text()), a.texconv)
        if a.output:
            replace_lumps(a.bsp, a.output, changes)
        else:
            replace_in_place(a.bsp, changes, '.cubemaps')
        print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
