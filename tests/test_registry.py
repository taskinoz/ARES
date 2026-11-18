from __future__ import annotations

import importlib.util
import unittest
from unittest.mock import patch
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate-registry.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_registry", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def entries():
    return [(path, yaml.safe_load(path.read_text(encoding="utf-8"))) for path in sorted((ROOT / "registry" / "tools").glob("*.yaml"))]


class RegistryValidationTests(unittest.TestCase):
    def test_validator_rejects_filename_mismatch(self):
        module = load_module()
        path, entry = entries()[0]
        with patch.object(module, 'load_registry_entries', return_value=[(path.with_name('wrong.yaml'), entry)]):
            with self.assertRaisesRegex(ValueError, 'filename'):
                module.validate_registry()

    def test_validator_rejects_missing_and_escaping_local_paths(self):
        module = load_module()
        path, original = next((path, entry) for path, entry in entries()
                              if entry['integration']['type'] == 'local-adapter')
        for value in ('../outside', 'does-not-exist', ''):
            entry = dict(original, upstream=dict(original['upstream'], harness_path=value))
            with self.subTest(value=value), patch.object(module, 'load_registry_entries', return_value=[(path, entry)]):
                with self.assertRaisesRegex(ValueError, 'inside ARES'):
                    module.validate_registry()

    def test_registry_validation_passes(self):
        module = load_module()
        module.validate_registry()

    def test_file_names_match_ids(self):
        for path, entry in entries():
            with self.subTest(path=path.name):
                self.assertEqual(path.stem, entry["id"])

    def test_local_adapters_point_at_files_in_this_repository(self):
        local = [(path, entry) for path, entry in entries() if entry["integration"]["type"] == "local-adapter"]
        self.assertTrue(local)
        for path, entry in local:
            with self.subTest(path=path.name):
                for key in ("readme_path", "agents_path", "skills_path", "harness_path"):
                    value = entry["upstream"][key]
                    if value is not None:
                        self.assertTrue((ROOT / value).exists(), f"{key}: {value} does not exist")


if __name__ == "__main__":
    unittest.main()
