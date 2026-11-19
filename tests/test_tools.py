"""The ares package: readers on the committed fixtures, the catalogue, and result adapters."""
import importlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIX = ROOT / 'tests' / 'fixtures' / 'models'

from ares import result  # noqa: E402
from ares.__main__ import CATALOGUE  # noqa: E402


def run(*args):
    return subprocess.run([sys.executable, '-m', *args], cwd=ROOT, capture_output=True, text=True, timeout=120)


class Readers(unittest.TestCase):
    def test_mdl52(self):
        from ares.r1 import mdl52
        info = mdl52.inspect(FIX / 'r1/physics_box.mdl')
        self.assertEqual(info['version'], 52)
        self.assertEqual(info['name'], 'r1c_examples/physics_box.mdl')

    def test_mdl53(self):
        from ares.r2 import mdl53
        model, offsets = mdl53.survey(str(FIX / 'r2/physics_box.mdl'))
        self.assertEqual(model.hdr['name'], 'r2c_examples/physics_box.mdl')
        self.assertTrue(model.hdr['phySize'] > 0)

    def test_ivp_phy_v52_companion_and_v53_embedded(self):
        from ares.source import ivp_phy
        for path in (FIX / 'r1/physics_box.mdl', FIX / 'r2/physics_box.mdl', FIX / 'r1/physics_box.phy'):
            with self.subTest(path=path.name):
                phy = ivp_phy.load(path)
                self.assertEqual(len(phy['solids']), 1)
                self.assertEqual(len(phy['solids'][0]['points']), 8)  # a box
                self.assertIn('"mass" "50', phy['text'])
        # a v52 model whose companion .phy is missing
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as work:
            lone = Path(work) / 'box.mdl'
            shutil.copyfile(FIX / 'r1/box.mdl', lone)
            with self.assertRaises(ValueError):
                ivp_phy.load(lone)

    def test_mdl54_render_s0_and_s3(self):
        from ares.r5.mdl54 import Model
        for path, target in ((FIX / 'r5/box.rmdl', 's3'), (FIX / 'r5-s0/physics_box.rmdl', 's0')):
            with self.subTest(target=target):
                meshes = Model(path, target).render()[0]
                self.assertEqual(sum(len(m['triangles']) for m in meshes), 12)

    def test_phy54_and_compare(self):
        from ares.r5 import compare_phy54, phy54
        for path, target in ((FIX / 'r5/physics_box.phy', 's3'), (FIX / 'r5-s0/physics_box.phy', 's0')):
            with self.subTest(target=target):
                phy = phy54.parse(path.read_bytes(), target)
                (solid,) = phy['solids']
                (hull,) = solid['hulls']
                self.assertEqual((len(hull['verts']), len(hull['faces'])), (8, 6))
                self.assertEqual(phy54.check_hull(hull, target == 's3'), [])
                self.assertEqual(compare_phy54.compare(path, path, target)['issues'], [])

    def test_bvh54_entries_and_compare(self):
        from ares.r5 import bvh54
        from ares.r5.compare_bvh54 import compare
        static = bvh54.from_model(FIX / 'r5/box.rmdl', strict=True)
        self.assertEqual((static['hull'], static['trace']), (-1, 0))
        physics = bvh54.from_model(FIX / 'r5/physics_box.rmdl', strict=True)
        self.assertEqual((physics['hull'], physics['trace']), (0, -1))
        for parsed in (static, physics):
            (entry,) = parsed['entries']
            self.assertEqual(entry['problems'], [])
            self.assertEqual(len(entry['triangles']), 12)
        self.assertEqual(compare(FIX / 'r5/box.rmdl', FIX / 'r5/box.rmdl')['issues'], [])
        # a static prop is not a physics prop: roles differ
        self.assertTrue(compare(FIX / 'r5/box.rmdl', FIX / 'r5/physics_box.rmdl')['issues'])

    def test_rpak_asset_paths(self):
        from ares.r5 import rpak
        self.assertEqual(rpak.asset_path('r5c_examples\\box.rmdl'), 'mdl/r5c_examples/box.rmdl')


class Catalogue(unittest.TestCase):
    def test_every_module_imports_and_has_help(self):
        for module, targets, kind, purpose in CATALOGUE:
            with self.subTest(module=module):
                importlib.import_module(module)
                self.assertEqual(run(module, '--help').returncode, 0)
                self.assertTrue(set(targets) <= {'r1', 'tfo', 'r2', 'r5'})

    def test_listing(self):
        out = run('ares', '--json')
        self.assertEqual(out.returncode, 0)
        self.assertEqual(len(json.loads(out.stdout)), len(CATALOGUE))

    def test_sources_recorded(self):
        sources = json.loads((ROOT / 'ares/SOURCES.json').read_text(encoding='utf-8'))
        modules = {m.replace('ares.', '').replace('.', '/') + '.py' for m, *_ in CATALOGUE if m not in ('ares.result',)}
        self.assertEqual(modules - set(sources), set())


class Results(unittest.TestCase):
    def schema_check(self, value):
        result.validate(value)
        try:
            import jsonschema
        except ImportError:
            return
        jsonschema.validate(value, json.loads((ROOT / 'harnesses/contracts/result.schema.json').read_text(encoding='utf-8')))

    def test_r5reloaded(self):
        report = dict(state='finished', passed=True, failures=[], screenshots=['a.tga'], elapsed_seconds=12.5,
                      collision=dict(passed=True))
        out = result.from_r5reloaded(report, 'r5c-report.json')
        self.schema_check(out)
        self.assertEqual((out['status'], out['verification'], out['duration_ms']), ('success', 'runtime', 12500))
        failed = result.from_r5reloaded(dict(state='failed', passed=False, error='netconsole timed out'))
        self.assertEqual((failed['status'], failed['verification']), ('failure', 'tool'))
        self.assertIn('netconsole timed out', failed['errors'])

    def test_r1delta_unreviewed_screenshots_are_partial(self):
        out = result.from_r1delta(dict(server_passed=True, visual_passed=False, passed=False, issues=[], status='collected',
                                       screenshots=[dict(path='s.tga', sha256='0', reviewed=False)]))
        self.schema_check(out)
        self.assertEqual((out['status'], out['verification']), ('partial', 'runtime'))

    def test_tfo_prepare_only_is_tool_level(self):
        out = result.from_tfo(dict(status='prepared', passed=False, issues=[]))
        self.schema_check(out)
        self.assertEqual((out['status'], out['verification']), ('partial', 'tool'))

    def test_northstar_and_compare(self):
        self.schema_check(result.from_northstar(dict(success=False, failures=['no spawn'], spawns=[], screenshots=[], logs=[])))
        out = result.from_r1delta_compare(dict(results=[dict(name='a', issues=[]), dict(name='b', issues=['bounds'])],
                                               passed=1, total=2))
        self.schema_check(out)
        self.assertEqual(out['status'], 'partial')
        self.assertEqual(out['errors'], ['b: bounds'])

    def test_validation_rejects_bad_results(self):
        with self.assertRaises(ValueError):
            result.validate(dict(schema_version='1'))

    def test_empty_reports_do_not_claim_runtime_evidence(self):
        for kind, convert in result.CONVERTERS.items():
            with self.subTest(kind=kind):
                out = convert({})
                self.schema_check(out)
                self.assertEqual((out['status'], out['verification']), ('failure', 'tool'))
                self.assertFalse(any(check['passed'] for check in out['checks']))

    def test_unfinished_runs_do_not_pass_with_stale_success_flags(self):
        reports = {
            'r1delta': dict(status='prepared', passed=True),
            'tfo': dict(status='error', passed=True),
            'r5reloaded': dict(state='failed', passed=True),
            'northstar': dict(success=True, spawns=0),
            'r1delta-compare': dict(total=1, passed=1, results=[]),
        }
        for kind, report in reports.items():
            with self.subTest(kind=kind):
                out = result.CONVERTERS[kind](report)
                self.assertNotEqual(out['status'], 'success')
                self.assertEqual(out['verification'], 'tool')

    def test_comparison_uses_pair_evidence_over_summary_counts(self):
        out = result.from_r1delta_compare(dict(
            total=1, passed=1, results=[dict(name='box', issues=['bounds'])]))
        self.assertEqual((out['status'], out['verification']), ('failure', 'runtime'))
        self.assertEqual(out['errors'], ['box: bounds'])


if __name__ == '__main__':
    unittest.main()
