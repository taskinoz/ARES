#!/usr/bin/env python3
"""Run ARES map checks in Ion (an R2 / Northstar fork) without touching an existing install.

Ion ships its MCP server inside ``R2Northstar/Northstar.dll``; the ARES map
harness mod still supplies the check operations. This adapter prepares a
separate runtime folder: game files are hard-linked from the Titanfall 2
install, writable folders are copied, and the Ion release is overlaid with
real copies so no original file is modified. A marker makes the runtime
single-owner and refuses a different source or release.

  python harnesses/adapters/ion_harness.py --game C:/Games/Titanfall2 \\
      --ion C:/Downloads/Ion.release.v1.31.15 --prepare-only

  python harnesses/adapters/ion_harness.py --game C:/Games/Titanfall2 \\
      --ion C:/Downloads/Ion.release.v1.31.15 --map mp_glitch \\
      --checks checks.json --output REPORT_DIR

The isolated profile is R2AresIon by default (never R2Northstar). Ion's MCP
listener starts on 127.0.0.1:<mcp-port> and its state/log are included in
report.json. The result contract records tool='ion_harness'; a run is only
verified when the game actually launched and the checks finished.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # standalone runs need the ares package for MCP
sys.path.insert(0, str(Path(__file__).resolve().parent))
import northstar_harness as nh  # noqa: E402

MARKER = '.ares-ion-runtime'
# Folders the game or Northstar write to: real copies, never hard links.
COPY_PATHS = {Path('r2/cfg'), Path('r2/screenshots')}
RELEASE_KEYS = (Path('NorthstarLauncher.exe'), Path('R2Northstar/Northstar.dll'),
                Path('R2Northstar/mods/Northstar.Client/mod.json'))


def _identity(path):
    return str(Path(path).resolve()).casefold()


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_sources(game, ion_release):
    game, ion_release = Path(game).resolve(), Path(ion_release).resolve()
    if not (game / 'Titanfall2.exe').is_file() or not (game / 'r2' / 'maps').is_dir():
        raise ValueError(f'{game} does not look like a Titanfall 2 install')
    if game == ion_release or game in ion_release.parents or ion_release in game.parents:
        raise ValueError('the Ion release folder must be separate from the game install')
    for name in ('NorthstarLauncher.exe', 'R2Northstar/Northstar.dll',
                 'R2Northstar/mods/Northstar.Client/mod.json'):
        if not (ion_release / name).is_file():
            raise ValueError(f'Ion release is missing {name}')
    return game, ion_release


def release_version(ion_release):
    mod = json.loads((Path(ion_release) / 'R2Northstar/mods/Northstar.Client/mod.json').read_text('utf-8-sig'))
    version = mod.get('Version')
    if not isinstance(version, str) or not version:
        raise ValueError('Ion release has no Northstar.Client Version')
    return version


def _is_link(path):
    return path.is_symlink() or bool(getattr(path, 'is_junction', lambda: False)())


def prepare_runtime(game, ion_release, runtime):
    """Create or refresh an isolated Ion runtime; return its path.

    Refuses an existing directory that is not owned by this adapter or that
    was prepared from different sources. Base game files are hard-linked so a
    ~70 GB install costs little space; writable folders, the Ion launcher and
    all of Ion's R2Northstar tree are real copies. Existing Northstar profiles,
    mods and packages are never consulted, let alone staged: Ion's own core
    mods come from the release folder.
    """
    game, ion_release = validate_sources(game, ion_release)
    runtime = Path(runtime).resolve()
    if game == runtime or game in runtime.parents or runtime in game.parents:
        raise ValueError('isolated runtime must be separate from the game and Ion folders')
    if ion_release == runtime or ion_release in runtime.parents or runtime in ion_release.parents:
        raise ValueError('isolated runtime must be separate from the Ion release folder')
    if game.drive.casefold() != runtime.drive.casefold():
        raise ValueError('isolated runtime must be on the same volume as the game (hard links)')

    sources = {'game': _identity(game), 'ion_release': _identity(ion_release), 'ion_version': release_version(ion_release)}
    marker = runtime / MARKER
    if runtime.exists() and not marker.is_file():
        raise FileExistsError(f'{runtime} exists and is not an ARES Ion runtime; choose a new folder')
    if marker.is_file():
        try:
            existing = json.loads(marker.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise ValueError(f'{marker} is unreadable: {error}') from error
        for key in ('game', 'ion_release', 'ion_version'):
            if existing.get(key) != sources[key]:
                raise ValueError(f'{runtime} was prepared from a different {key}; choose a new folder')

    created = not runtime.exists()
    runtime.mkdir(parents=True, exist_ok=True)
    try:
        for source_root, dirs, files in os.walk(game):
            root = Path(source_root)
            relative_root = root.relative_to(game)
            # R2Northstar, every player profile and every backup folder stay
            # out. Ion supplies its own R2Northstar tree below.
            if relative_root.parts and relative_root.parts[0].startswith('R2'):
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if not _is_link(root / d) and
                       not (relative_root == Path('.') and d.startswith('R2')) and
                       not any((relative_root / d) == path or path in (relative_root / d).parents
                               for path in COPY_PATHS)]
            target_root = runtime / relative_root
            target_root.mkdir(parents=True, exist_ok=True)
            for name in files:
                source = root / name
                target = target_root / name
                if target.exists():
                    continue
                # r2/ root files such as stats.txt are written by the engine;
                # copy them so an Ion session cannot modify the source install.
                if relative_root == Path('r2') or _is_link(source):
                    shutil.copy2(source, target)  # copy the content, never escape the install
                else:
                    try:
                        os.link(source, target)
                    except OSError:
                        shutil.copy2(source, target)

        for relative in sorted(COPY_PATHS):
            source = game / relative
            if source.is_dir() and not _is_link(source):
                shutil.copytree(source, runtime / relative, dirs_exist_ok=True)

        for source_root, dirs, files in os.walk(ion_release):
            root = Path(source_root)
            relative_root = root.relative_to(ion_release)
            dirs[:] = [d for d in dirs if not _is_link(root / d)]
            target_root = runtime / relative_root
            target_root.mkdir(parents=True, exist_ok=True)
            for name in files:
                source, target = root / name, target_root / name
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()  # break any hard link to the original install
                shutil.copy2(source, target)

        provenance = {path.as_posix(): _sha256(ion_release / path) for path in RELEASE_KEYS}
        (runtime / 'ares-ion-release.json').write_text(json.dumps(
            {'version': sources['ion_version'], 'sha256': provenance}, indent=2) + '\n', encoding='utf-8')
        marker.write_text(json.dumps(sources, indent=2) + '\n', encoding='utf-8')
    except BaseException:
        if created and runtime.exists():
            shutil.rmtree(runtime)
        raise
    return runtime


def stage_ion_dll(game, profile):
    """Put Ion's Northstar.dll where its launcher looks for an isolated profile.

    IonLauncher checks ``<profile>/Northstar.dll`` before the install root. The
    release ships the DLL under ``R2Northstar/Northstar.dll`` (the default
    profile), so an ARES profile needs its own real copy; otherwise the loader
    falls back to the source install's Northstar DLL and Ion's built-ins such
    as NSIsVanilla() are missing.
    """
    source = Path(game) / 'R2Northstar' / 'Northstar.dll'
    target = Path(profile) / 'Northstar.dll'
    if not source.is_file():
        raise FileNotFoundError(f'{source} is missing; Ion was not staged')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()  # never leave a hard link or stale DLL in the profile
    shutil.copyfile(source, target)
    return target


def stage_ion_profile(game, profile):
    """Stage Ion's DLL and plugins into the isolated ARES profile.

    IonLauncher loads ``<profile>/Northstar.dll`` and Northstar loads plugins
    from ``<profile>/plugins``. The release keeps both under ``R2Northstar``
    (its default profile), so the ARES profile needs its own real copies.
    Without the DiscordRPC plugin, Ion's UI scripts fail on ClearJoinSecret.
    """
    target = stage_ion_dll(game, profile)
    source_plugins = Path(game) / 'R2Northstar' / 'plugins'
    target_plugins = Path(profile) / 'plugins'
    if source_plugins.is_dir():
        if target_plugins.is_file():
            target_plugins.unlink()
        shutil.copytree(source_plugins, target_plugins, dirs_exist_ok=True)
    return target


class IonSession(nh.Session):
    """Northstar harness Session that loads Ion's DLL/plugins from its profile."""

    def launch(self):
        stage_ion_profile(self.game, self.profile)
        super().launch()


def mcp_observation(port, timeout=20):
    """Return Ion MCP state/log after a run, or an error string (never fatal)."""
    from ares.harness.ion_mcp import IonMCP  # imported lazily so --prepare-only needs no game
    client = IonMCP(port=port, timeout=max(1, min(timeout, 10)))
    try:
        client.connect()
        state, log = client.state(), client.log()
        tools = [tool.get('name') for tool in client.tools()]
        return {'reachable': True, 'state': state, 'log_tail': log[-4000:], 'tools': tools}
    except Exception as error:
        return {'reachable': False, 'error': '%s: %s' % (type(error).__name__, error)}
    finally:
        client.close()


def build_result(report, started, mode, runtime, ion_version):
    mcp = report.get('mcp', {})
    checks = list(report['checks'])
    checks.insert(0, {'name': 'map loaded', 'passed': report['loaded']})
    checks.insert(1, {'name': 'checks finished', 'passed': report['finished']})
    if not mcp.get('skipped'):
        checks.append({'name': 'Ion MCP reachable', 'passed': bool(mcp.get('reachable'))})
    checks.append({'name': 'no script errors', 'passed': not report['script_errors']})
    checks.append({'name': 'no crash dumps', 'passed': not report.get('crash_dumps')})
    passed = all(c['passed'] for c in checks) and not report['errors']
    artifacts = [{'path': name, 'type': 'screenshot'} for name in report['screenshots']]
    artifacts += [{'path': 'report.json', 'type': 'report'}, {'path': 'nslog.txt', 'type': 'log'}]
    artifacts += [{'path': name, 'type': 'crash-dump'} for name in report.get('crash_dumps', [])]
    finished = report['loaded'] and report['finished']
    return {'schema_version': '1.0', 'tool': 'ion_harness', 'target': 'r2',
            'operation': f'map-runtime-ion:{report["map"]}:{mode}',
            'status': 'success' if passed else ('partial' if report['loaded'] else 'failure'),
            # A session that never loaded is a tool-level attempt, not runtime evidence.
            'verification': 'runtime' if finished else 'tool',
            'duration_ms': int((time.time() - started) * 1000),
            'artifacts': artifacts, 'checks': checks, 'errors': report['errors'],
            'details': {'runtime': str(runtime), 'ion_version': ion_version, 'mcp': mcp}}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--game', type=Path, default=os.environ.get('ARES_R2_GAME'),
                   help='source Titanfall 2 install (default: $ARES_R2_GAME)')
    p.add_argument('--ion', type=Path, default=os.environ.get('ARES_ION_RELEASE'),
                   help='downloaded Ion release folder (default: $ARES_ION_RELEASE)')
    p.add_argument('--runtime', type=Path, default=os.environ.get('ARES_ION_RUNTIME'),
                   help='isolated runtime folder (default: sibling <game>-Ion)')
    p.add_argument('--prepare-only', action='store_true', help='stage the isolated runtime and exit')
    p.add_argument('--profile', default='R2AresIon', help='isolated profile name, never R2Northstar')
    p.add_argument('--map', help='map to load')
    p.add_argument('--mode', default='tdm')
    p.add_argument('--maps', type=Path, help='folder containing a compiled <map>.bsp')
    p.add_argument('--mod', type=Path, action='append', default=[])
    p.add_argument('--enable', action='append', default=[])
    p.add_argument('--checks', type=Path)
    p.add_argument('--output', type=Path, help='report directory')
    p.add_argument('--timeout', type=int, default=300)
    p.add_argument('--hostport', type=int, default=37044, help='listen-server port; avoid 37015/37040')
    p.add_argument('--mcp-port', type=int, default=8766, help="Ion's loopback MCP port (avoid 8765/R1Delta)")
    p.add_argument('--no-mcp', action='store_true', help='do not start or observe Ion MCP')
    args = p.parse_args(argv)
    if args.game is None:
        p.error('--game is required (or set ARES_R2_GAME)')
    if args.ion is None:
        p.error('--ion is required (or set ARES_ION_RELEASE)')
    if (not nh.PROFILE_NAME.fullmatch(args.profile) or args.profile.endswith('.') or
            Path(args.profile).is_reserved() or args.profile.lower() == 'r2northstar'):
        p.error('use a separate profile name, not R2Northstar')
    game, ion_release = validate_sources(args.game, args.ion)
    runtime = (args.runtime or game.parent / (game.name + '-Ion')).resolve()
    runtime = prepare_runtime(game, ion_release, runtime)
    version = release_version(ion_release)
    if args.prepare_only:
        print(json.dumps({'runtime': str(runtime), 'ion_version': version, 'marker': str(runtime / MARKER)}, indent=2))
        return 0
    if not args.map:
        p.error('--map is required unless --prepare-only was used')
    if not nh.MAP_NAME.fullmatch(args.map) or not nh.MODE_NAME.fullmatch(args.mode):
        p.error('invalid map or mode name')
    checks = nh.validate_checks(nh.read_json(args.checks) if args.checks else {})
    output = (args.output or Path.cwd() / 'ion-report').resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    report = {'map': args.map, 'mode': args.mode, 'runtime': str(runtime), 'ion_version': version,
              'loaded': False, 'finished': False, 'events': [], 'checks': [], 'screenshots': [],
              'errors': [], 'script_errors': [], 'crash_dumps': [],
              'mcp': {'reachable': False, 'skipped': args.no_mcp}}
    extra = [] if args.no_mcp else ['+mcp_start_http', str(args.mcp_port)]
    session = IonSession(runtime, output, profile=args.profile, mods=args.mod, maps=args.maps,
                         map_name=args.map, enable_installed=args.enable, hostport=args.hostport,
                         extra_args=extra)
    text = ''
    try:
        with session:
            nh.run_checks(session, checks, args.mode, report, args.timeout)
            if not args.no_mcp:
                report['mcp'] = mcp_observation(args.mcp_port)
            text = session.log_text()
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
    if not text and (output / 'nslog.txt').exists():
        text = (output / 'nslog.txt').read_text('utf-8', 'replace')
    report['script_errors'] = session.script_errors(text)
    report['crash_dumps'] = list(session.crash_dumps)
    report['errors'].extend(f'CRASH: {name}' for name in report['crash_dumps'])
    report['errors'].extend(e for e in report['script_errors'] if not any(e in seen for seen in report['errors']))
    report['errors'].extend(nh.expectation_errors(report['events'], checks.get('expect', {})))
    (output / 'report.json').write_text(json.dumps(report, indent=2))
    result = build_result(report, started, args.mode, runtime, version)
    (output / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'success' else 1


if __name__ == '__main__':
    sys.exit(main())
