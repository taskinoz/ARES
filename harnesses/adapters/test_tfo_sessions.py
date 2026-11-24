"""Launch classification tests; poses are from real TFO crate reports (MRVN-Radiant phase 2)."""
import json
import tempfile
import unittest
from pathlib import Path

from physics_observations import rest_tilt
from tfo_sessions import classify, summarize

BOUNDS = 'bounds_mins=(vector : (-19.9, -10.3, -0.25)) bounds_maxs=(vector : (20.0, 10.3, 19.2))'


def drop(index, origin, angles, velocity=(0, 0, 0)):
    vec = lambda v: '(vector : (%f, %f, %f))' % tuple(v)
    return (f'DROP {index} z={origin[2]} origin={vec(origin)} velocity={vec(velocity)} '
            f'angles={vec(angles)} {BOUNDS}')


def report(*events, sequential=True, loaded=True, finished=True):
    return {'events': list(events), 'loaded': loaded, 'finished': finished, 'drop_sequential': sequential}


GOOD = [drop(0, (-0.19, -5.69, 0.5), (-0.18, -2.64, -0.35)), drop(1, (299.8, 294.3, 0.5), (-0.13, -2.64, -0.26))]
# A bad launch: one crate propped 58 degrees up, one 2.3 units into a z=0 floor.
BAD = [drop(0, (-6.4, -49.9, 15.56), (58.4, -89.87, 101.95)), drop(1, (293.3, 262.5, -2.31), (-2.94, -4.7, 9.71))]


class RestTiltTests(unittest.TestCase):
    def test_faces_sides_and_ends_are_level(self):
        for angles in ((0, 37, 0), (0, 0, 90), (0, 0, -180), (90, 12, 0), (-0.57, 16.7, -177.54)):
            with self.subTest(angles=angles):
                self.assertLess(rest_tilt(angles), 3)

    def test_wedged_poses_are_tilted(self):
        self.assertAlmostEqual(rest_tilt((58.4, -89.87, 101.95)), 31.6, places=1)
        self.assertAlmostEqual(rest_tilt((0, 0, 45)), 45)
        self.assertGreater(rest_tilt((-2.94, -4.7, 9.71)), 10)


class ClassifyTests(unittest.TestCase):
    def test_good_and_bad_launches(self):
        self.assertEqual(classify(report(*GOOD), floors={0: 0, 1: 0})[0], 'good')
        label, drops, reasons = classify(report(*BAD))
        self.assertEqual(label, 'bad')
        self.assertEqual(len(reasons), 2)
        self.assertEqual([d['index'] for d in drops], [0, 1])

    def test_floor_catches_a_level_crate_that_sank(self):
        sunk = drop(0, (0, 0, -3.0), (0, 0, 0))
        self.assertEqual(classify(report(sunk))[0], 'good')
        label, _, reasons = classify(report(sunk), floors={0: 0})
        self.assertEqual(label, 'bad')
        self.assertIn('floor', reasons[0])
        self.assertEqual(classify(report(*GOOD), floors={5: 0})[0], 'bad')

    def test_moving_drop_is_bad(self):
        self.assertEqual(classify(report(drop(0, (0, 0, 0.5), (0, 0, 0), velocity=(0, 0, -30))))[0], 'bad')

    def test_piled_simultaneous_drops_are_unclear_not_bad(self):
        pile = [drop(0, (2434.0, 195.5, 139.7), (-1.76, 169.5, 88.33)),
                drop(1, (2472.4, 192.5, 150.2), (2.77, 113.47, -158.29))]
        self.assertEqual(classify(report(*pile, sequential=False))[0], 'unclear')
        # Sequential drops never share the world, so the same poses are a bad launch.
        self.assertEqual(classify(report(*pile, sequential=True))[0], 'bad')
        self.assertEqual(classify(report(*pile, sequential=False), contact=10)[0], 'bad')
        # A tilt with no neighbour still makes a simultaneous launch bad.
        far = pile + [drop(2, (0, 0, 20), (40, 0, 0))]
        self.assertEqual(classify(report(*far, sequential=False))[0], 'bad')

    def test_failed_launches(self):
        self.assertEqual(classify(None)[0], 'failed')
        self.assertEqual(classify(report(*GOOD, loaded=False))[0], 'failed')
        self.assertEqual(classify(report(*GOOD, finished=False))[0], 'failed')
        self.assertEqual(classify(report('BEGIN', 'DONE'))[0], 'failed')

    def test_summary_counts_launch_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            folders = []
            for name, events in (('one', GOOD), ('two', BAD), ('three', None)):
                folder = Path(tmp) / name
                folder.mkdir()
                if events is not None:
                    (folder / 'report.json').write_text(json.dumps(report(*events)))
                folders.append(folder)
            summary = summarize(folders)
        self.assertEqual(summary['counts'], {'good': 1, 'bad': 1, 'unclear': 0, 'failed': 1})
        self.assertEqual([launch['label'] for launch in summary['launches']], ['good', 'bad', 'failed'])


if __name__ == '__main__':
    unittest.main()
