import unittest

from physics_observations import bounds_bottom, observations, hull_bottom, support_errors, sample_motion, motion_errors


class PhysicsObservationTests(unittest.TestCase):
    def test_sampled_translation_detects_motion_with_zero_reported_velocity(self):
        events = [f'SAMPLE 0 t={t} origin=(vector : ({x}, 0, 0)) velocity=(vector : (0, 0, 0))'
                  for t, x in ((0, 100), (1, 0), (2, 1), (3, 0))]
        row = sample_motion(events, 2)[0]
        self.assertEqual(row['translation'], 1)
        self.assertEqual(row['max_interval_speed'], 1)
        self.assertTrue(motion_errors([row], [0], .25))
        self.assertFalse(motion_errors([row], [0], 1))

    def test_motion_uses_per_body_tail_and_requires_full_window(self):
        events = [f'SAMPLE {i} t={t} origin=(vector : ({x}, 0, 0))'
                  for i, values in ((0, ((0, 50), (1, 0), (2, 0), (3, 0))),
                                    (1, ((0, 0), (1, 5)))) for t, x in values]
        rows = sample_motion(events)
        self.assertEqual(rows[0]['translation'], 0)
        self.assertFalse(motion_errors(rows, [0]))
        self.assertTrue(motion_errors(rows, [1, 2]))

    def test_invalid_samples_cannot_silently_pass_as_stationary(self):
        valid = 'SAMPLE 0 t=0 origin=(vector : (0, 0, 0))'
        for bad in ('SAMPLE 0 t=nan origin=(vector : (0, 0, 0))',
                    'SAMPLE 0 t=1 origin=(vector : (nan, 0, 0))', valid):
            rows = sample_motion([valid, bad, valid.replace('t=0 ', 't=3 ')])
            self.assertTrue(motion_errors(rows, [0]))
        for window in (0, float('nan')):
            with self.assertRaises(ValueError):
                sample_motion([], window)

    def test_upright_and_tipped_box_have_different_origin_heights(self):
        mins, maxs = [-2, -3, 0], [2, 3, 10]
        self.assertAlmostEqual(bounds_bottom([0, 0, 0], [0, 90, 0], mins, maxs), 0)
        self.assertAlmostEqual(bounds_bottom([0, 0, 2], [90, 0, 0], mins, maxs), 0)
        self.assertAlmostEqual(bounds_bottom([0, 0, 3], [0, 30, 90], mins, maxs), 0)

    def test_missing_or_nonfinite_diagnostics_are_not_reported_as_contacts(self):
        for event in ('DROP 0 z=gone', 'DROP 0 z=1 origin=(vector : (nan, 0, 1))'):
            row = observations({'events': [event]})[0]
            self.assertIn('diagnostic_error', row)
            self.assertNotIn('world_bounds_bottom', row)

    def test_native_vector_format_and_extra_fields(self):
        event = ('DROP 7 z=2 origin=(vector : (0, 0, 2)) velocity=(vector : (3, 4, 0)) '
                 'angles=(vector : (90, 120, 0)) bounds_mins=(vector : (-2, -3, 0)) '
                 'bounds_maxs=(vector : (2, 3, 10))')
        row = observations({'events': ['BEGIN', event, 'DONE']})[0]
        self.assertEqual(row['index'], 7)
        self.assertEqual(row['speed'], 5)
        self.assertAlmostEqual(row['world_bounds_bottom'], 0)

    def test_inverted_bounds_are_rejected(self):
        with self.assertRaises(ValueError):
            bounds_bottom([0, 0, 0], [0, 0, 0], [1, 0, 0], [0, 1, 1])

    def test_rest_expectations_reject_motion_and_missing_pose(self):
        from tfo_harness import expectation_errors
        event = ('DROP 0 z=2 origin=(vector : (0, 0, 2)) velocity=(vector : (0, 0, 0)) '
                 'angles=(vector : (90, 0, 0)) bounds_mins=(vector : (-2, -3, 0)) '
                 'bounds_maxs=(vector : (2, 3, 10))')
        expect = {'drop_speed': [[0, 0, .1]], 'drop_bounds_bottom': [[0, -.01, .01]]}
        self.assertEqual(expectation_errors([event], expect), [])
        self.assertTrue(expectation_errors([event.replace('(0, 0, 0)) angles', '(1, 0, 0)) angles')], expect))
        self.assertTrue(expectation_errors(['DROP 0 z=2'], expect))
        self.assertTrue(expectation_errors([event.replace('angles=', 'unknown=')], expect))

    def test_legacy_velocity_can_be_checked_without_inventing_a_pose(self):
        from tfo_harness import expectation_errors
        legacy = 'DROP 0 z=1 velocity=(vector : (0, 0, 0))'
        self.assertEqual(expectation_errors([legacy], {'drop_speed': [[0, 0, .1]]}), [])
        self.assertTrue(expectation_errors([legacy], {'drop_bounds_bottom': [[0, 0, 2]]}))

    def test_hull_support_does_not_use_empty_corners_of_visual_box(self):
        # A triangular cross-section has no vertex at the bounding box's low/low corner.
        points = [(0, 0, 1), (0, 1, 0), (0, 1, 1)]
        self.assertAlmostEqual(hull_bottom([0, 0, 0], [0, 0, 45], points), 2 ** -.5)
        self.assertEqual(bounds_bottom([0, 0, 0], [0, 0, 45], [0, 0, 0], [0, 1, 1]), 0)

    def test_support_checks_reject_missing_fallthrough_and_motion(self):
        row = {'index': 0, 'physics_bottom': .4, 'speed': 0}
        self.assertEqual(support_errors([row], {0: 0}), [])
        for rows in ([], [dict(row, physics_bottom=-64)], [dict(row, speed=3)], [{'index': 0}],
                     [dict(row, physics_bottom=float('nan'))], [dict(row, speed=float('inf'))]):
            self.assertTrue(support_errors(rows, {0: 0}))


if __name__ == '__main__':
    unittest.main()
