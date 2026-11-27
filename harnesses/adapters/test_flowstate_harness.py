import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path

import flowstate_harness as fh


def fake_install(root):
    game = root / 'Flowstate'
    for name in ('r5apex_dx12.exe', 'r5apex_ds.exe'):
        (game / name).parent.mkdir(parents=True, exist_ok=True)
        (game / name).write_bytes(b'MZ' + b'\0' * 64)
    (game / 'paks' / 'Win64').mkdir(parents=True)
    (game / 'paks' / 'Win64' / 'common.rpak').write_bytes(b'pak')
    (game / 'platform' / 'cfg').mkdir(parents=True)
    (game / 'platform' / 'cfg' / 'game.cfg').write_text('exec x')
    (game / 'platform' / 'scripts').mkdir()
    (game / 'platform' / 'scripts' / 'a.nut').write_text('// script')
    (game / 'mods').mkdir()
    (game / 'mods' / 'mods.vdf').write_text('"ModList"\n{\n\t"CafeFPS.DevBox"\t"1"\n}\n')
    (game / 'cfg').mkdir()
    (game / 'cfg' / 'config_default_pc.cfg').write_text('// cfg')
    return game


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.game = fake_install(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_assets_are_linked_and_written_folders_copied(self):
        runtime = fh.prepare_runtime(self.game, self.root / 'runtime')
        pak = runtime / 'paks' / 'Win64' / 'common.rpak'
        self.assertTrue(pak.samefile(self.game / 'paks' / 'Win64' / 'common.rpak'))
        self.assertTrue((runtime / 'platform' / 'scripts' / 'a.nut').samefile(self.game / 'platform' / 'scripts' / 'a.nut'))
        for relative in ('platform/cfg/game.cfg', 'mods/mods.vdf', 'cfg/config_default_pc.cfg'):
            copy = runtime / relative
            self.assertTrue(copy.is_file(), relative)
            self.assertFalse(copy.samefile(self.game / relative), relative)

    def test_refuses_unsafe_runtimes(self):
        with self.assertRaises(ValueError):
            fh.prepare_runtime(self.game, self.game / 'inner')
        (self.root / 'other').mkdir()
        with self.assertRaises(ValueError):  # existing folder without the marker
            fh.prepare_runtime(self.game, self.root / 'other')
        with self.assertRaises(ValueError):
            fh.prepare_runtime(self.root / 'missing', self.root / 'runtime2')

    def test_mod_goes_into_the_copy_only(self):
        runtime = fh.prepare_runtime(self.game, self.root / 'runtime')
        before = (self.game / 'mods' / 'mods.vdf').read_text()
        mod = fh.write_mod(runtime, [[0, 0, 100, 10, 90]], 'ares_' + 'a' * 32)
        self.assertEqual((self.game / 'mods' / 'mods.vdf').read_text(), before)
        self.assertFalse((self.game / 'mods' / fh.MOD_DIR).exists())
        listing = (runtime / 'mods' / 'mods.vdf').read_text()
        self.assertIn('"ARES.Harness"\t"1"', listing)
        self.assertIn('"CafeFPS.DevBox"', listing)
        self.assertIn('"realm"\t\t\t"client"', (mod / 'mod.vdf').read_text())
        fh.write_mod(runtime, [[0, 0, 100, 10, 90]], 'ares_' + 'b' * 32)  # a second run does not duplicate it
        self.assertEqual((runtime / 'mods' / 'mods.vdf').read_text().count('ARES.Harness'), 1)
        with self.assertRaises(ValueError):
            fh.write_mod(self.game, [[0, 0, 0, 0, 0]], 'ares_x')


class ProfileTests(unittest.TestCase):
    def test_settings_are_restored_and_new_files_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'Apex_s30'
            (root / 'local').mkdir(parents=True)
            settings = root / 'local' / 'videoconfig.txt'
            settings.write_bytes(b'"setting.fullscreen" "1"')
            (root / 'local' / 'psoCache.pso').write_bytes(b'cache')
            backup = fh.backup_profile(root)
            settings.write_bytes(b'"setting.fullscreen" "0"')   # the run changes it
            (root / 'profile').mkdir()
            (root / 'profile' / 'profile.cfg').write_text('new')  # and creates one
            created = fh.restore_profile(backup)
            self.assertEqual(settings.read_bytes(), b'"setting.fullscreen" "1"')
            self.assertEqual(created, [str(root / 'profile' / 'profile.cfg')])
            self.assertEqual(fh.backup_profile(Path(tmp) / 'missing')[1], {})


class ScriptTests(unittest.TestCase):
    def test_views_drive_the_world_crawler_camera(self):
        script = fh.mod_script([[1, 2, 3, 10, 90], [4, 5, 6, -5, 180]], 'ares_tok', hide_hud=True)
        self.assertIn('array<vector> origins = [ <1.000, 2.000, 3.000>, <4.000, 5.000, 6.000> ]', script)
        self.assertIn('array<vector> angles = [ <10.000, 90.000, 0.000>, <-5.000, 180.000, 0.000> ]', script)
        self.assertIn('CreateWorldCrawlerCamera()', script)
        self.assertIn('ClientCommand( "screenshot ares_tok_" + i )', script)
        self.assertIn('DevHud_ClientSet( true )', script)
        self.assertIn('DevHud_ClientSet( false )', script)
        self.assertIn('global function ClientCodeCallback_ARES_Harness_ModInit', script)
        self.assertNotIn('cl_drawhud', fh.mod_script([[0, 0, 0, 0, 0]], 'ares_tok', hide_hud=False))

    def test_cubemap_balls_follow_the_camera(self):
        script = fh.mod_script([[1, 2, 3, 10, 90]], 'ares_tok', balls=True)
        self.assertIn('CreateClientSidePropDynamic( <0, 0, 0>, <0, 0, 0>, $"mdl/dev/envballs.rmdl" )', script)
        self.assertIn('balls.SetOrigin( base + origin )', script)
        self.assertIn('balls.SetAngles( angles[i] )', script)
        self.assertIn('balls.Destroy()', script)
        self.assertNotIn('envballs', fh.mod_script([[1, 2, 3, 10, 90]], 'ares_tok'))

    def test_rejects_bad_views_and_tokens(self):
        for views in ([], [[1, 2, 3]], [[1, 2, 3, 4, 'x']], [[1, 2, 3, 4, True]], 'x'):
            with self.assertRaises(ValueError):
                fh.validate_views(views)
        with self.assertRaises(ValueError):
            fh.mod_script([[0, 0, 0, 0, 0]], 'ares tok"; quit')


class NetConsoleTests(unittest.TestCase):
    def test_frame_layout(self):
        data = fh.frame(1, 77, fh.request(0, 'status', 'status'))
        magic, size = struct.unpack_from('>II', data)
        self.assertEqual((magic, size), (0x6E6F4352, len(data) - 8))
        self.assertEqual(data[:4], b'noCR')
        envelope = fh.parse(data[8:])
        header = fh.parse(envelope[1])
        self.assertEqual((header[1], header[2]), (1, 77))
        body = fh.parse(envelope[4])
        self.assertEqual((body[3], body[4], body[5]), (0, b'status', b'status'))

    def test_session_auth_and_command_against_a_fake_server(self):
        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]
        seen = []

        def reply(conn, sequence, text):
            body = fh.field(3, 0) + fh.field(4, text)
            envelope = fh.field(1, fh.field(1, sequence) + fh.field(2, 9)) + fh.field(4, body)
            conn.sendall(struct.pack('>II', fh.FRAME_MAGIC, len(envelope)) + envelope)

        def serve():
            conn, _ = server.accept()
            with conn:
                buffer = b''
                for expected in (1, 2):
                    while len(buffer) < 8 or len(buffer) < 8 + struct.unpack_from('>II', buffer)[1]:
                        buffer += conn.recv(65536)
                    size = struct.unpack_from('>II', buffer)[1]
                    envelope = fh.parse(buffer[8:8 + size])
                    buffer = buffer[8 + size:]
                    header, body = fh.parse(envelope[1]), fh.parse(envelope[4])
                    seen.append((header[1], header[2], body.get(3, 0), body.get(4), body.get(5)))
                    if expected == 1:
                        reply(conn, 1, 'Authentication successful.\n')

        thread = threading.Thread(target=serve)
        thread.start()
        console = fh.NetConsole(port, 'secret-password')
        console.command('script printt( 1 )')
        console.close()
        thread.join(5)
        server.close()
        self.assertEqual([s[0] for s in seen], [1, 2])          # sequence rises by one
        self.assertEqual(seen[0][1], seen[1][1])                # one session id per connection
        self.assertEqual(seen[0][2:4], (1, b'secret-password'))
        self.assertEqual(seen[1][2:], (0, b'script', b'script printt( 1 )'))
        with self.assertRaises(ValueError):
            fh.NetConsole.command(console, 'a\nb')


if __name__ == '__main__':
    unittest.main()
