"""Tests for tools/cubemaps.py `faces`: reading a BSP PAKFILE cubemap and decoding its BC6H faces."""
import io
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

import cubemaps

try:
    from PIL import Image  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def mode11_block(endpoint):
    """A BC6H mode-11 block with both endpoints `endpoint` (10 bits) on every channel: one flat colour."""
    bits = 0x03
    for i in range(6):
        bits |= endpoint << (5 + 10 * i)
    return bits.to_bytes(16, 'little')


def cubemap_vtf(frames, block):
    """A full 256x256, 9-mip VTF whose every block is `block`."""
    faces = [[block * (max(1, (cubemaps.FACE >> m) // 4) ** 2) for m in range(cubemaps.MIPS)] for _ in range(6)]
    return cubemaps.vtf([faces] * frames, [1.0] * frames)


def write_bsp(folder, vtf):
    pak = cubemaps.pakfile('materials/maps/mp_test/cubemaps.hdr.vtf', vtf)
    directory = bytearray(128 * 16)
    struct.pack_into('<ii', directory, 0x28 * 16, 16 + len(directory), len(pak))
    path = Path(folder) / 'mp_test.bsp'
    path.write_bytes(b'rBSP' + struct.pack('<3i', 47, 30, 127) + bytes(directory) + pak)
    return path


@unittest.skipUnless(HAVE_PIL, 'Pillow is needed to decode BC6H')
class CubemapFacesTests(unittest.TestCase):
    def test_decodes_each_frame_and_face(self):
        vtf = cubemap_vtf(2, mode11_block(512))
        cubes = cubemaps.decode_faces(vtf, mip=2)
        self.assertEqual((len(cubes), len(cubes[0])), (2, 6))
        face = cubes[1][5]
        self.assertEqual(face.size, (64, 64))
        colours = set(face.getdata())
        self.assertEqual(len(colours), 1)  # one flat colour
        self.assertGreater(next(iter(colours))[0], 0)

    def test_smallest_mips_are_padded_blocks(self):
        cubes = cubemaps.decode_faces(cubemap_vtf(1, mode11_block(512)), mip=8)
        self.assertEqual(cubes[0][0].size, (1, 1))

    def test_write_faces_from_bsp(self):
        with tempfile.TemporaryDirectory() as tmp:
            bsp = write_bsp(tmp, cubemap_vtf(3, bytes(16)))  # mode-0 zero blocks decode black
            report = cubemaps.write_faces(bsp, Path(tmp) / 'out', mip=3)
            self.assertEqual(report['vtf'], 'materials/maps/mp_test/cubemaps.hdr.vtf')
            self.assertEqual(len(report['cubemaps']), 3)
            self.assertEqual(report['cubemaps'][0]['max'], 0)
            self.assertTrue(Path(report['cubemaps'][2]['png']).is_file())

    def test_rejects_empty_pakfile_and_other_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'mp_empty.bsp'
            path.write_bytes(b'rBSP' + struct.pack('<3i', 37, 1, 127) + bytes(128 * 16))
            with self.assertRaisesRegex(ValueError, 'empty'):
                cubemaps.pakfile_vtf(path)
        vtf = bytearray(cubemap_vtf(1, bytes(16)))
        struct.pack_into('<i', vtf, 52, 13)
        with self.assertRaisesRegex(ValueError, 'format 13'):
            cubemaps.decode_faces(bytes(vtf))


if __name__ == '__main__':
    unittest.main()
