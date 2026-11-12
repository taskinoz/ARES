#!/usr/bin/env python3
"""Mirror canonical skills from .agents/skills/ into .claude/skills/.

Claude Code loads skills only from .claude/skills/<name>/SKILL.md, so each
canonical SKILL.md is copied there verbatim. Edit the canonical copy, then run
this script. With --check it changes nothing and exits 1 if the mirror is stale.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SKILLS = ROOT / ".agents" / "skills"
CLAUDE_SKILLS = ROOT / ".claude" / "skills"
FRONTMATTER = re.compile(r"\A---\nname: ([a-z0-9-]+)\ndescription: (.+?)\n---\n", re.S)


def canonical() -> dict[str, Path]:
    skills = {}
    for skill_dir in sorted(p for p in CANONICAL_SKILLS.iterdir() if p.is_dir()):
        doc = skill_dir / "SKILL.md"
        match = FRONTMATTER.match(doc.read_text(encoding="utf-8")) if doc.exists() else None
        if not match or match.group(1) != skill_dir.name:
            raise ValueError(f"{doc}: needs frontmatter with name: {skill_dir.name} and a description")
        skills[skill_dir.name] = doc
    return skills


def index_text(skills: dict[str, Path]) -> str:
    lines = ["# Skills", "", "Mirrored from `.agents/skills/` by `scripts/sync-agent-skills.py`.",
             "Edit the canonical copies there, then run the script.", ""]
    for name, doc in skills.items():
        description = FRONTMATTER.match(doc.read_text(encoding="utf-8")).group(2).strip()
        lines.append(f"- [{name}]({name}/SKILL.md): {description}")
    return "\n".join(lines) + "\n"


def stale(skills: dict[str, Path]) -> list[str]:
    problems = []
    for name, doc in skills.items():
        mirror = CLAUDE_SKILLS / name / "SKILL.md"
        if not mirror.exists() or mirror.read_bytes() != doc.read_bytes():
            problems.append(f"{mirror.relative_to(ROOT)} differs from {doc.relative_to(ROOT)}")
    for extra in (p for p in CLAUDE_SKILLS.iterdir() if p.is_dir() and p.name not in skills) if CLAUDE_SKILLS.exists() else ():
        problems.append(f"{extra.relative_to(ROOT)} has no canonical skill")
    index = CLAUDE_SKILLS / "README.md"
    if not index.exists() or index.read_text(encoding="utf-8") != index_text(skills):
        problems.append(".claude/skills/README.md is out of date")
    return problems


def sync(skills: dict[str, Path]) -> None:
    CLAUDE_SKILLS.mkdir(parents=True, exist_ok=True)
    for extra in [p for p in CLAUDE_SKILLS.iterdir() if p.is_dir() and p.name not in skills]:
        shutil.rmtree(extra)
    for stale_file in ("INDEX.md",):
        (CLAUDE_SKILLS / stale_file).unlink(missing_ok=True)
    for name, doc in skills.items():
        (CLAUDE_SKILLS / name).mkdir(exist_ok=True)
        shutil.copyfile(doc, CLAUDE_SKILLS / name / "SKILL.md")
    (CLAUDE_SKILLS / "README.md").write_text(index_text(skills), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report a stale mirror without writing")
    args = parser.parse_args()
    skills = canonical()
    if args.check:
        problems = stale(skills)
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    sync(skills)
    print(f"Mirrored {len(skills)} skills into {CLAUDE_SKILLS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
