"""List the ARES tools: `python -m ares` (add `--json` for a machine-readable catalogue).

Run a tool from the repository root with `python -m <module> --help`.
"""
import json
import sys

# module, targets, kind, purpose
CATALOGUE = [
    ('ares.r1.mdl52', ['r1'], 'reader', 'Titanfall 1 MDL v52 summary (header, bones, sequences, companions)'),
    ('ares.r2.mdl53', ['tfo', 'r2'], 'reader', 'Titanfall 2 MDL v53 header and section offsets'),
    ('ares.r5.mdl54', ['r5'], 'reader', 'Apex S0-S3 RMDL v54 (render, bones, sequences, animations; --target s0..s3)'),
    ('ares.source.ivp_phy', ['r1', 'tfo', 'r2'], 'reader', 'IVP PHY: standalone, embedded in v53, or beside a v52 model'),
    ('ares.r5.phy54', ['r5'], 'reader', 'early-Apex PHY: solids, convex hulls, keyvalues; hull checks'),
    ('ares.r5.bvh54', ['r5'], 'reader', 'early-Apex BVH collision: all leaf types, tree/box checks'),
    ('ares.r5.compare_phy54', ['r5'], 'compare', 'compare two early-Apex PHY files within fixed limits'),
    ('ares.r5.compare_bvh54', ['r5'], 'compare', 'compare the BVH collision of a rebuilt model with the original'),
    ('ares.r5.rpak', ['r5'], 'package', 'build an S3 RPak with a user-supplied RePak from --external-assets output'),
    ('ares.harness.r5reloaded', ['r5'], 'harness', 'isolated R5Reloaded run: spawns, sequences, collision, physics, ragdolls'),
    ('ares.harness.northstar', ['r2'], 'harness', 'Titanfall 2 / Northstar run: spawn, sequences, motion, physics, screenshots'),
    ('ares.harness.tfo', ['tfo'], 'harness', 'Titanfall Online (TFORevive) native v52 smoke test'),
    ('ares.harness.r1delta', ['r1'], 'harness', 'R1Delta addon staging, telemetry collection and cleanup'),
    ('ares.harness.r1delta_mcp', ['r1'], 'harness', "client for R1Delta's MCP server (console, squirrel, state, log)"),
    ('ares.harness.ion_mcp', ['r2'], 'harness', "client for Ion's MCP server (console, squirrel, state, log)"),
    ('ares.harness.r1delta_compare', ['r1'], 'harness', 'compare original and rebuilt models side by side in R1Delta'),
    ('ares.result', ['r1', 'tfo', 'r2', 'r5'], 'contract', 'convert a harness report into the ARES result contract'),
]


def main(argv):
    if '--json' in argv:
        print(json.dumps([dict(module=m, targets=t, kind=k, purpose=p) for m, t, k, p in CATALOGUE], indent=2))
        return 0
    width = max(len(m) for m, *_ in CATALOGUE)
    for module, targets, kind, purpose in CATALOGUE:
        print('%-*s  %-8s %-14s %s' % (width, module, kind, ','.join(targets), purpose))
    print('\nRun: python -m <module> --help   (from the repository root)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
