# Skills, hooks and harness audit - 2026-11-17

## Scope and environment

Targets: R1/R1Delta, TFO, R2/Northstar, R5/R5Reloaded. Additional sources include
Ion, Prime, Valkyrie, S21 SDKs, animation tools and two Recast forks. This is a
focused source/automation audit, not an exhaustive security certification.

Baseline ARES commit: `8b1c08b196d454a90e2d0e684dd5a49e5b8c7916`.
Environment: Windows, Python 3.10.7, Git 2.54.0.windows.1. Game installation
availability was not established: no installation path was requested or searched,
no game launched, no installed game files modified and no existing game/server
process stopped. Tests use temporary synthetic installs and owned helper processes.
Upstream repositories were read only, not modified, built or installed.

## Inventory and evidence

- Reviewed target instructions, skill metadata/workflows, mirror/discovery/vendor
  scripts, result-contract code, CI gates and selected adapter staging/controller
  paths. The final catalogue has 22 canonical skills and 37 tool entries.
- The repository has no tracked provider hook configuration. Local Git hooks
  contained sample files only and `core.hooksPath` was unset. This does not audit
  global provider settings, externally configured hooks or every upstream detour.
- In-game hooks include Northstar UI/client/server callbacks, TFO's temporary
  mapspawn instrumentation and R1Delta's temporary precache script. The Northstar
  packaged callback, opt-ins and Python transport received focused changes.
- CI already runs registry/mirror gates plus all four test suites. No automated
  game launch, dependency installation or global hook registration was added.
- Upstream revisions, source links and compatibility conflicts are documented in
  [runtime-sources.md](../runtime-sources.md) and the twelve new registry entries.
  These entries remain partially verified/documentation-inspected.

## Findings and remediation

| Priority | Finding | Resolution / evidence boundary |
| --- | --- | --- |
| High | R5 connection URLs used a textual loopback prefix; user-info URLs could name a remote host, and redirects/proxy configuration could carry the bearer token elsewhere. | Parse and validate origin, restrict endpoint, disable environment proxies and redirects. Tests cover hostile URLs, authenticated local round trip and refusal to follow a redirect. |
| High | Northstar accepted arbitrary existing profiles and special dot names, and lacked exclusive session ownership. Redirected paths could escape isolation. | Require profile marker; reject reserved/trailing-dot names and redirected staging/state paths; exclusive per-profile token/PID lock. Tests cover user-profile preservation and concurrent-session refusal. Real symlink tests may skip when Windows denies creation. |
| High | Ownership was recorded only after mod copying; failed copies could leave untracked partial mods. Direct `prepare()` failures did not guarantee rollback. | Mark/register destinations before copying, ignore source owner markers, roll back on preparation failure and refuse recursive/in-profile sources. Cleanup errors are no longer silently discarded. Synthetic failure test checks removal, exact enabled-state restoration and controller shutdown. |
| Medium | Repeated `close()` could restore old enabled state over later user edits. | Idempotent close and reuse rejection, with regression coverage. |
| Medium | Map prefix matching could stage neighboring maps. | Require exact BSP/base ENT, underscored ENT sidecars or dotted lump sidecars. Tests include both prefix-sharing and underscored neighboring BSP names. |
| Medium | Northstar controller accepted malformed JSON/non-object state and unbounded/invalid lengths; unknown endpoints succeeded. | Known routes, JSON-object/ack-ID validation, 64 KiB ceiling and socket timeout. Offline HTTP tests cover invalid state, lengths, endpoints and recovery. |
| Medium | Early Northstar server callback changed local-server settings before checking all documented opt-ins. | Require nonempty token and both HTTP opt-ins in that guard. Natively verified 2026-11-18 (see Validation follow-up). |
| Medium | Skill mirroring copied only SKILL.md, could delete unknown directories and could follow redirected paths. | Mirror complete resource trees, validate YAML metadata, reject redirections, preserve/refuse unexpected resources and keep `--check` read-only. Tests cover nested-resource drift, metadata and preservation. |
| Medium | Registry CLI validated schema but left filename/path checks to tests; discovery dropped provenance and silently accepted bad game IDs. | Enforce filename/contained-existing local paths and URI formats in the validator. Add full JSON, validated game/integration selection and intersected capability filters; regression tests cover rejection and compatibility. |
| Capability | Runtime forks, later-season tools and navigation sources were absent from discovery. | Twelve conservative, commit-pinned entries; routing guide covers all six additional developers. New build-navmesh skill and updated discovery/research/compile/conversion/runtime guidance. No new runtime parity claimed. |

## Validation commands and artifacts

Baseline: 61 tests in `tests/` passed before edits; registry and mirror checks
passed. Existing vendored-reader/socket ResourceWarnings were observed and are
not treated as new failures or fixed in upstream-owned files.

Final validation uses the same commands as CI:

```powershell
python scripts/validate-registry.py
python scripts/sync-agent-skills.py
python scripts/sync-agent-skills.py --check
python -m unittest discover -s tests -p "test_*.py"
python -m unittest discover -s tools -p "test_*.py"
python -m unittest discover -s harnesses/adapters -p "test_*.py"
python -m unittest discover -s harnesses/recipes -p "test_*.py"
git diff --check
```

The execution record and per-command logs are written under the ignored,
isolated `reports/automation-audit-2026-11-17/` directory. New upstream sources
were inspected using GitHub metadata, pinned raw documents and read-only
`git ls-remote --symref`. GitHub's unauthenticated API rate limit was reached;
read-only Git/raw-document access supplied the additional revision evidence.
The R5Reloaded website returned HTTP 403; its SDK source README was available.

Final outcome: **408 tests run, 406 passed and 2 skipped**, with no failures.
The suites ran 71 package/script tests, 172 map-tool tests, 164 adapter tests
and 1 recipe test. Both skips were real-directory symlink tests because this
Windows account lacks symlink creation privileges. Registry validation, mirror
check, new-skill metadata validation and `git diff --check` passed. ResourceWarnings
from existing vendored readers/socket tests remain; no runtime verification is
claimed from these results.

## Remaining work and verification labels

- **Verified (tool-level):** only the offline tests/gates recorded in the execution
  report. No chart of runtime parity or broad security assurance is implied.
- **Partially verified:** source integrations and workflow routing based on pinned
  upstream documentation. Licence directories with unresolved SPDX identification
  retain `license: null`; review them before code reuse or redistribution.
- **Experimental:** S21 animation output is explicitly marked experimental by its
  converter; no conversion or runtime validation occurred here.
- **Untested:** Ion/Prime/Valkyrie/S21
  runtime adaptation, AGENTLINK 2 integration, Recast baking/export/pathfinding and
  new compiler/converter outputs. Run matching-build native acceptance with
  explicit staging permission before deploying/releasing those changes.
- A leftover profile lock is intentionally not auto-reclaimed. Confirm the owning
  process/session has ended before manual recovery; use separate profiles for
  parallel runs. Forced termination can still require manual inspection.
- Result converters retain legacy report-shape assumptions. A follow-up should
  harden malformed/missing-report evidence and empty-result handling against the
  contract before treating arbitrary imported reports as trustworthy attestations.
- Vendored model harness implementation changes belong upstream. No automatic
  vendor refresh was performed, and historical verification entries were not
  relabelled simply because a newer revision exists.

## Validation follow-up (2026-11-18)

- Offline: `validate-registry.py` and `sync-agent-skills.py --check` pass;
  unittest discovery passes in `tests` (71, 1 skipped), `tools` (172),
  `harnesses/adapters` (173, 1 skipped) and `harnesses/recipes` (1). The two
  remaining ResourceWarnings come from unchanged code (`test_harness_r1delta.py`
  MCP client test and vendored `ares/r2/mdl53.py`).
- **Verified (native):** Northstar 1.31.15 at `C:/Games/Titanfall2`, profile
  `R2AresHarness`, stock `mp_glitch` in `tdm`. The updated server guard compiled
  and ran (`NSIsHttpEnabled`/`NSIsLocalHttpAllowed` resolve in the server VM), the
  local client connected, the trace and mode check ran, `trace_z` expectation
  passed, no script errors, exit 0. Afterwards the ARES mods and session lock were
  gone and `enabledmods.json` was byte-identical (SHA-256 unchanged). Evidence:
  `reports/automation-audit-2026-11-17/native/run2/`. Only the positive (opted-in)
  path was exercised natively; the negative guard path is covered offline only.
