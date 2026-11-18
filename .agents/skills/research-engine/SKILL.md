---
name: research-engine
description: Investigate engine behaviour and document evidence-backed findings.
---

# Research Engine

## Procedure
1. Frame a specific technical question.
2. Gather authoritative sources.
3. Separate verified facts from hypotheses.
4. Document findings in `docs/research/` with citations.

## Evidence boundaries

- Use `python scripts/discover-tools.py --game <target> --capability runtime-source --json`
  and `docs/runtime-sources.md` to find upstream code. Record the source commit,
  game build and module hash for binary findings; moving branches are not evidence pins.
- For hook changes, identify the VM (UI/client/server), initialization order,
  opt-in conditions, reload behaviour and cleanup owner. An HTTP round trip or
  source-text assertion is a tool-level check, not proof that a Squirrel hook ran.
- Keep observations, inferences and unresolved conflicts separate. A fork's name
  or ancestry does not establish protocol or asset compatibility.
- Record a minimal reproducer, expected/observed output, artifacts and a next
  falsifying test. Never promote an isolated probe to whole-engine parity.
