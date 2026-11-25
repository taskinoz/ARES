"""Ion adapter tests that need no game install or game execution."""
import contextlib
import io
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

import ion_harness as ih


def temp_root(temp):
    """Canonical temp root; Windows CI exposes short 8.3 names from tempfile."""
    return Path(temp.name).resolve()


def write_mod(root, name, version='1.31.15'):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'mod.json').write_text(json.dumps({'Name': name, 'Version': version}))
    return root


def fixtures(root):
    game = root / 'Titanfall2'
    game.mkdir()
    (game / 'Titanfall2.exe').write_bytes(b'base-game')
    (game / 'r2' / 'maps').mkdir(parents=True)
    (game / 'r2' / 'maps' / 'mp_test.bsp').write_bytes(b'bsp')
    (game / 'r2' / 'cfg').mkdir()
    (game / 'r2' / 'cfg' / 'autoexec.cfg').write_text('from game', encoding='utf-8')
    (game / 'r2' / 'stats.txt').write_text('from game', encoding='utf-8')
    (game / 'r2' / 'screenshots').mkdir()
    (game / 'R2Northstar' / 'mods').mkdir(parents=True)
    (game / 'R2Northstar' / 'Northstar.dll').write_bytes(b'northstar-dll')
    write_mod(game / 'R2Northstar' / 'mods' / 'PlayerMod', 'PlayerMod')

    ion = root / 'IonRelease'
    ion.mkdir()
    (ion / 'NorthstarLauncher.exe').write_bytes(b'ion-launcher')
    (ion / 'R2Northstar' / 'mods').mkdir(parents=True)
    (ion / 'R2Northstar' / 'Northstar.dll').write_bytes(b'ion-dll')
    for core in ('Northstar.Client', 'Northstar.Custom', 'Northstar.CustomServers'):
        write_mod(ion / 'R2Northstar' / 'mods' / core, core)
    (ion / 'R2Northstar' / 'plugins').mkdir()
    (ion / 'R2Northstar' / 'plugins' / 'DiscordRPC.dll').write_bytes(b'discord')
    return game, ion


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = temp_root(self.temp)
        self.game, self.ion = fixtures(self.root)

    def test_rejects_non_game_and_nested_release(self):
        with self.assertRaises(ValueError):
            ih.validate_sources(self.root, self.ion)
        with self.assertRaises(ValueError):
            ih.validate_sources(self.game, self.game / 'R2Northstar')
        self.assertEqual(ih.validate_sources(self.game, self.ion), (self.game, self.ion))

    def test_release_version_reads_bom_and_missing_version_fails(self):
        self.assertEqual(ih.release_version(self.ion), '1.31.15')
        mod = self.ion / 'R2Northstar' / 'mods' / 'Northstar.Client' / 'mod.json'
        mod.write_text(json.dumps({'Name': 'Northstar.Client'}), encoding='utf-8-sig')
        with self.assertRaises(ValueError):
            ih.release_version(self.ion)


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = temp_root(self.temp)
        self.game, self.ion = fixtures(self.root)
        self.runtime = self.root / 'Titanfall2-Ion'

    def test_prepare_stages_ion_only_and_leaves_game_untouched(self):
        result = ih.prepare_runtime(self.game, self.ion, self.runtime)
        self.assertEqual(result, self.runtime)
        self.assertEqual((self.runtime / 'Titanfall2.exe').read_bytes(), b'base-game')
        self.assertEqual((self.runtime / 'r2/maps/mp_test.bsp').read_bytes(), b'bsp')
        self.assertEqual((self.runtime / 'R2Northstar/Northstar.dll').read_bytes(), b'ion-dll')
        self.assertTrue((self.runtime / 'R2Northstar/mods/Northstar.Custom').is_dir())
        self.assertTrue((self.runtime / 'R2Northstar/plugins/DiscordRPC.dll').is_file())
        # Northstar user mods and profiles are not migrated into Ion.
        self.assertFalse((self.runtime / 'R2Northstar/mods/PlayerMod').exists())
        self.assertTrue((self.game / 'R2Northstar/mods/PlayerMod').is_dir())
        self.assertEqual((self.game / 'R2Northstar/Northstar.dll').read_bytes(), b'northstar-dll')

        # Writable configuration is a copy, not a link back to the player install.
        (self.runtime / 'r2/cfg/autoexec.cfg').write_text('from runtime', encoding='utf-8')
        self.assertEqual((self.game / 'r2/cfg/autoexec.cfg').read_text(encoding='utf-8'), 'from game')
        (self.runtime / 'r2/stats.txt').write_text('from runtime', encoding='utf-8')
        self.assertEqual((self.game / 'r2/stats.txt').read_text(encoding='utf-8'), 'from game')

        marker = json.loads((self.runtime / ih.MARKER).read_text(encoding='utf-8'))
        self.assertEqual(marker['game'], ih._identity(self.game))
        self.assertEqual(marker['ion_version'], '1.31.15')
        provenance = json.loads((self.runtime / 'ares-ion-release.json').read_text(encoding='utf-8'))
        self.assertIn('R2Northstar/Northstar.dll', provenance['sha256'])

    def test_existing_unowned_runtime_is_refused(self):
        self.runtime.mkdir()
        (self.runtime / 'keep.txt').write_text('user data')
        with self.assertRaises(FileExistsError):
            ih.prepare_runtime(self.game, self.ion, self.runtime)
        self.assertEqual((self.runtime / 'keep.txt').read_text(), 'user data')

    def test_runtime_marker_prevents_mixing_sources(self):
        ih.prepare_runtime(self.game, self.ion, self.runtime)
        other = self.root / 'IonOther'
        shutil.copytree(self.ion, other)
        mod = other / 'R2Northstar' / 'mods' / 'Northstar.Client' / 'mod.json'
        mod.write_text(json.dumps({'Name': 'Northstar.Client', 'Version': '1.31.16'}))
        with self.assertRaisesRegex(ValueError, 'different'):
            ih.prepare_runtime(self.game, other, self.runtime)

    def test_nested_runtime_is_refused(self):
        with self.assertRaises(ValueError):
            ih.prepare_runtime(self.game, self.ion, self.game / 'Titanfall2-Ion')
        self.assertFalse((self.game / 'Titanfall2-Ion').exists())

    def test_runtime_containing_release_is_refused(self):
        with self.assertRaises(ValueError):
            ih.prepare_runtime(self.game, self.ion, self.root)
        self.assertFalse((self.root / 'Titanfall2.exe').exists())


class IonDllTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = temp_root(self.temp)
        self.game, self.ion = fixtures(self.root)
        self.runtime = ih.prepare_runtime(self.game, self.ion, self.root / 'Titanfall2-Ion')

    def test_profile_gets_ion_dll_not_source_northstar_dll(self):
        target = ih.stage_ion_dll(self.runtime, self.runtime / 'R2AresIon')
        self.assertEqual(target.read_bytes(), b'ion-dll')
        self.assertEqual((self.game / 'R2Northstar/Northstar.dll').read_bytes(), b'northstar-dll')
        self.assertEqual((self.runtime / 'R2Northstar/Northstar.dll').read_bytes(), b'ion-dll')

    def test_profile_gets_ion_plugins(self):
        ih.stage_ion_profile(self.runtime, self.runtime / 'R2AresIon')
        target = self.runtime / 'R2AresIon' / 'plugins' / 'DiscordRPC.dll'
        self.assertEqual(target.read_bytes(), b'discord')

    def test_launch_stages_dll_and_plugins_before_parent_launch(self):
        calls = []
        original = ih.nh.Session.launch

        def fake_launch(session):
            profile = session.profile
            calls.append(('launch', (profile / 'Northstar.dll').is_file(),
                          (profile / 'plugins' / 'DiscordRPC.dll').is_file()))

        ih.nh.Session.launch = fake_launch
        try:
            session = ih.IonSession(self.runtime, self.root / 'out', profile='R2AresIon')
            session.launch()
        finally:
            ih.nh.Session.launch = original
        self.assertEqual(calls, [('launch', True, True)])


class MainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = temp_root(self.temp)
        self.game, self.ion = fixtures(self.root)

    def test_profile_cannot_be_the_main_northstar_profile(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            ih.main(['--game', str(self.game), '--ion', str(self.ion),
                     '--profile', 'R2Northstar', '--prepare-only'])
        self.assertFalse((self.root / 'Titanfall2-Ion').exists())


class ResultTests(unittest.TestCase):
    def test_result_matches_contract_and_records_mcp(self):
        report = {'map': 'mp_test', 'loaded': True, 'finished': True, 'checks': [],
                  'screenshots': [], 'errors': [], 'script_errors': [],
                  'mcp': {'reachable': True, 'tools': ['execute_squirrel']}}
        result = ih.build_result(report, time.time(), 'tdm', Path('C:/Games/Titanfall2-Ion'), '1.31.15')
        schema = json.loads((Path(__file__).resolve().parents[1] / 'contracts' / 'result.schema.json').read_text())
        self.assertLessEqual(set(schema['required']), set(result))
        self.assertEqual(result['tool'], 'ion_harness')
        self.assertEqual(result['target'], 'r2')
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['details']['ion_version'], '1.31.15')
        report['mcp']['reachable'] = False
        self.assertEqual(ih.build_result(report, time.time(), 'tdm', 'runtime', '1.31.15')['status'], 'partial')

    def test_skipped_mcp_is_not_a_failed_check(self):
        report = {'map': 'mp_test', 'loaded': True, 'finished': True, 'checks': [],
                  'screenshots': [], 'errors': [], 'script_errors': [],
                  'mcp': {'reachable': False, 'skipped': True}}
        result = ih.build_result(report, time.time(), 'tdm', 'runtime', '1.31.15')
        self.assertEqual(result['status'], 'success')
        self.assertFalse(any(check['name'] == 'Ion MCP reachable' for check in result['checks']))

    def test_session_that_never_loaded_is_only_tool_level(self):
        report = {'map': 'mp_test', 'loaded': False, 'finished': False, 'checks': [],
                  'screenshots': [], 'errors': ['launch failed'], 'script_errors': [],
                  'mcp': {'reachable': False, 'skipped': True}}
        result = ih.build_result(report, time.time(), 'tdm', 'runtime', '1.31.15')
        self.assertEqual(result['verification'], 'tool')
        self.assertEqual(result['status'], 'failure')


if __name__ == '__main__':
    unittest.main()
