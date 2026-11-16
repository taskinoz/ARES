import copy
import unittest
from unittest.mock import Mock, patch

from trigger_checks import validate_triggers, trigger_errors, trigger_script
import r1_harness
import tfo_harness


class TriggerChecksTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{'targetname':'ares_trigger','points':[[-300,0,1],[0,0,1],[300,0,1]],
                      'counts':[[0,0],[1,0],[1,1]]}]
        self.events = [f'TRIGGER 0 STEP {i} start={s} end={e} alive=true origin=(vector : ({x}, 0, 0.03125))'
                       for i,(x,s,e) in enumerate([(-300,0,0),(0,1,0),(300,1,1)])]

    def test_matching_alive_pose_and_counts(self):
        self.assertEqual(trigger_errors(self.events,self.rows), [])
        self.assertEqual(r1_harness.validate_checks({'triggers':self.rows})['triggers'], self.rows)

    def test_missing_duplicate_dead_wrong_counts_and_nonfinite_fail(self):
        for events in [self.events[:-1],self.events+[self.events[0]],
                       [e.replace('alive=true','alive=false') for e in self.events],
                       [e.replace('start=1','start=2') for e in self.events],
                       [e.replace('0.03125','nan') for e in self.events],
                       [e.replace('300,','900,') for e in self.events]]:
            self.assertTrue(trigger_errors(events,self.rows))

    def test_rejects_malformed_and_script_input(self):
        for key,value in [('targetname','a";quit'),('points',[[0,0,0]]),('points',[[0,0,0],[0,0,float('inf')]]),
                          ('counts',[[0,0],[1,0],[0,0]]),('counts',[[True,0]]*3),('wait',0),('tolerance',65),('unknown',True)]:
            row=copy.deepcopy(self.rows[0]);row[key]=value
            with self.assertRaises(ValueError): validate_triggers([row])
        with self.assertRaises(ValueError): validate_triggers(self.rows*2)

    def test_tfo_rejects_before_staging(self):
        with self.assertRaises(ValueError): tfo_harness.write_mod(None,None,{'triggers':'bad'})

    def test_r1_guards_mcp_retries_and_collects_done(self):
        control=Mock();control.squirrel.side_effect=[[],self.events+['TRIGGERS_DONE']]
        events=[]
        r1_harness.run_trigger_checks(control,self.rows,events)
        self.assertEqual(events,self.events)
        setup=control.squirrel.call_args_list[0].args[0]
        self.assertIn('ARES_TriggerToken',setup)
        self.assertIn('thread ARES_RunTriggers',setup)

    def test_r1_times_out_incomplete_thread(self):
        control=Mock();control.squirrel.return_value=[]
        with patch.object(r1_harness.time,'monotonic',side_effect=[0,100]):
            with self.assertRaises(TimeoutError): r1_harness.run_trigger_checks(control,self.rows,[])

    def test_shared_script_keeps_missing_target_explicit(self):
        script=trigger_script(self.rows)
        self.assertIn('MISSING',script)
        self.assertIn('OnStartTouch',script)
        self.assertIn('OnEndTouch',script)
        self.assertIn('ARES_RunTriggers(player)',tfo_harness.SCRIPT)
        self.assertEqual(validate_triggers([]),[])


if __name__=='__main__': unittest.main()
