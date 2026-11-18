import contextlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

import convar_scan as cs

try:
    import capstone  # noqa: F401
except ImportError:
    capstone = None

BASE = 0x180000000
TEXT_RVA, TEXT_RAW, DATA_RVA, DATA_RAW, SIZE = 0x1000, 0x400, 0x3000, 0x2400, 0x2000


def rel(target, after):
    return struct.pack('<i', target - after)


class Builder:
    """A minimal PE32+ with one code and one data section."""

    def __init__(self):
        self.code = bytearray()
        self.data = bytearray(b'\0' * 16)
        self.strings = {}

    def string(self, text):
        if text not in self.strings:
            self.strings[text] = BASE + DATA_RVA + len(self.data)
            self.data += text.encode() + b'\0'
        return self.strings[text]

    def here(self):
        return BASE + TEXT_RVA + len(self.code)

    def lea(self, prefix, modrm, target):
        at = self.here()
        self.code += bytes([prefix, 0x8D, modrm]) + rel(target, at + 7)

    def convar(self, ctor, name, default, flags, help_text):
        self.code += b'\xcc' * 4
        self.code += b'\x48\x83\xec\x38'                    # sub rsp, 38h
        self.lea(0x48, 0x05, self.string(help_text))        # lea rax, help
        self.lea(0x4C, 0x05, self.string(default))          # lea r8, default
        self.lea(0x48, 0x15, self.string(name))             # lea rdx, name
        self.code += b'\x41\xb9' + struct.pack('<I', flags)  # mov r9d, flags
        self.code += b'\x48\x89\x44\x24\x20'                # mov [rsp+20h], rax
        at = self.here()
        self.code += b'\xe8' + rel(ctor, at + 5) + b'\x48\x83\xc4\x38\xc3'

    def inline(self, name, help_text, flags, field):
        self.code += b'\xcc' * 4
        for text, target in ((name, field), (help_text, field + 8)):
            self.lea(0x48, 0x05, self.string(text))
            at = self.here()
            self.code += b'\x48\x89\x05' + rel(target, at + 7)
        at = self.here()
        self.code += b'\xc7\x05' + rel(field + 16, at + 10) + struct.pack('<I', flags) + b'\xc3'

    def write(self, path):
        image = bytearray(TEXT_RAW)
        image[:2] = b'MZ'
        struct.pack_into('<I', image, 0x3C, 0x40)
        image[0x40:0x44] = b'PE\0\0'
        struct.pack_into('<HHIIIHH', image, 0x44, 0x8664, 2, 0, 0, 0, 0xF0, 0x22)
        struct.pack_into('<H', image, 0x58, 0x20B)
        struct.pack_into('<Q', image, 0x58 + 24, BASE)
        sections = 0x58 + 0xF0
        for i, (name, rva, raw, flags) in enumerate(((b'.text', TEXT_RVA, TEXT_RAW, 0x60000020),
                                                    (b'.rdata', DATA_RVA, DATA_RAW, 0x40000040))):
            at = sections + i * 40
            image[at:at + 8] = name.ljust(8, b'\0')
            struct.pack_into('<IIII', image, at + 8, SIZE, rva, SIZE, raw)
            struct.pack_into('<I', image, at + 36, flags)
        image += bytes(self.code).ljust(SIZE, b'\xcc') + bytes(self.data).ljust(SIZE, b'\0')
        Path(path).write_bytes(image)
        return path


class ConvarScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rejects_non_pe(self):
        bad = self.root / 'x.dll'
        bad.write_bytes(b'not a pe')
        with self.assertRaises(ValueError):
            cs.PE(bad)

    def test_inline_registration_without_capstone(self):
        b = Builder()
        field = BASE + DATA_RVA + 0x1800
        b.inline('sv_gravity', 'World gravity.', 0x2100, field)
        b.inline('ai_misaligned', 'Wrong field.', 0x4000, field + 0x40)
        b.code[-15:-11] = rel(field + 0x40 + 24, b.here() - 10)  # flags not at name+16
        pe = cs.PE(b.write(self.root / 'server.dll'))
        found = cs.inline_registrations(pe)
        self.assertEqual(list(found), ['sv_gravity'])
        self.assertEqual(found['sv_gravity']['help'], 'World gravity.')
        self.assertEqual(found['sv_gravity']['flag_names'], ['NOTIFY', 'REPLICATED'])

    def test_static_command_objects_without_capstone(self):
        b = Builder()
        b.code += b'\xcc' * 8 + b'\xc3'
        callback = BASE + TEXT_RVA + 8
        vtable = b.string('vtable-placeholder')
        names = [f'freecam_cmd_{i}' for i in range(20)]
        for i, name in enumerate(names):
            name_va, help_va = b.string(name), b.string(f'Help {i}.' if i else '')
            while len(b.data) % 8:
                b.data += b'\0'
            b.data += struct.pack('<QQQQQQQQQQQ', vtable, 0, 0, name_va, help_va, 0x4000 if i == 1 else 0,
                                  0, 0, 0, callback, 0)
        found = cs.static_objects(cs.PE(b.write(self.root / 'client.dll')))
        self.assertEqual(sorted(found), sorted(names))
        self.assertEqual((found['freecam_cmd_1']['help'], found['freecam_cmd_1']['flag_names']), ('Help 1.', ['CHEAT']))
        self.assertIsNone(found['freecam_cmd_0']['help'])
        self.assertEqual(cs.static_objects(cs.PE(self.root / 'client.dll'), min_sites=21), {})

    def test_flag_names(self):
        self.assertEqual(cs.decode_flags(0x4002), ['DEVELOPMENTONLY', 'CHEAT'])
        self.assertEqual(cs.decode_flags(None), [])

    @unittest.skipIf(capstone is None, 'needs capstone')
    def test_constructor_found_from_call_shape(self):
        b = Builder()
        ctor = BASE + TEXT_RVA + 0x10
        b.code += b'\xcc' * 0x10 + b'\xc3'
        for i in range(21):
            b.convar(ctor, f'test_var_{i}', str(i), 0x4000 if i % 2 else 0x2, f'Help {i}.')
        dll = b.write(self.root / 'client.dll')
        found = cs.scan(dll)
        self.assertEqual(len(found), 21)
        entry = found['test_var_3']
        self.assertEqual((entry['kind'], entry['default'], entry['flags'], entry['help']),
                         ('convar', '3', 0x4000, 'Help 3.'))
        self.assertEqual(found['test_var_2']['flag_names'], ['DEVELOPMENTONLY'])
        out = self.root / 'out.json'
        verified = self.root / 'verified.json'
        verified.write_text(json.dumps({'test_var_0': {}}))
        with contextlib.redirect_stdout(io.StringIO()):
            cs.main([str(out), str(dll), '--verified', str(verified)])
        report = json.loads(out.read_text())
        self.assertEqual(report['count'], 21)
        self.assertTrue(report['entries']['test_var_0']['in_game'])
        self.assertFalse(report['entries']['test_var_1']['in_game'])

    @unittest.skipIf(capstone is None, 'needs capstone')
    def test_too_few_sites_is_not_a_constructor(self):
        b = Builder()
        ctor = BASE + TEXT_RVA + 0x10
        b.code += b'\xcc' * 0x10 + b'\xc3'
        for i in range(5):
            b.convar(ctor, f'test_var_{i}', '0', 0, 'Help.')
        self.assertEqual(cs.scan(b.write(self.root / 'client.dll')), {})


if __name__ == '__main__':
    unittest.main()
