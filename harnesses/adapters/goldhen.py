#!/usr/bin/env python3
"""Deploy and observe homebrew on a real PS4 running GoldHEN.

GoldHEN (a PS4 homebrew enabler) serves FTP on port 2121, streams the kernel
log on TCP 3232 and loads plugins listed in /data/GoldHEN/plugins.ini when a
title starts. This adapter uses those to install a plugin or mod files, record
the kernel log and summarise the last boot, including where a crash happened.

Commands:
  ls             List a remote folder (read-only).
  upload         Upload files or folder trees; files whose size already matches
                 are skipped, every upload is verified by size.
  enable-plugin  Add a [TITLEID] section loading a plugin to plugins.ini,
                 keeping what is there (a copy of the old file is saved locally).
  klog           Record the kernel log to a file, reconnecting when it drops.
  lastboot       Summarise the last boot in a recorded kernel log: tagged lines,
                 then any crash with rip and the last branch mapped to a module
                 (and a symbol with llvm-nm and the plugin's ELF).

Notes:
  * GoldHEN's FTP server reports a .prx's *decrypted* size from SIZE and sends
    it decrypted on RETR, so sizes are compared through LIST.
  * GoldHEN serves one kernel-log reader at a time and answers "failed to open
    klog" while an earlier connection is held; klog backs off.
  * The raw kernel log can contain anything the game prints, including sign-in
    secrets. lastboot replaces lines that look like they carry one; share its
    output, not the raw log.

Writing to a console changes it: ask the owner before running upload or
enable-plugin.
"""
from __future__ import annotations

import argparse
import ftplib
import io
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

FTP_PORT, KLOG_PORT = 2121, 3232
PLUGINS_INI = '/data/GoldHEN/plugins.ini'
BUSY = b'failed to open klog'
SECRET = re.compile(r'playerToken|password|passwd|token|authcode|auth_code|"code"|secret|cookie|bearer', re.I)
CRASH = 'A user thread receives a fatal signal'
TITLE_ID = re.compile(r'CUSA\d{5}|[A-Z]{4}\d{5}')


# FTP ----------------------------------------------------------------------

def connect(host, port=FTP_PORT, timeout=30):
    ftp = ftplib.FTP()
    ftp.connect(host, port, timeout=timeout)
    ftp.login()
    return ftp


def list_dir(ftp, folder):
    """Name -> {'size', 'dir'} from LIST (GoldHEN's LIST gives the stored size)."""
    lines = []
    try:
        ftp.retrlines('LIST ' + folder, lines.append)
    except ftplib.all_errors:
        return None
    entries = {}
    for line in lines:
        parts = line.split(None, 8)
        if len(parts) == 9 and parts[8] not in ('.', '..'):
            entries[parts[8]] = {'size': int(parts[4]) if parts[4].isdigit() else None, 'dir': line.startswith('d')}
    return entries


def remote_size(ftp, path):
    folder, name = path.rsplit('/', 1)
    entry = (list_dir(ftp, folder or '/') or {}).get(name)
    return entry['size'] if entry and not entry['dir'] else None


def ensure_dir(ftp, path):
    current = ''
    for part in path.strip('/').split('/'):
        current += '/' + part
        try:
            ftp.mkd(current)
        except ftplib.error_perm:
            pass


def put(ftp, local, remote, always=False):
    """Uploads one file unless the remote size already matches. Returns True if sent."""
    size = os.path.getsize(local)
    if not always and remote_size(ftp, remote) == size:
        return False
    with open(local, 'rb') as source:
        ftp.storbinary('STOR ' + remote, source, blocksize=256 * 1024)
    after = remote_size(ftp, remote)
    if after != size:
        raise RuntimeError(f'size mismatch after upload: {remote} is {after}, expected {size}')
    return True


def tree_files(local_root, remote_root):
    local_root = Path(local_root)
    pairs = []
    for directory, dirs, names in os.walk(local_root):
        dirs.sort()
        for name in sorted(names):
            local = Path(directory) / name
            pairs.append((local, remote_root.rstrip('/') + '/' + local.relative_to(local_root).as_posix()))
    return pairs


def upload(ftp, pairs, always=False, progress=None):
    made, sent = set(), []
    for index, (local, remote) in enumerate(pairs):
        if not remote.startswith('/') or '/../' in remote + '/':
            raise ValueError(f'remote path must be absolute and plain: {remote}')
        folder = remote.rsplit('/', 1)[0]
        if folder and folder not in made:
            ensure_dir(ftp, folder)
            made.add(folder)
        if put(ftp, str(local), remote, always):
            sent.append(remote)
        if progress and index % 100 == 0:
            progress(f'{index}/{len(pairs)} checked, {len(sent)} sent')
    return {'files': len(pairs), 'sent': len(sent), 'sent_paths': sent[:200]}


def add_plugin_section(text, title, plugin):
    """plugins.ini text with `plugin` listed under [title]; unchanged when already there."""
    section = f'[{title}]'
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == section]
    for start in starts:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith('[')), len(lines))
        if any(line.strip() == plugin for line in lines[start + 1:end]):
            return text, False
    if starts:
        start = starts[0]
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith('[')), len(lines))
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        lines.insert(end, plugin)
        return '\n'.join(lines) + '\n', True
    if text and not text.endswith('\n'):
        text += '\n'
    return text + f'\n{section}\n{plugin}\n', True


def enable_plugin(ftp, title, plugin, backup=None):
    buffer = io.BytesIO()
    try:
        ftp.retrbinary('RETR ' + PLUGINS_INI, buffer.write)
        text = buffer.getvalue().decode('utf-8', 'replace')
    except ftplib.error_perm:
        text = ''
    if backup is not None:
        Path(backup).write_text(text, encoding='utf-8')
    new, changed = add_plugin_section(text, title, plugin)
    if changed:
        ftp.storbinary('STOR ' + PLUGINS_INI, io.BytesIO(new.encode('utf-8')))
    return {'changed': changed, 'title': title, 'plugin': plugin}


# Kernel log ---------------------------------------------------------------

def record_klog(host, out, port=KLOG_PORT, duration=None, until=None, retry=5, busy_wait=30, echo=None):
    """Appends the kernel log to `out`. Stops after `duration` seconds or when `until` matches."""
    deadline = time.time() + duration if duration else None
    pattern = re.compile(until.encode()) if until else None
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    tail = b''
    stats = {'connections': 0, 'bytes': 0, 'matched': False}
    while deadline is None or time.time() < deadline:
        connection = None
        try:
            connection = socket.create_connection((host, port), timeout=10)
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if hasattr(socket, 'SIO_KEEPALIVE_VALS'):
                connection.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 15000, 5000))
            connection.settimeout(1.0 if deadline else None)
            stats['connections'] += 1
            first = True
            with open(out, 'ab') as log:
                log.write(b'\n--- connected %d ---\n' % int(time.time()))
                while deadline is None or time.time() < deadline:
                    try:
                        data = connection.recv(65536)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    log.write(data)
                    log.flush()
                    stats['bytes'] += len(data)
                    if echo:
                        echo(data)
                    if first and BUSY in data:
                        time.sleep(busy_wait)
                        break
                    first = False
                    if pattern:
                        tail = (tail + data)[-65536:]
                        if pattern.search(tail):
                            stats['matched'] = True
                            return stats
        except OSError:
            pass
        finally:
            if connection:
                connection.close()
        if deadline is not None and time.time() + retry >= deadline:
            break
        time.sleep(retry)
    return stats


def safe_line(line, limit=240):
    return '[line left out: may contain a secret]' if SECRET.search(line) else line[:limit]


def symbol_for(elf, offset, nm='llvm-nm'):
    try:
        rows = subprocess.run([nm, '-n', '-C', '--defined-only', str(elf)], capture_output=True, text=True,
                              timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    best = None
    for row in rows.splitlines():
        parts = row.split(' ', 2)
        if len(parts) == 3 and parts[0] and parts[1] in 'tTwW' and int(parts[0], 16) <= offset:
            best = (int(parts[0], 16), parts[2])
    return f'{best[1]}+{offset - best[0]:#x}' if best else None


def summarise(text, boot_marker=None, tag=None, exclude=None, elf=None, elf_module=None, max_lines=400):
    lines = text.splitlines()
    if boot_marker:
        marker = re.compile(boot_marker)
        starts = [i for i, line in enumerate(lines) if marker.search(line)]
    else:
        starts = [i for i, line in enumerate(lines) if line.startswith('--- connected ')]
    if not starts:
        raise ValueError('no boot found in the log' + (f' (marker {boot_marker!r})' if boot_marker else ''))
    boot = lines[starts[-1]:]
    skip = re.compile(exclude) if exclude else None
    shown = [safe_line(line) for line in boot
             if (tag is None or tag in line) and not (skip and skip.search(line))]
    summary = {'boot_line': starts[-1] + 1, 'lines': shown[:max_lines], 'lines_total': len(shown), 'crash': None}

    crash = next((i for i, line in enumerate(boot) if CRASH in line), None)
    if crash is None:
        return summary
    details, registers = [], {}
    for line in boot[crash:crash + 40]:
        if line.startswith('# ') and any(k in line for k in ('signal', 'reason', 'fault address', 'thread name')):
            details.append(safe_line(line))
        for name, value in re.findall(r'\b(r[a-z0-9]+|BrF|BrT)\s*:\s*([0-9a-f]{16})', line):
            registers[name] = int(value, 16)
    modules, current = [], None
    for line in boot[crash:crash + 600]:
        match = re.match(r'# (/\S+)$', line)
        if match:
            current = match.group(1)
        match = re.match(r'#\s+(text|data): ([0-9a-f]+):([0-9a-f]+)', line)
        if match and current:
            modules.append((current, match.group(1), int(match.group(2), 16), int(match.group(3), 16)))
    where = {}
    for name in ('rip', 'BrF', 'BrT'):
        if name not in registers:
            continue
        address = registers[name]
        found = next(((m, kind, address - a) for m, kind, a, b in modules if a <= address < b), None)
        if not found:
            where[name] = {'address': hex(address), 'module': None}
            continue
        module, kind, offset = found
        entry = {'address': hex(address), 'module': module.rsplit('/', 1)[-1], 'segment': kind, 'offset': hex(offset)}
        if elf and kind == 'text' and (elf_module is None or elf_module in module):
            entry['symbol'] = symbol_for(elf, offset)
        where[name] = entry
    summary['crash'] = {'line': starts[-1] + crash + 1, 'details': details, 'registers': where}
    return summary


# CLI ----------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    host = argparse.ArgumentParser(add_help=False)
    host.add_argument('--host', default=os.environ.get('ARES_PS4_HOST'), help='PS4 address (default: $ARES_PS4_HOST)')

    p = sub.add_parser('ls', parents=[host], help='List a remote folder')
    p.add_argument('path')
    p.add_argument('--port', type=int, default=FTP_PORT)

    p = sub.add_parser('upload', parents=[host], help='Upload files and folder trees')
    p.add_argument('--file', nargs=2, action='append', default=[], metavar=('LOCAL', 'REMOTE'))
    p.add_argument('--tree', nargs=2, action='append', default=[], metavar=('LOCAL_DIR', 'REMOTE_DIR'))
    p.add_argument('--always', action='store_true', help='Send even when the size matches')
    p.add_argument('--port', type=int, default=FTP_PORT)

    p = sub.add_parser('enable-plugin', parents=[host], help='Load a plugin for a title through plugins.ini')
    p.add_argument('--title', required=True, help='Title ID, e.g. CUSA04013')
    p.add_argument('--plugin', required=True, help='Plugin path on the console, e.g. /data/GoldHEN/plugins/x.prx')
    p.add_argument('--backup', type=Path, required=True, help='Where to save the old plugins.ini locally')
    p.add_argument('--port', type=int, default=FTP_PORT)

    p = sub.add_parser('klog', parents=[host], help='Record the kernel log')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--duration', type=float, help='Stop after this many seconds (default: run until stopped)')
    p.add_argument('--until', help='Stop when this regex appears')
    p.add_argument('--port', type=int, default=KLOG_PORT)

    p = sub.add_parser('lastboot', help='Summarise the last boot in a recorded kernel log')
    p.add_argument('--log', type=Path, required=True)
    p.add_argument('--boot-marker', help='Regex for the first line of a boot (default: the last klog connection)')
    p.add_argument('--tag', help='Only show lines containing this text, e.g. "[MyPlugin]"')
    p.add_argument('--exclude', help='Regex for lines to leave out (bulk listings)')
    p.add_argument('--elf', type=Path, help="The plugin's unstripped ELF, for crash symbols (needs llvm-nm)")
    p.add_argument('--elf-module', help='Module name substring the ELF belongs to, e.g. my_plugin')
    p.add_argument('--output', type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == 'lastboot':
            text = args.log.read_bytes().decode('utf-8', 'replace')
            result = summarise(text, args.boot_marker, args.tag, args.exclude, args.elf, args.elf_module)
            out = json.dumps(result, indent=2)
            if args.output:
                args.output.write_text(out + '\n', encoding='utf-8')
            else:
                print(out)
            return 0
        if not args.host:
            parser.error('no PS4 address: pass --host or set ARES_PS4_HOST')
        if args.command == 'klog':
            result = record_klog(args.host, args.out, args.port, args.duration, args.until)
            result['out'] = str(args.out)
        elif args.command == 'ls':
            ftp = connect(args.host, args.port)
            try:
                result = {'path': args.path, 'entries': list_dir(ftp, args.path)}
            finally:
                ftp.quit()
        elif args.command == 'upload':
            pairs = [(Path(local), remote) for local, remote in args.file]
            for local, remote in args.tree:
                if not Path(local).is_dir():
                    parser.error(f'not a folder: {local}')
                pairs += tree_files(local, remote)
            if not pairs:
                parser.error('nothing to upload')
            for local, _ in pairs:
                if not Path(local).is_file():
                    parser.error(f'not a file: {local}')
            ftp = connect(args.host, args.port)
            try:
                result = upload(ftp, pairs, args.always, progress=lambda m: print(m, file=sys.stderr, flush=True))
            finally:
                ftp.quit()
        else:
            if not TITLE_ID.fullmatch(args.title) or not args.plugin.startswith('/') or '\n' in args.plugin:
                parser.error('bad --title or --plugin')
            ftp = connect(args.host, args.port)
            try:
                result = enable_plugin(ftp, args.title, args.plugin, args.backup)
            finally:
                ftp.quit()
    except (OSError, ftplib.Error, RuntimeError, ValueError) as error:
        print(json.dumps({'error': f'{type(error).__name__}: {error}'}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
