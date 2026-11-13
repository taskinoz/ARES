"""Tests for shadps4_harness.py and goldhen.py; no emulator, console or game files needed."""
import ftplib
import io
import socket
import struct
import sys
import tempfile
import threading
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import goldhen  # noqa: E402
import shadps4_harness as shad  # noqa: E402

LOG = """[Core.Linker] <Info> module.cpp:129 LoadModuleToMemory: Loading module eboot.bin to 0x55a0000
[Core.Linker] <Info> module.cpp:129 LoadModuleToMemory: Loading module engine.sprx to 0x82000000
[Tty] <Info> [stdout] game ready
"""


class ShadPs4Tests(unittest.TestCase):
    def test_modules(self):
        modules = shad.parse_modules(LOG.splitlines())
        self.assertEqual(modules, {'eboot.bin': 0x55a0000, 'engine.sprx': 0x82000000})
        self.assertEqual(shad.module_base(modules, 'engine'), 0x82000000)
        self.assertEqual(shad.module_base(modules, 'ENGINE.prx'), 0x82000000)
        self.assertIsNone(shad.module_base(modules, 'client'))
        self.assertEqual(shad.resolve_address({'module': 'engine', 'offset': '0x10'}, modules), 0x82000010)
        with self.assertRaisesRegex(ValueError, 'not in the log'):
            shad.resolve_address({'module': 'client'}, modules)

    def test_scan_prefers_first_match(self):
        import re
        lines = ['ok line', 'guest crash here', 'game ready']
        self.assertEqual(shad.scan(lines, re.compile('ready'), re.compile('crash')), ('failure', 'guest crash here'))
        self.assertEqual(shad.scan(lines[2:], re.compile('ready'), re.compile('crash')), ('success', 'game ready'))
        self.assertEqual(shad.scan(['x'], re.compile('ready'), None), (None, None))

    def test_log_follower_reads_only_new_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'shad_log.txt'
            path.write_text('old line\n')
            follower = shad.LogFollower(path)
            with path.open('a') as log:
                log.write('first\nsecond part')
            self.assertEqual(follower.poll(), ['first'])
            with path.open('a') as log:
                log.write('ial\n')
            self.assertEqual(follower.poll(), ['second partial'])
            path.write_text('new\n')  # truncated by a fresh run
            self.assertEqual(follower.poll(), ['new'])

    def test_png_and_black_detection(self):
        width, height = 4, 3
        black = bytes(width * height * 3)
        self.assertTrue(shad.image_stats(black, width, height)['black'])
        lit = bytearray(black)
        lit[0:3] = b'\xff\xff\xff'
        self.assertFalse(shad.image_stats(bytes(lit), width, height)['black'])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'x.png'
            shad.write_png(path, width, height, bytes(lit))
            data = path.read_bytes()
            self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II', data[16:24]), (width, height))
            idat = data.index(b'IDAT')
            length = struct.unpack('>I', data[idat - 4:idat])[0]
            raw = zlib.decompress(data[idat + 4:idat + 4 + length])
            self.assertEqual(raw[:4], b'\0\xff\xff\xff')

    def test_steps_validation(self):
        shad.validate_steps([{'wait': 'x'}, {'key': 'cross', 'times': 2}, {'capture': 'a.png', 'expect': 'not-black'}])
        for bad in ([{'key': 'jump'}], [{'capture': '../a.png'}], [{'sleep': 1, 'bogus': 1}], [{}], {'wait': 'x'}):
            with self.assertRaises(ValueError):
                shad.validate_steps(bad)

    def test_decode(self):
        value = shad.decode(struct.pack('<I', 2) + b'\0' * 4)
        self.assertEqual((value['u32'], value['u64']), (2, '0x2'))
        self.assertEqual(shad.decode(b'abc\0')['string'], 'abc')

    def test_build_result_shape(self):
        report = {'status': 'success', 'checks': [{'name': 'x', 'passed': True}], 'errors': [], 'screenshots': ['a.png']}
        result = shad.build_result(report, 0, 'r2', Path('game/CUSA00000/eboot.bin'))
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['operation'], 'shadps4-boot:CUSA00000')
        self.assertIn({'path': 'a.png', 'type': 'screenshot'}, result['artifacts'])
        report['status'] = 'timeout'
        self.assertEqual(shad.build_result(report, 0, 'r2', Path('e'))['status'], 'failure')


class FakeFtp:
    """Enough of ftplib.FTP for goldhen.upload/enable_plugin."""

    def __init__(self, files=None):
        self.files = dict(files or {})
        self.dirs = {'/'}

    def mkd(self, path):
        if path in self.dirs:
            raise ftplib.error_perm('550 exists')
        self.dirs.add(path)

    def retrlines(self, command, callback):
        folder = command.split(' ', 1)[1].rstrip('/') or ''
        for path, data in self.files.items():
            parent, name = path.rsplit('/', 1)
            if parent == folder:
                callback(f'-rw-rw-rw- 1 root root {len(data)} Jan 1 00:00 {name}')

    def storbinary(self, command, source, blocksize=8192):
        self.files[command.split(' ', 1)[1]] = source.read()

    def retrbinary(self, command, callback):
        path = command.split(' ', 1)[1]
        if path not in self.files:
            raise ftplib.error_perm('550 missing')
        callback(self.files[path])


class GoldhenTests(unittest.TestCase):
    def test_upload_skips_matching_sizes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'mods' / 'A').mkdir(parents=True)
            (root / 'mods' / 'A' / 'mod.json').write_text('{}')
            (root / 'mods' / 'b.txt').write_text('hello')
            ftp = FakeFtp({'/data/x/mods/b.txt': b'HELLO'})
            pairs = goldhen.tree_files(root / 'mods', '/data/x/mods')
            result = goldhen.upload(ftp, pairs)
            self.assertEqual(result['files'], 2)
            self.assertEqual(result['sent_paths'], ['/data/x/mods/A/mod.json'])
            self.assertEqual(goldhen.upload(ftp, pairs, always=True)['sent'], 2)
            with self.assertRaises(ValueError):
                goldhen.upload(ftp, [(root / 'mods' / 'b.txt', 'relative/b.txt')])

    def test_plugins_ini(self):
        text, changed = goldhen.add_plugin_section('', 'CUSA04013', '/data/p.prx')
        self.assertTrue(changed)
        self.assertIn('[CUSA04013]\n/data/p.prx\n', text)
        self.assertEqual(goldhen.add_plugin_section(text, 'CUSA04013', '/data/p.prx'), (text, False))
        merged, changed = goldhen.add_plugin_section('[default]\n/a.prx\n[CUSA04013]\n/b.prx\n\n[CUSA1]\n/c.prx\n',
                                                     'CUSA04013', '/data/p.prx')
        self.assertTrue(changed)
        self.assertIn('[CUSA04013]\n/b.prx\n/data/p.prx\n\n[CUSA1]', merged)
        self.assertIn('[default]\n/a.prx', merged)

    def test_enable_plugin_backs_up(self):
        with tempfile.TemporaryDirectory() as folder:
            ftp = FakeFtp({goldhen.PLUGINS_INI: b'[default]\n/a.prx\n'})
            backup = Path(folder) / 'plugins.ini.bak'
            self.assertTrue(goldhen.enable_plugin(ftp, 'CUSA04013', '/p.prx', backup)['changed'])
            self.assertEqual(backup.read_text(), '[default]\n/a.prx\n')
            self.assertIn(b'[CUSA04013]\n/p.prx', ftp.files[goldhen.PLUGINS_INI])

    def test_klog_records_until_pattern(self):
        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]

        def serve():
            connection, _ = server.accept()
            connection.sendall(b'boot line\n')
            connection.sendall(b'[Game] ready\n')
            connection.recv(1)  # held open until the client closes
            connection.close()
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'klog.txt'
            stats = goldhen.record_klog('127.0.0.1', out, port, duration=10, until=r'\] ready')
            self.assertTrue(stats['matched'])
            self.assertIn(b'[Game] ready', out.read_bytes())
        server.close()

    def test_lastboot_summary(self):
        log = '\n'.join([
            '--- connected 1 ---', '[Mod] loaded', 'old crash? no',
            '--- connected 2 ---', '[Mod] loaded', '[Mod] playerToken=abc', 'kernel noise',
            'A user thread receives a fatal signal',
            '# signal: 11 (SIGSEGV)', '# thread name: GameMain',
            '# rip: 0000000000401010  BrF: 0000000000500020  BrT: 0000000000900000',
            '# /app0/bin/my_mod.prx', '#   text: 0000000000400000:0000000000402000',
            '# /app0/eboot.bin', '#   text: 0000000000500000:0000000000600000',
        ])
        summary = goldhen.summarise(log, tag='[Mod]')
        self.assertEqual(summary['lines'], ['[Mod] loaded', '[line left out: may contain a secret]'])
        crash = summary['crash']
        self.assertIn('# signal: 11 (SIGSEGV)', crash['details'])
        self.assertEqual(crash['registers']['rip'], {'address': '0x401010', 'module': 'my_mod.prx',
                                                     'segment': 'text', 'offset': '0x1010'})
        self.assertEqual(crash['registers']['BrF']['module'], 'eboot.bin')
        self.assertIsNone(crash['registers']['BrT']['module'])
        with self.assertRaises(ValueError):
            goldhen.summarise('nothing', boot_marker='never')


if __name__ == '__main__':
    unittest.main()
