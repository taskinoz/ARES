#!/usr/bin/env python3
"""Load a map in Titanfall 2 / Northstar and drive it over a loopback HTTP controller.

The ARES.MapHarness mod (harnesses/adapters/northstar/) polls this controller
from the UI, client and server Squirrel VMs. Jobs it runs: load a map in a mode,
console commands, client cameras, server player placement, line and hull
traces, spawn probes, entity counts and screenshots. The mod is inert unless
the game is started with -allowlocalhttp, ares_harness_enabled 1 and a token.

Everything runs in a separate Northstar profile (default R2AresHarness), so
the player's R2Northstar profile and any dedicated server profile are left
alone. Mods the harness copies in are marked as owned and removed afterwards;
enabledmods.json is restored byte for byte. GPL-2.0-or-later.

  python harnesses/adapters/northstar_harness.py --game C:/Games/Titanfall2 \\
      --maps BUILD_DIR --map mp_name --checks checks.json --output REPORT_DIR

  python harnesses/adapters/northstar_harness.py --game ... --mod path/to/MyMod \\
      --map mp_glitch --mode tdm --checks checks.json --output REPORT_DIR

checks.json (every key optional):
  {"settle": 20,                       seconds after the client is ready (pre-match
                                       loadout overlays cover views for ~15 s)
   "traces": [[x, y, z, ex, ey, ez]],  server TraceLine, brush-only solid mask
   "hulls": [[x, y, z, ex, ey, ez, minx, miny, minz, maxx, maxy, maxz]],
   "spawn_probe": [[x, y, z]],         floor, pilot and titan clearance per point
   "mode_check": true,                 counts spawn, objective and hazard entities
   "views": [[x, y, z, pitch, yaw]],   client camera captures, or with
   "thirdperson": false,               true: views are the player's feet position
   "console": ["sv_cheats 1"],         UI console commands before the checks
   "expect": {"trace_z": [[index, min, max]], "hull_z": [[index, min, max]]}}

Trace and hull events use the TFO/R1 harness text format, so results compare
line for line across engines. report.json holds the raw results; result.json
follows harnesses/contracts/result.schema.json. Exit code 0 means the map
loaded, every check ran and no expectation or script error failed.

For multi-phase tests, import Session and Controller and script them directly.
"""
from __future__ import annotations

import argparse
import hmac
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tfo_harness import capture_window, expectation_errors, height_expectations  # noqa: E402

HARNESS_MOD = 'ARES.MapHarness'
HARNESS_SOURCE = Path(__file__).resolve().parent / 'northstar' / HARNESS_MOD
CORE_MODS = ('Northstar.Client', 'Northstar.Custom', 'Northstar.CustomServers')
OWNER = '.ares-harness-owner'
PROFILE_MARKER = '.ares-harness-profile'
CONTEXTS = ('ui', 'client', 'server')
MAP_NAME = re.compile(r'[A-Za-z0-9_]+')
MODE_NAME = re.compile(r'[A-Za-z0-9_]+')
PROFILE_NAME = re.compile(r'[A-Za-z0-9_.-]+')
SCRIPT_ERRORS = ('SCRIPT ERROR', 'COMPILE ERROR', 'SCRIPT COMPILE ERROR')
CHECK_KEYS = {'settle', 'traces', 'hulls', 'spawn_probe', 'mode_check', 'views', 'thirdperson', 'console', 'expect'}
MAX_BODY = 65536


class Controller:
    """Loopback HTTP endpoint the harness mod polls. One job queue per Squirrel VM."""

    def __init__(self):
        self.token = uuid.uuid4().hex
        self.jobs = {context: queue.Queue() for context in CONTEXTS}
        self.states = {}
        self.acks = {}
        self.lock = threading.Lock()
        controller = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 5

            def log_message(self, *args):
                pass

            def do_POST(self):
                supplied = self.headers.get('Authorization', '')
                if not hmac.compare_digest(supplied, 'Bearer ' + controller.token):
                    self.send_response(403)
                    self.end_headers()
                    return
                if self.path not in ('/poll/ui', '/poll/client', '/poll/server', '/ack'):
                    self.send_error(404, 'Unknown endpoint')
                    return
                try:
                    length = int(self.headers.get('Content-Length') or 0)
                    if not 0 <= length <= MAX_BODY:
                        self.send_error(413, 'Request body too large')
                        return
                    body = json.loads(self.rfile.read(length) or b'{}')
                    if not isinstance(body, dict):
                        raise ValueError('Expected a JSON object')
                    if self.path == '/ack' and not isinstance(body.get('id'), str):
                        raise ValueError('Expected an acknowledgement id')
                except ValueError:
                    self.send_error(400, 'Invalid request body')
                    return
                if self.path.startswith('/poll/') and self.path[6:] in CONTEXTS:
                    context = self.path[6:]
                    with controller.lock:
                        controller.states[context] = body
                    try:
                        job = controller.jobs[context].get_nowait()
                    except queue.Empty:
                        self.send_response(204)
                        self.end_headers()
                        return
                    data = json.dumps(job).encode()
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if self.path == '/ack' and isinstance(body, dict):
                    with controller.lock:
                        controller.acks[body.get('id')] = body
                self.send_response(200)
                self.end_headers()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def state(self, context):
        with self.lock:
            return dict(self.states.get(context, {}))

    def submit(self, context, op, **fields):
        if context not in CONTEXTS:
            raise ValueError(f'unknown context {context!r}')
        job_id = uuid.uuid4().hex
        self.jobs[context].put(dict(id=job_id, op=op, **fields))
        return job_id

    def result(self, job_id, timeout, alive=lambda: True):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                ack = self.acks.pop(job_id, None)
            if ack is not None:
                return ack
            if not alive():
                raise RuntimeError('game exited while waiting for a harness job')
            time.sleep(0.1)
        raise TimeoutError(f'harness job {job_id} timed out after {timeout}s')

    def run(self, context, op, timeout=60, alive=lambda: True, **fields):
        """Queue a job and return its acknowledgement; raise if the mod reports failure."""
        ack = self.result(self.submit(context, op, **fields), timeout, alive)
        if not ack.get('ok'):
            raise RuntimeError(f'{context} {op} failed: {ack.get("error")} (stage {ack.get("stage")})')
        return ack


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def mod_identity(mod_dir):
    manifest = read_json(Path(mod_dir) / 'mod.json')
    name, version = manifest.get('Name'), manifest.get('Version')
    if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
        raise ValueError(f'{mod_dir}/mod.json needs a Name and Version')
    return name, version


def enable(enabled, name, version):
    """Enable exactly one version of a mod identity.

    Northstar disables every copy of a mod when several versions are enabled,
    which silently drops its gamemode or scripts.
    """
    enabled[name] = {version: True}


def owned(path, token=None):
    marker = Path(path) / OWNER
    return marker.is_file() and (token is None or marker.read_text().strip() == token)


def map_files(build, map_name):
    files = [f for f in Path(build).iterdir() if f.is_file() and (
             f.name in (map_name + '.bsp', map_name + '.ent') or
             (f.name.startswith(map_name + '_') and f.suffix == '.ent') or
             (f.name.startswith(map_name + '.') and f.name.endswith('.bsp_lump')))]
    if not any(f.name == map_name + '.bsp' for f in files):
        raise FileNotFoundError(f'{build} has no {map_name}.bsp')
    return sorted(files)


def validate_checks(checks):
    if not isinstance(checks, dict) or set(checks) - CHECK_KEYS:
        raise ValueError(f'checks may contain only {sorted(CHECK_KEYS)}')

    def rows(key, width):
        value = checks.get(key, [])
        if not isinstance(value, list) or any(
                not isinstance(row, list) or len(row) != width or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in row) for row in value):
            raise ValueError(f'{key} rows must be {width} finite numbers')
        return value

    rows('traces', 6)
    rows('spawn_probe', 3)
    rows('views', 5)
    if any(row[6 + i] > row[9 + i] for row in rows('hulls', 12) for i in range(3)):
        raise ValueError('hull mins must not exceed maxs')
    settle = checks.get('settle', 20)
    if type(settle) not in (int, float) or not math.isfinite(settle) or settle < 0:
        raise ValueError('settle must be a non-negative number of seconds')
    console = checks.get('console', [])
    if not isinstance(console, list) or any(
            not isinstance(c, str) or not re.fullmatch(r'[A-Za-z0-9_ .+-]{1,96}', c) for c in console):
        raise ValueError('console must be short console commands')
    for key in ('mode_check', 'thirdperson'):
        if type(checks.get(key, False)) is not bool:
            raise ValueError(f'{key} must be true or false')
    expect = checks.get('expect', {})
    if isinstance(expect, dict) and 'drop_z' in expect:
        raise ValueError('drop_z is not supported by the Northstar harness')
    height_expectations(expect)
    return checks


class Session:
    """Stages an isolated Northstar profile, launches the game and cleans up.

    with Session(game, output, mods=[...], maps=BUILD, map_name='mp_x') as s:
        s.load('mp_x', 'tdm')
        s.controller.run('server', 'trace', px=0.0, py=0.0, pz=64.0, ex=0.0, ey=0.0, ez=-64.0, alive=s.alive)
    """

    def __init__(self, game, output, profile='R2AresHarness', mods=(), maps=None, map_name=None,
                 enable_installed=(), width=1280, height=720, extra_args=(), startup_timeout=240, hostport=37040):
        self.game = Path(game).resolve()
        self.output = Path(output).resolve()
        if (not PROFILE_NAME.fullmatch(profile) or profile.endswith('.') or
                Path(profile).is_reserved() or profile.lower() == 'r2northstar'):
            raise ValueError('use a separate profile name, not R2Northstar')
        self.profile = self.game / profile
        self.mods = [Path(m).resolve() for m in mods]
        self.maps = Path(maps).resolve() if maps else None
        self.map_name = map_name
        if self.maps and not (map_name and MAP_NAME.fullmatch(map_name)):
            raise ValueError('--maps needs a valid --map name')
        self.enable_installed = list(enable_installed)
        self.size = (int(width), int(height))
        self.extra_args = list(extra_args)
        self.hostport = int(hostport)
        self.startup_timeout = startup_timeout
        self.controller = None
        self.process = None
        self.installed = []
        self.enabled_backup = None
        self.log_start = time.time()
        self.old_logs = set()
        self.closed = False
        self.closed_log = ''
        self.profile_lock = self.profile / '.ares-session.lock'
        self.profile_lock_token = None

    def checked_target(self, target):
        mods = self.profile / 'mods'
        enabled = self.profile / 'enabledmods.json'
        if (self.profile.resolve() != self.profile or mods.resolve() != mods or
                enabled.resolve() != enabled or self.profile_lock.resolve() != self.profile_lock or
                target.parent != mods or target.resolve() != target):
            raise ValueError(f'refusing redirected staging path: {target}')
        return target

    # -- profile ---------------------------------------------------------
    def ensure_profile(self):
        """Create the harness profile from the installed Northstar core mods when missing."""
        self.checked_target(self.profile / 'mods' / HARNESS_MOD)
        launcher = self.game / 'NorthstarLauncher.exe'
        if not launcher.is_file():
            raise FileNotFoundError(f'{launcher} not found; --game must be a Northstar install')
        mods = self.profile / 'mods'
        if self.profile.exists() and not (self.profile / PROFILE_MARKER).is_file():
            raise FileExistsError(f'{self.profile} is not an ARES-owned profile; use a new profile name')
        if not self.profile.exists():
            source = self.game / 'R2Northstar' / 'mods'
            mods.mkdir(parents=True)
            enabled = {'Version': 1}
            for core in CORE_MODS:
                shutil.copytree(source / core, mods / core)
                enable(enabled, *mod_identity(mods / core))
            (self.profile / 'enabledmods.json').write_text(json.dumps(enabled, indent=4))
            (self.profile / PROFILE_MARKER).write_text('Created by ARES northstar_harness.py\n')
        mods.mkdir(exist_ok=True)
        enabled_path = self.profile / 'enabledmods.json'
        if not enabled_path.exists():
            enabled_path.write_text(json.dumps({'Version': 1}, indent=4))
        return mods

    def install(self, source, mods, token):
        name, version = mod_identity(source)
        target = self.checked_target(mods / source.name)
        if source.is_relative_to(self.profile) or target.is_relative_to(source):
            raise ValueError('mod source must be outside its staging destination')
        if target.exists():
            if owned(target):
                shutil.rmtree(target)  # left behind by an interrupted run
            else:
                raise FileExistsError(f'{target} exists and is not owned by the harness; remove or rename it')
        target.mkdir()
        (target / OWNER).write_text(token)
        self.installed.append(target)
        shutil.copytree(source, target, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.git', '__pycache__', OWNER))
        return name, version

    def stage_map(self, mods, token):
        name = 'ARES.MapUnderTest'
        target = self.checked_target(mods / name)
        files = map_files(self.maps, self.map_name)
        if target.exists():
            if not owned(target):
                raise FileExistsError(f'{target} exists and is not owned by the harness')
            shutil.rmtree(target)
        target.mkdir()
        (target / OWNER).write_text(token)
        self.installed.append(target)
        (target / 'mod' / 'maps').mkdir(parents=True)
        for f in files:
            shutil.copyfile(f, target / 'mod' / 'maps' / f.name)
        (target / 'mod.json').write_text(json.dumps({'Name': name, 'Version': '0.0.1', 'LoadPriority': 1,
                                                     'Description': 'Compiled map staged by the ARES harness'}, indent=1))
        return name, '0.0.1'

    def prepare(self):
        if self.closed:
            raise RuntimeError('a closed session cannot be reused')
        if self.controller is not None:
            raise RuntimeError('session is already prepared')
        self.checked_target(self.profile / 'mods' / HARNESS_MOD)
        try:
            self._prepare()
        except BaseException:
            self.close()
            raise

    def _prepare(self):
        mods = self.ensure_profile()
        lock_token = json.dumps({'pid': os.getpid(), 'token': uuid.uuid4().hex})
        with self.profile_lock.open('x', encoding='utf-8') as lock_file:
            lock_file.write(lock_token)
        self.profile_lock_token = lock_token
        self.controller = Controller().start()
        token = self.controller.token
        enabled_path = self.profile / 'enabledmods.json'
        self.enabled_backup = enabled_path.read_bytes()
        enabled = json.loads(self.enabled_backup.decode('utf-8-sig'))
        identities = [self.install(HARNESS_SOURCE, mods, token)]
        identities += [self.install(m, mods, token) for m in self.mods]
        if self.maps:
            identities.append(self.stage_map(mods, token))
        for name, version in identities:
            enable(enabled, name, version)
        for name in self.enable_installed:
            versions = enabled.get(name)
            if not isinstance(versions, dict) or not versions:
                raise ValueError(f'{name} is not listed in {enabled_path}')
            enable(enabled, name, sorted(versions)[-1])
        enabled_path.write_text(json.dumps(enabled, indent=4))
        self.old_logs = {p.name for p in (self.profile / 'logs').glob('*.txt')} if (self.profile / 'logs').exists() else set()

    # -- process ---------------------------------------------------------
    def launch(self):
        width, height = self.size
        command = [str(self.game / 'NorthstarLauncher.exe'), f'-profile={self.profile.name}', '-multiple',
                   '-allowlocalhttp', '-novid', '-windowed', '-noborder', '-w', str(width), '-h', str(height),
                   '+ip', '127.0.0.1', '+hostport', str(self.hostport), '+sv_lan', '1', '+developer', '1',
                   '+ares_harness_enabled', '1', '+ares_harness_port', str(self.controller.port),
                   '+ares_harness_token', self.controller.token, *self.extra_args]
        self.process = subprocess.Popen(command, cwd=self.game)
        self.wait_state('ui', lambda s: s.get('ready') is True, self.startup_timeout, 'main menu')

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def log_text(self):
        logs = [p for p in (self.profile / 'logs').glob('*.txt') if p.name not in self.old_logs] \
            if (self.profile / 'logs').exists() else []
        if not logs:
            return ''
        return max(logs, key=lambda p: p.stat().st_mtime).read_text('utf-8', 'replace')

    def script_errors(self, text=None):
        text = self.log_text() if text is None else text
        return [line for line in text.splitlines() if any(marker in line for marker in SCRIPT_ERRORS)]

    def wait_state(self, context, predicate, timeout, what):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if not self.alive():
                raise RuntimeError(f'game exited before {what}')
            if predicate(self.controller.state(context)):
                return self.controller.state(context)
            errors = self.script_errors()
            if errors:
                raise RuntimeError('script error before ' + what + ': ' + errors[0])
            time.sleep(0.5)
        raise TimeoutError(f'{what} not reached within {timeout}s')

    def healthy(self):
        """False once the game exits; raises on a new script error (checked at most once a second)."""
        if not self.alive():
            return False
        now = time.monotonic()
        if now - getattr(self, '_checked', 0) >= 1:
            self._checked = now
            errors = self.script_errors()
            if errors:
                raise RuntimeError('script error: ' + errors[0])
        return True

    def run(self, context, op, timeout=60, **fields):
        return self.controller.run(context, op, timeout=timeout, alive=self.healthy, **fields)

    def load(self, map_name, mode='tdm', timeout=300):
        if not MAP_NAME.fullmatch(map_name) or not MODE_NAME.fullmatch(mode):
            raise ValueError('invalid map or mode name')
        generation = self.run('ui', 'load', map=map_name, mode=mode)['generation']
        self.wait_state('client', lambda s: s.get('ready') and s.get('generation') == generation and
                        s.get('level') == map_name, timeout, f'{map_name} client ready')
        return generation

    def capture(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        return capture_window(self.process.pid, path)

    def close(self):
        if self.closed:
            return self.closed_log
        self.checked_target(self.profile / 'mods' / HARNESS_MOD)
        if self.process is not None and self.process.poll() is None:
            try:
                self.controller.submit('ui', 'console', command='quit')
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=30)
        text = self.log_text()
        if text:
            self.output.mkdir(parents=True, exist_ok=True)
            (self.output / 'nslog.txt').write_text(text, encoding='utf-8')
        if self.controller is not None:
            self.controller.stop()
        if self.enabled_backup is not None:
            (self.profile / 'enabledmods.json').write_bytes(self.enabled_backup)
        token = self.controller.token if self.controller else None
        for target in self.installed:
            self.checked_target(target)
            if owned(target, token):
                shutil.rmtree(target)
        if self.profile_lock_token is not None and self.profile_lock.read_text('utf-8') == self.profile_lock_token:
            self.profile_lock.unlink()
        self.closed_log = text
        self.closed = True
        return text

    def __enter__(self):
        try:
            self.prepare()
            self.launch()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def trace_event(kind, index, data):
    normal = data.get('normal', [0, 0, 0])
    return (f'{kind} {index} fraction={data["fraction"]} end={data["end"][2]} solid={data["startSolid"]} '
            f'normal=<{normal[0]}, {normal[1]}, {normal[2]}> endpos={data["end"]}')


def run_checks(session, checks, mode, report, timeout=300):
    """Run one map's checks inside an open Session, appending to report."""
    events, checks_out = report['events'], report['checks']
    session.load(report['map'], mode, timeout)
    report['loaded'] = True
    time.sleep(checks.get('settle', 20))
    for command in checks.get('console', []):
        session.run('ui', 'console', command=command)
        time.sleep(0.5)
    for i, t in enumerate(checks.get('traces', [])):
        data = session.run('server', 'trace', px=float(t[0]), py=float(t[1]), pz=float(t[2]),
                           ex=float(t[3]), ey=float(t[4]), ez=float(t[5]))['data']
        events.append(trace_event('TRACE', i, data))
    for i, h in enumerate(checks.get('hulls', [])):
        data = session.run('server', 'hull', px=float(h[0]), py=float(h[1]), pz=float(h[2]),
                           ex=float(h[3]), ey=float(h[4]), ez=float(h[5]),
                           minx=float(h[6]), miny=float(h[7]), minz=float(h[8]),
                           maxx=float(h[9]), maxy=float(h[10]), maxz=float(h[11]))['data']
        events.append(trace_event('HULL', i, data))
    if checks.get('spawn_probe'):
        points = [[float(v) for v in p] for p in checks['spawn_probe']]
        results = session.run('server', 'spawn_probe', points=points)['data']
        report['spawn_probe'] = results
        for i, r in enumerate(results):
            events.append(f'SPAWN {i} origin={r["origin"]} floor={r["floor"]} pilot={r["pilot"]} titan={r["titan"]}')
            checks_out.append({'name': f'spawn_probe[{i}] floor and pilot clearance',
                               'passed': bool(r['floor'] and r['pilot'])})
    if checks.get('mode_check'):
        data = session.run('server', 'mode_check')['data']
        report['mode_check'] = data
        events.append('MODE ' + json.dumps(data, sort_keys=True))
    views = checks.get('views', [])
    if views and checks.get('thirdperson'):
        session.run('ui', 'console', command='sv_cheats 1')
        time.sleep(1)
        session.run('ui', 'console', command='thirdperson')
        time.sleep(1)
    for i, v in enumerate(views):
        session.run('ui', 'clear_ui')
        pose = dict(px=float(v[0]), py=float(v[1]), pz=float(v[2]), pitch=float(v[3]), yaw=float(v[4]), roll=0.0)
        if checks.get('thirdperson'):
            session.run('server', 'player', freeze=True, **pose)
            time.sleep(2.5)
        else:
            session.run('client', 'camera', fov=90.0, **pose)
            time.sleep(1.5)
        path = session.output / f'view{i}.png'
        captured = session.capture(path)
        events.append(f'VIEW {i} captured={captured}')
        if captured:
            report['screenshots'].append(path.name)
        checks_out.append({'name': f'view[{i}] captured', 'passed': bool(captured)})
    report['finished'] = True


def build_result(report, started, mode):
    checks = list(report['checks'])
    checks.insert(0, {'name': 'map loaded', 'passed': report['loaded']})
    checks.insert(1, {'name': 'checks finished', 'passed': report['finished']})
    checks.append({'name': 'no script errors', 'passed': not report['script_errors']})
    expectation_failures = [e for e in report['errors'] if e.startswith(('TRACE ', 'HULL '))]
    checks.append({'name': 'height expectations', 'passed': not expectation_failures})
    passed = all(c['passed'] for c in checks) and not report['errors']
    artifacts = [{'path': name, 'type': 'screenshot'} for name in report['screenshots']]
    artifacts += [{'path': 'report.json', 'type': 'report'}, {'path': 'nslog.txt', 'type': 'log'}]
    return {'schema_version': '1.0', 'tool': 'northstar_harness', 'target': 'r2',
            'operation': f'map-runtime:{report["map"]}:{mode}',
            'status': 'success' if passed else ('partial' if report['loaded'] else 'failure'),
            'verification': 'runtime', 'duration_ms': int((time.time() - started) * 1000),
            'artifacts': artifacts, 'checks': checks, 'errors': report['errors']}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--game', type=Path, default=os.environ.get('ARES_R2_GAME'),
                   help='Titanfall 2 folder with NorthstarLauncher.exe (default: $ARES_R2_GAME)')
    p.add_argument('--profile', default='R2AresHarness', help='Isolated Northstar profile folder name')
    p.add_argument('--map', required=True)
    p.add_argument('--mode', default='tdm', help='Gamemode for the load, e.g. tdm, ffa, surf')
    p.add_argument('--maps', type=Path, help='Folder with a compiled <map>.bsp (+ .ent, .bsp_lump) to stage')
    p.add_argument('--mod', type=Path, action='append', default=[], help='Mod folder (with mod.json) to install for this run')
    p.add_argument('--enable', action='append', default=[], help='Also enable this mod already installed in the profile')
    p.add_argument('--checks', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=300, help='Seconds for the map to load')
    p.add_argument('--hostport', type=int, default=37040,
                   help='Listen-server port; keep it off any dedicated server port (37015)')
    args = p.parse_args(argv)
    if args.game is None:
        p.error('--game is required (or set ARES_R2_GAME)')
    if not MAP_NAME.fullmatch(args.map) or not MODE_NAME.fullmatch(args.mode):
        p.error('invalid map or mode name')
    checks = validate_checks(read_json(args.checks) if args.checks else {})
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    report = {'map': args.map, 'mode': args.mode, 'loaded': False, 'finished': False, 'events': [],
              'checks': [], 'screenshots': [], 'errors': [], 'script_errors': []}
    session = Session(args.game, args.output, profile=args.profile, mods=args.mod, maps=args.maps,
                      map_name=args.map, enable_installed=args.enable, hostport=args.hostport)
    text = ''
    try:
        with session:
            run_checks(session, checks, args.mode, report, args.timeout)
            text = session.log_text()
    except Exception as error:  # report every failure in the same shape
        report['errors'].append(f'{type(error).__name__}: {error}')
    if not text and (args.output / 'nslog.txt').exists():  # Session.close saved it
        text = (args.output / 'nslog.txt').read_text('utf-8', 'replace')
    report['script_errors'] = session.script_errors(text)
    report['errors'].extend(e for e in report['script_errors'] if not any(e in seen for seen in report['errors']))
    report['errors'].extend(expectation_errors(report['events'], checks.get('expect', {})))
    (args.output / 'report.json').write_text(json.dumps(report, indent=2))
    result = build_result(report, started, args.mode)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'success' else 1


if __name__ == '__main__':
    sys.exit(main())
