#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SKILLS = ROOT / ".agents" / "skills"
CLAUDE_SKILLS = ROOT / ".claude" / "skills"


def main() -> None:
    CLAUDE_SKILLS.mkdir(parents=True, exist_ok=True)
    index = CLAUDE_SKILLS / "INDEX.md"
    lines = ["# Synced skill index", "", "Canonical skill definitions:", ""]
    for skill_dir in sorted(CANONICAL_SKILLS.iterdir()):
        skill_doc = skill_dir / "SKILL.md"
        if skill_doc.exists():
            lines.append(f"- ../{skill_dir.relative_to(ROOT)}")
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {index}")


if __name__ == "__main__":
    main()
