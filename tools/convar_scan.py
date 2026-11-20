#!/usr/bin/env python3
"""List the ConVars and ConCommands registered in Respawn x64 PE binaries.

Static: nothing is launched, so it is safe on fragile builds (TFO) and also finds
development-only convars that retail hides from help/find. Each registration is
a small static-initialiser that loads the arguments and calls a constructor:

  ConVar:     rdx=name, r8=default string, r9d=flags, [rsp+20h]=help
  ConCommand: rdx=name, r8=callback (code), r9=help string, [rsp+20h]=flags

A call target (direct, or through a pointer as in the legacy R5Reloaded SDK)
becomes a constructor when at least --min-sites of its call sites (and 80% of
them) have one of those shapes. Inlined registrations (R1's server.dll, Apex
S0-S3 and the S21 client) and ConCommands laid out as data (TFO, Apex) are
read too. No
per-build byte signatures are used. Script-registered and mod convars (Northstar mods, Squirrel) are not in
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
              0x2000000: 'ACCESSIBLE_FROM_THREADS', 0x20000000: 'SERVER_CANNOT_QUERY',
              # Remaining names from r5sdk's tier1/iconvar.h (Apex); same bits as Source.
              0x400: 'PRINTABLEONLY', 0x800: 'UNLOGGED', 0x8000: 'SS', 0x40000: 'SS_ADDED',
              0x100000: 'RELOAD_MATERIALS', 0x200000: 'RELOAD_TEXTURES', 0x4000000: 'STUDIO_SYSTEM',
              0x8000000: 'SERVER_FRAME_THREAD', 0x10000000: 'SERVER_CAN_EXECUTE',
              0x40000000: 'CLIENTCMD_CAN_EXECUTE', 0x80000000: 'PLATFORM_SYSTEM'}
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
    """Map call target -> call site VAs for every E8 rel32 call in code, and for
    every FF 15 call through a rip-relative pointer (keyed by the pointer's
    address: an import, or a pointer the SDK filled in at runtime)."""
    sites = collections.defaultdict(list)
    for start, data in pe.code():
        at = data.find(b'\xe8')
        while 0 <= at < len(data) - 4:
            target = start + at + 5 + struct.unpack_from('<i', data, at + 1)[0]
            sites[target].append(start + at)
            at = data.find(b'\xe8', at + 1)
        at = data.find(b'\xff\x15')
        while 0 <= at < len(data) - 5:
            pointer = start + at + 6 + struct.unpack_from('<i', data, at + 2)[0]
            sites[('ptr', pointer)].append(start + at)
            at = data.find(b'\xff\x15', at + 1)
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
    for ins in engine.disasm(data[first:at + 6], start + first):
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


VALUE = re.compile(r'-?[0-9.]+( -?[0-9.]+)*')
NAME_LEA = re.compile(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d](.{4})', re.S)


def full_register(name):
    """rax for eax, r8 for r8d: a 32-bit write clears the upper half anyway."""
    if name.startswith('e') and len(name) == 3:
        return 'r' + name[1:]
    return name.rstrip('dwb') if name[:1] == 'r' and name[1:2].isdigit() else name


def inline_registrations(pe, engine=None):
    """ConVars and ConCommands whose constructor the compiler inlined.

    The initialiser stores the name and help straight into the object (name at
    F, help at F+8) and then the flags dword: at F+16 in R1's server.dll, at
    F+32 in Apex, which stores a usage string at F+16. Apex keeps a convar's
    default string in the object's initialised data at F+56; R1 builds it
    separately and it isn't recovered. The legacy R5Reloaded SDK fills heap
    ConCommands the same way through a register, with the callback at F+56.

    The order of the stores and the registers carrying the values vary between
    builds, so the straight-line code after each lea of a name is followed and
    every store to [rip+x] or [reg+x] is recorded. An object that gets any
    other code pointer is a script function binding, not a convar.
    """
    if engine is None:
        import capstone
        engine = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        engine.detail = True
    from capstone import x86
    found = {}
    for start, data in pe.code():
        for m in NAME_LEA.finditer(data):
            target = start + m.end() + struct.unpack('<i', m.group(1))[0]
            name = pe.string(target)
            if not name or not NAME.fullmatch(name):
                continue
            regs, stores, ints = {}, {}, {}  # (base, displacement) -> value; base 'rip' is absolute
            for count, ins in enumerate(engine.disasm(data[m.start():m.start() + 160], start + m.start())):
                if count > 24 or ins.mnemonic in ('call', 'ret', 'jmp') or ins.mnemonic.startswith('j') and stores:
                    break
                ops = ins.operands
                if len(ops) != 2:
                    continue
                dst, src = ops
                if dst.type == x86.X86_OP_REG:
                    reg = full_register(ins.reg_name(dst.reg))
                    for table in (stores, ints):  # the base moved: earlier [reg+x] were another object
                        for key in [k for k in table if k[0] == reg]:
                            del table[key]
                    if ins.mnemonic == 'lea' and src.type == x86.X86_OP_MEM and src.mem.base == x86.X86_REG_RIP:
                        regs[reg] = ins.address + ins.size + src.mem.disp
                    elif ins.mnemonic == 'xor' and src.type == x86.X86_OP_REG and src.reg == dst.reg:
                        regs[reg] = 0
                    elif ins.mnemonic == 'mov' and src.type == x86.X86_OP_IMM:
                        regs[reg] = src.imm
                    else:
                        regs.pop(reg, None)
                elif ins.mnemonic == 'mov' and dst.type == x86.X86_OP_MEM and dst.mem.index == 0 and dst.mem.base:
                    if dst.mem.base == x86.X86_REG_RIP:
                        key = ('rip', ins.address + ins.size + dst.mem.disp)
                    else:
                        key = (full_register(ins.reg_name(dst.mem.base)), dst.mem.disp)
                    value = (regs.get(full_register(ins.reg_name(src.reg))) if src.type == x86.X86_OP_REG
                             else src.imm if src.type == x86.X86_OP_IMM else None)
                    if value is None:
                        continue
                    if dst.size == 8:
                        stores[key] = value
                    elif dst.size == 4:
                        ints[key] = value & 0xFFFFFFFF
            name_key = next((k for k, v in stores.items() if v == target), None)
            if name_key is None:
                continue
            base, field = name_key
            at = lambda offset: (base, field + offset)  # noqa: E731
            help_va = stores.get(at(8))
            help_text = pe.string(help_va) if help_va else None
            # vgui and particle attribute descriptors are (name, value) pairs:
            # a "help" that is a number, a vector or the name again is a value.
            if help_text is None or help_text == name or VALUE.fullmatch(help_text):
                continue
            callback = stores.get(at(56))
            if callback is not None and pe.is_code(callback):
                flags = ints.get(at(32))
                if flags is not None:
                    found.setdefault(name, {'kind': 'command', 'module': pe.path.name, 'constructor': 'inline',
                                            'flags': flags, 'help': help_text, 'flag_names': decode_flags(flags)})
                continue
            # Squirrel function bindings have the same name/help shape but also
            # store a code pointer (the native function) into the object.
            if any(pe.is_code(v) for k, v in stores.items() if k[0] == base and -0x30 <= k[1] - field <= 0x80):
                continue
            usage = stores.get(at(16))
            default = None
            if usage is not None and pe.string(usage) is not None:  # Apex layout
                flags = ints.get(at(32))
                offset = pe.offset(field + 56) if base == 'rip' else None
                if offset is not None:
                    default = pe.string(struct.unpack_from('<Q', pe.data, offset)[0])
            elif at(16) in ints:
                flags = ints[at(16)]
            elif stores.get(at(16)) == 0:  # Apex S21: a zero qword at F+16, flags at F+24
                flags = ints.get(at(24))
            else:
                flags = None
            if flags is None:
                continue
            found.setdefault(name, {'kind': 'convar', 'module': pe.path.name, 'constructor': 'inline',
                                    'default': default, 'flags': flags, 'help': help_text,
                                    'flag_names': decode_flags(flags)})
    return found


# ConCommand data layouts, as offsets from the name pointer: vtable, help,
# flags, callback, the usage string where the build has one, and a qword that
# must be zero. TFO's client.dll, Apex S0-S3 r5apex.exe, and the Apex S21
# client (R5Flowstate's r5apex_dx12.exe), whose retail help strings are empty.
STATIC_LAYOUTS = ({'vtable': -24, 'help': 8, 'flags': 16, 'callback': 48, 'usage': None, 'zero': None},
                  {'vtable': -24, 'help': 8, 'flags': 32, 'callback': 56, 'usage': 16, 'zero': None},
                  {'vtable': -16, 'help': 8, 'flags': 24, 'callback': 48, 'usage': None, 'zero': 16})


def static_objects(pe, min_sites=20):
    """ConCommands the compiler laid out as initialised data (TFO, Apex).

    Each object is vtable, ..., name, help, ... (STATIC_LAYOUTS). Objects are
    grouped by vtable; a vtable shared by at least min_sites named objects with
    code callbacks is treated as ConCommand's.
    """
    size = max(rva + span for rva, span, _, _, _ in pe.sections)
    inside = lambda va: pe.base <= va < pe.base + size  # noqa: E731
    groups = collections.defaultdict(list)
    for rva, span, raw, raw_size, flags in pe.sections:
        if flags & 0x20000000 or not flags & 0x40:  # initialised, non-code data
            continue
        data = pe.data[raw:raw + raw_size]
        for at in range(24, len(data) - 64, 8):
            name_va = struct.unpack_from('<Q', data, at)[0]
            if not inside(name_va) or pe.is_code(name_va):
                continue
            for layout in STATIC_LAYOUTS:
                q = {key: struct.unpack_from('<Q', data, at + off)[0] for key, off in layout.items() if off is not None}
                vtable = q['vtable']
                if not inside(vtable) or q['flags'] >> 32 or not pe.is_code(q['callback']):
                    continue
                if 'zero' in q and q['zero'] != 0:
                    continue
                if 'usage' in q and (not inside(q['usage']) or pe.string(q['usage']) is None):
                    continue
                name = pe.string(name_va)
                if not name or not NAME.fullmatch(name):
                    break
                help_text = pe.string(q['help']) if inside(q['help']) else None
                if help_text is None:
                    continue
                groups[vtable].append((name, help_text, q['flags']))
                break
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
            # A short window first; a wider one only if that finds nothing (the
            # legacy R5Reloaded SDK sets the arguments up ~200 bytes early, and a
            # wide window can start mid-instruction in tightly packed code).
            for window in (96, 256):
                args = arguments(pe, engine, site, window)
                result = shape(*args) if args else None
                if result:
                    break
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
                found.setdefault(entry['name'], {'kind': kind, 'module': pe.path.name, 'constructor': hex(target) if isinstance(target, int) else 'ptr:' + hex(target[1]),
                                                 **{k: v for k, v in entry.items() if k != 'name'},
                                                 'flag_names': decode_flags(entry['flags'])})
    for name, entry in inline_registrations(pe, engine).items():
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
