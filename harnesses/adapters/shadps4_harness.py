#!/usr/bin/env python3
"""Runtime harness for PS4 games and mods running in the shadPS4 emulator.

shadPS4 runs a decrypted PS4 game folder on Windows, Linux and macOS. This
adapter launches it, follows its log, drives the game with pad input, captures
the game window and reads guest memory, and writes a result.json in the ARES
result schema. It knows nothing about a particular game: success and failure
are log patterns you choose, and a step script drives menus.

Commands:
  boot     Launch shadPS4 on an eboot, follow new log lines until a success or
           failure pattern matches (or a timeout), optionally run a step script,
           then stop the emulator it started.
  modules  List module load addresses from a shadPS4 log.
  pad      Press pad buttons in a running shadPS4 window (Windows).
  capture  Save the shadPS4 window to a PNG and report whether it is black (Windows).
  peek     Read guest memory of a running shadPS4 (Windows), by absolute address
           or module+offset with the base taken from the log.

Step script (`boot --steps steps.json`), run after the success pattern:
  [{"wait": "main menu ready", "timeout": 60},
   {"key": "cross", "times": 1},
   {"sleep": 2},
   {"capture": "menu.png", "expect": "not-black"},
   {"peek": {"module": "engine", "offset": "0x3818688", "length": 4}, "expect_u32": 2}]

Rules: shadPS4 is stopped only when this adapter started it; a running shadPS4
is never touched unless you pass --allow-running. Guest memory is read, never
written. Game files are not modified.

Pad input posts key messages to the window through shadPS4's keyboard mapping
(input_config/default.ini), so it works without focus; text can't be typed into
the on-screen keyboard this way.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

TOOL = 'shadps4_harness'
TARGETS = ('r1', 'tfo', 'r2', 'r5')
DEFAULT_FAILURE = (r'SIGSEGV|access violation|guest crash|Unhandled exception|'
                   r'\[Debug\] <Critical>|Unreachable code')
MODULE_LINE = re.compile(r'LoadModuleToMemory: Loading module (\S+) to (0x[0-9a-fA-F]+)')

# shadPS4's default keyboard mapping (input_config/default.ini).
KEYS = {
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    'cross': 0x4E, 'circle': 0x42, 'square': 0x56, 'triangle': 0x43,
    'l1': 0x51, 'r1': 0x55, 'l2': 0x45, 'r2': 0x4F, 'l3': 0x58, 'r3': 0x4D,
    'options': 0x0D, 'touchpad': 0x20,
    'lstick_up': 0x57, 'lstick_down': 0x53, 'lstick_left': 0x41, 'lstick_right': 0x44,
    'rstick_up': 0x49, 'rstick_down': 0x4B, 'rstick_left': 0x4A, 'rstick_right': 0x4C,
}
EXTENDED_KEYS = {0x25, 0x26, 0x27, 0x28}


# Logs ---------------------------------------------------------------------

def default_log(exe):
    """shadPS4 writes user/log/shad_log.txt next to a portable install, else in the user folder."""
    if exe:
        portable = Path(exe).resolve().parent / 'user' / 'log' / 'shad_log.txt'
        if portable.parent.exists():
            return portable
    if sys.platform == 'win32' and os.environ.get('APPDATA'):
        return Path(os.environ['APPDATA']) / 'shadPS4' / 'log' / 'shad_log.txt'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'shadPS4' / 'log' / 'shad_log.txt'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'shadPS4' / 'log' / 'shad_log.txt'


class LogFollower:
    """Reads only lines appended after it was created; survives truncation."""

    def __init__(self, path):
        self.path = Path(path)
        self.offset = self.path.stat().st_size if self.path.exists() else 0
        self.partial = ''
        self.lines = []

    def poll(self):
        if not self.path.exists():
            return []
        size = self.path.stat().st_size
        if size < self.offset:
            self.offset = 0
        if size == self.offset:
            return []
        with self.path.open('rb') as handle:
            handle.seek(self.offset)
            data = handle.read()
        self.offset += len(data)
        text = self.partial + data.decode('utf-8', 'replace')
        parts = re.split(r'\r?\n', text)
        self.partial = parts.pop()
        new = [line for line in parts if line]
        self.lines += new
        return new

    def text(self):
        return '\n'.join(self.lines + ([self.partial] if self.partial else [])) + '\n'


def parse_modules(lines):
    """Module name -> load address (the last load wins). Names are kept as logged."""
    modules = {}
    for line in lines:
        match = MODULE_LINE.search(line)
        if match:
            modules[match.group(1)] = int(match.group(2), 16)
    return modules


def module_base(modules, name):
    """Finds a module by name, ignoring .prx/.sprx/.elf and case: 'engine' finds engine.sprx."""
    def stem(value):
        return re.sub(r'\.(s?prx|elf|bin)$', '', value.lower())
    wanted = stem(name)
    for logged, base in modules.items():
        if stem(logged) == wanted:
            return base
    return None


def scan(lines, success, failure):
    """First line matching failure or success: ('failure'|'success', line) or (None, None)."""
    for line in lines:
        if failure and failure.search(line):
            return 'failure', line
        if success and success.search(line):
            return 'success', line
    return None, None


# PNG and image checks ----------------------------------------------------

def write_png(path, width, height, rgb):
    """Writes 8-bit RGB rows (bytes, top-down, width*3 per row) as a PNG."""
    stride = width * 3
    raw = b''.join(b'\0' + rgb[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
                           chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def image_stats(rgb, width, height, black_threshold=8.0):
    """Mean brightness and spread over a sample grid; 'black' when nearly all dark."""
    if not width or not height:
        return {'mean': 0.0, 'max': 0, 'black': True, 'uniform': True}
    samples = []
    step_x, step_y = max(1, width // 64), max(1, height // 64)
    for y in range(0, height, step_y):
        row = y * width * 3
        for x in range(0, width, step_x):
            i = row + x * 3
            samples.append((rgb[i] * 299 + rgb[i + 1] * 587 + rgb[i + 2] * 114) // 1000)
    mean = sum(samples) / len(samples)
    return {'mean': round(mean, 2), 'max': max(samples), 'black': mean < black_threshold and max(samples) < 64,
            'uniform': max(samples) - min(samples) < 4}


# Windows process, window, input and memory -----------------------------

def _require_windows(what):
    if sys.platform != 'win32':
        raise RuntimeError(f'{what} is only implemented on Windows')


def _win():
    import ctypes
    from ctypes import wintypes
    user32, kernel32, gdi32 = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.gdi32
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                           ctypes.POINTER(ctypes.c_size_t)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    return ctypes, wintypes, user32, kernel32, gdi32


def find_processes(name='shadPS4.exe'):
    """PIDs of running processes with this image name (Windows)."""
    if sys.platform != 'win32':
        out = subprocess.run(['pgrep', '-f', Path(name).stem], capture_output=True, text=True).stdout
        return [int(p) for p in out.split()]
    ctypes, wintypes, _, kernel32, _ = _win()

    class Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD), ('szExeFile', ctypes.c_wchar * 260)]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    entry = Entry()
    entry.dwSize = ctypes.sizeof(Entry)
    pids = []
    try:
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == name.lower():
                pids.append(entry.th32ProcessID)
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return pids


def resolve_pid(pid):
    if pid:
        return pid
    pids = find_processes()
    if not pids:
        raise RuntimeError('shadPS4 is not running')
    if len(pids) > 1:
        raise RuntimeError(f'several shadPS4 processes are running ({pids}); pass --pid')
    return pids[0]


def game_windows(pid):
    """Visible windows of the process, largest client area first."""
    _require_windows('window access')
    ctypes, wintypes, user32, _, _ = _win()
    found = []

    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            rect = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            found.append((rect.right * rect.bottom, hwnd, rect.right, rect.bottom))
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(visit), 0)
    found.sort(reverse=True)
    return [(hwnd, width, height) for _, hwnd, width, height in found]


def press(pid, key, times=1, hold_ms=120, gap_ms=350):
    _require_windows('pad input')
    vk = KEYS.get(key) if not isinstance(key, int) else key
    if vk is None:
        raise ValueError(f'unknown key {key!r}; known: {", ".join(sorted(KEYS))}')
    _, _, user32, _, _ = _win()
    windows = [w[0] for w in game_windows(pid)]
    if not windows:
        raise RuntimeError('no visible shadPS4 window')
    scan_code = user32.MapVirtualKeyW(vk, 0)
    flags = (1 << 24) if vk in EXTENDED_KEYS else 0
    down = 1 | (scan_code << 16) | flags
    up = down | (1 << 30) | (1 << 31)
    for _ in range(times):
        for hwnd in windows:
            user32.PostMessageW(hwnd, 0x0100, vk, down)
        time.sleep(hold_ms / 1000)
        for hwnd in windows:
            user32.PostMessageW(hwnd, 0x0101, vk, up)
        time.sleep(gap_ms / 1000)


def capture(pid, path):
    """PrintWindow (works while covered) -> PNG. Returns size and image stats."""
    _require_windows('capture')
    ctypes, wintypes, user32, _, gdi32 = _win()
    windows = game_windows(pid)
    if not windows or windows[0][1] <= 0:
        raise RuntimeError('no visible shadPS4 window')
    hwnd, width, height = windows[0]
    screen = user32.GetDC(hwnd)
    memory = gdi32.CreateCompatibleDC(screen)
    bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
    old = gdi32.SelectObject(memory, bitmap)
    try:
        printed = bool(user32.PrintWindow(hwnd, memory, 3))  # PW_CLIENTONLY | PW_RENDERFULLCONTENT
        header = struct.pack('<IiiHHIIiiII', 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        info = ctypes.create_string_buffer(header, 44)
        pixels = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(memory, bitmap, 0, height, pixels, info, 0)
    finally:
        gdi32.SelectObject(memory, old)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(hwnd, screen)
    bgra = pixels.raw
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
    rgb = bytes(rgb)
    write_png(path, width, height, rgb)
    return {'path': str(path), 'width': width, 'height': height, 'printed': printed, **image_stats(rgb, width, height)}


def read_memory(pid, address, length):
    _require_windows('memory reads')
    if not address:
        raise ValueError('address is 0; the module base was not found')
    ctypes, _, _, kernel32, _ = _win()
    handle = kernel32.OpenProcess(0x0010 | 0x0400, False, pid)  # VM_READ | QUERY_INFORMATION
    if not handle:
        raise RuntimeError(f'cannot open process {pid}')
    try:
        buffer = ctypes.create_string_buffer(length)
        done = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(handle, ctypes.c_void_p(address), buffer, length, ctypes.byref(done)):
            raise RuntimeError(f'cannot read {length} bytes at {address:#x}')
        return buffer.raw[:done.value]
    finally:
        kernel32.CloseHandle(handle)


def decode(data):
    out = {'hex': data.hex(' ')}
    if len(data) >= 4:
        out['u32'] = struct.unpack_from('<I', data)[0]
        out['i32'] = struct.unpack_from('<i', data)[0]
        out['f32'] = round(struct.unpack_from('<f', data)[0], 6)
    if len(data) >= 8:
        out['u64'] = hex(struct.unpack_from('<Q', data)[0])
    text = data.split(b'\0', 1)[0]
    if text and all(0x20 <= b < 0x7F for b in text):
        out['string'] = text.decode('ascii')
    return out


def resolve_address(spec, modules):
    """{'address': '0x..'} or {'module': 'engine', 'offset': '0x..'} -> absolute guest address."""
    if 'address' in spec:
        return int(str(spec['address']), 0)
    base = module_base(modules, spec['module'])
    if base is None:
        raise ValueError(f'module {spec["module"]!r} is not in the log (seen: {", ".join(sorted(modules)) or "none"})')
    return base + int(str(spec.get('offset', 0)), 0)


# Boot ---------------------------------------------------------------------

def validate_steps(steps):
    if not isinstance(steps, list):
        raise ValueError('steps must be a list')
    allowed = {'wait', 'timeout', 'key', 'times', 'hold_ms', 'gap_ms', 'sleep', 'capture', 'expect', 'peek',
               'expect_u32', 'name'}
    for i, step in enumerate(steps):
        if not isinstance(step, dict) or not step.keys() & {'wait', 'key', 'sleep', 'capture', 'peek'}:
            raise ValueError(f'step {i} needs one of wait, key, sleep, capture, peek')
        unknown = set(step) - allowed
        if unknown:
            raise ValueError(f'step {i}: unknown keys {sorted(unknown)}')
        if 'key' in step and step['key'] not in KEYS:
            raise ValueError(f'step {i}: unknown key {step["key"]!r}')
        if 'capture' in step and (not re.fullmatch(r'[A-Za-z0-9_.-]+\.png', str(step['capture']))):
            raise ValueError(f'step {i}: capture must be a plain file name ending .png')
        if 'expect' in step and step['expect'] not in ('black', 'not-black'):
            raise ValueError(f'step {i}: expect must be black or not-black')
    return steps


def run_steps(steps, pid, follower, failure, output, report):
    for i, step in enumerate(steps):
        label = step.get('name', f'step[{i}]')
        if 'wait' in step:
            pattern = re.compile(step['wait'])
            deadline = time.time() + float(step.get('timeout', 60))
            matched = any(pattern.search(line) for line in follower.lines[report['scan_from']:])
            while not matched and time.time() < deadline:
                new = follower.poll()
                bad = next((line for line in new if failure and failure.search(line)), None)
                if bad:
                    report['errors'].append(f'{label}: failure pattern matched: {bad[:300]}')
                    report['checks'].append({'name': f'{label} wait', 'passed': False})
                    return False
                matched = any(pattern.search(line) for line in new)
                if not matched:
                    time.sleep(0.25)
            report['scan_from'] = len(follower.lines)
            report['checks'].append({'name': f'{label} wait {step["wait"]!r}', 'passed': matched})
            if not matched:
                report['errors'].append(f'{label}: timed out waiting for {step["wait"]!r}')
                return False
        if 'key' in step:
            press(pid, step['key'], int(step.get('times', 1)), int(step.get('hold_ms', 120)), int(step.get('gap_ms', 350)))
            report['events'].append(f'{label} key {step["key"]} x{step.get("times", 1)}')
        if 'sleep' in step:
            time.sleep(float(step['sleep']))
        if 'capture' in step:
            stats = capture(pid, output / step['capture'])
            report['screenshots'].append(step['capture'])
            report['events'].append(f'{label} capture {json.dumps(stats)}')
            if 'expect' in step:
                passed = stats['black'] == (step['expect'] == 'black')
                report['checks'].append({'name': f'{label} {step["capture"]} is {step["expect"]}', 'passed': passed})
                if not passed:
                    report['errors'].append(f'{label}: {step["capture"]} expected {step["expect"]} (mean {stats["mean"]})')
        if 'peek' in step:
            spec = step['peek']
            address = resolve_address(spec, parse_modules(follower.lines))
            data = read_memory(pid, address, int(spec.get('length', 8)))
            value = decode(data)
            report['events'].append(f'{label} peek {address:#x} {json.dumps(value)}')
            if 'expect_u32' in step:
                passed = value.get('u32') == int(step['expect_u32'])
                report['checks'].append({'name': f'{label} u32 == {step["expect_u32"]}', 'passed': passed})
                if not passed:
                    report['errors'].append(f'{label}: read {value.get("u32")} at {address:#x}, expected {step["expect_u32"]}')
        for line in follower.poll():
            if failure and failure.search(line):
                report['errors'].append(f'{label}: failure pattern matched: {line[:300]}')
                return False
    return not report['errors']


def stop(process, grace=10):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def boot(args):
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    report = {'eboot': str(args.eboot), 'status': None, 'matched_line': None, 'events': [], 'checks': [],
              'screenshots': [], 'errors': [], 'modules': {}, 'scan_from': 0}
    steps = validate_steps(json.loads(args.steps.read_text()) if args.steps else [])
    success = re.compile(args.success) if args.success else None
    failure = re.compile(args.failure) if args.failure else None
    log = args.log or default_log(args.shadps4)
    if not args.allow_running and find_processes(Path(args.shadps4).name):
        raise SystemExit('shadPS4 is already running; close it or pass --allow-running')
    follower = LogFollower(log)
    command = [str(args.shadps4), '--game', str(args.eboot)] + (['--log-append'] if args.log_append else []) + args.extra
    report['command'] = command
    process = subprocess.Popen(command, cwd=Path(args.shadps4).resolve().parent,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    report['pid'] = process.pid
    try:
        deadline = started + args.timeout
        status = None
        while time.time() < deadline:
            status, line = scan(follower.poll(), success, failure)
            if status:
                report['matched_line'] = line[:500]
                break
            if process.poll() is not None:
                status = 'process-exited'
                break
            time.sleep(0.25)
        report['status'] = status or 'timeout'
        report['scan_from'] = len(follower.lines)
        if report['status'] == 'success' and steps:
            run_steps(steps, process.pid, follower, failure, output, report)
        if args.capture_end and process.poll() is None:
            try:
                stats = capture(process.pid, output / 'end.png')
                report['screenshots'].append('end.png')
                report['events'].append(f'end capture {json.dumps(stats)}')
            except (RuntimeError, OSError) as error:
                report['events'].append(f'end capture failed: {error}')
    except Exception as error:  # report every failure in the same shape
        report['errors'].append(f'{type(error).__name__}: {error}')
    finally:
        follower.poll()
        if not args.keep_running:
            stop(process)
            time.sleep(0.5)
            follower.poll()
        report['process_exit_code'] = process.poll()
        report['kept_running'] = bool(args.keep_running)
    report['modules'] = {name: hex(base) for name, base in parse_modules(follower.lines).items()}
    (output / 'shad-new-lines.log').write_text(follower.text(), encoding='utf-8')
    if report['status'] != 'success':
        report['errors'].insert(0, {'failure': f'failure pattern matched: {report["matched_line"]}',
                                    'timeout': f'timed out after {args.timeout}s',
                                    'process-exited': 'shadPS4 exited before a pattern matched'}[report['status']])
    report.pop('scan_from')
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    result = build_result(report, started, args.target, args.eboot)
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'success' else 1


def build_result(report, started, target, eboot):
    checks = [{'name': 'success pattern matched', 'passed': report['status'] == 'success'}] + report['checks']
    passed = all(c['passed'] for c in checks) and not report['errors']
    artifacts = [{'path': 'report.json', 'type': 'report'}, {'path': 'shad-new-lines.log', 'type': 'log'}]
    artifacts += [{'path': name, 'type': 'screenshot'} for name in report['screenshots']]
    return {'schema_version': '1.0', 'tool': TOOL, 'target': target,
            'operation': f'shadps4-boot:{Path(eboot).parent.name}',
            'status': 'success' if passed else ('partial' if report['status'] == 'success' else 'failure'),
            'verification': 'runtime', 'duration_ms': int((time.time() - started) * 1000),
            'artifacts': artifacts, 'checks': checks, 'errors': report['errors']}


# CLI ----------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    exe_default = os.environ.get('ARES_SHADPS4_EXE')

    p = sub.add_parser('boot', help='Launch shadPS4 and follow its log')
    p.add_argument('--shadps4', type=Path, default=exe_default, help='shadPS4 executable (default: $ARES_SHADPS4_EXE)')
    p.add_argument('--eboot', type=Path, default=os.environ.get('ARES_PS4_EBOOT'),
                   help='eboot.bin of the decrypted game folder (default: $ARES_PS4_EBOOT)')
    p.add_argument('--log', type=Path, help='shadPS4 log file (default: found from the install)')
    p.add_argument('--success', required=True, help='Regex for a log line that means the boot worked')
    p.add_argument('--failure', default=DEFAULT_FAILURE, help='Regex for a log line that means it failed ("" to disable)')
    p.add_argument('--timeout', type=int, default=180, help='Seconds to wait for a pattern')
    p.add_argument('--steps', type=Path, help='JSON step script run after the success pattern')
    p.add_argument('--capture-end', action='store_true', help='Save end.png before stopping')
    p.add_argument('--keep-running', action='store_true', help='Leave shadPS4 running afterwards')
    p.add_argument('--allow-running', action='store_true', help='Launch even if a shadPS4 is already running')
    p.add_argument('--no-log-append', dest='log_append', action='store_false',
                   help="Don't pass --log-append (older shadPS4 builds)")
    p.add_argument('--target', choices=TARGETS, default='r2', help='Game target for result.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('extra', nargs='*', help='Extra shadPS4 arguments after --')

    p = sub.add_parser('modules', help='Module load addresses from a shadPS4 log')
    p.add_argument('--log', type=Path, required=True)

    p = sub.add_parser('pad', help='Press pad buttons in the running shadPS4 window')
    p.add_argument('keys', nargs='+', help=f'Buttons in order: {", ".join(KEYS)}')
    p.add_argument('--times', type=int, default=1)
    p.add_argument('--hold-ms', type=int, default=120)
    p.add_argument('--gap-ms', type=int, default=350)
    p.add_argument('--pid', type=int)

    p = sub.add_parser('capture', help='Save the shadPS4 window as a PNG')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--pid', type=int)

    p = sub.add_parser('peek', help='Read guest memory')
    p.add_argument('--address', help='Absolute guest address')
    p.add_argument('--module', help='Module name (e.g. engine); base read from --log')
    p.add_argument('--offset', default='0', help='Offset inside --module')
    p.add_argument('--log', type=Path, help='shadPS4 log with the module load lines')
    p.add_argument('--length', type=int, default=16)
    p.add_argument('--pid', type=int)

    args = parser.parse_args(argv)
    try:
        if args.command == 'boot':
            if not args.shadps4 or not args.eboot:
                parser.error('--shadps4 and --eboot are required (or set ARES_SHADPS4_EXE and ARES_PS4_EBOOT)')
            for path in (args.shadps4, args.eboot):
                if not Path(path).is_file():
                    parser.error(f'not found: {path}')
            return boot(args)
        if args.command == 'modules':
            lines = Path(args.log).read_text('utf-8', 'replace').splitlines()
            result = {name: hex(base) for name, base in parse_modules(lines).items()}
        elif args.command == 'pad':
            pid = resolve_pid(args.pid)
            for key in args.keys:
                press(pid, key, args.times, args.hold_ms, args.gap_ms)
            result = {'pid': pid, 'pressed': args.keys, 'times': args.times}
        elif args.command == 'capture':
            result = capture(resolve_pid(args.pid), args.out)
        else:
            if bool(args.address) == bool(args.module):
                parser.error('peek needs --address or --module (with --log)')
            if args.module and not args.log:
                parser.error('--module needs --log')
            modules = parse_modules(Path(args.log).read_text('utf-8', 'replace').splitlines()) if args.log else {}
            spec = {'address': args.address} if args.address else {'module': args.module, 'offset': args.offset}
            address = resolve_address(spec, modules)
            pid = resolve_pid(args.pid)
            result = {'pid': pid, 'address': hex(address), **decode(read_memory(pid, address, args.length))}
    except (RuntimeError, ValueError, OSError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
