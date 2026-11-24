import os
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from tfo_harness import SCRIPT, MOD, main, CrashHandlers, game_crashed, target_map_loaded, target_map_started, write_mod, expectation_errors, height_expectations, screenshot_results, view_errors


@contextmanager
def process_directory():
    temporary = tempfile.TemporaryDirectory()
    try:
        yield temporary.name
    finally:
        # Windows can retain an executable image lock briefly after all process
        # handles close (including filter-driver work). Retry cleanup, but keep
        # a bounded failure rather than ignoring leaked processes or files.
        deadline = time.monotonic() + 5
        while True:
            try:
                temporary.cleanup()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)


def close_process(process):
    if process.poll() is None:
        process.terminate()
    process.wait(timeout=5)
    # CPython retains the Windows process handle until Popen is collected. Close
    # it before TemporaryDirectory removes the executable's image section.
    process._handle.Close()


class TfoHarnessTests(unittest.TestCase):
    def test_missing_entity_sidecar_fails_before_mod_install(self):
        from test_tf1_sidecars import write_bsp
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            maps = root / 'maps'
            maps.mkdir()
            write_bsp(maps / 'mp_probe.bsp')
            with self.assertRaisesRegex(ValueError, 'mp_probe_spawn.ent'):
                write_mod(root / 'game', maps, {})
            self.assertFalse((root / 'game/Mods' / MOD).exists())

    def test_internal_capture_requires_owned_fresh_decodable_image(self):
        from PIL import Image
        from tfo_harness import collect_internal_capture
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder)
            screenshots = game/'Data/screenshots'
            screenshots.mkdir(parents=True)
            name = 'ares_' + 'a' * 32 + '_0'
            source = screenshots/(name + '.jpg')
            target = game/'view.png'
            source.write_bytes(b'incomplete')
            self.assertFalse(collect_internal_capture(game, name, target, 0))
            Image.new('RGB', (16, 16), 'red').save(source)
            self.assertFalse(collect_internal_capture(game, name, target, time.time_ns() + 10**9))
            self.assertTrue(source.exists())
            self.assertTrue(collect_internal_capture(game, name, target, 0))
            self.assertFalse(source.exists())
            with Image.open(target) as frame:
                self.assertEqual(frame.size, (16, 16))
            with self.assertRaises(ValueError):
                collect_internal_capture(game, '../user-image', target, 0)

    def test_old_output_images_cannot_satisfy_a_failed_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'view0.png').write_bytes(b'old')
            (root / 'view99.png').write_bytes(b'old')
            shots, errors = screenshot_results(root, 2, set())
            self.assertEqual(shots, [])
            self.assertEqual(len(errors), 2)
            shots, errors = screenshot_results(root, 2, {'0', '1'})
            self.assertEqual([p.name for p in shots], ['view0.png'])
            self.assertEqual(len(errors), 1)  # view1 has no file despite a claimed capture
            self.assertEqual(screenshot_results(root, 0, set()), ([], []))

    def test_missing_or_drifting_view_pose_cannot_pass(self):
        view = [[0, 0, 128, 0, 90]]
        valid = 'VIEW 0 origin=(vector : (0, 0, 127.6)) eye=(vector : (0, 0, 187.6)) alive=true'
        self.assertEqual(view_errors([valid], view), [])
        for event in (valid.replace('alive=true', 'alive=false'), valid.replace(' alive=true', ''),
                      valid.replace('187.6', 'nan')):
            self.assertTrue(view_errors([event], view))
        for events in ([], ['VIEW 0'], [valid, valid], [valid.replace('127.6', '0.0')],
                       [valid.replace('127.6', 'nan')]):
            self.assertTrue(view_errors(events, view))

    def test_failed_launch_restores_enabled_mod_bytes(self):
        with process_directory() as folder:
            root = Path(folder)
            game = root/'game'
            maps = root/'maps'
            maps.mkdir()
            base = game/'Mods/TFORevive.Core/mod/scripts/vscripts'
            base.mkdir(parents=True)
            (base/'_mapspawn.nut').write_text('// base')
            enabled = game/'Mods/enabledmods.json'
            original = b'\xef\xbb\xbf{ "existing": true }\n'
            enabled.write_bytes(original)
            arguments = ['tfo_harness','--game',str(game),'--maps',str(maps),
                         '--map','mp_test','--output',str(root/'output')]
            with patch('sys.argv',arguments), patch('tfo_harness.subprocess.Popen',side_effect=OSError('test launch failure')):
                with self.assertRaisesRegex(OSError,'test launch failure'):
                    main()
            self.assertEqual(enabled.read_bytes(),original)
            self.assertFalse((game/'Mods'/MOD).exists())

    def test_geometry_sweeps_ignore_the_harness_player(self):
        calls = [line for line in SCRIPT.splitlines() if 'local result = Trace' in line]
        self.assertEqual(len(calls),2)
        self.assertTrue(all(', player, mask,' in line for line in calls))
        self.assertIn('ARES_TraceMasks[i] : TRACE_MASK_PLAYERSOLID', SCRIPT)
        self.assertIn('ARES_HullMasks[i] : TRACE_MASK_PLAYERSOLID', SCRIPT)

    def test_trace_masks_are_allowlisted_and_match_rows(self):
        from tfo_harness import validate_masks
        self.assertEqual(validate_masks([], 2, 'test'), [])
        self.assertEqual(validate_masks(['shot', 'water'], 2, 'test'), ['shot', 'water'])
        for values in (None, 'shot', ['solid'], ['shot', None], ['shot', 1],
                       ['shot', 'unknown'], ['shot', 'water);evil()']):
            with self.assertRaises(ValueError):
                validate_masks(values, 2, 'test')

    def test_lobby_loading_does_not_count_as_target(self):
        text = ('Raw command line: +map mp_test\n'
                'UICodeCallback_LevelLoadingStarted: mp_lobby_02\n'
                'UICodeCallback_LevelLoadingFinished: mp_lobby_02 (error: false)\n')
        self.assertFalse(target_map_started(text, 'mp_test'))
        self.assertFalse(target_map_loaded(text, 'mp_test'))
        text += 'UICodeCallback_LevelLoadingStarted: mp_test\n'
        self.assertTrue(target_map_started(text, 'mp_test'))
        self.assertFalse(target_map_loaded(text, 'mp_test'))
        text += 'UICodeCallback_LevelLoadingFinished: mp_test (error: false) [1 seconds]\n'
        self.assertTrue(target_map_loaded(text, 'mp_test'))
        self.assertFalse(target_map_started(text, 'mp_tes'))

    def test_expectations_detect_missed_collision(self):
        events = ['TRACE 0 fraction=0.999756 end=0.03125 solid=false', 'DROP 0 z=65.3125', 'DONE']
        expected = {'trace_z': [[0, 63.9, 64.1]], 'drop_z': [[0, 65, 66]]}
        errors = expectation_errors(events, expected)
        self.assertEqual(len(errors), 1)
        self.assertIn('TRACE 0', errors[0])
        events[0] = 'TRACE 0 fraction=0.499756 end=64.0313 solid=false'
        self.assertEqual(expectation_errors(events, expected), [])
        self.assertTrue(expectation_errors(['DROP 0 z=gone'], {'drop_z': [[0, 65, 66]]}))
        self.assertTrue(expectation_errors(['DROP 0 z=nan'], {'drop_z': [[0, 65, 66]]}))
        self.assertTrue(expectation_errors([], {'drop_z': [[0, 65, 66]]}))

    def test_expectations_reject_invalid_ranges(self):
        for expect in ({'unknown': []}, {'trace_z': [[0, 5, 4]]}, {'drop_z': [[-1, 0, 1]]},
                       {'drop_z': [[0, 0, float('inf')]]}, {'drop_z': [[True, 0, 1]]}):
            with self.assertRaises(ValueError):
                height_expectations(expect)

    def test_hull_expectations_detect_wrong_contact(self):
        expected = {'hull_z': [[0, 57.9, 58.1]]}
        self.assertEqual(expectation_errors(['HULL 0 fraction=0.5 end=58.03125 solid=false'], expected), [])
        self.assertTrue(expectation_errors(['HULL 0 fraction=1 end=-32 solid=false'], expected))
        self.assertTrue(expectation_errors([], expected))

    def test_hull_rows_are_validated_before_mod_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for hulls in (None, [[0]*11], [[0]*11+[float('nan')]], [[0]*6+[1,0,0,0,0,0]]):
                with self.assertRaises(ValueError):
                    write_mod(root/'game', root/'maps', {'hulls': hulls})
                self.assertFalse((root/'game').exists())

    def test_crash_after_done_still_closes_handler(self):
        self.assertTrue(game_crashed('[ARES] DONE', 1))
        self.assertTrue(game_crashed('A CRASH HAS BEEN CAPTURED', None))
        self.assertFalse(game_crashed('[ARES] DONE', 0))
        self.assertFalse(game_crashed('', None))

    def test_startup_stack_overflow_is_retried(self):
        from tfo_harness import retry_launch, STACK_OVERFLOW
        startup = 'A CRASH HAS BEEN CAPTURED!\nSCRIPT ERROR: [UI] _utility_ui'
        self.assertTrue(retry_launch(startup, 'mp_x', STACK_OVERFLOW))
        self.assertFalse(retry_launch(startup, 'mp_x', 1))
        self.assertTrue(retry_launch('', 'mp_x', 0))
        self.assertFalse(retry_launch('UICodeCallback_LevelLoadingStarted: mp_x', 'mp_x', STACK_OVERFLOW))

    def test_drop_models_and_observation_duration(self):
        with process_directory() as folder:
            root = Path(folder)
            maps = root/'maps'
            maps.mkdir()
            base = root/'game/Mods/TFORevive.Core/mod/scripts/vscripts'
            base.mkdir(parents=True)
            (base/'_mapspawn.nut').write_text('// base')
            model = 'models/containers/barrel.mdl'
            mod = write_mod(root/'game', maps, {'drops':[[0,0,32]],'drop_models':[model],'drop_wait':8})
            script = (mod/'mod/scripts/vscripts/ares_tf1_harness.nut').read_text()
            self.assertIn('::ARES_DropModels <- ["'+model+'"]',script)
            self.assertIn('::ARES_DropWait <- 8.0',script)
            self.assertEqual(script.count('wait ARES_DropWait'),2)
            self.assertIn('if ( !ARES_DropModels.len() ) prop.SetModel',script)

    def test_freecam_views_place_the_camera_not_the_player(self):
        with process_directory() as folder:
            root = Path(folder)
            maps = root/'maps'
            maps.mkdir()
            base = root/'game/Mods/TFORevive.Core/mod/scripts/vscripts'
            base.mkdir(parents=True)
            (base/'_mapspawn.nut').write_text('// base')
            mod = write_mod(root/'game', maps, {'views': [[1500, 0, 800, 20, 180]], 'freecam': True})
            script = (mod/'mod/scripts/vscripts/ares_tf1_harness.nut').read_text()
            self.assertIn('::ARES_Freecam <- true', script)
            self.assertIn('"freecam_setpos " + v[0]', script)
            self.assertIn('ClientCommand( player, "freecam_disable" )', script)
            shutil.rmtree(mod)
            with self.assertRaises(ValueError):
                write_mod(root/'game', maps, {'views': [[0, 0, 0, 0, 0]], 'freecam': 'yes'})
        event = 'VIEW 0 freecam=true pose=1500,0,800,20,180'
        self.assertEqual(view_errors([event], [[1500, 0, 800, 20, 180]]), [])
        self.assertTrue(view_errors([event, event], [[1500, 0, 800, 20, 180]]))

    def test_invalid_drop_probe_configuration_is_rejected_before_install(self):
        with process_directory() as folder:
            root = Path(folder)
            invalid = ({'drop_models':['models/a.mdl']},
                       {'drops':[[0,0,0]],'drop_models':['models/../secret.mdl']},
                       {'drops':[[0,0,0]],'drop_models':['models/a.mdl"; quit']},
                       {'drop_wait':0},{'drop_wait':float('nan')},{'drop_wait':True})
            for checks in invalid:
                with self.assertRaises(ValueError):
                    write_mod(root/'game',root/'maps',checks)
                self.assertFalse((root/'game/Mods'/MOD).exists())

    def test_sequential_drops_are_opt_in(self):
        with process_directory() as folder:
            root = Path(folder)
            maps = root / 'maps'
            maps.mkdir()
            base = root / 'game/Mods/TFORevive.Core/mod/scripts/vscripts'
            base.mkdir(parents=True)
            (base / '_mapspawn.nut').write_text('// base')
            for enabled in (False, True):
                mod = write_mod(root / 'game', maps, {'drop_sequential': enabled, 'drops': [[1, 2, 3]]})
                script = (mod / 'mod/scripts/vscripts/ares_tf1_harness.nut').read_text()
                self.assertIn('::ARES_DropSequential <- ' + str(enabled).lower(), script)
                self.assertIn('::ARES_Drops <- [[1.000, 2.000, 3.000]]', script)
                self.assertNotIn('%DROP_SEQUENTIAL%', script)
                shutil.rmtree(mod)

    @unittest.skipUnless(os.name == 'nt', 'Windows process APIs')
    def test_replacement_handler_and_normal_exit(self):
        with process_directory() as folder:
            game = Path(folder)
            (game / 'Bin').mkdir()
            executable = game / 'Bin/crashpad_handler.exe'
            shutil.copyfile(Path(os.environ['SystemRoot']) / 'System32/cmd.exe', executable)
            processes = []
            tracker = CrashHandlers(os.getpid(), game)
            try:
                for _ in range(2):
                    process = subprocess.Popen([str(executable), '/c', 'for /L %i in (1,0,2) do @ver >nul'],
                                               creationflags=subprocess.CREATE_NO_WINDOW)
                    processes.append(process)
                    for _ in range(20):
                        tracker.capture()
                        if process.pid in tracker.handles:
                            break
                        time.sleep(0.1)
                    self.assertIn(process.pid, tracker.handles)
                tracker.close(False)
                self.assertTrue(all(process.poll() is None for process in processes))
                tracker.capture()
                tracker.close(True)
                for process in processes:
                    process.wait(timeout=5)
            finally:
                tracker.close(False)
                for process in processes:
                    close_process(process)

    @unittest.skipUnless(os.name == 'nt', 'Windows process APIs')
    def test_nested_crash_dialog_and_foreign_install(self):
        with process_directory() as folder:
            game = Path(folder) / 'game'
            (game / 'Bin').mkdir(parents=True)
            foreign = Path(folder) / 'foreign/messagebox-win.exe'
            foreign.parent.mkdir()
            handler = game / 'Bin/crashpad_handler.exe'
            dialog = game / 'Bin/messagebox-win.exe'
            for path in (handler, dialog, foreign):
                shutil.copyfile(Path(os.environ['SystemRoot']) / 'System32/cmd.exe', path)
            script = game / 'dialog.cmd'
            script.write_text('@echo off\n"' + str(dialog) + '" /c "for /L %%i in (1,0,2) do @ver >nul"\n')
            foreign_process = subprocess.Popen([str(foreign), '/c', 'for /L %i in (1,0,2) do @ver >nul'],
                                               creationflags=subprocess.CREATE_NO_WINDOW)
            parent = subprocess.Popen([str(handler), '/c', str(script)],
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            tracker = CrashHandlers(os.getpid(), game)
            try:
                for _ in range(40):
                    tracker.capture()
                    if len(tracker.handles) == 2:
                        break
                    time.sleep(0.1)
                self.assertIn(parent.pid, tracker.handles)
                self.assertEqual(len(tracker.handles), 2, 'nested dialog must be tracked')
                self.assertNotIn(foreign_process.pid, tracker.handles)
                tracker.close(True)
                parent.wait(timeout=5)
                self.assertIsNone(foreign_process.poll(), 'another install must remain running')
            finally:
                tracker.close(True)
                for process in (parent, foreign_process):
                    close_process(process)

    @unittest.skipUnless(os.name == 'nt', 'Windows process APIs')
    def test_only_owned_crash_handler_is_stopped(self):
        with process_directory() as folder:
            game = Path(folder)
            (game / 'Bin').mkdir()
            executable = game / 'Bin/crashpad_handler.exe'
            shutil.copyfile(Path(os.environ['SystemRoot']) / 'System32/cmd.exe', executable)
            process = subprocess.Popen([str(executable), '/c', 'for /L %i in (1,0,2) do @ver >nul'],
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                tracker = CrashHandlers(os.getpid(), game)
                for _ in range(20):
                    tracker.capture()
                    if process.pid in tracker.handles:
                        break
                    time.sleep(0.1)
                self.assertIn(process.pid, tracker.handles)
                tracker.close(True)
                process.wait(timeout=5)
            finally:
                close_process(process)


if __name__ == '__main__':
    unittest.main()
