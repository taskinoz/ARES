import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r1_harness


class R1HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / 'Titanfall'
        self.r1 = self.game / 'r1'
        self.app = self.root / 'R1Delta/app-3.0.4'
        self.maps = self.root / 'build'
        (self.game / 'vpk').mkdir(parents=True)
        self.r1.mkdir(parents=True)
        self.app.mkdir(parents=True)
        (self.app / 'Titanfall.exe').write_bytes(b'')
        (self.r1 / 'GameInfo.txt').write_text('"GameInfo" {}')
        self.maps.mkdir()
        (self.maps / 'mp_test.bsp').write_bytes(b'BSP')
        (self.maps / 'mp_test_spawn.ent').write_text('ENT')
        (self.maps / 'mp_test.bsp.0000.bsp_lump').write_bytes(b'LUMP')
        (self.maps / 'mp_test.map').write_text('SOURCE')
        (self.maps / 'other.bsp').write_bytes(b'OTHER')
        (self.r1 / 'addonlist.txt').write_text('"AddonList"\n{\n"UserMod" "1"\n}\n')

    def prepare(self, maps=True):
        return r1_harness.prepare(self.app, self.game, self.maps if maps else None, 'mp_test',
                                  ['models/containers/barrel.mdl'] if maps else None, run_id='a' * 32)

    def test_native_ain_initialization_flag_is_explicit_and_typed(self):
        session = {'app': str(self.app), 'game': str(self.game)}
        with patch.object(r1_harness.subprocess, 'Popen') as launch:
            r1_harness.launch(session, 12345)
            self.assertNotIn(r1_harness.AIN_BUILD_FLAG, launch.call_args.args[0])
            r1_harness.launch(dict(session, build_navigation=True), 12345)
            self.assertEqual(launch.call_args.args[0].count(r1_harness.AIN_BUILD_FLAG), 1)
            self.assertEqual(launch.call_args.kwargs['cwd'], self.game)
            launch.reset_mock()
            with self.assertRaises(ValueError):
                r1_harness.launch(dict(session, build_navigation='yes'), 12345)
            launch.assert_not_called()

    def test_staging_copies_only_the_level_and_cleanup_preserves_other_addons(self):
        session = self.prepare()
        addon = Path(session['addon'])
        staged = sorted(p.name for p in (addon / 'maps').iterdir())
        self.assertEqual(staged, ['mp_test.bsp', 'mp_test.bsp.0000.bsp_lump', 'mp_test_spawn.ent'])
        self.assertIn('"addonContent_Map" "1"', (addon / 'addoninfo.txt').read_text())
        hook = (addon / 'scripts/vscripts/test/myscript.nut').read_text()
        self.assertIn('PrecacheModel( "models/containers/barrel.mdl" )', hook)
        self.assertIn('"ARES.TF1Harness.' + 'a' * 32 + '" "1"', (self.r1 / 'addonlist.txt').read_text())
        r1_harness.cleanup(session)
        self.assertFalse(addon.exists())
        listing = (self.r1 / 'addonlist.txt').read_text()
        self.assertIn('"UserMod" "1"', listing)
        self.assertNotIn('ARES.TF1Harness', listing)

    def test_missing_declared_spawn_sidecar_fails_before_addon_mutation(self):
        from test_tf1_sidecars import write_bsp
        write_bsp(self.maps / 'mp_test.bsp')
        (self.maps / 'mp_test_spawn.ent').unlink()
        original = (self.r1 / 'addonlist.txt').read_bytes()
        with self.assertRaisesRegex(ValueError, 'mp_test_spawn.ent'):
            self.prepare()
        self.assertEqual((self.r1 / 'addonlist.txt').read_bytes(), original)
        self.assertFalse((self.r1 / 'addons').exists())

    def test_drop_model_files_are_staged_from_a_loose_tree(self):
        dump = self.root / 'assets_dump/models/containers'
        dump.mkdir(parents=True)
        for name in ('barrel.mdl', 'barrel.vvd', 'barrel.dx11.vtx', 'barrel.phy', 'barrel.txt', 'barrel_lid.mdl'):
            (dump / name).write_bytes(b'x')
        session = r1_harness.prepare(self.app, self.game, self.maps, 'mp_test', [], run_id='a' * 32,
                                     model_source=self.root / 'assets_dump')
        addon = Path(session['addon'])
        staged = sorted(p.name for p in (addon / 'models/containers').iterdir())
        self.assertEqual(staged, ['barrel.dx11.vtx', 'barrel.mdl', 'barrel.phy', 'barrel.vvd'])
        r1_harness.cleanup(session)
        self.assertFalse(addon.exists())
        with self.assertRaisesRegex(ValueError, 'crate.mdl is not in'):
            r1_harness.prepare(self.app, self.game, self.maps, 'mp_test', ['models/containers/crate.mdl'],
                               run_id='b' * 32, model_source=self.root / 'assets_dump')
        self.assertFalse((self.r1 / 'addons' / ('ARES.TF1Harness.' + 'b' * 32)).exists())

    def test_material_dependencies_are_staged_and_removed(self):
        source = self.root / 'assets'
        material = source / 'materials/water/test.vmt'
        material.parent.mkdir(parents=True)
        material.write_text('Water {}')
        material.with_suffix('.vtf').write_bytes(b'texture')
        session = r1_harness.prepare(self.app, self.game, self.maps, 'mp_test',
                                     material_source=source)
        addon = Path(session['addon'])
        self.assertEqual((addon / 'materials/water/test.vmt').read_text(), 'Water {}')
        self.assertEqual((addon / 'materials/water/test.vtf').read_bytes(), b'texture')
        r1_harness.cleanup(session)
        self.assertFalse(addon.exists())

    def test_material_tree_rejects_scripts_before_staging(self):
        source = self.root / 'assets'
        (source / 'materials').mkdir(parents=True)
        (source / 'materials/unexpected.nut').write_text('script')
        before = (self.r1 / 'addonlist.txt').read_bytes()
        with self.assertRaisesRegex(ValueError, 'unsupported material file'):
            r1_harness.prepare(self.app, self.game, self.maps, 'mp_test', material_source=source)
        self.assertEqual((self.r1 / 'addonlist.txt').read_bytes(), before)
        self.assertFalse((self.r1 / 'addons').exists())
        (source / 'materials/unexpected.nut').unlink()
        with self.assertRaisesRegex(ValueError, 'empty'):
            r1_harness.material_files(source)

    def test_cleanup_accepts_the_games_tab_indented_listing(self):
        session = self.prepare()
        name = Path(session['addon']).name
        (self.r1 / 'addonlist.txt').write_text(f'"AddonList"\n{{\n\t"UserMod"\t\t"1"\n\t"{name}"\t\t"1"\n}}\n')
        r1_harness.cleanup(session)
        self.assertEqual((self.r1 / 'addonlist.txt').read_text(), '"AddonList"\n{\n\t"UserMod"\t\t"1"\n}\n')

    def test_existing_precache_hook_is_not_shadowed(self):
        other = self.r1 / 'addons/UserMod/scripts/vscripts/test/myscript.nut'
        other.parent.mkdir(parents=True)
        other.write_text('// user script')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.r1 / 'addons' / ('ARES.TF1Harness.' + 'a' * 32)).exists())

    def test_retail_map_with_drops_stages_only_the_precache_hook(self):
        session = r1_harness.prepare(self.app, self.game, None, 'mp_test', [], run_id='b' * 32)
        addon = Path(session['addon'])
        self.assertFalse((addon / 'maps').exists())
        self.assertIn(r1_harness.DEFAULT_MODEL, (addon / 'scripts/vscripts/test/myscript.nut').read_text())
        self.assertIn('"addonContent_Map" "0"', (addon / 'addoninfo.txt').read_text())
        r1_harness.cleanup(session)
        self.assertFalse(addon.exists())

    def test_retail_map_stages_nothing(self):
        session = self.prepare(maps=False)
        self.assertIsNone(session['addon'])
        self.assertFalse((self.r1 / 'addons').exists())
        r1_harness.cleanup(session)
        self.assertEqual((self.r1 / 'addonlist.txt').read_text(), '"AddonList"\n{\n"UserMod" "1"\n}\n')

    def test_changed_addon_prevents_cleanup(self):
        session = self.prepare()
        (Path(session['addon']) / 'addoninfo.txt').write_text('user changes')
        with self.assertRaises(ValueError):
            r1_harness.cleanup(session)
        self.assertTrue(Path(session['addon']).exists())

    def test_unsupported_addon_list_is_not_rewritten(self):
        (self.r1 / 'addonlist.txt').write_text('"AddonList" { "Nested" { } }')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse((self.r1 / 'addons').exists())

    def test_cubemap_balls(self):
        checks = r1_harness.validate_checks({'views': [[0, 0, 0, 10, 90]], 'cubemap_balls': True})
        self.assertTrue(checks['cubemap_balls'])
        self.assertFalse(r1_harness.validate_checks({})['cubemap_balls'])
        for bad in ({'cubemap_balls': True}, {'views': [[0, 0, 0, 0, 0]], 'cubemap_balls': 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                r1_harness.validate_checks(bad)
        script = r1_harness.balls_script(2, [0, 0, 0, 15, 90])
        self.assertIn('b.kv.model = "models/dev/envballs.mdl"', script)
        self.assertIn('SetAngles( Vector( 15.0, 90.0, 0 ) )', script)
        self.assertIn('"[ARES] BALLS 2 valid="', script)
        self.assertIn('::ARES_Balls <- b\n}', script)  # newslot needs a line break before the brace

    def test_check_validation_matches_tfo_schema(self):
        checks = r1_harness.validate_checks({
            'traces': [[0, 0, 10, 0, 0, 0]], 'hulls': [[0, 0, 10, 0, 0, 0, -8, -8, 0, 8, 8, 72]],
            'drops': [[0, 0, 10]], 'drop_models': ['models/containers/barrel.mdl'], 'drop_wait': 2,
            'drop_samples': True, 'expect': {'trace_z': [[0, -1, 1]]}})
        self.assertTrue(checks['drop_samples'])
        for bad in ({'hulls': [[0, 0, 0, 0, 0, 0, 8, 0, 0, -8, 0, 0]]},
                    {'drops': [[0, 0, 0]], 'drop_models': ['../x.mdl']},
                    {'drop_wait': 0}, {'traces': [[0, 0, float('nan'), 0, 0, 0]]},
                    {'expect': {'trace_z': [[0, 2, 1]]}}):
            with self.assertRaises(ValueError):
                r1_harness.validate_checks(bad)

    def test_trace_script_matches_tfo_event_format(self):
        script = r1_harness.trace_script([[1, 2, 3, 4, 5, 6, -1, -1, -1, 1, 1, 1]], 7, True)
        self.assertIn('TraceHull( Vector( 1.0000, 2.0000, 3.0000 )', script)
        self.assertIn('"[ARES] HULL 7 fraction=" + r.fraction + " end=" + r.endPos.z', script)
        self.assertIn('TRACE_COLLISION_GROUP_NONE );', script)

    def test_trace_masks_select_constants_per_batch(self):
        rows = [[0, 0, 10, 0, 0, 0]] * 2
        script = r1_harness.trace_script(rows, 120, False, ['shot', 'water'])
        self.assertIn('TRACE_MASK_SHOT,', script)
        self.assertIn('TRACE_MASK_WATER,', script)
        self.assertIn('TRACE 120', script)
        self.assertIn('TRACE 121', script)
        with self.assertRaises(ValueError):
            r1_harness.validate_checks({'traces': rows, 'trace_masks': ['shot']})
        with self.assertRaises(ValueError):
            r1_harness.trace_script(rows, 0, False, ['water', 'bad'])

    def test_sequential_drops_keep_indices_and_destroy_before_next_spawn(self):
        calls = []
        class FakeControl:
            def squirrel(self, script):
                if 'CreateEntity' in script:
                    calls.append('spawn')
                    return ['SPAWNED 0 valid=true']
                if 'p.Destroy()' in script:
                    calls.append('destroy')
                    return []
                calls.append('sample')
                return ['DROP 0 z=0.5']
        checks = r1_harness.validate_checks({'drops': [[0, 0, 32], [128, 0, 32]],
                                            'drop_sequential': True, 'drop_wait': 1})
        events = []
        with patch('r1_harness.time.sleep'):
            r1_harness.run_checks(FakeControl(), checks, 0, self.root, events, [])
        self.assertEqual(calls, ['spawn', 'sample', 'destroy', 'spawn', 'sample', 'destroy'])
        self.assertEqual(events, ['SPAWNED 0 valid=true', 'DROP 0 z=0.5',
                                  'SPAWNED 1 valid=true', 'DROP 1 z=0.5'])
        with self.assertRaises(ValueError):
            r1_harness.validate_checks({'drop_sequential': 'true'})

    def test_view_hold_is_cancelled_on_success_and_capture_failure(self):
        for capture_ok in (True, False):
            scripts = []
            commands = []
            class FakeControl:
                def squirrel(self, script, context='server'):
                    scripts.append(script)
                    return ['VIEW 0 origin=(vector : (0, 0, 128))'] if 'printl' in script else []
                def console(self, command):
                    commands.append(command)
            checks = r1_harness.validate_checks({'views': [[0, 0, 128, 0, 90]]})
            shots = []
            with patch('r1_harness.time.sleep'), patch('r1_harness.capture_window', return_value=capture_ok):
                if capture_ok:
                    r1_harness.run_checks(FakeControl(), checks, 0, self.root, [], shots)
                else:
                    with self.assertRaisesRegex(RuntimeError, 'screenshot capture failed'):
                        r1_harness.run_checks(FakeControl(), checks, 0, self.root, [], shots)
            self.assertEqual(commands, ['unpause nomsg', 'sv_cheats 1', 'noclip', 'noclip'])
            self.assertEqual(len(shots), int(capture_ok))
            self.assertIn('::ARES_ViewToken = ""', scripts[-1])
            self.assertEqual(sum('thread ARES_HoldView' in s for s in scripts), 1)


if __name__ == '__main__':
    unittest.main()
