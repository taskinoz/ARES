import copy
import unittest

from navigation_checks import navigation_errors, navigation_script, validate_navigation
from r1_harness import validate_checks


PROBE = dict(start=[-400, 0, 1], goal=[400, 0, 0], nodes=8, samples=5, floor_z=0,
             forbidden_box=[[-64, -144, -1], [64, 144, 192]])


def events():
    def pose(label, x, y):
        return f'NAVIGATION {label} valid=true alive=true origin=(vector : ({x}, {y}, 0.03125))'
    return ['NAVIGATION CONTEXT nodes=8 neighbors=8', pose('START', -400, 0)] + [
        pose(f'SAMPLE {i}', *point) for i, point in enumerate(
            [(-200, -90), (0, -166), (200, -90), (400, 0), (400, 0)])]


class NavigationTests(unittest.TestCase):
    def test_valid_probe_and_route(self):
        self.assertEqual(validate_navigation(PROBE), PROBE)
        self.assertEqual(validate_checks({'navigation_probe': PROBE})['navigation_probe'], PROBE)
        self.assertEqual(navigation_errors(events(), PROBE), [])
        self.assertEqual(navigation_errors([], None), [])
        self.assertEqual(navigation_script(None), '')

    def test_bad_config(self):
        for key, value in [('start', [0, 0]), ('goal', [-400, 0, 1]), ('nodes', True),
                           ('samples', 4), ('samples', 31), ('wait', float('nan')),
                           ('radius', 100), ('floor_z', None),
                           ('forbidden_box', [[0, 0, 0], [0, 1, 1]]), ('extra', 1)]:
            probe = copy.deepcopy(PROBE)
            probe[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_navigation(probe)

    def test_absent_duplicate_dead_nonfinite_and_wrong_start(self):
        rows = events()
        variants = [rows[:-1], rows + [rows[-1]],
                    [e.replace('alive=true', 'alive=false') for e in rows],
                    [e.replace('-400, 0,', 'nan, 0,') for e in rows],
                    [e.replace('-400, 0,', '-300, 0,') for e in rows],
                    rows + ['NAVIGATION ERROR failed']]
        for bad in variants:
            with self.subTest(events=bad):
                self.assertTrue(navigation_errors(bad, PROBE))

    def test_stationary_grunt_and_incomplete_hold_fail(self):
        rows = events()
        rows[-1] = rows[-1].replace('400, 0,', '-400, 0,')
        self.assertTrue(navigation_errors(rows, PROBE))
        rows = [e if 'SAMPLE' not in e else e[:e.index('origin=')] +
                'origin=(vector : (-400, 0, 0.03125))' for e in events()]
        self.assertTrue(navigation_errors(rows, PROBE))

    def test_obstacle_and_floor_fail(self):
        for old, new in [('0, -166,', '0, 0,'), ('0.03125', '30')]:
            self.assertTrue(navigation_errors([e.replace(old, new) for e in events()], PROBE))

    def test_disconnected_and_missing_context_fail(self):
        self.assertTrue(navigation_errors([e.replace('neighbors=8', 'neighbors=1') for e in events()], PROBE))
        self.assertTrue(navigation_errors(events()[1:], PROBE))

    def test_script_has_natural_goal_and_bounded_waits(self):
        script = navigation_script(PROBE)
        self.assertIn('SendAIToAssaultPoint', script)
        self.assertIn('i<90', script)
        self.assertIn('npc.Destroy()', script)
        self.assertNotIn('SetOrigin', script)
        self.assertNotIn('SetGameState', script)
        self.assertNotIn('%CONFIG%', script)
