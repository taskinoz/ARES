# Runtime, SDK and navigation source routing

Inspected on 2026-11-17. These are source-discovery integrations, **partially
verified** by metadata and documentation inspection, not newly tested game
adapters. Registered revisions and evidence are in `registry/tools/`. A target
tag routes a search; it does not imply binary, scripting, asset or wire parity.

## Find sources without losing provenance

```powershell
python scripts/discover-tools.py --game r2 --capability runtime-source --json
python scripts/discover-tools.py --game r5 --capability agent-control --json
python scripts/discover-tools.py --game r2 --capability navmesh-generation --json
python scripts/discover-tools.py --game r5 --capability animation-conversion --json
python scripts/discover-tools.py --game r2 --integration local-adapter --json
```

Repeated `--capability` flags intersect. JSON includes full entries, verification
notes, commits and documentation. Unsupported game IDs are rejected instead of
silently returning an empty list. ARES target IDs follow Respawn's engine naming:
`r1` Titanfall, `r2` Titanfall 2, `r5` Apex Legends (`tfo` is Titanfall Online).
There is no `r3`/`r4` target. R5Valkyrie is an Apex Legends (R5) runtime: route it
under `r5` and record its exact SDK/build and season.

## Runtime identity matters

| Runtime/source | Routing and evidence boundary |
| --- | --- |
| [R1Delta](https://github.com/r1delta/r1delta), [docs](https://github.com/r1delta/docs) | R1 only. Keep R1Delta and TFO runtime evidence separate. |
| [Northstar](https://github.com/R2Northstar/NorthstarLauncher), [wiki](https://docs.northstar.tf/Wiki/), [modding](https://docs.northstar.tf/Modding/) | R2. Existing ARES Northstar evidence is tied to the builds in the harness registry, not every new launcher revision. |
| [Ion releases](https://github.com/R2Ion/Ion), [launcher source](https://github.com/r2ion/IonLauncher) | R2 candidate, not an ARES-validated runtime. Release and launcher revisions differ. Release README documents `NSIsVanilla()` instead of compile-time `VANILLA` checks for runtime switching. Recheck UI/server/client initialization and mod identity on Ion. |
| [Northstar Prime](https://github.com/F1F7Y/NorthstarPrime) | `primedev` reference. Its README warns users must fix their own problems. Do not present it as the maintained Northstar adapter. |
| [Mauler125 R5 SDK](https://github.com/Mauler125/r5sdk) | Inspected `p4sync` README lists S3 N1094. ARES's legacy SDK 2.3 dedicated adapter is not proof of compatibility with every source revision. |
| [Valkyrie SDK](https://github.com/r5valkyrie/r5sdk), [organization](https://github.com/orgs/r5valkyrie/repositories) | R5 (Apex Legends) later-season runtime. The inspected SDK README still lists S3 N1094; that repository alone does not resolve later-season compatibility. |
| [KralRindo S21 SDK](https://github.com/kralrindo/s21-r5sdk) | Its `s21-unify` README and `AGENTS.md` explicitly distinguish an S21 client from an S3 dedicated server. This is stronger later-season evidence, but still upstream-documented rather than ARES runtime-verified. |

The S21 SDK names client build `R5pc_r5-211_J12_CL6933961_2024_06_14_13_58`
and dedicated build `R5pc_r5launch_N1094_CL456479_2019_10_30_05_20_PM`.
Follow its upstream `AGENTS.md`: product macros, layouts, precompiled headers and
hook ownership differ. Do not copy offsets or assume the same ABI across products.

## Agent-link control is not legacy RCON

[CafeFPS/r5sdk-mcp](https://github.com/CafeFPS/r5sdk-mcp), at
`444c3b4abf413f740a25731f883cc86d561d3a3e`, documents **AGENTLINK 2**:
a token-authenticated loopback line protocol, not RCON. Its GitHub repository
description still mentions RCON; use the pinned README/protocol instead.

The README requires an SDK with the agent link, matching `agent/` scripts,
Windows, Node 18+ and explicit `-devsdk` or `-agentlink` opt-in. It documents
server/client links separately and per-launch tokens. Do not attach the ARES
legacy netconsole encoder to these ports, forward them, or log their tokens.
Do not assume another S21 SDK includes this link without inspecting that build.

This is a high-value future integration: VM execution, events, named map places,
player control and client screenshots. No MCP installation, SDK deployment or
ARES agent-link runtime validation was performed during this audit.

## Additional developer sources

All six user-supplied profiles were enumerated through GitHub's public repository
API. Selected revisions were then inspected through pinned raw READMEs and
read-only `git ls-remote --symref` after the unauthenticated API rate limit was
reached. A fork relationship is a discovery lead, not season support evidence.

| Developer | Selected source and inspected revision | What to use it for / limitation |
| --- | --- | --- |
| [CafeFPS](https://github.com/CafeFPS) | [r5sdk-mcp](https://github.com/CafeFPS/r5sdk-mcp/tree/444c3b4abf413f740a25731f883cc86d561d3a3e); [r5sdk](https://github.com/CafeFPS/r5sdk/tree/914bf2bb97dd3ef04bbd29390e9cd1c356ce9ec0) | Agent-link automation candidate; the SDK README itself still lists S3. Profile also exposes BSP/model conversion forks. |
| [0Mephisto](https://github.com/0Mephisto) | [r5_flowstate](https://github.com/0Mephisto/r5_flowstate/tree/78157443738608cc080bab5a29743011a97bcf71) | Gameplay scripting reference; README describes systems powered by S21 scripts. This is not proof of an S21 native ABI or drop-in server compatibility. |
| [zeex64](https://github.com/zeex64) | [studiormdl](https://github.com/zeex64/studiormdl/tree/c74cc68846354739aa49b31a51ba9655f1fd7b52) | QC/model compiler candidate. README specifies **S3 RMDL v54 subversion 10**, not a general S21 compiler, and warns it is incomplete. Other leads include R5Admin, RePak and RSXPlus. |
| [ReGlitched](https://github.com/ReGlitched) | [r5sdk](https://github.com/ReGlitched/r5sdk/tree/ece0cb55ef9be0d1b89ac75c295b08f34e2179c8) | SDK comparison reference; inspected README still lists S3. Flowstate and RSX forks are discovery leads, not verified later-season adapters. |
| [kralrindo](https://github.com/kralrindo) | [s21-r5sdk](https://github.com/kralrindo/s21-r5sdk/tree/10077bbf020292fa0bab69d9a9a05fef125d6ba5) | Explicit split S21-client/S3-dedicated evidence. Asset/script forks must retain their own build and format identity. |
| [someoneatemylastsliceofpizza](https://github.com/someoneatemylastsliceofpizza) | [R5-AnimConv](https://github.com/someoneatemylastsliceofpizza/R5-AnimConv/tree/6d2ff73da25dc23cab3e458b80f36493689fc68b); [R5-AnimInspector](https://github.com/someoneatemylastsliceofpizza/R5-AnimInspector/tree/26b1777b967621f7073830cc8c2d9d3185eed633) | AnimConv documents MDL v49/v53 and RSEQ seasons 7-28 input, S3 and **experimental S21** output. AnimInspector documents season 3 and 9-27 QC generation. No ARES conversion/runtime tests yet. |

## Navigation sources

- [Mauler125/recastnavigation](https://github.com/Mauler125/recastnavigation):
  candidate for R2/R5 geometry baking and Detour queries. The inspected README is
  generic Recast documentation, not proof of game-specific export compatibility.
- [r-ex/r2recast](https://github.com/r-ex/r2recast): R2 candidate whose default
  branch is `Change-XZY-to-XYZ-coordinates`. Establish coordinate basis, scale,
  winding, agent bounds and file version explicitly; a branch name is not proof
  that all inputs/outputs share the game's coordinate system.

Use the `build-navmesh` skill. Existing TF1/TFO `navigation_probe` evidence is for
sampled native grunt routes using node graphs, not Recast baking or Apex AI parity.
