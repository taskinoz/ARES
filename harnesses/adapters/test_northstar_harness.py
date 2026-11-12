"""Northstar harness tests that need no game install."""
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import northstar_harness as nh
from tfo_harness import expectation_errors


def post(controller, path, body, token=None):
    request = urllib.request.Request(f'http://127.0.0.1:{controller.port}{path}', data=json.dumps(body).encode(),
                                     headers={'Authorization': 'Bearer ' + (token or controller.token)})
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, response.read()


def write_mod(folder, name, version='1.0.0'):
    folder.mkdir(parents=True)
    (folder / 'mod.json').write_text(json.dumps({'Name': name, 'Version': version}))
    return folder


def fake_game(root):
    game = root / 'Titanfall2'
    game.mkdir()
    (game / 'NorthstarLauncher.exe').write_bytes(b'')
    for core in nh.CORE_MODS:
        write_mod(game / 'R2Northstar' / 'mods' / core, core, '1.31.15')
    return game


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.controller = nh.Controller().start()

    def tearDown(self):
        self.controller.stop()

    def test_rejects_wrong_token(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            post(self.controller, '/poll/ui', {}, token='wrong')
        self.assertEqual(caught.exception.code, 403)

    def test_poll_records_state_and_delivers_one_job(self):
        status, _ = post(self.controller, '/poll/ui', {'ready': True})
        self.assertEqual(status, 204)
        self.assertTrue(self.controller.state('ui')['ready'])
        job_id = self.controller.submit('ui', 'console', command='status')
        status, body = post(self.controller, '/poll/ui', {})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'id': job_id, 'op': 'console', 'command': 'status'})
        self.assertEqual(post(self.controller, '/poll/ui', {})[0], 204)

    def test_run_returns_ack_and_raises_on_failure(self):
        def game():
            for ok in (True, False):
                while True:
                    status, body = post(self.controller, '/poll/server', {})
                    if status == 200:
                        break
                    time.sleep(0.05)
                job = json.loads(body)
                post(self.controller, '/ack', {'id': job['id'], 'ok': ok, 'data': {'fraction': 0.5},
                                               'error': None if ok else 'boom', 'stage': 'x'})
        threading.Thread(target=game, daemon=True).start()
        self.assertEqual(self.controller.run('server', 'trace', timeout=5)['data'], {'fraction': 0.5})
        with self.assertRaisesRegex(RuntimeError, 'boom'):
            self.controller.run('server', 'trace', timeout=5)

    def test_run_stops_when_game_exits(self):
        with self.assertRaisesRegex(RuntimeError, 'game exited'):
            self.controller.run('ui', 'status', timeout=5, alive=lambda: False)

    def test_unknown_context_rejected(self):
        with self.assertRaises(ValueError):
            self.controller.submit('menu', 'status')


class CheckTests(unittest.TestCase):
    def test_valid_checks(self):
        checks = {'traces': [[0, 0, 64, 0, 0, -64]], 'hulls': [[0, 0, 64, 0, 0, -64, -16, -16, 0, 16, 16, 72]],
                  'views': [[0, 0, 64, 10, 90]], 'spawn_probe': [[0, 0, 0]], 'mode_check': True,
                  'console': ['sv_cheats 1'], 'expect': {'trace_z': [[0, -1, 1]]}}
        self.assertIs(nh.validate_checks(checks), checks)

    def test_invalid_checks(self):
        for checks in ({'trace': []}, {'traces': [[0, 0, 0]]}, {'hulls': [[0] * 6 + [16, 0, 0, -16, 0, 0]]},
                       {'console': ['quit; rm']}, {'settle': -1}, {'mode_check': 1},
                       {'expect': {'drop_z': [[0, 0, 1]]}}, {'traces': [[float('nan')] * 6]}):
            with self.subTest(checks=checks), self.assertRaises(ValueError):
                nh.validate_checks(checks)

    def test_trace_events_feed_tfo_expectations(self):
        event = nh.trace_event('TRACE', 0, {'fraction': 0.5, 'end': [1, 2, 16.03], 'startSolid': False,
                                            'normal': [0, 0, 1]})
        self.assertEqual(expectation_errors([event], {'trace_z': [[0, 16, 16.1]]}), [])
        self.assertTrue(expectation_errors([event], {'trace_z': [[0, 0, 1]]}))


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.game = fake_game(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def session(self, **kw):
        return nh.Session(self.game, self.root / 'out', **kw)

    def test_profile_name_must_be_separate(self):
        with self.assertRaises(ValueError):
            self.session(profile='R2Northstar')

    def test_prepare_creates_profile_and_close_restores_everything(self):
        mod = write_mod(self.root / 'src' / 'My.Mod', 'My.Mod', '0.2.0')
        (mod / 'mod').mkdir()
        build = self.root / 'build'
        build.mkdir()
        for name in ('mp_x.bsp', 'mp_x.ent', 'mp_x.bsp.0000.bsp_lump', 'mp_x.map', 'mp_y.bsp'):
            (build / name).write_bytes(b'x')
        session = self.session(mods=[mod], maps=build, map_name='mp_x')
        session.prepare()
        profile = self.game / 'R2AresHarness'
        enabled = json.loads((profile / 'enabledmods.json').read_text())
        self.assertEqual(enabled['Northstar.Client'], {'1.31.15': True})
        self.assertEqual(enabled['My.Mod'], {'0.2.0': True})
        self.assertEqual(enabled[nh.HARNESS_MOD], {'0.1.0': True})
        self.assertEqual(enabled['ARES.MapUnderTest'], {'0.0.1': True})
        staged = sorted(p.name for p in (profile / 'mods' / 'ARES.MapUnderTest' / 'mod' / 'maps').iterdir())
        self.assertEqual(staged, ['mp_x.bsp', 'mp_x.bsp.0000.bsp_lump', 'mp_x.ent'])
        self.assertTrue((profile / 'mods' / nh.HARNESS_MOD / 'mod' / 'scripts' / 'vscripts' /
                         '_ares_map_harness.nut').exists())
        session.close()
        self.assertEqual(json.loads(session.enabled_backup), json.loads((profile / 'enabledmods.json').read_text()))
        self.assertNotIn('My.Mod', json.loads((profile / 'enabledmods.json').read_text()))
        self.assertEqual(sorted(p.name for p in (profile / 'mods').iterdir()), sorted(nh.CORE_MODS))

    def test_existing_profile_backup_is_byte_identical(self):
        session = self.session()
        session.ensure_profile()
        enabled_path = self.game / 'R2AresHarness' / 'enabledmods.json'
        original = b'\xef\xbb\xbf{"Version": 1, "Other.Mod": {"1.0.0": true, "2.0.0": true}}'
        enabled_path.write_bytes(original)
        session = self.session(enable_installed=['Other.Mod'])
        session.prepare()
        self.assertEqual(json.loads(enabled_path.read_text())['Other.Mod'], {'2.0.0': True})
        session.close()
        self.assertEqual(enabled_path.read_bytes(), original)

    def test_refuses_to_overwrite_unowned_mod(self):
        mod = write_mod(self.root / 'src' / 'My.Mod', 'My.Mod')
        session = self.session(mods=[mod])
        session.ensure_profile()
        write_mod(self.game / 'R2AresHarness' / 'mods' / 'My.Mod', 'My.Mod')
        with self.assertRaises(FileExistsError):
            session.prepare()
        session.close()
        self.assertTrue((self.game / 'R2AresHarness' / 'mods' / 'My.Mod' / 'mod.json').exists())

    def test_missing_bsp_rejected(self):
        build = self.root / 'build'
        build.mkdir()
        with self.assertRaises(FileNotFoundError):
            nh.map_files(build, 'mp_x')


class ResultTests(unittest.TestCase):
    def test_result_matches_contract_fields(self):
        report = {'map': 'mp_x', 'loaded': True, 'finished': True, 'checks': [{'name': 'view[0] captured', 'passed': True}],
                  'screenshots': ['view0.png'], 'errors': [], 'script_errors': []}
        result = nh.build_result(report, time.time(), 'tdm')
        schema = json.loads((Path(__file__).resolve().parents[1] / 'contracts' / 'result.schema.json').read_text())
        self.assertLessEqual(set(schema['required']), set(result))
        self.assertEqual(result['status'], 'success')
        report['errors'] = ['TRACE 0: expected Z in [0, 1], observed [5]']
        self.assertEqual(nh.build_result(report, time.time(), 'tdm')['status'], 'partial')


if __name__ == '__main__':
    unittest.main()
