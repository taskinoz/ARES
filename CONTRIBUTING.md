# Contributing to ARES

## Scope

ARES holds reusable tools, harnesses and skills that AI agents use to test
Respawn-engine maps, models, mods and conversions. Compilers and converters stay
in their own repositories and are listed in `registry/`.

## Rules

- Record verification status and evidence. Label anything that wasn't run in a
  game as unit-tested, partial or unverified.
- Keep tools standalone: no paths into other repositories or game installs, and
  no hard-coded user folders. Take game paths as arguments or `ARES_*`
  environment variables.
- Harnesses stage only owned files (with an owner marker), never overwrite
  something they don't own, and restore every file they change, including
  after failures.
- Never commit game files, extracted assets, credentials, tokens or binaries.
  Test fixtures must be synthetic or original.
- Keep changes focused. Code written with AI keeps the `Co-Authored-By` trailer
  and is covered by [AI.md](AI.md).

## Skills

Edit skills only in `.agents/skills/<name>/SKILL.md`, then mirror them for Claude Code:

```powershell
python scripts/sync-agent-skills.py
```

## Validation

Before opening a pull request:

```powershell
python -m pip install -r requirements.txt
python scripts/validate-registry.py
python scripts/sync-agent-skills.py --check
python -m unittest discover -s tests -p "test_*.py"
python -m unittest discover -s tools -p "test_*.py"
python -m unittest discover -s harnesses/adapters -p "test_*.py"
python -m unittest discover -s harnesses/recipes -p "test_*.py"
```

## Licensing

The repository is MIT licensed (see [LICENSE](LICENSE)), with this exception:
files whose header says GPL-2.0-or-later remain under that licence. These are
the format tools in `tools/` and the map harnesses in `harnesses/adapters/`,
which were moved from MRVN-Radiant. Keep each file's header when you change it.
