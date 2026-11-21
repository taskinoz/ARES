#!/usr/bin/env python3
"""R5Flowstate (Apex S21 client + S3 dedicated server) map views and screenshots.

Runs in an isolated copy of the install, so the installed game is never
changed: large assets are hard links on the same volume, and everything the
game writes (cfg, platform/cfg, mods, LiveAPI, logs, screenshots) is a copy or
lives only in the copy. The copy gets a client-only ARES mod that moves
Flowstate's own client script camera (the "World Crawler" camera,
CreateWorldCrawlerCamera / SetWorldCrawlerCameraPositionAndAngles) to each view,
hides the HUD and takes a named engine screenshot.

The dedicated server is started the way the R5Flowstate launcher starts it
(launcher loopback RCON session: FROM_R5F_LAUNCHER=1, a fresh password in
R5F_LOCAL_RCON, frames unencrypted on loopback). The client then connects to it.
Only the processes this script starts are stopped.

  python harnesses/adapters/flowstate_harness.py --game "F:/Games/Apex Detours/Flowstate" \
      --runtime "F:/Games/Apex Detours/.ares-flowstate" --map mp_rr_canyonlands_staging_mu1 \
      --playlist survival_dev --checks views.json --output reports/flowstate-run

views.json: {"views": [[x, y, z, pitch, yaw], ...], "hide_hud": true, "relative_to_spawn": false,
             "server_commands": ["host_timescale 1"]}

Original implementation, GPL-2.0-or-later. Protocol reference: R5Flowstate
s21-r5sdk src/resource/protobuf/netcon.proto, engine/shared/shared_rcon.cpp and
engine/server/sv_rcon_launcher.cpp.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screenshots import collect_engine_screenshot, review_frames  # noqa: E402

MARKER = '.ares-flowstate-runtime'
MOD_ID = 'ARES.Harness'
MOD_DIR = 'ARES-Harness'
FRAME_MAGIC = 0x6E6F4352  # 'RCon', sent big-endian
MAX_FRAME = 4 * 1024 * 1024
TOKEN = re.compile(r'[A-Za-z0-9_]+')
# Written by the game, so copied rather than linked.
COPY_DIRS = ('cfg', 'mods', 'LiveAPI', 'r2', 'bin')
COPY_SUBDIRS = (('platform', 'cfg'),)
LINK_MIN_BYTES = 1 << 20  # root files below this are copied


# --- netconsole (R5Flowstate framing) -------------------------------------

def varint(value):
    value &= (1 << 64) - 1
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def field(number, value):
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    if isinstance(value, str):
        value = value.encode('utf-8')
    return varint(number << 3 | 2) + varint(len(value)) + value


def parse(data):
    """Top-level protobuf fields: number -> int or bytes (last one wins)."""
    at, out = 0, {}

    def read():
        nonlocal at
        value = 0
        for shift in range(0, 70, 7):
            if at >= len(data):
                raise ValueError('truncated protobuf varint')
            byte = data[at]
            at += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError('oversized protobuf varint')

    while at < len(data):
        key = read()
        wire = key & 7
        if wire == 0:
            value = read()
        elif wire == 2:
            size = read()
            if size > len(data) - at:
                raise ValueError('truncated protobuf field')
            value = data[at:at + size]
            at += size
        else:
            raise ValueError('unsupported protobuf wire type')
        out[key >> 3] = value
    return out


def frame(sequence, session, request):
    """A plaintext envelope: header{seqNr, sessionId}, data. Sequence numbers
    start at 1 and must rise by one; the session id stays fixed per connection."""
    envelope = field(1, field(1, sequence) + field(2, session)) + field(4, request)
    if len(envelope) > MAX_FRAME:
        raise ValueError('console request too large')
    return struct.pack('>II', FRAME_MAGIC, len(envelope)) + envelope


def request(kind, message='', value=''):
    """netcon.request: requestType (0 exec, 1 auth, 2 logs), requestMsg, requestVal."""
    return field(3, kind) + field(4, message) + field(5, value)


class NetConsole:
    """Loopback client for the launcher RCON session of an R5Flowstate dedicated server."""

    def __init__(self, port, password, timeout=5.0):
        # The SDK binds the launcher session to the IPv6 loopback.
        for host in ('::1', '127.0.0.1'):
            try:
                self.sock = socket.create_connection((host, port), timeout)
                break
            except OSError:
                if host == '127.0.0.1':
                    raise
        self.sequence = 0
        self.session = secrets.randbits(63)
        self.buffer = bytearray()
        try:
            self.send(request(1, password))
            for _ in range(4):  # skip any instruction text sent before the AUTH reply
                reply = self.receive()
                text = reply.get(4, b'').decode('utf-8', 'replace')
                if reply.get(3, 0) == 0 and 'successful' in text:
                    break
                if 'incorrect' in text or 'max authenticated' in text:
                    raise PermissionError('netconsole authentication failed: ' + text.strip())
            else:
                raise PermissionError('netconsole sent no AUTH reply')
        except BaseException:
            self.close()
            raise

    def send(self, payload):
        self.sequence += 1
        self.sock.sendall(frame(self.sequence, self.session, payload))

    def command(self, text):
        """Run one console command. The launcher session wants the command name
        as requestMsg and the whole line (name first) as requestVal."""
        if '\n' in text or '\r' in text:
            raise ValueError('one command per call')
        self.send(request(0, text.split(' ', 1)[0], text))

    def receive(self):
        while len(self.buffer) < 8:
            self._fill()
        magic, size = struct.unpack_from('>II', self.buffer)
        if magic != FRAME_MAGIC or size > MAX_FRAME:
            raise ValueError('invalid netconsole frame')
        while len(self.buffer) < 8 + size:
            self._fill()
        envelope = parse(bytes(self.buffer[8:8 + size]))
        del self.buffer[:8 + size]
        if envelope.get(2) or envelope.get(3):
            raise ValueError('encrypted netconsole frame; the launcher session should be plaintext')
        return parse(envelope.get(4, b''))

    def wait_for(self, needle, timeout):
        """Console log text up to the first line containing ``needle`` (sv_rcon_sendlogs 1
        and a SEND_CONSOLE_LOG subscription), or None on timeout."""
        seen = []
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.sock.settimeout(max(0.1, end - time.monotonic()))
            try:
                reply = self.receive()
            except socket.timeout:
                break
            text = reply.get(4, b'').decode('utf-8', 'replace')
            seen.append(text)
            if needle in text:
                self.sock.settimeout(5.0)
                return ''.join(seen)
        self.sock.settimeout(5.0)
        return None

    def _fill(self):
        chunk = self.sock.recv(65536)
        if not chunk:
            raise ConnectionError('netconsole closed')
        self.buffer.extend(chunk)

    def close(self):
        self.sock.close()


# --- isolated runtime -------------------------------------------------------

def prepare_runtime(game, runtime):
    """Hard-link the install into ``runtime``; copy what the game writes."""
    game, runtime = Path(game).resolve(), Path(runtime).resolve()
    if game == runtime or game in runtime.parents or runtime in game.parents:
        raise ValueError('runtime must be separate from the installed game')
    for name in ('r5apex_dx12.exe', 'r5apex_ds.exe'):
        if not (game / name).is_file():
            raise ValueError(f'{name} missing: not an R5Flowstate install')
    if game.drive.casefold() != runtime.drive.casefold():
        raise ValueError('runtime must be on the same volume as the install (hard links)')
    marker = runtime / MARKER
    if runtime.exists() and not marker.is_file():
        raise ValueError('existing directory is not an ARES Flowstate runtime')
    if marker.is_file() and marker.read_text(encoding='utf-8').strip() != str(game):
        raise ValueError('runtime was prepared from a different install')
    runtime.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(game), encoding='utf-8')
    copied = {Path(name) for name in COPY_DIRS} | {Path(*parts) for parts in COPY_SUBDIRS}
    for source in game.rglob('*'):
        relative = source.relative_to(game)
        if any(part == relative or part in relative.parents for part in copied):
            continue
        target = runtime / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            if len(relative.parts) == 1 and source.stat().st_size < LINK_MIN_BYTES:
                shutil.copy2(source, target)
            else:
                os.link(source, target)
    for relative in sorted(copied):
        source, target = game / relative, runtime / relative
        if source.is_dir() and not target.exists():
            shutil.copytree(source, target)
    return runtime


def vector(values):
    return '<' + ', '.join(f'{float(v):.3f}' for v in values) + '>'


def validate_views(views):
    if not isinstance(views, list) or not views:
        raise ValueError('views must be a non-empty list of [x, y, z, pitch, yaw]')
    for view in views:
        if (not isinstance(view, list) or len(view) != 5 or
                not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in view)):
            raise ValueError(f'invalid view {view!r}: want [x, y, z, pitch, yaw]')
    return views


def mod_script(views, token, hide_hud=True, settle=6.0, hold=2.0, relative=False):
    """Client script: World Crawler camera to each view, then a named screenshot.

    With ``relative`` the view origins are offsets from where the local player
    spawned (useful before a map's coordinates are known)."""
    if not TOKEN.fullmatch(token):
        raise ValueError('invalid screenshot token')
    validate_views(views)
    origins = ', '.join(vector(v[:3]) for v in views)
    angles = ', '.join(vector((v[3], v[4], 0)) for v in views)
    base = 'player.GetOrigin()' if relative else '<0, 0, 0>'
    # cl_drawhud does not reach the S21 RUI HUD; Flowstate's dev HUD toggle sets the
    # cinematic flags that hide the main and permanent HUD, and hides the obituary.
    hud = ('\tDevHud_ClientSet( true )\n\tClientCommand( "cl_drawhud 0" )\n' if hide_hud else '')
    restore = ('\tDevHud_ClientSet( false )\n\tClientCommand( "cl_drawhud 1" )\n' if hide_hud else '')
    return f'''// Generated by ARES flowstate_harness.py for one run; not for distribution.
global function CodeCallback_ARES_Harness_ModInit
global function ClientCodeCallback_ARES_Harness_ModInit

#if CLIENT
struct
{{
	bool registered = false
	bool started = false
}} file

void function CodeCallback_ARES_Harness_ModInit()
{{
	ARES_Register()
}}

void function ClientCodeCallback_ARES_Harness_ModInit()
{{
	ARES_Register()
}}

void function ARES_Register()
{{
	if ( file.registered )
		return
	file.registered = true
	printt( "ARES_FS INIT" )
	AddCallback_LocalClientPlayerSpawned( ARES_OnLocalPlayerSpawned )
}}

void function ARES_OnLocalPlayerSpawned( entity player )
{{
	if ( file.started )
		return
	file.started = true
	thread ARES_RunViews()
}}

void function ARES_RunViews()
{{
	array<vector> origins = [ {origins} ]
	array<vector> angles = [ {angles} ]
	entity player = GetLocalViewPlayer()
	printt( "ARES_FS SPAWNED map=" + GetMapName() + " origin=" + player.GetOrigin() + " angles=" + player.EyeAngles() )
	vector base = {base}
	wait {settle:.1f}
	CreateWorldCrawlerCamera()
{hud}	wait 1.0
	foreach ( int i, vector origin in origins )
	{{
		SetWorldCrawlerCameraPositionAndAngles( base + origin, angles[i] )
		wait {hold:.1f}
		ClientCommand( "screenshot {token}_" + i )
		printt( "ARES_FS VIEW " + i + " origin=" + ( base + origin ) + " angles=" + angles[i] )
		wait {hold:.1f}
	}}
{restore}	printt( "ARES_FS DONE" )
}}
#endif
'''


def write_mod(runtime, views, token, hide_hud=True, relative=False):
    runtime = Path(runtime)
    if not (runtime / MARKER).is_file():
        raise ValueError('not an ARES Flowstate runtime')
    mod = runtime / 'mods' / MOD_DIR
    scripts = mod / 'scripts' / 'vscripts'
    (scripts / 'ares_harness').mkdir(parents=True, exist_ok=True)
    (mod / 'mod.vdf').write_text('''"mod"
{
	"author"		"ARES"
	"name"			"ARES Harness"
	"id"			"%s"
	"description"	"Per-run ARES view and screenshot probe (isolated runtime only)."
	"version"		"1.0.0"
	"realm"			"client"
}
''' % MOD_ID, encoding='utf-8')
    (scripts / 'scripts.rson').write_text('When: "CLIENT"\nScripts:\n[\n\tares_harness/cl_ares_harness.nut\n]\n',
                                         encoding='utf-8')
    (scripts / 'ares_harness' / 'cl_ares_harness.nut').write_text(mod_script(views, token, hide_hud, relative=relative), encoding='utf-8')
    listing = runtime / 'mods' / 'mods.vdf'
    text = listing.read_text(encoding='utf-8') if listing.is_file() else '"ModList"\n{\n}\n'
    if f'"{MOD_ID}"' not in text:
        text = text.rstrip().rstrip('}').rstrip() + f'\n\t"{MOD_ID}"\t"1"\n}}\n'
        listing.write_text(text, encoding='utf-8')
    return mod


# --- run ----------------------------------------------------------------------

def free_port(kind):
    with socket.socket(socket.AF_INET, kind) as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def read_logs(runtime, since_ns):
    """Text of every log the game wrote under platform/logs during this run."""
    texts = []
    for path in sorted((Path(runtime) / 'platform' / 'logs').rglob('*')):
        if path.is_file() and path.suffix in ('.log', '.txt') and path.stat().st_mtime_ns >= since_ns:
            texts.append(path.read_text('utf-8', 'replace'))
    return '\n'.join(texts)


def screenshot_roots(runtime):
    runtime = Path(runtime)
    return [runtime / 'screenshots', runtime / 'platform' / 'screenshots', runtime / 'r2' / 'screenshots', runtime]


def profile_dir():
    """Where the S21 client keeps settings.cfg, videoconfig.txt and profile.cfg.
    It is outside the install and shared with normal play, so a run backs it up."""
    return Path(os.environ.get('USERPROFILE', Path.home())) / 'Saved Games' / 'Respawn' / 'Apex_s30'


def backup_profile(root=None):
    root = Path(root) if root else profile_dir()
    saved = {}
    for path in root.rglob('*') if root.is_dir() else ():
        if path.is_file() and path.suffix.lower() in ('.cfg', '.txt'):
            saved[path] = path.read_bytes()
    return root, saved


def restore_profile(backup):
    """Put back every settings file that existed; return the ones the run created."""
    root, saved = backup
    for path, data in saved.items():
        if not path.is_file() or path.read_bytes() != data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    return sorted(str(p) for p in root.rglob('*') if root.is_dir() and p.is_file()
                  and p.suffix.lower() in ('.cfg', '.txt') and p not in saved)


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()


def run(args, checks):
    runtime = prepare_runtime(args.game, args.runtime)
    token = 'ares_' + secrets.token_hex(16)
    views = validate_views(checks.get('views'))
    write_mod(runtime, views, token, checks.get('hide_hud', True), checks.get('relative_to_spawn', False))
    report = {'map': args.map, 'playlist': args.playlist, 'runtime': str(runtime), 'events': [], 'errors': [],
              'screenshots': [], 'server_commands': []}
    if args.prepare_only:
        report['prepared_only'] = True
        return report
    password = secrets.token_urlsafe(24)
    game_port, rcon_port = free_port(socket.SOCK_DGRAM), free_port(socket.SOCK_STREAM)
    env = dict(os.environ, FROM_R5F_LAUNCHER='1', R5F_LOCAL_RCON=password, R5F_LOCAL_RCON_PORT=str(rcon_port))
    dedi_cmd = [str(runtime / 'r5apex_ds.exe'), '-dedicated', '-port', str(game_port), '-offline', '-nodiscord',
                '+sv_onlineAuthEnable', '0', '+sv_cheats', '1', '+sv_rcon_sendlogs', '1', '+launchplaylist', args.playlist, '+map', args.map]
    client_cmd = [str(runtime / 'r5apex_dx12.exe'), '-offline', '-offlinename', 'ares', '+cl_onlineAuthEnable', '0',
                  '-dev', '-nodiscord', '-allowmultiple', '-windowed', '-width', '1280', '-height', '720',
                  '+connect', f'127.0.0.1:{game_port}']
    started = time.time_ns()
    dedi = client = console = profile_backup = None
    text = ''
    captured = set()
    try:
        dedi = subprocess.Popen(dedi_cmd, cwd=runtime, env=env)
        env.pop('R5F_LOCAL_RCON')  # only the dedicated server gets the secret
        deadline = time.monotonic() + args.timeout
        while console is None and time.monotonic() < deadline and dedi.poll() is None:
            try:
                console = NetConsole(rcon_port, password)
            except (OSError, ConnectionError):
                time.sleep(1)
        if console is None:
            raise RuntimeError('dedicated server RCON never came up' if dedi.poll() is None
                               else f'dedicated server exited with code {dedi.returncode}')
        report['events'].append('rcon authenticated')
        console.send(request(2, value='1'))  # stream the server console back
        server_log = None
        while server_log is None and time.monotonic() < deadline and dedi.poll() is None:
            # The server script VM only answers once the map has loaded.
            console.command('script printt( "ARES_FS SERVER map=" + GetMapName() )')
            server_log = console.wait_for('ARES_FS SERVER map=', 3.0)
        if server_log is None:
            raise RuntimeError('the server never loaded the map (no script VM answer over RCON)')
        report['events'].append(re.search(r'ARES_FS (SERVER map=\S+)', server_log).group(1))
        for line in checks.get('server_commands', []):
            console.command(line)
            report['server_commands'].append(line)
        profile_backup = backup_profile()
        client = subprocess.Popen(client_cmd, cwd=runtime, env={k: v for k, v in env.items() if k != 'R5F_LOCAL_RCON_PORT'})
        args.output.mkdir(parents=True, exist_ok=True)
        next_query = 0.0
        # Client script prints are not logged to a file, so progress is read from
        # the screenshots it names and from the server (player pose over RCON).
        while time.monotonic() < deadline and client.poll() is None and dedi.poll() is None:
            if 'player' not in report and time.monotonic() >= next_query:
                next_query = time.monotonic() + 5
                console.command('script if ( GetPlayerArray().len() ) printt( "ARES_FS PLAYER origin=" + '
                                'GetPlayerArray()[0].GetOrigin() + " angles=" + GetPlayerArray()[0].EyeAngles() )')
                found = console.wait_for('ARES_FS PLAYER', 1.0)
                if found:
                    report['player'] = re.search(r'ARES_FS PLAYER (.*)', found).group(1).strip()
            else:
                time.sleep(0.5)
            for view in map(str, range(len(views))):
                if view not in captured and collect_engine_screenshot(
                        screenshot_roots(runtime), f'{token}_{view}', args.output / f'view{view}.png', started):
                    captured.add(view)
            if len(captured) == len(views):
                time.sleep(4)  # let the script restore the HUD before the client is stopped
                break
        text = read_logs(runtime, started)
    except (RuntimeError, OSError, ValueError) as error:
        report['errors'].append(f'harness: {error}')
        text = read_logs(runtime, started)
    finally:
        if console is not None:
            console.close()
        report['client_exit'] = client.poll() if client else None
        report['server_exit'] = dedi.poll() if dedi else None
        if not args.keep_open:
            stop(client)
            stop(dedi)
            if profile_backup is not None:
                report['profile_files_created'] = restore_profile(profile_backup)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'logs.txt').write_text(text, encoding='utf-8')
    report['events'] += [line.split('ARES_FS ', 1)[1].strip() for line in text.splitlines() if 'ARES_FS ' in line]
    report['errors'] += [line.strip() for line in text.splitlines() if 'SCRIPT ERROR' in line]
    shots = sorted(args.output.glob('view*.png'), key=lambda p: int(re.sub(r'\D', '', p.name) or 0))
    report['screenshots'] = [p.name for p in shots]
    missing = sorted(set(map(str, range(len(views)))) - captured, key=int)
    if missing:
        report['errors'].append('no engine screenshot for view(s) ' + ', '.join(missing))
    frames = review_frames(shots)
    report.update(frames=frames['frames'], frame_warnings=frames['warnings'])
    report['errors'] += frames['errors']
    report['finished'] = len(captured) == len(views)
    for name, code in (('client', report['client_exit']), ('server', report['server_exit'])):
        if code not in (None, 0):
            report['errors'].append(f'{name} exited with code {code}')
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--game', type=Path, required=True, help='R5Flowstate install (read only)')
    p.add_argument('--runtime', type=Path, required=True, help='isolated copy, same volume as --game')
    p.add_argument('--map', required=True)
    p.add_argument('--playlist', required=True)
    p.add_argument('--checks', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=600)
    p.add_argument('--prepare-only', action='store_true', help='build the runtime and mod, launch nothing')
    p.add_argument('--keep-open', action='store_true', help='leave the game running for manual inspection')
    args = p.parse_args(argv)
    if not TOKEN.fullmatch(args.map) or not TOKEN.fullmatch(args.playlist):
        p.error('map and playlist must be plain identifiers')
    checks = json.loads(args.checks.read_text(encoding='utf-8'))
    for line in checks.get('server_commands', []):
        if not isinstance(line, str) or not line or '\n' in line or ';' in line:
            p.error(f'invalid server command {line!r}')
    report = run(args, checks)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    if report.get('prepared_only'):
        return 0
    return 0 if report['finished'] and not report['errors'] else 1


if __name__ == '__main__':
    sys.exit(main())
