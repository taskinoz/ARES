from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "validate-registry.py"


def load_module():
    spec = importlib.util.spec_from_file_location("validate_registry", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


class RegistryValidationTests(unittest.TestCase):
    def test_registry_validation_passes(self):
        module = load_module()
        module.validate_registry()

    def test_expected_tool_count(self):
        tool_files = list((ROOT / "registry" / "tools").glob("*.yaml"))
        self.assertEqual(len(tool_files), 6)


if __name__ == "__main__":
    unittest.main()
