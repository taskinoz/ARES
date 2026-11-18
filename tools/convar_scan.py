#!/usr/bin/env python3
"""List the ConVars and ConCommands registered in Respawn x64 PE binaries.

Static: nothing is launched, so it is safe on fragile builds (TFO) and also finds
development-only convars that retail hides from help/find. Each registration is
a small static-initialiser that loads the arguments and calls a constructor:

  ConVar:     rdx=name, r8=default string, r9d=flags, [rsp+20h]=help
  ConCommand: rdx=name, r8=callback (code), r9=help string, [rsp+20h]=flags

A call target becomes a constructor when at least --min-sites of its call sites
(and 80% of them) have one of those shapes. No per-build byte signatures are
used. Script-registered and mod convars (Northstar mods, Squirrel) are not in
the binaries; confirm anything a test depends on in the game (help <name>).

  python tools/convar_scan.py OUTPUT.json client.dll server.dll engine.dll ...
  python tools/convar_scan.py OUTPUT.json --game C:/Games/Titanfall2

Needs capstone (pip install capstone). Standard library otherwise. GPL-2.0-or-later.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import struct
import sys
from pathlib import Path

NAME = re.compile(r'[+\-]?[A-Za-z_][A-Za-z0-9_.]{1,63}')
# FCVAR bits, checked against Northstar's help output for the same convars
# (e.g. 0x4000 matched CHEAT for 289 of 290). Unknown bits stay in 'flags'.
FLAG_NAMES = {0x2: 'DEVELOPMENTONLY', 0x4: 'GAMEDLL', 0x8: 'CLIENTDLL', 0x10: 'HIDDEN', 0x20: 'PROTECTED',
              0x40: 'SPONLY', 0x80: 'ARCHIVE', 0x100: 'NOTIFY', 0x200: 'USERINFO', 0x1000: 'NEVER_AS_STRING',
              0x2000: 'REPLICATED', 0x4000: 'CHEAT', 0x10000: 'DEMO', 0x20000: 'DONTRECORD', 0x80000: 'RELEASE',
              0x400000: 'NOT_CONNECTED', 0x800000: 'MATERIAL_SYSTEM_THREAD', 0x1000000: 'ARCHIVE_PLAYERPROFILE',
              0x2000000: 'ACCESSIBLE_FROM_THREADS', 0x20000000: 'SERVER_CANNOT_QUERY'}
GAME_BINARIES = ('bin/x64_retail/*.dll', 'Bin/*.dll', 'r1/bin/x64_retail/*.dll', '*.dll', '*.exe')


class PE:
    """Just enough of a PE32+ image: base, sections and C strings."""

    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        d = self.data
        if d[:2] != b'MZ':
            raise ValueError(f'{path}: not a PE file')
        pe = struct.unpack_from('<I', d, 0x3C)[0]
        if d[pe:pe + 4] != b'PE\0\0':
            raise ValueError(f'{path}: not a PE file')
        machine, count = struct.unpack_from('<HH', d, pe + 4)
        optional_size = struct.unpack_from('<H', d, pe + 20)[0]
        optional = pe + 24
        if machine != 0x8664 or struct.unpack_from('<H', d, optional)[0] != 0x20B:
            raise ValueError(f'{path}: not an x86-64 PE32+ image')
        self.base = struct.unpack_from('<Q', d, optional + 24)[0]
        self.sections = []
        for i in range(count):
            at = optional + optional_size + i * 40
            vsize, rva, raw_size, raw = struct.unpack_from('<IIII', d, at + 8)
            flags = struct.unpack_from('<I', d, at + 36)[0]
            self.sections.append((rva, max(vsize, raw_size), raw, raw_size, flags))

    def offset(self, va):
        rva = va - self.base
        for start, size, raw, raw_size, _ in self.sections:
            if start <= rva < start + size and rva - start < raw_size:
                return raw + rva - start
        return None

    def is_code(self, va):
        rva = va - self.base
        return any(start <= rva < start + size and flags & 0x20000000
                   for start, size, _, _, flags in self.sections)

    def code(self):
        for start, size, raw, raw_size, flags in self.sections:
            if flags & 0x20000000:
                yield self.base + start, self.data[raw:raw + raw_size]

    def string(self, va):
        at = self.offset(va)
        if at is None:
            return None
        end = self.data.find(b'\0', at, at + 1024)
        if end < 0:
            return None
        try:
            text = self.data[at:end].decode('ascii')
        except UnicodeDecodeError:
            return None
        return text if all(32 <= ord(c) < 127 or c in '\t\n' for c in text) else None


def calls(pe):
    """Map call target -> call site VAs for every E8 rel32 in code."""
    sites = collections.defaultdict(list)
    for start, data in pe.code():
        at = data.find(b'\xe8')
        while 0 <= at < len(data) - 4:
            target = start + at + 5 + struct.unpack_from('<i', data, at + 1)[0]
            sites[target].append(start + at)
            at = data.find(b'\xe8', at + 1)
    return sites


def arguments(pe, engine, call, window=96):
    """Registers and stack slots set by the straight-line code before a call."""
    for start, data in pe.code():
        if start <= call < start + len(data):
            break
    else:
        return None
    at = call - start
    low = max(0, at - window)
    # Start after the int3 padding before the initialiser. A 0xC3 byte can sit
    # inside an instruction, so a ret is only used when there is no padding.
    pad = data.rfind(b'\xcc\xcc', low, at)
    ret = data.rfind(b'\xc3', low, at)
    first = pad + 2 if pad >= 0 else (ret + 1 if ret >= 0 else low)
    from capstone import x86
    regs, stack = {}, {}
    for ins in engine.disasm(data[first:at + 5], start + first):
        if ins.address == call:
            return regs, stack
        if ins.mnemonic == 'call':  # several registrations can share a function;
            regs, stack = {}, {}    # don't carry the previous one's arguments over
            continue
        ops = ins.operands
        if (ins.mnemonic == 'lea' and len(ops) == 2 and ops[1].type == x86.X86_OP_MEM and
                ops[1].mem.base == x86.X86_REG_RIP):
            target = ins.address + ins.size + ops[1].mem.disp
            regs[ins.reg_name(ops[0].reg)] = ('code', target) if pe.is_code(target) else ('str', pe.string(target))
        elif ins.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == x86.X86_OP_REG and ops[1].type == x86.X86_OP_IMM:
            regs[ins.reg_name(ops[0].reg)] = ('int', ops[1].imm)
        elif (ins.mnemonic == 'xor' and len(ops) == 2 and ops[0].type == x86.X86_OP_REG and
              ops[1].type == x86.X86_OP_REG and ops[0].reg == ops[1].reg):
            regs[ins.reg_name(ops[0].reg)] = ('int', 0)
        elif (ins.mnemonic == 'mov' and len(ops) == 2 and ops[0].type == x86.X86_OP_MEM and
              ops[0].mem.base == x86.X86_REG_RSP):
            if ops[1].type == x86.X86_OP_REG:
                stack[ops[0].mem.disp] = regs.get(ins.reg_name(ops[1].reg))
            elif ops[1].type == x86.X86_OP_IMM:
                stack[ops[0].mem.disp] = ('int', ops[1].imm)
    return None


def shape(regs, stack):
    """('convar' | 'command', entry) when the arguments look like a registration."""
    get = lambda key: regs.get(key) or (None, None)  # noqa: E731
    name = get('rdx')
    if name[0] != 'str' or not name[1] or not NAME.fullmatch(name[1]):
        return None
    r8, r9 = get('r8'), get('r9d') if 'r9d' in regs else get('r9')
    slot = stack.get(0x20) or (None, None)
    if r8[0] == 'str' and r9[0] == 'int':
        return 'convar', {'name': name[1], 'default': r8[1], 'flags': r9[1],
                          'help': slot[1] if slot[0] == 'str' else None}
    if r8[0] == 'code' and (r9[0] == 'str' or r9 == ('int', 0)):
        return 'command', {'name': name[1], 'flags': slot[1] if slot[0] == 'int' else None,
                           'help': r9[1] if r9[0] == 'str' else None}
    return None


INLINE = re.compile(rb'([\x48\x4c])\x8d(.)(.{4})\1\x89\2(.{4})([\x48\x4c])\x8d(.)(.{4})\5\x89\6(.{4})\xc7\x05(.{4})(.{4})',
                    re.S)


def inline_registrations(pe):
    """ConVars whose constructor the compiler inlined (R1's server.dll).

    The initialiser stores the name, help and flags straight into the global
    object: lea reg,name / mov [F],reg / lea reg,help / mov [F+8],reg /
    mov dword [F+16],flags. The default is built separately and isn't recovered.
    """
    found = {}
    for start, data in pe.code():
        for m in INLINE.finditer(data):
            if (m.group(2)[0] & 0xC7) != 0x05 or (m.group(6)[0] & 0xC7) != 0x05:
                continue
            at = start + m.start()
            rel = lambda group, end: at + end + struct.unpack('<i', m.group(group))[0]  # noqa: E731
            name, name_field = pe.string(rel(3, 7)), rel(4, 14)
            help_text, help_field = pe.string(rel(7, 21)), rel(8, 28)
            flags_field = rel(9, 38)
            if (not name or not NAME.fullmatch(name) or help_text is None or
                    help_field != name_field + 8 or flags_field != name_field + 16):
                continue
            flags = struct.unpack('<I', m.group(10))[0]
            found.setdefault(name, {'kind': 'convar', 'module': pe.path.name, 'constructor': 'inline',
                                    'default': None, 'flags': flags, 'help': help_text,
                                    'flag_names': decode_flags(flags)})
    return found


def static_objects(pe, min_sites=20):
    """ConCommands the compiler laid out as initialised data (TFO's client.dll).

    Each object is vtable, 0, 0, 0, name, help, flags, ..., callback at +48 from
    the name. Objects are grouped by vtable; a vtable shared by at least
    min_sites named objects with code callbacks is treated as ConCommand's.
    """
    size = max(rva + span for rva, span, _, _, _ in pe.sections)
    groups = collections.defaultdict(list)
    for rva, span, raw, raw_size, flags in pe.sections:
        if flags & 0x20000000 or not flags & 0x40:  # initialised, non-code data
            continue
        data = pe.data[raw:raw + raw_size]
        for at in range(24, len(data) - 56, 8):
            name_va = struct.unpack_from('<Q', data, at)[0]
            if not pe.base <= name_va < pe.base + size or pe.is_code(name_va):
                continue
            vtable, help_va, flag_value, callback = (struct.unpack_from('<Q', data, at + k)[0] for k in (-24, 8, 16, 48))
            if flag_value >> 32 or not pe.is_code(callback) or not pe.base <= vtable < pe.base + size:
                continue
            name = pe.string(name_va)
            if not name or not NAME.fullmatch(name):
                continue
            help_text = pe.string(help_va) if pe.base <= help_va < pe.base + size else None
            if help_text is None:
                continue
            groups[vtable].append((name, help_text, flag_value))
    found = {}
    for vtable, rows in groups.items():
        if len(rows) < min_sites:
            continue
        for name, help_text, flag_value in rows:
            found.setdefault(name, {'kind': 'command', 'module': pe.path.name, 'constructor': 'static:' + hex(vtable),
                                    'flags': flag_value, 'help': help_text or None,
                                    'flag_names': decode_flags(flag_value)})
    return found


def decode_flags(value):
    if value is None:
        return []
    return [label for bit, label in sorted(FLAG_NAMES.items()) if value & bit]


def scan(path, min_sites=20):
    import capstone
    pe = PE(path)
    engine = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    engine.detail = True
    found = {}
    for target, sites in calls(pe).items():
        if len(sites) < min_sites:
            continue
        kinds = collections.Counter()
        rows = []
        for number, site in enumerate(sites):
            if number == 40 and sum(kinds.values()) < 20:
                break  # most call targets are ordinary functions; give up early
            args = arguments(pe, engine, site)
            result = shape(*args) if args else None
            if result:
                kinds[result[0]] += 1
                rows.append(result)
        if not kinds:
            continue
        kind, count = kinds.most_common(1)[0]
        if count < min_sites or count < 0.8 * len(sites):
            continue
        for row_kind, entry in rows:
            if row_kind == kind:
                found.setdefault(entry['name'], {'kind': kind, 'module': pe.path.name, 'constructor': hex(target),
                                                 **{k: v for k, v in entry.items() if k != 'name'},
                                                 'flag_names': decode_flags(entry['flags'])})
    for name, entry in inline_registrations(pe).items():
        found.setdefault(name, entry)
    for name, entry in static_objects(pe, min_sites).items():
        found.setdefault(name, entry)
    return found


def game_binaries(game):
    game = Path(game)
    seen = []
    for pattern in GAME_BINARIES:
        for path in sorted(game.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.append(path)
    return seen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('output', type=Path)
    parser.add_argument('binaries', nargs='*', type=Path)
    parser.add_argument('--game', type=Path, help='Scan the game folder\'s DLLs and EXEs')
    parser.add_argument('--min-sites', type=int, default=20)
    parser.add_argument('--verified', type=Path,
                        help='JSON of names confirmed in game (object keyed by name); marks each entry')
    args = parser.parse_args(argv)
    binaries = list(args.binaries) + (game_binaries(args.game) if args.game else [])
    if not binaries:
        parser.error('give binaries or --game')
    try:
        import capstone  # noqa: F401
    except ImportError:
        parser.error('needs the capstone module (pip install capstone)')
    verified = set(json.loads(args.verified.read_text())) if args.verified else None
    entries, modules = {}, {}
    for path in binaries:
        try:
            found = scan(path, args.min_sites)
        except ValueError as error:
            print(f'skipped {error}', file=sys.stderr)
            continue
        try:  # same-named DLLs exist in several folders; label by path
            label = path.resolve().relative_to(args.game.resolve()).as_posix() if args.game else str(path)
        except ValueError:
            label = str(path)
        modules[label] = len(found)
        for name, entry in found.items():
            entry['module'] = label
            entries.setdefault(name, entry)
    if verified is not None:
        for name, entry in entries.items():
            entry['in_game'] = name in verified
    report = {'modules': modules, 'count': len(entries), 'entries': dict(sorted(entries.items()))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1))
    print(json.dumps({'count': len(entries), 'modules': modules}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
