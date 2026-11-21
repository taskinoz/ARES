# R5 agent guidance

Applicable tool IDs:
- apex-to-titanfall-2
- mrvn-radiant
- r5-model-compiler
- ares-model-readers
- ares-r5-collision
- ares-rpak-packager
- ares-model-harness-r5reloaded
- ares-map-harness-r5reloaded
- ares-map-harness-flowstate
- ares-bsp-tools

Do not claim full runtime parity with R2 or R1 toolchains.

Before any R5 runtime operation, ask the user for the exact R5Reloaded or
R5Flowstate install folder and identify whether the operation targets the S21
client, S3 dedicated server or R5Reloaded runtime. Do not assume an Apex or
Flowstate install path.

Runtime/build routing and additional developer sources: [source guide](../../docs/runtime-sources.md).
Modern seasons: R5Flowstate (successor to R5Valkyrie) is the S21-client/S3-dedicated
bridge; its tools are the `r5flowstate-*` entries (map compiler, S30 port kit, RePak,
RSX, rmdlconv, AnimConv and bspconv S21 forks). See the source guide's R5Flowstate section.
S21 client and S3 dedicated products in `r5sdk-s21` have different ABIs. The
`r5sdk-agentlink` source uses AGENTLINK 2, not the legacy SDK 2.3 RCON adapter.
These are upstream-documented candidates, not ARES runtime-verified integrations.
Recast work uses skill `build-navmesh`; later-season animation conversion uses
the `r5-animation-converter` entry and its explicit experimental-output limits.

Model tools (`ares/`): skills `inspect-respawn-model`, `test-r5reloaded`. Model harness: package with `python -m ares.r5.rpak`, run `python -m ares.harness.r5reloaded`; check collision with `validate-r5-collision`.

Map tools: skill `inspect-bsp` (`tools/`, BSP v47, Apex RPak v8). Map harness: `python harnesses/adapters/r5_harness.py` + `r5_harnessctl.py` (SDK 2.3 dedicated; [guide](../../harnesses/docs/r5reloaded.md)). Server-side only; it does not check rendering. Skill `run-harness`.

Rendered Apex views: `python harnesses/adapters/flowstate_harness.py` runs R5Flowstate (S21 client + S3 dedicated) from an isolated hard-linked copy, moves its client script camera, hides the HUD and takes engine screenshots ([guide](../../harnesses/docs/flowstate.md)).
