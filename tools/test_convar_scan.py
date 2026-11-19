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

    def store(self, target):
        """mov [rip+target], rax"""
        at = self.here()
        self.code += b'\x48\x89\x05' + rel(target, at + 7)

    def pointer_call(self, pointer, name, default, flags, help_text):
        """The legacy R5Reloaded SDK: call [rip+pointer] after a long setup."""
        self.code += b'\xcc' * 4
        self.lea(0x4C, 0x05, self.string(default))          # lea r8, default
        self.lea(0x48, 0x15, self.string(name))             # lea rdx, name
        self.code += b'\x41\xb9' + struct.pack('<I', flags)  # mov r9d, flags
        self.code += b'\x48\xc7\x40\x18\x00\x00\x00\x00' * 16  # mov qword [rax+18h], 0 (object setup)
        self.lea(0x48, 0x05, self.string(help_text))        # lea rax, help
        self.code += b'\x48\x89\x44\x24\x20'                # mov [rsp+20h], rax
        at = self.here()
        self.code += b'\xff\x15' + rel(pointer, at + 6) + b'\xc3'

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

    @unittest.skipIf(capstone is None, 'needs capstone')
    def test_inline_registration(self):
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

    @unittest.skipIf(capstone is None, 'needs capstone')
    def test_apex_inline_convar_with_interleaved_stores(self):
        b = Builder()
        field = BASE + DATA_RVA + 0x1800
        default = b.string('1.0')
        b.data = b.data.ljust(0x1800 + 56, b'\x00') + struct.pack('<Q', default) + bytes(64)
        b.code += b'\xcc' * 4
        b.lea(0x48, 0x05, b.string('host_timescale'))       # lea rax, name
        at = b.here()
        b.code += b'\xc6\x05' + rel(field - 8, at + 7) + b'\x00'  # mov byte [F-8], 0
        b.store(field)
        b.lea(0x48, 0x05, b.string(''))                     # help and usage share ""
        b.store(field + 8)
        b.store(field + 16)
        b.code += b'\x31\xc0'                               # xor eax, eax
        at = b.here()
        b.code += b'\x89\x05' + rel(field + 32, at + 6) + b'\xc3'  # mov dword [F+32], eax
        found = cs.inline_registrations(cs.PE(b.write(self.root / 'r5apex.exe')))
        entry = found['host_timescale']
        self.assertEqual((entry['default'], entry['flags'], entry['help']), ('1.0', 0, ''))

    @unittest.skipIf(capstone is None, 'needs capstone')
    def test_script_binding_is_not_a_convar(self):
        b = Builder()
        field = BASE + DATA_RVA + 0x1800
        b.code += b'\xcc' * 4
        native = b.here()
        b.lea(0x48, 0x05, b.string('table'))
        b.store(field)
        b.lea(0x48, 0x05, b.string('xyz startPos, xyz endPos'))
        b.store(field + 8)
        b.lea(0x48, 0x05, native)                           # the native function
        b.store(field + 0x40)
        at = b.here()
        b.code += b'\xc7\x05' + rel(field + 16, at + 10) + struct.pack('<I', 0x20) + b'\xc3'
        self.assertEqual(cs.inline_registrations(cs.PE(b.write(self.root / 'server.dll'))), {})

    @unittest.skipIf(capstone is None, 'needs capstone')
    def test_heap_command_filled_through_a_register(self):
        b = Builder()
        b.code += b'\xcc' * 4
        callback = b.here()
        b.code += b'\xc3' + b'\xcc' * 3
        for text, disp in (('reload_playlists', 0x18), ('Reloads the playlists file.', 0x20)):
            b.lea(0x48, 0x05, b.string(text))
            b.code += b'\x48\x89\x42' + bytes([disp])        # mov [rdx+disp], rax
        b.lea(0x48, 0x05, callback)
        b.code += b'\x48\x89\x42\x50'                       # mov [rdx+50h], rax
        b.code += b'\xc7\x42\x38' + struct.pack('<I', 0x80000) + b'\xc3'  # mov dword [rdx+38h], flags
        found = cs.inline_registrations(cs.PE(b.write(self.root / 'gamesdk.dll')))
        self.assertEqual((found['reload_playlists']['kind'], found['reload_playlists']['flag_names']),
                         ('command', ['RELEASE']))

    def test_apex_static_command_objects(self):
        b = Builder()
        b.code += b'\xcc' * 8 + b'\xc3'
        callback = BASE + TEXT_RVA + 8
        vtable, usage = b.string('vtable-placeholder'), b.string('')
        names = [f'apex_cmd_{i}' for i in range(20)]
        for i, name in enumerate(names):
            name_va, help_va = b.string(name), b.string(f'Help {i}.')
            while len(b.data) % 8:
                b.data += b'\x00'
            b.data += struct.pack('<QQQQQQQQQQQ', vtable, 0, 0, name_va, help_va, usage, 0,
                                  0x80000 if i == 1 else 0, callback, 0, callback)
        found = cs.static_objects(cs.PE(b.write(self.root / 'r5apex.exe')))
        self.assertEqual(sorted(found), sorted(names))
        self.assertEqual(found['apex_cmd_1']['flag_names'], ['RELEASE'])

    @unittest.skipIf(capstone is None, 'needs capstone')
    def test_constructor_called_through_a_pointer(self):
        b = Builder()
        pointer = BASE + DATA_RVA + 0x1F00
        for i in range(21):
            b.pointer_call(pointer, f'sdk_var_{i}', str(i), 0x2, f'Help {i}.')
        found = cs.scan(b.write(self.root / 'gamesdk.dll'))
        self.assertEqual(len(found), 21)
        entry = found['sdk_var_4']
        self.assertEqual((entry['default'], entry['help'], entry['constructor']), ('4', 'Help 4.', 'ptr:' + hex(pointer)))

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
