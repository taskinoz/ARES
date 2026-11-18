import unittest
from unittest.mock import Mock
from mode_checks import validate_mode,mode_script,mode_errors
import r1_harness
import tfo_harness


class ModeChecksTests(unittest.TestCase):
    def setUp(self):
        self.probe={'mode':'cp','hardpoints':3}
        self.events=['MODE actual=cp gametype=cp','MODE_OBJECTIVES count=3 initialized=true']+[f'MODE_HARDPOINT {i} id={i} terminal=true' for i in range(3)]

    def test_initialized_mode_and_hardpoints(self):
        self.assertEqual(mode_errors(self.events,self.probe),[])
        self.assertEqual(r1_harness.validate_checks({'mode_check':self.probe})['mode_check'],self.probe)

    def test_wrong_mode_missing_duplicate_uninitialized_or_invalid_terminal_fail(self):
        for rows in [self.events[1:],self.events+[self.events[0]],
                     [e.replace('actual=cp','actual=tdm') for e in self.events],
                     [e.replace('initialized=true','initialized=false') for e in self.events],
                     [e.replace('terminal=true','terminal=false') for e in self.events],
                     [e.replace('id=2','id=1') for e in self.events], self.events[:-1]]:
            self.assertTrue(mode_errors(rows,self.probe))

    def test_r1_caches_before_reading_after_mcp_retry(self):
        control=Mock();control.squirrel.side_effect=[[],self.events]
        events=[];r1_harness.run_mode_checks(control,self.probe,events)
        self.assertEqual(events,self.events)
        setup=control.squirrel.call_args_list[0].args[0]
        self.assertIn('ARES_ModeToken',setup)
        self.assertIn('ARES_ModeEvents.append',setup)
        self.assertNotIn('printl(',setup)

    def test_optional_objectives_do_not_claim_capture_acceptance(self):
        self.assertEqual(mode_errors(['MODE actual=tdm gametype=tdm'],{'mode':'tdm'}),[])
        self.assertNotIn('MODE_OBJECTIVES',mode_script({'mode':'tdm'}))

    def test_rejects_bad_or_script_mode_names_and_counts(self):
        for probe in [False,{}, {'mode':'cp;quit'}, {'mode':'cp\nquit'},dict(self.probe,hardpoints=True),
                      dict(self.probe,hardpoints=0),dict(self.probe,unknown=True),dict(self.probe,mode='tdm')]:
            with self.assertRaises(ValueError):validate_mode(probe)
        with self.assertRaises(ValueError):tfo_harness.write_mod(None,None,{'mode_check':False})

    def test_disabled_and_order_independent_hardpoint_ids(self):
        self.assertEqual(mode_errors([],None),[])
        self.assertEqual(mode_script(None),'')
        self.assertEqual(mode_errors(self.events[:2]+list(reversed(self.events[2:])),self.probe),[])


if __name__=='__main__':unittest.main()
