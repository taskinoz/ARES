# Contributing to ARES

## Scope

ARES is a coordination and knowledge repository. Upstream tool repositories remain the implementation source of truth.

## Rules

- Prefer references to upstream docs over copied instructions.
- Record verification status and evidence sources.
- Explicitly label experimental or unverified behaviour.
- Keep changes minimal and focused.
- Do not commit proprietary assets, credentials, or binaries.

## Validation

Before opening a PR:

1. `python scripts/validate-registry.py`
2. `python -m unittest discover -s tests -p "test_*.py"`
3. Ensure links between local docs resolve.
