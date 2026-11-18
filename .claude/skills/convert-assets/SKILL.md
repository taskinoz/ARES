---
name: convert-assets
description: Convert assets across supported workflows while preserving provenance.
---

# Convert Assets

## Procedure
1. Identify source and target formats.
2. Select conversion tooling from registry.
3. Follow upstream conversion instructions.
4. Check converted models with the target's reader (`inspect-respawn-model`) and, for
   R5 collision, `validate-r5-collision`; test them in game with `run-harness`.
5. Record assumptions, artifacts, and limitations.

For animation/season conversions, query
`python scripts/discover-tools.py --game r5 --capability animation-conversion --json`
and read `r5-animation-converter` or `studiormdl`. Record source and destination
seasons independently; experimental S21 output is not established runtime support.
Use only upstream-documented CLI options, inspect licensing and preserve input
hashes. Do not run extracted assets through an S3-only reader and call a later
season verified. The source-routing guide is `docs/runtime-sources.md`.
