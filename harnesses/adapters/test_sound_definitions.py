import unittest
import tempfile
import json
from pathlib import Path
from sound_definitions import inspect_sound_definitions,repair_hardpoint_definitions,load_sound_sources
from tfo_harness import write_mod, MOD


VALID=b'"probe" { "wave" "sound/probe.wav" }'
FIRST=b'"diag_hp_mcor_bish_generalpurpose_02" {\n "rndwave" {\n "wave" "dialogue/hardpoints/diag_hp_mcor_bish_generalpurpose_02.wav"\n // }\n}\n'
LAST=b'"diag_hp_mcor_bish_generalpurpose_03" { "wave" "sound/probe.wav" }\n'


class SoundDefinitionTests(unittest.TestCase):
    def test_counts_nested_duplicate_wave_properties_and_comments(self):
        info=inspect_sound_definitions(b'// original fixture\n"probe" { "rndwave" { "wave" "one.wav" "wave" "one.wav" "wave" "two.wav" } }')
        self.assertEqual((info['alias_count'],info['wave_reference_count'],info['unique_wave_count']),(1,3,2))

    def test_malformed_encoded_duplicate_and_unsupported_sources(self):
        for data in [b'',b'"p" { "wave" }',b'"p" { "wave" "one.wav"',b'"p" {}',VALID+b'\0',b'\xff',VALID+VALID,b'unquoted { "wave" "one.wav" }',b'"p" { "wave" "" }']:
            with self.assertRaises(ValueError):inspect_sound_definitions(data)

    def test_known_repair_changes_only_commented_brace(self):
        source=FIRST+LAST
        with self.assertRaises(ValueError):inspect_sound_definitions(source)
        fixed,info=repair_hardpoint_definitions(source)
        self.assertEqual(fixed,source.replace(b'// }',b'}'))
        self.assertTrue(info['repaired'])
        self.assertEqual(info['alias_count'],2)
        self.assertNotEqual(info['base_sha256'],info['sha256'])

    def test_crlf_repair_preserves_every_other_byte(self):
        source=(FIRST+LAST).replace(b'\n',b'\r\n');fixed,_=repair_hardpoint_definitions(source)
        self.assertEqual(fixed,source.replace(b'// }',b'}'))

    def test_already_valid_source_is_unchanged(self):
        fixed,info=repair_hardpoint_definitions(VALID)
        self.assertEqual(fixed,VALID)
        self.assertFalse(info['repaired'])

    def test_unknown_fault_or_multiple_faults_fail_closed(self):
        for source in [FIRST.replace(b'_02.wav',b'_different.wav')+LAST,FIRST+LAST+b'"dangling"',FIRST+FIRST+LAST,b'"bad" {',None]:
            with self.assertRaises(ValueError):repair_hardpoint_definitions(source)

    def test_loads_and_repairs_only_explicit_cp_source(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'mp_hardpoints.txt';p.write_bytes(FIRST+LAST)
            name,payload,info=load_sound_sources([p],True,'cp')[0]
            self.assertEqual(name,p.name)
            self.assertTrue(info['repaired'])
            self.assertEqual(p.read_bytes(),FIRST+LAST)
            self.assertEqual(payload,(FIRST+LAST).replace(b'// }',b'}'))
            with self.assertRaises(ValueError):load_sound_sources([p],True,'tdm')

    def test_source_name_duplicates_and_missing_files_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'probe.txt';p.write_bytes(VALID)
            for paths in [[p,p],[p.with_name('missing.txt')]]:
                with self.assertRaises(ValueError):load_sound_sources(paths)
            with self.assertRaises(ValueError):load_sound_sources([p],True,'cp')
            bad=p.with_suffix('.nut');bad.write_bytes(VALID)
            with self.assertRaises(ValueError):load_sound_sources([bad])

    def test_stages_manifest_bound_audio_without_editing_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=root/'probe.txt';p.write_bytes(VALID)
            maps=root/'maps';maps.mkdir()
            base=root/'game/Mods/TFORevive.Core/mod/scripts';(base/'vscripts').mkdir(parents=True)
            (base/'vscripts/_mapspawn.nut').write_bytes(b'// original fixture')
            (base/'game_sounds_manifest.txt').write_bytes(b'game_sounds_manifest { "precache_file" "scripts/audio/probe.txt" }')
            mod=write_mod(root/'game',maps,{},sound_files=[p])
            self.assertEqual(p.read_bytes(),VALID)
            self.assertEqual((mod/'mod/scripts/audio/probe.txt').read_bytes(),VALID)
            info=json.loads((mod/'compatibility.json').read_text(encoding='utf-8'))
            self.assertEqual(info['sound_definitions'][0]['alias_count'],1)

    def test_unlisted_sound_fails_before_staging(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=root/'probe.txt';p.write_bytes(VALID)
            base=root/'game/Mods/TFORevive.Core/mod/scripts';base.mkdir(parents=True)
            (base/'game_sounds_manifest.txt').write_bytes(b'game_sounds_manifest {}')
            with self.assertRaises(ValueError):write_mod(root/'game',root/'maps',{},sound_files=[p])
            self.assertFalse((root/'game/Mods'/MOD).exists())

    def test_depth_is_bounded(self):
        data=b'"p" {'+b'"nested" {'*18+b'"wave" "one.wav"'+b'}'*19
        with self.assertRaisesRegex(ValueError,'nesting'):inspect_sound_definitions(data)


if __name__=='__main__':unittest.main()
