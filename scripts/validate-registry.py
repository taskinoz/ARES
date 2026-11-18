#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "registry" / "schema" / "tool.schema.json"
TOOLS_DIR = ROOT / "registry" / "tools"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def load_registry_entries() -> list[tuple[Path, dict]]:
    entries: list[tuple[Path, dict]] = []
    for path in sorted(TOOLS_DIR.glob("*.yaml")):
        entries.append((path, yaml.safe_load(path.read_text(encoding="utf-8"))))
    return entries


def validate_registry() -> None:
    schema = load_schema()
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())

    ids: set[str] = set()
    for path, entry in load_registry_entries():
        validator.validate(entry)
        tool_id = entry["id"]
        if tool_id in ids:
            raise ValueError(f"Duplicate tool id detected: {tool_id} ({path})")
        ids.add(tool_id)
        if path.stem != tool_id:
            raise ValueError(f"Registry filename must match tool id: {path} ({tool_id})")
        if entry["integration"]["type"] == "local-adapter":
            for key in ("readme_path", "agents_path", "skills_path", "harness_path"):
                value = entry["upstream"][key]
                if value is None:
                    continue
                candidate = (ROOT / value).resolve()
                if not value or not candidate.is_relative_to(ROOT) or not candidate.exists():
                    raise ValueError(f"{path}: {key} must point inside ARES to an existing file or directory: {value}")

    if not ids:
        raise ValueError("No registry entries found.")


def main() -> None:
    validate_registry()
    print("Registry validation passed")


if __name__ == "__main__":
    main()
