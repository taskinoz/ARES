import unittest
from spawn_checks import validate_spawn, spawn_errors, spawn_script
from r1_harness import validate_checks
from tfo_harness import write_mod, SCRIPT


class SpawnChecksTests(unittest.TestCase):
    def setUp(self):
        self.probe={'origins':[[-400,0,0]],'tolerance':2}
        self.event='SPAWN alive=true team=2 origin=(vector : (-400, 0, 0.03125))'

    def test_exact_initial_spawn_and_optional_team(self):
        self.assertEqual(spawn_errors([self.event],self.probe),[])
        self.assertEqual(spawn_errors([self.event],dict(self.probe,team=2)),[])
        self.assertTrue(spawn_errors([self.event],dict(self.probe,team=3)))
        self.assertEqual(validate_checks({'spawn_probe':self.probe})['spawn_probe'],self.probe)

    def test_missing_duplicate_dead_nonfinite_and_wrong_position(self):
        for rows in [[],[self.event]*2,[self.event.replace('true','false')],
                     [self.event.replace('-400','nan')],[self.event.replace('-400','-500')],
                     [self.event.replace('team=2','team=0')]]:
            self.assertTrue(spawn_errors(rows,self.probe))

    def test_malformed_probe_rejected(self):
        for probe in [False,{}, {'origins':[]},dict(self.probe,origins=[[0,0,float('inf')]]),
                      dict(self.probe,tolerance=0),dict(self.probe,team=True),dict(self.probe,extra='script')]:
            with self.assertRaises(ValueError): validate_spawn(probe)

    def test_disabled_probe_has_no_script_or_failures(self):
        self.assertIsNone(validate_spawn(None))
        self.assertEqual(spawn_script(None),'')
        self.assertEqual(spawn_errors([],None),[])

    def test_tfo_validates_before_staging_and_before_repositioning(self):
        with self.assertRaises(ValueError): write_mod(None,None,{'spawn_probe':False})
        self.assertLess(SCRIPT.index('%SPAWN_SCRIPT%'),SCRIPT.index('ARES_RunTriggers(player)'))


if __name__=='__main__': unittest.main()
