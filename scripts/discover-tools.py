#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "registry" / "tools"


def load_entries() -> list[dict]:
    entries = []
    for path in sorted(TOOLS_DIR.glob("*.yaml")):
        entries.append(yaml.safe_load(path.read_text(encoding="utf-8")))
    return entries


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="List tools by target/capability")
    parser.add_argument("--game", choices=("r1", "tfo", "r2", "r5"), help="Target game id")
    parser.add_argument("--capability", action="append", default=[], help="Required capability; repeat for intersection")
    parser.add_argument("--integration", choices=("local-adapter", "external-repository"))
    parser.add_argument("--json", action="store_true", help="Emit full entries including provenance and verification")
    args = parser.parse_args(argv)

    matches = []
    for entry in load_entries():
        if args.game and args.game not in entry.get("targets", []):
            continue
        if not set(args.capability).issubset(entry.get("capabilities", [])):
            continue
        if args.integration and args.integration != entry["integration"]["type"]:
            continue
        matches.append(entry)

    if args.json:
        print(json.dumps(matches, indent=2))
    else:
        for entry in matches:
            print(f"{entry['id']}: {entry['name']}")


if __name__ == "__main__":
    main()
