"""Synthetic-BSP tests for bsp_edit, weld_tricoll, weld_shadow_meshes, csm_props, cubemaps, cells_all_visible
and thunderstore_upload's package check."""
import io
import json
import struct
import tempfile
import unittest
import zipfile
from array import array
from pathlib import Path

import bsp_edit
import cells_all_visible
import csm_props
import cubemaps
import thunderstore_upload
import weld_shadow_meshes
import weld_tricoll
from inspect_bsp import HEADER_SIZE


def make_bsp(path, lumps, version=37):
    """A v37 BSP holding `lumps` ({index: bytes}) at 16-byte aligned offsets, in reverse index order."""
    head = bytearray(HEADER_SIZE)
    struct.pack_into('<4s3I', head, 0, b'rBSP', version, 30, 127)
    body = bytearray()
    for i in sorted(lumps, reverse=True):
        body += bytes(-(HEADER_SIZE + len(body)) % 16)
        struct.pack_into('<4I', head, 16 + 16 * i, HEADER_SIZE + len(body), len(lumps[i]), 0, 0)
        body += lumps[i]
    Path(path).write_bytes(head + body)


def game_lump(base, sprp_body):
    """A GAME_LUMP with one sprp v13 entry, its offset absolute for a lump stored at `base`."""
    return struct.pack('<I4sHHII', 1, b'prps', 0, 13, base + 20, len(sprp_body)) + sprp_body


def sprp(models, placements):
    names = b''.join(m.encode().ljust(128, b'\0') for m in models)
    body = struct.pack('<I', len(models)) + names + struct.pack('<3I', len(placements), 0, 0)
    for origin, angles, scale, model in placements:
        body += struct.pack('<7fH2B2H4f4b4B2H', *origin, *angles, scale, model, 0, 0, 0, 0xFFFF, -1, 0, 0, 0,
                            -1, -1, -1, -1, 255, 255, 255, 255, 0, 0)
    return body + struct.pack('<I', 0)


def grid(n, z=0.0):
    """2n^2 triangles of an n x n quad grid with varied heights, sharing corners."""
    p = lambda i, j: (i * 64.0, j * 64.0, z + ((i * 7 + j * 3) % 5) * 8.0)
    return [t for i in range(n) for j in range(n) for t in ((p(i, j), p(i + 1, j), p(i + 1, j + 1)),
                                                             (p(i, j), p(i + 1, j + 1), p(i, j + 1)))]


def tricoll(groups, first_position):
    """Positions, words and headers as a generator writing three fresh positions per triangle would."""
    positions, words, headers = bytearray(), array('I'), bytearray()
    for faces in groups:
        base = first_position + len(positions) // 12
        first = len(words)
        for i, face in enumerate(faces):
            positions += b''.join(struct.pack('<3f', *v) for v in face)
            words.append(i * 3 | 1 << 10 | 2 << 17 | weld_tricoll.z_bits([v[2] for v in face]))
        headers += weld_tricoll.HEADER.pack(0, 0x200, 0, 3 * len(faces), len(faces), 0, base, first, 0, 0, 0, 0, 0, 1)
    return bytes(positions), words.tobytes(), bytes(headers)


class TempDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()


class BspEditTests(TempDir):
    def test_replace_keeps_other_lumps_and_moves_game_lump_offsets(self):
        src, out = self.dir / 'a.bsp', self.dir / 'b.bsp'
        body = sprp(['models/a.mdl'], [((1, 2, 3), (0, 0, 0), 1.0, 0)])
        # The game lump's absolute offset depends on where make_bsp puts it: build, read, rebuild.
        make_bsp(src, {8: b'eight', 35: game_lump(0, body), 3: b'x' * 24})
        base = bsp_edit.header(src)[1][35][0]
        make_bsp(src, {8: b'eight', 35: game_lump(base, body), 3: b'x' * 24})
        bsp_edit.replace_lumps(src, out, {3: b'y' * 100})
        got = bsp_edit.read_lumps(out, (3, 8, 35))
        self.assertEqual(got[3], b'y' * 100)
        self.assertEqual(got[8], b'eight')
        new_base = bsp_edit.header(out)[1][35][0]
        self.assertEqual(struct.unpack_from('<I', got[35], 12)[0], new_base + 20)
        self.assertEqual(got[35][20:], body)

    def test_refuses_sidecars_and_in_place_targets(self):
        src = self.dir / 'a.bsp'
        make_bsp(src, {3: b'z' * 12})
        with self.assertRaises(ValueError):
            bsp_edit.replace_lumps(src, src, {})
        (self.dir / 'a.bsp.0003.bsp_lump').write_bytes(b'')
        with self.assertRaises(bsp_edit.FormatError):
            bsp_edit.read_lumps(src, (3,))


class WeldTricollTests(TempDir):
    def test_weld_shares_corners_and_keeps_render_positions(self):
        render = struct.pack('<9f', 1, 2, 3, 4, 5, 6, 7, 8, 9)
        positions, words, headers = tricoll([grid(3), grid(2, 500.0)], first_position=3)
        lit = b''.join(struct.pack('<2I2f4B4f2I', i, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) for i in (2, 0, 1))
        src = self.dir / 'm.bsp'
        make_bsp(src, {3: render + positions, 0x42: words, 0x45: headers, 0x49: lit})
        lumps = bsp_edit.read_lumps(src, (3, 0x42, 0x45, *weld_tricoll.STRIDE))
        changes, report = weld_tricoll.weld(lumps)
        self.assertEqual(report['collision_positions_after'], 16 + 9)
        self.assertEqual(report['render_positions'], 3)
        out = changes[3]
        for at in range(0, len(changes[0x49]), 44):
            i = struct.unpack_from('<I', changes[0x49], at)[0]
            j = struct.unpack_from('<I', lit, at)[0]
            self.assertEqual(out[12 * i:12 * i + 12], render[12 * j:12 * j + 12])

    def test_long_spans_reemit_positions(self):
        faces = [((t * 10.0, 0.0, 0.0), (t * 10.0, 5.0, 1.0), (t * 10.0, 0.0, 2.0)) for t in range(96)]
        faces[-1] = (faces[0][0], faces[-1][1], faces[-1][2])  # shares a corner 285 positions back
        positions, words, headers = tricoll([faces], 0)
        changes, report = weld_tricoll.weld({3: positions, 0x42: words, 0x45: headers})
        self.assertEqual(report['collision_positions_after'], 3 * 96)  # re-emitted, not shared out of range
        for w in array('I', changes[0x42]):
            i0, i1, i2 = weld_tricoll.decode(w)
            self.assertTrue(i0 <= i1 and i0 <= i2 and max(i1, i2) - i0 <= 127)


class WeldShadowTests(unittest.TestCase):
    def test_meshes_share_positions_and_alpha_meshes_stay(self):
        a, b = grid(3), grid(2, 100.0)
        positions = b''.join(struct.pack('<3f', *v) for face in a + b for v in face)
        idx = array('H', list(range(3 * len(a))) + list(range(3 * len(b))) + [0, 1, 2])
        meshes = weld_shadow_meshes.MESH.pack(0, len(a), 1, -1) + weld_shadow_meshes.MESH.pack(3 * len(a), len(b), 1, -1) + \
            weld_shadow_meshes.MESH.pack(0, 1, 0, 3)
        changes, report = weld_shadow_meshes.weld({0x7C: positions, 0x7E: idx.tobytes(), 0x7F: meshes})
        self.assertEqual(report['positions_after'], 16 + 9)
        self.assertEqual(len(changes[0x7E]), len(idx) * 2)
        self.assertEqual(list(weld_shadow_meshes.MESH.iter_unpack(changes[0x7F]))[2], (0, 1, 0, 3))


class CsmPropsTests(TempDir):
    def map_with_props(self, path, placements):
        level = struct.pack('<4I3f', 0, 0, 10, 0, 0, 0, 0)
        envs = csm_props.ENV.pack(0, 0, 0, 1, 0, 0, 0.0, 0.0, -1.0) + csm_props.ENV.pack(1, 0, 0, 2, 0, 0, 0.0, 0.0, -1.0)
        root = csm_props.NODE.pack(*[3e38] * 3, 0, 0, 0, *[-3e38] * 3, 0, 0)
        body = sprp(['models/rock.mdl', 'models/grass_a.mdl'], placements)
        make_bsp(path, {5: envs, 0x63: root * 2, 0x7B: level, 35: game_lump(0, body)})
        base = bsp_edit.header(path)[1][35][0]
        make_bsp(path, {5: envs, 0x63: root * 2, 0x7B: level, 35: game_lump(base, body)})

    def test_props_go_in_a_light_space_tree_and_grass_is_left_out(self):
        src = self.dir / 'm.bsp'
        placements = [((x * 300.0, 0.0, 0.0), (0, 0, 0), 1.0, 0) for x in range(40)] + [((0, 0, 0), (0, 0, 0), 1.0, 1)]
        self.map_with_props(src, placements)
        bounds = {'models/rock.mdl': [[-60, -60, 0], [60, 60, 120]]}
        changes, report = csm_props.add(src, bounds, 64.0, csm_props.EXCLUDE, 48.0)
        self.assertEqual(report['casters'], 40)
        self.assertEqual(report['skipped']['excluded'], 1)
        self.assertEqual(report['prop_object_base'], 64)
        refs = struct.unpack(f'<{len(changes[0x64]) // 2}H', changes[0x64])
        self.assertEqual(sorted(refs), list(range(64, 104)))
        envs = [csm_props.ENV.unpack_from(changes[5], i) for i in range(0, len(changes[5]), csm_props.ENV.size)]
        nodes = len(changes[0x63]) // csm_props.NODE.size
        self.assertEqual((envs[0][0], envs[0][3], envs[1][0], envs[1][3]), (0, nodes - 1, nodes - 1, nodes))
        # Light space for a sun straight down: z = up, so every prop's box spans its height.
        root = csm_props.NODE.unpack_from(changes[0x63], 0)
        self.assertAlmostEqual(root[2], -1.0, places=3)
        self.assertAlmostEqual(root[8], 121.0, places=3)

    def test_refuses_a_map_that_already_lists_objects(self):
        src = self.dir / 'm.bsp'
        self.map_with_props(src, [((0, 0, 0), (0, 0, 0), 1.0, 0)])
        csm_props.add(src, {}, 64.0, csm_props.EXCLUDE, 0.0)
        changes, _ = csm_props.add(src, {}, 64.0, csm_props.EXCLUDE, 0.0)
        out = self.dir / 'n.bsp'
        bsp_edit.replace_lumps(src, out, changes)
        with self.assertRaises(ValueError):
            csm_props.add(out, {}, 64.0, csm_props.EXCLUDE, 0.0)


class CubemapTests(TempDir):
    def test_vtf_and_pakfile_layout(self):
        cube = [[bytes(max(1, (256 >> m) // 4) ** 2 * 16) for m in range(9)] for _ in range(6)]
        v = cubemaps.vtf([cube, cube], [1.0, 1.0])
        self.assertEqual(len(v), 104 + 12 + 2 * 6 * sum(max(1, (256 >> m) // 4) ** 2 * 16 for m in range(9)))
        self.assertEqual(struct.unpack_from('<i', v, 52)[0], 66)
        z = zipfile.ZipFile(io.BytesIO(cubemaps.pakfile('materials/maps/x/cubemaps.hdr.vtf', v)))
        self.assertEqual(z.namelist(), ['materials/maps/x/cubemaps.hdr.vtf'])
        self.assertTrue(z.comment.startswith(b'XZP1 0'))
        self.assertEqual(len(z.comment), 32)

    def test_faces_join_and_meshes_take_the_nearest_cubemap(self):
        # +X's bottom row (v = 1) is -Y's right column (u = 1): the edge x = 1, y = -1.
        for t in (-0.9, 0.0, 0.7):
            a = cubemaps.face_direction(0, t, 1.0)
            b = cubemaps.face_direction(3, 1.0, t)
            self.assertTrue(all(abs(x - y) < 1e-9 for x, y in zip(a, b)))
        meshes = cubemaps.MESH.pack(0, 1, 0, 0, 2, -1, -1, -1, -1, -1, -1, -1, 255, 255, 0, 0x200) + \
            cubemaps.MESH.pack(0, 1, 0, 0, 2, -1, -1, -1, -1, -1, -1, -1, 255, 255, 0, 0x400)
        bounds = struct.pack('<8f', 900, 0, 0, 1, 1, 1, 1, 0) * 2
        out, sorts, assigned = cubemaps.assign({0x50: meshes, 0x51: bounds, 0x52: struct.pack('<3hHI', 0, 0, -1, 0, 0)},
                                               [[0, 0, 0], [1000, 0, 0]])
        self.assertEqual((assigned, struct.unpack_from('<b', out, 11)[0], struct.unpack_from('<b', out, 28 + 11)[0]), (1, 1, -1))
        self.assertEqual(struct.unpack_from('<h', sorts, 4)[0], 0)

    def test_plan_puts_cubemaps_at_both_bases_and_between(self):
        ents = ''.join('{\n"classname" "info_spawnpoint_human"\n"origin" "%d %d 100"\n}\n' % (x, y)
                       for x, y in ((-3000, 0), (-3100, 50), (3000, 0), (3050, -40)))
        src = self.dir / 'm.bsp'
        make_bsp(src, {0: ents.encode() + b'\0'})
        plan = cubemaps.plan(src, between=3)
        xs = [o['origin'][0] for o in plan['origins']]
        self.assertEqual(len(xs), 5)
        self.assertLess(xs[0] * xs[-1], 0)
        self.assertEqual([o['floor_snap'] for o in plan['origins']], [False, True, True, True, False])


class CellsTests(TempDir):
    def test_points_go_to_the_cell_referencing_most(self):
        nodes = b''.join(cells_all_visible.NODE.pack(0, 0, 0, 0, 0, n, 1, 1, 1, 0, 0) for n in (3, 4, 9))
        src = self.dir / 'm.bsp'
        make_bsp(src, {0x6A: struct.pack('<iI', 0, 1) + struct.pack('<iI', -1, 0) + struct.pack('<iI', -1, 1),
                       0x6B: bytes(24), 0x77: nodes, 0x78: bytes(18)})
        info = cells_all_visible.inspect(src)
        self.assertTrue(info['split_without_portals'])
        changes, report = cells_all_visible.apply(src)
        self.assertEqual(changes[0x6A], struct.pack('<iI', -1, 2))
        with self.assertRaises(ValueError):
            cells_all_visible.apply(src, 0)


class ThunderstoreCheckTests(TempDir):
    def package(self, manifest, icon_size=(256, 256)):
        path = self.dir / 'p.zip'
        png = b'\x89PNG\r\n\x1a\n' + struct.pack('>I4s2I', 13, b'IHDR', *icon_size) + bytes(5)
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('manifest.json', json.dumps(manifest))
            z.writestr('README.md', '# x')
            z.writestr('icon.png', png)
        return path

    def test_good_and_bad_packages(self):
        good = dict(name='My_Map', version_number='1.2.3', website_url='', description='x', dependencies=[])
        self.assertEqual(thunderstore_upload.check(self.package(good)), [])
        bad = dict(good, name='My Map', version_number='1.2')
        problems = thunderstore_upload.check(self.package(bad, (128, 128)))
        self.assertEqual(len(problems), 3)


if __name__ == '__main__':
    unittest.main()
