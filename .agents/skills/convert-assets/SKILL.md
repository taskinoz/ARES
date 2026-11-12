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
