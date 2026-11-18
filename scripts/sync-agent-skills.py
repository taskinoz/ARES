#!/usr/bin/env python3
"""Mirror canonical skills from .agents/skills/ into .claude/skills/.

Claude Code loads skills only from .claude/skills/<name>/SKILL.md, so each
canonical skill and its supporting resources are copied there verbatim. Edit the canonical copy, then run
this script. With --check it changes nothing and exits 1 if the mirror is stale.
Unexpected mirror files are reported, never deleted automatically.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SKILLS = ROOT / ".agents" / "skills"
CLAUDE_SKILLS = ROOT / ".claude" / "skills"
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.S)


def metadata(doc: Path) -> dict:
    match = FRONTMATTER.match(doc.read_text(encoding="utf-8")) if doc.is_file() else None
    data = yaml.safe_load(match.group(1)) if match else None
    if (not isinstance(data, dict) or data.get("name") != doc.parent.name or
            not re.fullmatch(r"[a-z0-9-]+", str(data.get("name", ""))) or
            not isinstance(data.get("description"), str) or not data["description"].strip()):
        raise ValueError(f"{doc}: needs frontmatter with name: {doc.parent.name} and a description")
    return data


def tree_files(directory: Path) -> dict[Path, Path]:
    if directory.is_symlink() or directory.resolve() != directory.absolute():
        raise ValueError(f"refusing redirected skill directory: {directory}")
    files = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError(f"refusing redirected skill resource: {path}")
        if path.is_file():
            files[path.relative_to(directory)] = path
    return files


def canonical() -> dict[str, Path]:
    tree_files(CANONICAL_SKILLS)
    skills = {}
    for skill_dir in sorted(p for p in CANONICAL_SKILLS.iterdir() if p.is_dir()):
        doc = skill_dir / "SKILL.md"
        metadata(doc)
        skills[skill_dir.name] = doc
    return skills


def index_text(skills: dict[str, Path]) -> str:
    lines = ["# Skills", "", "Mirrored from `.agents/skills/` by `scripts/sync-agent-skills.py`.",
             "Edit the canonical copies there, then run the script.", ""]
    for name, doc in skills.items():
        description = " ".join(metadata(doc)["description"].split())
        lines.append(f"- [{name}]({name}/SKILL.md): {description}")
    return "\n".join(lines) + "\n"


def stale(skills: dict[str, Path]) -> list[str]:
    problems = []
    actual = tree_files(CLAUDE_SKILLS)
    for name, doc in skills.items():
        for relative, source in tree_files(doc.parent).items():
            mirror = CLAUDE_SKILLS / name / relative
            if not mirror.is_file() or mirror.read_bytes() != source.read_bytes():
                problems.append(f"{mirror.relative_to(ROOT)} differs from {source.relative_to(ROOT)}")
    expected = {Path(name) / relative for name, doc in skills.items() for relative in tree_files(doc.parent)}
    for relative in sorted(set(actual) - expected - {Path("README.md")}):
        problems.append(f"{(CLAUDE_SKILLS / relative).relative_to(ROOT)} has no canonical resource; review manually")
    for extra in (p for p in CLAUDE_SKILLS.iterdir() if p.is_dir() and p.name not in skills) if CLAUDE_SKILLS.exists() else ():
        problems.append(f"{extra.relative_to(ROOT)} has no canonical skill")
    index = CLAUDE_SKILLS / "README.md"
    if not index.exists() or index.read_text(encoding="utf-8") != index_text(skills):
        problems.append(".claude/skills/README.md is out of date")
    return problems


def sync(skills: dict[str, Path]) -> None:
    actual = tree_files(CLAUDE_SKILLS)
    expected = {Path(name) / relative for name, doc in skills.items() for relative in tree_files(doc.parent)}
    unexpected = set(actual) - expected - {Path("README.md")}
    extra_dirs = [p for p in CLAUDE_SKILLS.iterdir() if p.is_dir() and p.name not in skills] if CLAUDE_SKILLS.exists() else []
    if unexpected or extra_dirs:
        raise ValueError("unexpected mirror resources; review manually before syncing: " +
                         ", ".join(str(path) for path in sorted(unexpected) + extra_dirs))
    CLAUDE_SKILLS.mkdir(parents=True, exist_ok=True)
    for name, doc in skills.items():
        for relative, source in tree_files(doc.parent).items():
            target = CLAUDE_SKILLS / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    (CLAUDE_SKILLS / "README.md").write_text(index_text(skills), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report a stale mirror without writing")
    args = parser.parse_args()
    try:
        skills = canonical()
        if args.check:
            problems = stale(skills)
            for problem in problems:
                print(problem)
            return 1 if problems else 0
        else:
            sync(skills)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"Mirrored {len(skills)} skills into {CLAUDE_SKILLS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
