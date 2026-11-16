import copy
import unittest
from unittest.mock import Mock, patch
from titan_checks import validate_titans, titan_errors, titan_script
import r1_harness
import tfo_harness


class TitanChecksTests(unittest.TestCase):
    def setUp(self):
        self.rows=[dict(origin=[0,500,256],team=2,floor_z=0,samples=2)]
        self.events=[f'TITAN 0 SAMPLE {i} valid=true alive=true titan=true origin=(vector : (0, 500, 0.03125)) velocity=(vector : (0, 0, 0)) mins=(vector : (-60, -60, 0)) maxs=(vector : (60, 60, 235))' for i in range(2)]

    def test_sampled_native_support(self):
        self.assertEqual(titan_errors(self.events,self.rows),[])
        self.assertEqual(r1_harness.validate_checks({'titans':self.rows})['titans'],self.rows)

    def test_bad_sample_missing_duplicate_dead_wrong_type_and_fallthrough(self):
        for events in [self.events[:-1],self.events+self.events[:1],
                       [e.replace('alive=true','alive=false') for e in self.events],
                       [e.replace('titan=true','titan=false') for e in self.events],
                       [e.replace('0.03125','-12') for e in self.events],
                       [e.replace('235','nan') for e in self.events],
                       [e.replace('500','510') for e in self.events],
                       self.events+['TITAN 0 ERROR failed']]:
            self.assertTrue(titan_errors(events,self.rows))

    def test_motion_fails_even_with_zero_reported_velocity(self):
        events=list(self.events);events[1]=events[1].replace('0.03125','0.8')
        self.assertTrue(any('translation' in e for e in titan_errors(events,self.rows)))

    def test_bad_inputs_rejected_before_staging(self):
        for key,value in [('origin',[0,0,float('nan')]),('team',True),('floor_z',None),('samples',1),('wait',0),('settings','arbitrary_script')]:
            row=copy.deepcopy(self.rows[0]);row[key]=value
            with self.assertRaises(ValueError): validate_titans([row])
        with self.assertRaises(ValueError):tfo_harness.write_mod(None,None,{'titans':False})

    def test_settings_are_target_specific(self):
        self.assertIn('"titan_atlas"',titan_script(self.rows,'r1'))
        self.assertIn('"titan_atlas_tier0"',titan_script(self.rows,'tfo'))
        with self.assertRaises(ValueError):titan_script(self.rows,'northstar')
        self.assertIn('if(IsValid(titan)) titan.Destroy()',titan_script(self.rows,'r1'))

    def test_r1_guard_and_collection(self):
        control=Mock();control.squirrel.side_effect=[[],self.events+['TITANS_DONE']]
        events=[];r1_harness.run_titan_checks(control,self.rows,events)
        self.assertEqual(events,self.events)
        self.assertIn('ARES_TitanToken',control.squirrel.call_args_list[0].args[0])
        self.assertIn('thread ARES_RunTitans()',control.squirrel.call_args_list[0].args[0])

    def test_r1_timeout(self):
        control=Mock();control.squirrel.return_value=[]
        with patch.object(r1_harness.time,'monotonic',side_effect=[0,100]):
            with self.assertRaises(TimeoutError):r1_harness.run_titan_checks(control,self.rows,[])


if __name__=='__main__':unittest.main()
