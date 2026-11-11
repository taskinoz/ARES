#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "registry" / "tools"


def load_entries() -> list[dict]:
    entries = []
    for path in sorted(TOOLS_DIR.glob("*.yaml")):
        entries.append(yaml.safe_load(path.read_text(encoding="utf-8")))
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="List tools by target/capability")
    parser.add_argument("--game", dest="game", help="Target game id (r1, tfo, r2, r5)")
    parser.add_argument("--capability", dest="capability", help="Capability filter")
    args = parser.parse_args()

    matches = []
    for entry in load_entries():
        if args.game and args.game not in entry.get("targets", []):
            continue
        if args.capability and args.capability not in entry.get("capabilities", []):
            continue
        matches.append(entry)

    for entry in matches:
        print(f"{entry['id']}: {entry['name']}")


if __name__ == "__main__":
    main()
