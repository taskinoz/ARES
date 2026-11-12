# AI disclosure

ARES was built with AI. The maintainer, Tristan Kennedy (taskinoz), directed the
work, chose what to keep and ran the in-game tests. The code, documentation and
skills were written by AI tools:

- **Repository scaffold** (registry schema, game profiles, CI and the first skill
  stubs): GitHub Copilot's coding agent, merged in pull request #1.
- **Map format tools and map harnesses** (`tools/`, `harnesses/adapters/`,
  `harnesses/docs/`, the `ARES.MapHarness` Northstar mod): written with
  Anthropic's Claude (through Claude Code) and OpenAI's Codex in
  [taskinoz/MRVN-Radiant](https://github.com/taskinoz/MRVN-Radiant), then moved
  here by Claude.
- **Model readers and model harnesses** (`ares/`): written with Anthropic's Claude
  (through Claude Code) in taskinoz's r1-, r2- and r5-model-compiler repositories, then
  vendored here by Claude (see `ares/SOURCES.json`).
- **Skills and agent instructions** (`.agents/skills/`, `AGENTS.md`): Claude.

Commits written this way carry a `Co-Authored-By` trailer.

## The human-built work this depends on

ARES drives and reads files from projects built by people. Use those projects
as their authors made them:

- [MRVN-Radiant/MRVN-Radiant](https://github.com/MRVN-Radiant/MRVN-Radiant): the
  original, human-built Respawn map editor and compiler that the format research
  extends. ARES links to taskinoz's AI-modified fork only for provenance.
- [Northstar](https://github.com/R2Northstar), [R1Delta](https://github.com/r1delta),
  TFORevive and [R5Reloaded](https://github.com/Mauler125/r5sdk): the community
  runtimes the harnesses launch. ARES doesn't modify their files; it stages
  owned mods or profiles and removes them afterwards.

## Verification

Each harness and registry entry records how it was checked. A harness that
was only unit-tested is marked partial or unverified until it has been run
in game from ARES.
