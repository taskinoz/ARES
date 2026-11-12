---
name: compile-model
description: Compile models with the registered Respawn compilers and validate the output with ARES readers and harnesses.
---

# Compile Model

## Procedure
1. Identify the target game and format: R1/TFO MDL v52 (`r1-model-compiler`), R2 MDL v53
   (`r2-model-compiler`), R5 RMDL v54 (`r5-model-compiler`, private; `--target s0..s3`).
2. Read the compiler's own README/AGENTS for QC syntax and options.
3. Compile into an isolated output folder.
4. Check the output statically (`inspect-respawn-model`; for R5 collision,
   `validate-r5-collision`). When rebuilding an original, compare against it.
5. Get runtime evidence with the target's harness (`run-harness`).
6. Report the compiler commit/hash, commands, checks and verification level.
