#!/usr/bin/env python3
"""Refresh the vendored tools in `ares/` from the upstream compiler repositories.

ARES keeps standalone copies so it runs without the compiler repositories. This script
regenerates them from local checkouts of taskinoz/r1-model-compiler,
r2-model-compiler and r5-model-compiler (siblings under --source-root), applying the
same import rewrites each time. Every rewrite must match exactly once, so a changed
upstream file fails loudly instead of being copied half-adapted.

  python scripts/vendor-upstream.py --source-root <dir> --check   # report drift only
  python scripts/vendor-upstream.py --source-root <dir>           # rewrite ares/ + SOURCES.json

Review the diff and run the tests after a refresh. Files ARES owns (`ares/result.py`,
`ares/__main__.py`, package `__init__.py` files) are not touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'ares'

IVP_MAIN_UPSTREAM = """if __name__ == '__main__':
    sys.path.insert(0, __file__.rsplit('\\\\', 1)[0].rsplit('/', 1)[0])
    import mdl53
    d = open(sys.argv[1], 'rb').read()
    if d[:4] == b'IDST':
        h = mdl53.Model(d).hdr
        p = parse_phy(d[h['phyOffset']:h['phyOffset'] + h['phySize']])
    else:
        p = parse_phy(d)
"""
IVP_MAIN_ARES = """def load(path):
    \"\"\"Parse the PHY of a standalone .phy, a v53 model with embedded physics, or a v52
    model's companion .phy.\"\"\"
    from pathlib import Path
    from ares.r2 import mdl53
    source = Path(path)
    d = source.read_bytes()
    if d[:4] != b'IDST':
        return parse_phy(d)
    version = struct.unpack_from('<i', d, 4)[0]
    if version == 53:
        h = mdl53.Model(d).hdr
        if h['phySize']:
            return parse_phy(d[h['phyOffset']:h['phyOffset'] + h['phySize']])
    companion = source.with_suffix('.phy')
    if companion.exists():
        return parse_phy(companion.read_bytes())
    raise ValueError('no PHY found in or beside %s (MDL v%d)' % (source, version))


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=load.__doc__)
    ap.add_argument('path', help='.phy, or a v52/v53 .mdl')
    p = load(ap.parse_args().path)
"""

# destination: (repository, source path, [(old, new), ...])
PLAN = {
    'source/ivp_phy.py': ('r2-model-compiler', 'tools/phy.py', [
        ('"""Reader for Source/Titanfall 2 PHY data (IVP compact surfaces + keyvalue text).',
         '"""Reader for Source/Titanfall PHY data (IVP compact surfaces + keyvalue text): R1 (v52\n'
         'companion .phy), TFO and R2 (v53, embedded or companion .phy).'),
        (IVP_MAIN_UPSTREAM, IVP_MAIN_ARES),
    ]),
    'r1/mdl52.py': ('r1-model-compiler', 'tools/mdl52.py', []),
    'r2/mdl53.py': ('r2-model-compiler', 'tools/mdl53.py', [
        ('if __name__ == "__main__":\n    for p in sys.argv[1:]:\n        m, offs = survey(p)',
         'if __name__ == "__main__":\n    import argparse\n'
         '    ap = argparse.ArgumentParser(description="List the header fields and section offsets of MDL v53 files.")\n'
         '    ap.add_argument("models", nargs="+")\n    for p in ap.parse_args().models:\n        m, offs = survey(p)'),
    ]),
    'r5/mdl54.py': ('r5-model-compiler', 'tools/mdl54.py', [
        ("sys.path.insert(0,str(Path(__file__).resolve().parent))\n", ''),
        ("import mdl53 as common", "from ares.r2 import mdl53 as common"),
        ("from decompile53 import unpack_q64, matrix_angles, quat_matrix",
         "from ares.common.geometry import unpack_q64, matrix_angles, quat_matrix"),
    ]),
    'r5/phy54.py': ('r5-model-compiler', 'tools/phy54.py', []),
    'r5/bvh54.py': ('r5-model-compiler', 'tools/bvh54.py', []),
    'r5/compare_phy54.py': ('r5-model-compiler', 'tools/compare_phy54.py', [
        ("sys.path.insert(0, str(Path(__file__).resolve().parent))\n", ''),
        ("import phy54", "from ares.r5 import phy54"),
    ]),
    'r5/compare_bvh54.py': ('r5-model-compiler', 'tools/compare_bvh54.py', [
        ("sys.path.insert(0, str(Path(__file__).resolve().parent))\n", ''),
        ("import bvh54  # noqa: E402", "from ares.r5 import bvh54"),
        ("    from mdl54 import Model, PROFILES\n", "    from ares.r5.mdl54 import Model\n"),
    ]),
    'r5/rpak.py': ('r5-model-compiler', 'tools/pack54.py', [
        ("sys.path.insert(0,str(Path(__file__).resolve().parent))\nfrom mdl54 import Model, SequenceAsset",
         "from ares.r5.mdl54 import Model, SequenceAsset"),
    ]),
    'harness/northstar.py': ('r2-model-compiler', 'tools/ingame_test.py', []),
    'harness/tfo.py': ('r1-model-compiler', 'tools/ingame_test52.py', [
        ("import mdl52\n", "from ares.r1 import mdl52\n"),
        ("    parser.add_argument('--compiler',type=Path,default=Path(os.environ.get('R1C_COMPILER',Path(__file__).resolve().parents[1]/'build/r1studiomdl.exe')),help='compiler",
         "    parser.add_argument('--compiler',type=Path,default=Path(os.environ['R1C_COMPILER']) if os.environ.get('R1C_COMPILER') else None,help='compiler"),
        ("    if args.compiler.is_file():", "    if args.compiler and args.compiler.is_file():"),
    ]),
    'harness/r1delta.py': ('r1-model-compiler', 'tools/ingame_test_r1delta.py', [
        ("import ingame_test52 as common\nimport mdl52\n", "import os\n\nfrom ares.harness import tfo as common\nfrom ares.r1 import mdl52\n"),
        ("    compiler = Path(__file__).resolve().parents[1]/'build/r1studiomdl.exe'",
         "    # provenance only (inputs are not recompiled): R1C_COMPILER, when set\n"
         "    compiler = Path(os.environ['R1C_COMPILER']) if os.environ.get('R1C_COMPILER') else None"),
        ("'compiler_sha256':digest(compiler) if compiler.exists() else None,",
         "'compiler_sha256':digest(compiler) if compiler and compiler.is_file() else None,"),
        ("tools/r1delta_mcp.py", "python -m ares.harness.r1delta_mcp"),
    ]),
    'harness/r1delta_mcp.py': ('r1-model-compiler', 'tools/r1delta_mcp.py', []),
    'harness/r1delta_compare.py': ('r1-model-compiler', 'tools/r1delta_compare.py', [
        ("import r1delta_mcp", "from ares.harness import r1delta_mcp"),
    ]),
    'harness/r5reloaded.py': ('r5-model-compiler', 'tools/ingame54.py', []),
}
GEOMETRY = ('r2-model-compiler', 'tools/decompile53.py', ('matrix_angles', 'quat_matrix', 'unpack_q64'))


def read(path: Path) -> str:
    return path.read_bytes().decode('utf-8').replace('\r\n', '\n')


def commit(repo: Path) -> str:
    return subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()


def build(source_root: Path) -> tuple[dict[str, str], dict[str, dict]]:
    files, sources = {}, {}
    for dest, (repo, src, edits) in PLAN.items():
        path = source_root / repo / src
        text = read(path)
        for old, new in edits:
            count = text.count(old)
            if count != 1:
                raise SystemExit('%s/%s: expected one %r, found %d; adapt the rewrite' % (repo, src, old[:60], count))
            text = text.replace(old, new)
        files[dest] = text
        sources[dest] = dict(repository='taskinoz/' + repo, path=src, commit=commit(source_root / repo),
                             source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    repo, src, names = GEOMETRY
    text = read(source_root / repo / src)

    def function(name: str) -> str:
        start = text.index('def %s(' % name)
        return text[start:text.index('\n\n\n', start)]
    files['common/geometry.py'] = ('"""Rotation helpers shared by the Respawn model readers (from r2-model-compiler)."""\n'
                                   'import math\n\n\n' + '\n\n\n'.join(function(n) for n in names) + '\n')
    sources['common/geometry.py'] = dict(repository='taskinoz/' + repo, path='%s (%s)' % (src, ', '.join(names)),
                                         commit=commit(source_root / repo))
    return files, sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source-root', type=Path, required=True,
                        help='folder holding r1-model-compiler, r2-model-compiler and r5-model-compiler checkouts')
    parser.add_argument('--check', action='store_true', help='report files that differ; write nothing')
    args = parser.parse_args()
    files, sources = build(args.source_root)
    drift = [dest for dest, text in files.items()
             if not (PKG / dest).exists() or read(PKG / dest) != text]
    if args.check:
        for dest in drift:
            print('differs from upstream:', dest)
        print('%d of %d vendored files differ' % (len(drift), len(files)))
        return 1 if drift else 0
    for dest, text in files.items():
        (PKG / dest).parent.mkdir(parents=True, exist_ok=True)
        (PKG / dest).write_bytes(text.encode('utf-8'))
    (PKG / 'SOURCES.json').write_text(json.dumps(sources, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print('refreshed %d files (%d changed)' % (len(files), len(drift)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
