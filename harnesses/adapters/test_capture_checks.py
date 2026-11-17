import copy
import unittest
from unittest.mock import Mock,patch
from capture_checks import validate_capture,capture_errors,capture_script
import r1_harness
import tfo_harness


class CaptureChecksTests(unittest.TestCase):
    def setUp(self):
        self.probe={'targetname':'ares_cp_a','origin':[-600,-90,1],'samples':2}
        self.events=['CAPTURE_READY state=4 playing=4','CAPTURE_BEFORE owner=0 playerTeam=2 progress=0 score=0',
                     'CAPTURE 0 owner=0 playerTeam=2 progress=0 score=0 alive=true touching=true origin=(vector : (-600, -90, 0.575))',
                     'CAPTURE 1 owner=2 playerTeam=2 progress=-1 score=1 alive=true touching=true origin=(vector : (-600, -90, 0.575))']

    def test_neutral_capture_and_score(self):
        self.assertEqual(capture_errors(self.events,self.probe),[])
        self.assertEqual(r1_harness.validate_checks({'mode_check':{'mode':'cp'},'cp_capture':self.probe})['cp_capture'],self.probe)

    def test_other_team_uses_positive_progress(self):
        events=[e.replace('playerTeam=2','playerTeam=3').replace('owner=2','owner=3').replace('progress=-1','progress=1') for e in self.events]
        self.assertEqual(capture_errors(events,self.probe),[])

    def test_missing_duplicate_dead_untouched_and_wrong_pose_fail(self):
        for rows in [self.events[1:],self.events[:-1],self.events+[self.events[-1]],
                     [e.replace('alive=true','alive=false') for e in self.events],
                     [e.replace('touching=true','touching=false') for e in self.events],
                     [e.replace('-600','-800') for e in self.events],
                     [e.replace('0.575','nan') for e in self.events]]:
            self.assertTrue(capture_errors(rows,self.probe))

    def test_starting_owned_wrong_direction_or_no_score_gain_fail(self):
        for rows in [[e.replace('owner=0','owner=2') for e in self.events],
                     [e.replace('progress=-1','progress=1') for e in self.events],
                     [e.replace('score=1','score=0') for e in self.events],
                     self.events+['CAPTURE_ERROR failed']]:
            self.assertTrue(capture_errors(rows,self.probe))

    def test_owned_point_cannot_be_lost_during_hold(self):
        probe=dict(self.probe,samples=3)
        owned=self.events[-1]
        events=self.events[:2]+[owned.replace('CAPTURE 1','CAPTURE 0'),self.events[-2].replace('CAPTURE 0','CAPTURE 1').replace('score=0','score=1'),owned.replace('CAPTURE 1','CAPTURE 2').replace('score=1','score=2')]
        self.assertTrue(any('lost' in error for error in capture_errors(events,probe)))

    def test_invalid_parameters_and_wrong_mode_fail_before_staging(self):
        for key,value in [('targetname','bad";quit'),('origin',[0,0,float('inf')]),('samples',True),('ready_wait',31),('min_score',0),('wait',0)]:
            probe=copy.deepcopy(self.probe);probe[key]=value
            with self.assertRaises(ValueError):validate_capture(probe,'cp')
        with self.assertRaises(ValueError):validate_capture(self.probe,'tdm')
        with self.assertRaises(ValueError):tfo_harness.write_mod(None,None,{'cp_capture':self.probe})

    def test_script_never_forces_match_ownership_or_score(self):
        script=capture_script(self.probe)
        for name in ['SetGameState','SetTeamScore','SetHardpointProgress','SetPointAsCapturedByTeam']:
            self.assertNotIn(name,script)
        self.assertIn('hp.s.trigger.IsTouching(player)',script)
        self.assertEqual(capture_errors([],None),[])

    def test_r1_guard_and_collection(self):
        control=Mock();control.squirrel.side_effect=[[],self.events+['CAPTURE_DONE']]
        events=[];r1_harness.run_capture_checks(control,self.probe,events)
        self.assertEqual(events,self.events)
        self.assertIn('ARES_CaptureToken',control.squirrel.call_args_list[0].args[0])

    def test_r1_timeout(self):
        control=Mock();control.squirrel.return_value=[]
        with patch.object(r1_harness.time,'monotonic',side_effect=[0,1000]):
            with self.assertRaises(TimeoutError):r1_harness.run_capture_checks(control,self.probe,[])


if __name__=='__main__':unittest.main()
