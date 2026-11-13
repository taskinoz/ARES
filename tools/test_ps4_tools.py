"""Tests for rpak_platform.py, pdef.py and prx_inspect.py on synthetic data."""
import json
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdef  # noqa: E402
import prx_inspect  # noqa: E402
import rpak_platform  # noqa: E402


def make_rpak(textures=(), materials=0, datatables=0, flags=0, version=7, patch=0):
    """A v7 RPak with one page; `textures` lists each texture's platform byte."""
    head = 0x30
    assets = []
    page = bytearray()
    for platform in textures:
        offset = len(page)
        header = bytearray(head)
        header[0x1c] = platform
        page += header
        asset = bytearray(72)
        struct.pack_into('<II', asset, 16, 0, offset)
        struct.pack_into('<I', asset, 60, head)
        asset[68:72] = b'txtr'
        assets.append(asset)
    for kind, count in ((b'matl', materials), (b'dtbl', datatables)):
        for _ in range(count):
            asset = bytearray(72)
            asset[68:72] = kind
            assets.append(asset)
    header = bytearray(0x58)
    header[:4] = b'RPak'
    struct.pack_into('<HH', header, 4, version, flags)
    struct.pack_into('<HHHH', header, 0x38, 0, 0, 1, patch)
    struct.pack_into('<IIII', header, 0x40, 0, len(assets), 0, 0)
    page_header = struct.pack('<III', 0, 0, len(page))
    return bytes(header) + page_header + b''.join(assets) + bytes(page)


class RpakPlatformTests(unittest.TestCase):
    def test_counts_platforms(self):
        result = rpak_platform.inspect_data(make_rpak([8, 8, 8], materials=2))
        self.assertEqual((result['textures'], result['ps4'], result['pc'], result['materials']), (3, 3, 0, 2))
        self.assertTrue(result['ps4_ready'])
        self.assertFalse(result['pc_ready'])
        self.assertEqual(result['platform'], 'ps4')

    def test_pc_and_mixed(self):
        self.assertEqual(rpak_platform.inspect_data(make_rpak([0, 0]))['platform'], 'pc')
        mixed = rpak_platform.inspect_data(make_rpak([0, 8, 3]))
        self.assertEqual(mixed['platform'], 'mixed')
        self.assertEqual(mixed['other_platform_values'], [3])
        self.assertFalse(mixed['ps4_ready'])

    def test_material_only_pak_is_ready_everywhere(self):
        result = rpak_platform.inspect_data(make_rpak(materials=1, datatables=1))
        self.assertTrue(result['ps4_ready'] and result['pc_ready'])
        self.assertEqual(result['platform'], 'any')

    def test_empty_pak_is_not_ready(self):
        self.assertFalse(rpak_platform.inspect_data(make_rpak())['ps4_ready'])

    def test_rejects_compressed_patch_and_other_versions(self):
        for kwargs, text in (({'flags': 0x100}, 'compressed'), ({'patch': 1}, 'patch'), ({'version': 8}, 'version')):
            with self.assertRaisesRegex(rpak_platform.RpakError, text):
                rpak_platform.inspect_data(make_rpak([8], **kwargs))

    def test_rejects_truncated(self):
        data = make_rpak([8, 8])
        with self.assertRaises(rpak_platform.RpakError):
            rpak_platform.inspect_data(data[:-10])

    def test_cli_require(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'a.rpak').write_bytes(make_rpak([8]))
            (Path(folder) / 'b.rpak').write_bytes(make_rpak([0]))
            with redirect_stdout(StringIO()) as out:
                code = rpak_platform.main(['--scan', folder, '--require', 'ps4'])
            report = json.loads(out.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(report['summary'], {'paks': 2, 'errors': 0, 'ps4_ready': 1, 'pc_ready': 1})


PDEF = """
$ENUM_START eColor
    red
    green // comment
    blue
$ENUM_END
$STRUCT_START inner
    int a
    bool b
$STRUCT_END
int xp
string{16} name
eColor favourite
float scores[ eColor ]
inner items[2]
bool flags[5]
"""


class PdefTests(unittest.TestCase):
    def test_size_and_layout(self):
        p = pdef.Pdef(PDEF)
        # 4 + 16 + 1 + 4*3 + 5*2 + 5
        self.assertEqual(p.size(), 48)
        rows = {r['path']: r for r in p.layout()}
        self.assertEqual(rows['scores']['offset'], 21)
        self.assertEqual(rows['scores']['count'], 3)
        self.assertEqual(rows['items']['size'], 10)
        nested = {r['path']: r['offset'] for r in p.layout(depth=1)}
        self.assertEqual(nested['items[0].b'], 37)

    def test_unknown_type(self):
        with self.assertRaisesRegex(pdef.PdefError, 'unknown type'):
            pdef.Pdef('mystery x').size()

    def test_diff(self):
        old, new = pdef.Pdef(PDEF), pdef.Pdef(PDEF.replace('bool flags[5]', 'bool flags[6]\nint extra'))
        report = pdef.diff(old, new)
        self.assertEqual(report['size']['delta'], 5)
        self.assertEqual(report['fields']['added'], ['extra'])
        self.assertEqual(report['fields']['changed'], {'flags': {'old': 5, 'new': 6}})


def make_elf():
    """ELF64 with an r-x segment at VA 0 (file 0x1000) and an rw- one at VA 0x1000 (file 0x2000)."""
    code = bytearray(0x100)
    # 0x10: lea rsi, [rip + disp] -> string at 0x1000
    code[0x10:0x17] = b'\x48\x8d\x35' + struct.pack('<i', 0x1000 - 0x17)
    # 0x20: call 0x80
    code[0x20:0x25] = b'\xe8' + struct.pack('<i', 0x80 - 0x25)
    # 0x30: mov dword [rip + disp], 1 -> 0x1010 (imm32 follows the displacement)
    code[0x30:0x3a] = b'\xc7\x05' + struct.pack('<i', 0x1010 - 0x3a) + struct.pack('<I', 1)
    # 0x40: movss xmm0, [rip + disp] -> 0x1010
    code[0x40:0x48] = b'\xf3\x0f\x10\x05' + struct.pack('<i', 0x1010 - 0x48)
    code[0x80] = 0xC3
    data = bytearray(0x100)
    data[0:6] = b'hello\0'
    rela_va = 0x1040
    struct.pack_into('<QQq', data, 0x40, 0x1020, 8, 0x80)  # RELATIVE: *(0x1020) = base + 0x80
    dynamic = struct.pack('<qQqQqQ', 7, rela_va, 8, 24, 0, 0)
    data[0x80:0x80 + len(dynamic)] = dynamic

    phdrs = [(1, 5, 0x1000, 0, len(code), len(code)), (1, 6, 0x2000, 0x1000, len(data), 0x200),
             (2, 6, 0x2080, 0x1080, len(dynamic), len(dynamic))]
    header = bytearray(64)
    header[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<HHIQQQIHHH', header, 16, 3, 62, 1, 0, 64, 0, 0, 64, 56, len(phdrs))
    blob = bytearray(0x2100)
    blob[:64] = header
    for i, (kind, flags, offset, vaddr, filesz, memsz) in enumerate(phdrs):
        struct.pack_into('<IIQQQQQQ', blob, 64 + i * 56, kind, flags, offset, vaddr, vaddr, filesz, memsz, 0x1000)
    blob[0x1000:0x1100] = code
    blob[0x2000:0x2100] = data
    return bytes(blob)


class PrxInspectTests(unittest.TestCase):
    def setUp(self):
        self.module = prx_inspect.Module(make_elf())

    def test_addresses(self):
        self.assertEqual(self.module.va_to_offset(0x10), 0x1010)
        self.assertEqual(self.module.offset_to_va(0x2005), 0x1005)
        self.assertIsNone(self.module.va_to_offset(0x1150))  # bss: mapped but not in the file
        self.assertEqual(self.module.read(0x1150, 4), b'\0' * 4)

    def test_relocations(self):
        self.assertEqual(self.module.relative, {0x1020: 0x80})
        self.assertEqual(self.module.pointer(0x1020), 0x80)

    def test_code_refs(self):
        kinds = {(h['va'], h['kind']) for h in self.module.code_refs(0x1000, 0x1001)}
        self.assertEqual(kinds, {(0x10, 'lea')})
        self.assertEqual([(h['va'], h['kind']) for h in self.module.code_refs(0x80, 0x81)], [(0x20, 'call')])
        found = {(h['va'], h['kind']) for h in self.module.code_refs(0x1010, 0x1011)}
        self.assertEqual(found, {(0x30, 'mov-imm32'), (0x40, 'sse-load')})
        self.assertEqual(self.module.data_refs(0x80, 0x81)[0]['va'], 0x1020)

    def test_cli_xrefs_string(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'm.elf'
            path.write_bytes(make_elf())
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(prx_inspect.main(['xrefs', str(path), '--string', 'hello', '--exact']), 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result['targets'], ['0x1000'])
            self.assertEqual(result['refs'][0]['va'], '0x10')
            with redirect_stdout(StringIO()) as out:
                prx_inspect.main(['find', str(path), 'e8 ?? ?? ?? 00'])
            self.assertEqual(json.loads(out.getvalue())['matches'][0]['va'], '0x20')

    def test_rejects_non_elf(self):
        with self.assertRaises(prx_inspect.ModuleError):
            prx_inspect.Module(b'\0' * 128)


if __name__ == '__main__':
    unittest.main()
