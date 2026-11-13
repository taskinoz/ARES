#!/usr/bin/env python3
"""Static reverse-engineering helpers for decrypted PS4 modules (.prx/.sprx/eboot.bin).

Decrypted PS4 modules are x86-64 ELF files with Sony segment and dynamic
types. Addresses inside a module are written module-relative (`engine+0x1234`)
because load addresses change every run; this tool works in those
module-relative virtual addresses (VAs) and converts to file offsets through
the program headers. It also reads plain x86-64 ELF files (Linux .so, test
files).

Pointer tables (vtables, callback arrays) are zero in the file and filled by
R_X86_64_RELATIVE relocations at load; `ptr` and `xrefs` apply them, so they
show what a running game would see.

usage:
  python tools/prx_inspect.py info MODULE
  python tools/prx_inspect.py addr MODULE 0x1234 [--file-offset]
  python tools/prx_inspect.py strings MODULE TEXT [--utf16] [--limit N]
  python tools/prx_inspect.py xrefs MODULE (0xVA | --string TEXT) [--limit N]
  python tools/prx_inspect.py refs MODULE 0xSTART 0xEND
  python tools/prx_inspect.py ptr MODULE 0xVA [--count N]
  python tools/prx_inspect.py dump MODULE 0xVA [--length N]
  python tools/prx_inspect.py disasm MODULE 0xVA [--length N]   (needs capstone)
  python tools/prx_inspect.py find MODULE "48 8d 3d ?? ?? ?? ??" [--limit N]

`xrefs` finds code that reaches a VA through a rip-relative operand (lea, mov,
cmp, call, jmp, jcc, SSE loads) plus pointers relocated to it. It decodes only
the opcode bytes just before the 32-bit displacement, so treat hits as
candidates and confirm them with `disasm`.

Every command prints JSON. Nothing here modifies the module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

PT_LOAD, PT_DYNAMIC = 1, 2
PT_SCE_DYNLIBDATA, PT_SCE_RELRO = 0x61000000, 0x61000010
PT_NAMES = {0: 'NULL', 1: 'LOAD', 2: 'DYNAMIC', 3: 'INTERP', 4: 'NOTE', 6: 'PHDR', 7: 'TLS',
            0x6474E550: 'GNU_EH_FRAME', 0x6474E551: 'GNU_STACK', 0x6474E552: 'GNU_RELRO',
            0x61000000: 'SCE_DYNLIBDATA', 0x61000001: 'SCE_PROCPARAM', 0x61000002: 'SCE_MODULE_PARAM',
            0x61000010: 'SCE_RELRO', 0x6FFFFF00: 'SCE_COMMENT', 0x6FFFFF01: 'SCE_LIBVERSION'}
ET_NAMES = {2: 'EXEC', 3: 'DYN', 0xFE00: 'SCE_EXEC', 0xFE10: 'SCE_DYNEXEC', 0xFE18: 'SCE_DYNAMIC'}
DT_RELA, DT_RELASZ = 7, 8
DT_SCE_RELA, DT_SCE_RELASZ = 0x6100002F, 0x61000031
R_NAMES = {1: 'R_X86_64_64', 6: 'R_X86_64_GLOB_DAT', 7: 'R_X86_64_JUMP_SLOT', 8: 'R_X86_64_RELATIVE',
           16: 'R_X86_64_DTPMOD64', 17: 'R_X86_64_DTPOFF64'}
R_X86_64_RELATIVE = 8

# Opcodes whose ModRM byte (mod=00, rm=101) selects [rip+disp32]; the value is
# the number of immediate bytes after the displacement.
MODRM_OPCODES = {
    0x8D: ('lea', 0), 0x8B: ('mov-load', 0), 0x89: ('mov-store', 0), 0x8A: ('mov-load8', 0),
    0x88: ('mov-store8', 0), 0x3B: ('cmp', 0), 0x39: ('cmp', 0), 0x3A: ('cmp8', 0), 0x38: ('cmp8', 0),
    0x85: ('test', 0), 0x03: ('add', 0), 0x01: ('add', 0), 0x2B: ('sub', 0), 0x29: ('sub', 0),
    0x0B: ('or', 0), 0x09: ('or', 0), 0x23: ('and', 0), 0x21: ('and', 0), 0x33: ('xor', 0),
    0x31: ('xor', 0), 0x63: ('movsxd', 0), 0x87: ('xchg', 0), 0xFF: ('call/jmp/inc-mem', 0),
    0xC6: ('mov-imm8', 1), 0xC7: ('mov-imm32', 4), 0x80: ('alu-imm8', 1), 0x83: ('alu-imm8', 1),
    0x81: ('alu-imm32', 4), 0xF6: ('test-imm8', 1),
}
# Two-byte (0F xx) opcodes with a rip-relative ModRM: SSE moves, movzx/movsx, cmov.
TWO_BYTE_OPCODES = {0x10: 'sse-load', 0x11: 'sse-store', 0x28: 'movaps-load', 0x29: 'movaps-store',
                    0x2E: 'ucomis', 0x2F: 'comis', 0x6F: 'movdq-load', 0x7F: 'movdq-store',
                    0xB6: 'movzx8', 0xB7: 'movzx16', 0xBE: 'movsx8', 0xBF: 'movsx16',
                    0x58: 'sse-add', 0x59: 'sse-mul', 0x5C: 'sse-sub', 0x5E: 'sse-div',
                    0x54: 'sse-and', 0x57: 'sse-xor', 0x5A: 'cvtss2sd'}


class ModuleError(ValueError):
    pass


class Module:
    def __init__(self, data: bytes, path='<memory>'):
        self.data, self.path = data, str(path)
        if data[:4] != b'\x7fELF' or data[4] != 2 or data[5] != 1:
            raise ModuleError('not a little-endian ELF64 file (is the module decrypted?)')
        (self.type, self.machine, _, self.entry, phoff, _, _, _, phentsize,
         phnum) = struct.unpack_from('<HHIQQQIHHH', data, 16)
        self.segments = []
        for i in range(phnum):
            p_type, flags, offset, vaddr, _, filesz, memsz, align = struct.unpack_from(
                '<IIQQQQQQ', data, phoff + i * phentsize)
            self.segments.append({'index': i, 'type': p_type, 'flags': flags, 'offset': offset, 'vaddr': vaddr,
                                  'filesz': filesz, 'memsz': memsz, 'align': align})
        self.mapped = [s for s in self.segments if s['type'] in (PT_LOAD, PT_SCE_RELRO) and s['memsz']]
        self.relocations = self._relocations()
        self.relative = {r['offset']: r['addend'] for r in self.relocations if r['type'] == R_X86_64_RELATIVE}

    @classmethod
    def load(cls, path):
        return cls(Path(path).read_bytes(), path)

    # Address conversion ---------------------------------------------------
    def segment_for_va(self, va):
        return next((s for s in self.mapped if s['vaddr'] <= va < s['vaddr'] + s['memsz']), None)

    def va_to_offset(self, va):
        segment = self.segment_for_va(va)
        if segment is None or va - segment['vaddr'] >= segment['filesz']:
            return None
        return segment['offset'] + va - segment['vaddr']

    def offset_to_va(self, offset):
        for s in self.mapped:
            if s['offset'] <= offset < s['offset'] + s['filesz']:
                return s['vaddr'] + offset - s['offset']
        return None

    def read(self, va, length):
        """Bytes at a VA as loaded: zero fill past the file data, relocations not applied."""
        out = bytearray()
        while length > 0:
            segment = self.segment_for_va(va)
            if segment is None:
                raise ModuleError(f'{va:#x} is not inside a loaded segment')
            inside = va - segment['vaddr']
            chunk = min(length, segment['memsz'] - inside)
            available = max(0, min(chunk, segment['filesz'] - inside))
            start = segment['offset'] + inside
            out += self.data[start:start + available] + bytes(chunk - available)
            va, length = va + chunk, length - chunk
        return bytes(out)

    def pointer(self, va):
        """The qword at a VA after RELATIVE relocations (module-relative), or None."""
        if va in self.relative:
            return self.relative[va]
        return struct.unpack('<Q', self.read(va, 8))[0]

    def executable(self):
        return [s for s in self.mapped if s['flags'] & 1 and s['filesz']]

    # Dynamic information -------------------------------------------------
    def _relocations(self):
        dynamic = next((s for s in self.segments if s['type'] == PT_DYNAMIC), None)
        if dynamic is None:
            return []
        entries = {}
        for i in range(dynamic['filesz'] // 16):
            tag, value = struct.unpack_from('<qQ', self.data, dynamic['offset'] + i * 16)
            if tag == 0:
                break
            entries.setdefault(tag, value)
        dynlib = next((s for s in self.segments if s['type'] == PT_SCE_DYNLIBDATA), None)
        if DT_SCE_RELA in entries and dynlib is not None:
            start, size = dynlib['offset'] + entries[DT_SCE_RELA], entries.get(DT_SCE_RELASZ, 0)
        elif DT_RELA in entries:
            start, size = self.va_to_offset(entries[DT_RELA]), entries.get(DT_RELASZ, 0)
            if start is None:
                return []
        else:
            return []
        rows = []
        for i in range(size // 24):
            offset, info, addend = struct.unpack_from('<QQq', self.data, start + i * 24)
            rows.append({'offset': offset, 'type': info & 0xFFFFFFFF, 'symbol': info >> 32, 'addend': addend})
        return rows

    # Searches ------------------------------------------------------------
    def code_refs(self, low, high):
        """Rip-relative operands in executable segments whose target is in [low, high)."""
        hits = []
        for segment in self.executable():
            code = self.data[segment['offset']:segment['offset'] + segment['filesz']]
            base = segment['vaddr']
            unpack = struct.Struct('<i').unpack_from
            for p in range(1, len(code) - 3):
                near = base + p + 4 + unpack(code, p)[0]
                if not low - 4 <= near < high:  # an immediate adds at most 4 bytes
                    continue
                disp = near - base - p - 4
                for kind, start, extra in _decode(code, p):
                    target = base + p + 4 + extra + disp
                    if low <= target < high:
                        hits.append({'va': base + start, 'operand_va': base + p, 'kind': kind, 'target': target,
                                     'bytes': code[start:p + 4 + extra].hex(' ')})
        hits.sort(key=lambda h: h['va'])
        return hits

    def data_refs(self, low, high):
        return [{'va': where, 'kind': 'relocated-pointer', 'target': value}
                for where, value in sorted(self.relative.items()) if low <= value < high]

    def find_bytes(self, needle):
        return [m.start() for m in re.finditer(re.escape(needle), self.data)]

    def string_at(self, offset, limit=200):
        start = offset
        while start > 0 and offset - start < limit and 0x20 <= self.data[start - 1] < 0x7F:
            start -= 1
        end = self.data.find(b'\0', offset, offset + limit)
        end = end if end >= 0 else offset + limit
        return start, self.data[start:end].decode('latin-1')


def _decode(code, p):
    """Instruction forms that end with a disp32 at p: yields (kind, start, immediate bytes)."""
    op = code[p - 1]
    if op == 0xE8:
        yield 'call', p - 1, 0
    elif op == 0xE9:
        yield 'jmp', p - 1, 0
    if p >= 2 and code[p - 2] == 0x0F and 0x80 <= op <= 0x8F:
        yield 'jcc', p - 2, 0
    if (op & 0xC7) != 0x05 or p < 2:
        return
    opcode = code[p - 2]
    if opcode in MODRM_OPCODES:
        kind, immediate = MODRM_OPCODES[opcode]
        if opcode == 0xFF:
            kind = {2: 'call-indirect', 4: 'jmp-indirect', 6: 'push'}.get((op >> 3) & 7, 'inc/dec-mem')
        start = p - 3 if p >= 3 and 0x40 <= code[p - 3] <= 0x4F else p - 2
        yield kind, start, immediate
    elif p >= 3 and code[p - 3] == 0x0F and opcode in TWO_BYTE_OPCODES:
        start = p - 3
        if p >= 4 and (0x40 <= code[p - 4] <= 0x4F or code[p - 4] in (0x66, 0xF2, 0xF3)):
            start = p - 4
            if p >= 5 and code[p - 5] in (0x66, 0xF2, 0xF3):
                start = p - 5
        yield TWO_BYTE_OPCODES[opcode], start, 0


def parse_int(text):
    return int(text, 0)


def parse_pattern(text):
    """'48 8d ?? 05' -> regex bytes with wildcards."""
    parts = text.replace(',', ' ').split()
    if not parts:
        raise ModuleError('empty pattern')
    out = b''
    for part in parts:
        if part in ('?', '??'):
            out += b'.'
        elif re.fullmatch(r'[0-9a-fA-F]{2}', part):
            out += re.escape(bytes([int(part, 16)]))
        else:
            raise ModuleError(f'bad pattern byte {part!r}')
    return re.compile(out, re.S)


def segment_rows(module):
    rows = []
    for s in module.segments:
        flags = ''.join(c if s['flags'] & bit else '-' for c, bit in (('r', 4), ('w', 2), ('x', 1)))
        rows.append({'index': s['index'], 'type': PT_NAMES.get(s['type'], hex(s['type'])), 'flags': flags,
                     'file_offset': hex(s['offset']), 'va': hex(s['vaddr']), 'filesz': hex(s['filesz']),
                     'memsz': hex(s['memsz']),
                     'va_to_file': hex(s['offset'] - s['vaddr']) if s in module.mapped else None})
    return rows


def describe(module, va):
    segment = module.segment_for_va(va)
    offset = module.va_to_offset(va)
    return {'va': hex(va), 'file_offset': hex(offset) if offset is not None else None,
            'segment': segment['index'] if segment else None}


def hexdump(data, base):
    return [f'{base + i:#010x}  {data[i:i + 16].hex(" "):<47}  ' +
            ''.join(chr(b) if 0x20 <= b < 0x7F else '.' for b in data[i:i + 16])
            for i in range(0, len(data), 16)]


def disassemble(module, va, length):
    try:
        import capstone
    except ImportError as error:
        raise ModuleError('disasm needs the capstone module (pip install capstone)') from error
    engine = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    rows = []
    for insn in engine.disasm(module.read(va, length), va):
        row = {'va': hex(insn.address), 'bytes': insn.bytes.hex(' '), 'text': f'{insn.mnemonic} {insn.op_str}'.strip()}
        match = re.search(r'\[rip ([+-]) (0x[0-9a-f]+)\]', insn.op_str)
        if match:
            delta = int(match.group(2), 16) * (1 if match.group(1) == '+' else -1)
            row['rip_target'] = hex(insn.address + insn.size + delta)
        rows.append(row)
    return rows


def run(args):
    module = Module.load(args.module)
    if args.command == 'info':
        types = {}
        for r in module.relocations:
            name = R_NAMES.get(r['type'], str(r['type']))
            types[name] = types.get(name, 0) + 1
        return {'path': module.path, 'sha256': hashlib.sha256(module.data).hexdigest(), 'size': len(module.data),
                'elf_type': ET_NAMES.get(module.type, hex(module.type)), 'machine': module.machine,
                'entry': hex(module.entry), 'segments': segment_rows(module), 'relocations': types}
    if args.command == 'addr':
        if args.file_offset:
            va = module.offset_to_va(args.value)
            return {'file_offset': hex(args.value), 'va': hex(va) if va is not None else None}
        return describe(module, args.value)
    if args.command == 'strings':
        needle = args.text.encode('utf-16-le' if args.utf16 else 'utf-8')
        rows = []
        for offset in module.find_bytes(needle)[:args.limit]:
            start, text = module.string_at(offset) if not args.utf16 else (offset, args.text)
            va = module.offset_to_va(offset)
            start_va = module.offset_to_va(start)
            rows.append({'file_offset': hex(offset), 'va': hex(va) if va is not None else None,
                         'string_va': hex(start_va) if start_va is not None else None, 'string': text})
        return {'text': args.text, 'matches': rows}
    if args.command in ('xrefs', 'refs'):
        if args.command == 'refs':
            low, high = args.start, args.end
            targets = [(low, high)]
        elif args.string is not None:
            needle = args.string.encode() + (b'\0' if args.exact else b'')
            targets = []
            for offset in module.find_bytes(needle):
                start, _ = module.string_at(offset)
                va = module.offset_to_va(start if args.exact else offset)
                if va is not None and (not args.exact or start == offset):
                    targets.append((va, va + 1))
        else:
            targets = [(args.va, args.va + 1)]
        refs = []
        for low, high in targets:
            refs += module.code_refs(low, high) + module.data_refs(low, high)
        for row in refs:
            for key in ('va', 'operand_va', 'target'):
                if key in row:
                    row[key] = hex(row[key])
        return {'targets': [hex(t[0]) if t[1] == t[0] + 1 else [hex(t[0]), hex(t[1])] for t in targets],
                'count': len(refs), 'refs': refs[:args.limit]}
    if args.command == 'ptr':
        rows = []
        for i in range(args.count):
            va = args.va + 8 * i
            value = module.pointer(va)
            rows.append({'va': hex(va), 'value': hex(value), 'relocated': va in module.relative,
                         'points_into': (module.segment_for_va(value) or {}).get('index')})
        return {'pointers': rows}
    if args.command == 'dump':
        return {'va': hex(args.va), 'lines': hexdump(module.read(args.va, args.length), args.va)}
    if args.command == 'disasm':
        return {'va': hex(args.va), 'instructions': disassemble(module, args.va, args.length)}
    if args.command == 'find':
        pattern = parse_pattern(args.pattern)
        rows = []
        for segment in (module.executable() if not args.all_segments else module.mapped):
            code = module.data[segment['offset']:segment['offset'] + segment['filesz']]
            for match in pattern.finditer(code):
                rows.append({'va': hex(segment['vaddr'] + match.start()), 'bytes': match.group().hex(' ')})
                if len(rows) >= args.limit:
                    return {'pattern': args.pattern, 'matches': rows, 'truncated': True}
        return {'pattern': args.pattern, 'matches': rows}
    raise ModuleError(f'unknown command {args.command}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('module', type=Path, help='Decrypted module (.prx, .sprx, eboot.bin or ELF)')
    common.add_argument('--output', type=Path, help='Write the JSON here instead of stdout')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('info', parents=[common], help='Hash, ELF type, segments, relocation counts')
    p = sub.add_parser('addr', parents=[common], help='Convert a VA to a file offset, or back')
    p.add_argument('value', type=parse_int)
    p.add_argument('--file-offset', action='store_true', help='The value is a file offset')
    p = sub.add_parser('strings', parents=[common], help='Find text and report its VA')
    p.add_argument('text')
    p.add_argument('--utf16', action='store_true')
    p.add_argument('--limit', type=int, default=50)
    p = sub.add_parser('xrefs', parents=[common], help='Code and relocated pointers that reference a VA or string')
    p.add_argument('va', type=parse_int, nargs='?')
    p.add_argument('--string', help='Reference the string with this text instead of a VA')
    p.add_argument('--exact', action='store_true', help='With --string, match a whole NUL-terminated string')
    p.add_argument('--limit', type=int, default=100)
    p = sub.add_parser('refs', parents=[common], help='References into a VA range [start, end)')
    p.add_argument('start', type=parse_int)
    p.add_argument('end', type=parse_int)
    p.add_argument('--limit', type=int, default=200)
    p = sub.add_parser('ptr', parents=[common], help='Qwords at a VA with relocations applied (vtables)')
    p.add_argument('va', type=parse_int)
    p.add_argument('--count', type=int, default=1)
    p = sub.add_parser('dump', parents=[common], help='Hex dump at a VA')
    p.add_argument('va', type=parse_int)
    p.add_argument('--length', type=int, default=64)
    p = sub.add_parser('disasm', parents=[common], help='Disassemble at a VA (needs capstone)')
    p.add_argument('va', type=parse_int)
    p.add_argument('--length', type=int, default=64)
    p = sub.add_parser('find', parents=[common], help='Byte pattern search with ?? wildcards')
    p.add_argument('pattern')
    p.add_argument('--all-segments', action='store_true', help='Search data segments too')
    p.add_argument('--limit', type=int, default=100)
    args = parser.parse_args(argv)
    if args.command == 'xrefs' and (args.va is None) == (args.string is None):
        parser.error('xrefs needs a VA or --string, not both')
    try:
        result = run(args)
    except (OSError, ModuleError, struct.error) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
