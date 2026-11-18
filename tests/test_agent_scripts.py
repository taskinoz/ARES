from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SkillMirrorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.module = load_script('sync-agent-skills')
        self.module.ROOT = self.root
        self.module.CANONICAL_SKILLS = self.root / '.agents' / 'skills'
        self.module.CLAUDE_SKILLS = self.root / '.claude' / 'skills'
        self.source = self.module.CANONICAL_SKILLS / 'example'
        self.source.mkdir(parents=True)
        (self.source / 'SKILL.md').write_text(
            '---\nname: example\nmetadata:\n  version: 1\ndescription: >-\n  Test skill\n  resources.\n---\n# Example\n',
            encoding='utf-8')

    def test_mirrors_resources_and_detects_resource_drift(self):
        resource = self.source / 'references' / 'guide.md'
        resource.parent.mkdir()
        resource.write_bytes(b'reference\n')
        skills = self.module.canonical()
        self.module.sync(skills)
        self.assertEqual(self.module.stale(skills), [])
        mirror = self.module.CLAUDE_SKILLS / 'example' / 'references' / 'guide.md'
        self.assertEqual(mirror.read_bytes(), resource.read_bytes())
        mirror.write_bytes(b'changed')
        self.assertTrue(any('guide.md' in issue for issue in self.module.stale(skills)))
        self.module.sync(skills)
        self.assertEqual(self.module.stale(skills), [])

    def test_unexpected_files_are_preserved_and_block_sync(self):
        skills = self.module.canonical()
        self.module.sync(skills)
        extra = self.module.CLAUDE_SKILLS / 'example' / 'notes.txt'
        extra.write_bytes(b'user notes')
        with self.assertRaisesRegex(ValueError, 'review manually'):
            self.module.sync(skills)
        self.assertEqual(extra.read_bytes(), b'user notes')
        self.assertTrue(any('notes.txt' in issue for issue in self.module.stale(skills)))

    def test_removed_skills_are_not_deleted_automatically(self):
        skills = self.module.canonical()
        self.module.sync(skills)
        with self.assertRaisesRegex(ValueError, 'review manually'):
            self.module.sync({})
        self.assertTrue((self.module.CLAUDE_SKILLS / 'example' / 'SKILL.md').exists())

    def test_invalid_frontmatter_is_rejected(self):
        for header in ('name: other\ndescription: Test', 'name: example\ndescription: []', '[]'):
            with self.subTest(header=header):
                (self.source / 'SKILL.md').write_text(f'---\n{header}\n---\n', encoding='utf-8')
                with self.assertRaises(ValueError):
                    self.module.canonical()

    def test_redirected_mirror_is_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        self.module.CLAUDE_SKILLS.parent.mkdir(parents=True)
        try:
            self.module.CLAUDE_SKILLS.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f'symlink creation unavailable: {error}')
        with self.assertRaisesRegex(ValueError, 'redirected'):
            self.module.sync(self.module.canonical())
        self.assertEqual(list(outside.iterdir()), [])


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script('discover-tools')

    def output(self, *arguments):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.module.main(arguments)
        return stream.getvalue()

    def test_json_has_provenance_and_intersected_filters(self):
        entries = json.loads(self.output('--game', 'r2', '--capability', 'runtime-testing',
                                        '--capability', 'mod-testing', '--integration', 'local-adapter', '--json'))
        self.assertTrue(entries)
        for entry in entries:
            self.assertIn('r2', entry['targets'])
            self.assertTrue({'runtime-testing', 'mod-testing'}.issubset(entry['capabilities']))
            self.assertEqual(entry['integration']['type'], 'local-adapter')
            self.assertIn('commit', entry['upstream'])
            self.assertIn('status', entry['verification'])

    def test_empty_json_and_invalid_game(self):
        self.assertEqual(json.loads(self.output('--capability', 'not-a-capability', '--json')), [])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            self.module.main(['--game', 'r4'])
        self.assertEqual(caught.exception.code, 2)

    def test_text_output_remains_compatible(self):
        self.assertIn('ares-map-harness-northstar: ARES Northstar map harness', self.output('--game', 'r2'))


if __name__ == '__main__':
    unittest.main()
