import hashlib
import tempfile
import unittest
from pathlib import Path
from tfo_cp_dialogue import patch_dialogue,validate_compat
from tfo_harness import write_mod,run_stopped,MOD

SOURCE=b'IncludeScript( "_gamemode_cp_dialogue" )\nswitch (GAMETYPE) {\n case ATTRITION:\n case CAPTURE_THE_FLAG:\n break\n default: GameMode_RunSharedDialogueScripts( GAMETYPE )\n}\n'


class CpDialogueTests(unittest.TestCase):
    def test_only_legacy_switch_route_changes(self):
        result,meta=patch_dialogue(SOURCE)
        self.assertEqual(result.replace(b' case CAPTURE_POINT:\n',b''),SOURCE)
        self.assertEqual(meta['base_sha256'],hashlib.sha256(SOURCE).hexdigest())
        self.assertNotEqual(meta['base_sha256'],meta['patched_sha256'])

    def test_only_mfdp_mode_registers_mfdp_conversations(self):
        names=['MFDPFriendlyPilotsLeftTwoMarkedPlayer','MFDPFriendlyPilotsLeftTwo','MFDPEnemyPilotsLeftTwo','MFDPBothTeamsPilotsLeftOne','MFDPEnemyMarkIsAlone']
        data=SOURCE+b''.join((' AddVDULineForBish( "'+name+'", "fixture" )\n').encode() for name in names)
        fixed,meta=patch_dialogue(data)
        self.assertEqual(meta['guarded_mfdp_conversations'],5)
        self.assertEqual(fixed.count(b'if ( GAMETYPE == MARKED_FOR_DEATH_PRO )'),5)
        for name in names:self.assertIn(name.encode(),fixed)
        with self.assertRaises(ValueError):patch_dialogue(SOURCE+b' AddVDULineForBish( "MFDPEnemyMarkIsAlone", "fixture" )\n')

    def test_crlf_preserved(self):
        source=SOURCE.replace(b'\n',b'\r\n');result,_=patch_dialogue(source)
        self.assertEqual(result.replace(b' case CAPTURE_POINT:\r\n',b''),source)

    def test_unknown_duplicate_and_already_fixed_sources_fail(self):
        for data in [b'',SOURCE*2,SOURCE.replace(b'ATTRITION',b'OTHER'),SOURCE+b'case CAPTURE_POINT:',SOURCE.replace(b'IncludeScript',b'IncludeOther'),SOURCE+b'\0',SOURCE+b'\xff']:
            with self.assertRaises(ValueError):patch_dialogue(data)

    def test_requires_opt_in_and_cp(self):
        self.assertFalse(validate_compat({}))
        self.assertTrue(validate_compat({'mode_check':{'mode':'cp'},'tfo_cp_dialogue_compat':True}))
        for checks in [{'tfo_cp_dialogue_compat':1},{'tfo_cp_dialogue_compat':True},{'tfo_cp_dialogue_compat':True,'mode_check':None},{'tfo_cp_dialogue_compat':True,'mode_check':{'mode':'tdm'}}]:
            with self.assertRaises(ValueError):validate_compat(checks)

    def test_stages_only_owned_override_and_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);maps=root/'maps';maps.mkdir()
            base=root/'game/Mods/TFORevive.Core/mod/scripts/vscripts';base.mkdir(parents=True)
            (base/'_mapspawn.nut').write_bytes(b'// fixture')
            source=base/'game_state_dialog.nut';source.write_bytes(SOURCE)
            mod=write_mod(root/'game',maps,{'mode_check':{'mode':'cp'},'tfo_cp_dialogue_compat':True})
            self.assertEqual(source.read_bytes(),SOURCE)
            self.assertTrue((mod/'compatibility.json').is_file())
            self.assertIn(b'case CAPTURE_POINT:',(mod/'mod/scripts/vscripts/game_state_dialog.nut').read_bytes())

    def test_bad_source_fails_before_staging(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'game/Mods/TFORevive.Core/mod/scripts/vscripts';base.mkdir(parents=True)
            (base/'game_state_dialog.nut').write_bytes(b'unsupported')
            with self.assertRaises(ValueError):write_mod(root/'game',root/'maps',{'mode_check':{'mode':'cp'},'tfo_cp_dialogue_compat':True})
            self.assertFalse((root/'game/Mods'/MOD).exists())

    def test_script_errors_stop_without_done(self):
        self.assertTrue(run_stopped('SERVER SCRIPT ERROR: failed'))
        self.assertTrue(run_stopped('[ARES] DONE'))
        self.assertFalse(run_stopped('[ARES] BEGIN'))


if __name__=='__main__':unittest.main()
