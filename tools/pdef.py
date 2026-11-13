#!/usr/bin/env python3
"""Parse Respawn persistence definitions (.pdef) and compute their layout.

Titanfall 2 stores each player's save as one buffer laid out by
`persistent_player_data_version_*.pdef`. The engine's save buffer has a fixed
size (NorthstarLauncher's PERSISTENCE_MAX_SIZE is 56781 bytes), so check the
layout size before shipping a changed pdef, and compare definitions when
porting a save between builds (the PC v231 layout is 56169 bytes).

Layout rules: bool and enum values are 1 byte, int and float 4, string{N} N
bytes, structs are the sum of their fields, arrays multiply by their count (an
enum-sized array uses the enum's member count). Fields are laid out in
declaration order with no padding.

usage:
  python tools/pdef.py size FILE.pdef [FILE.pdef ...]
  python tools/pdef.py layout FILE.pdef [--depth N] [--find NAME]
  python tools/pdef.py diff OLD.pdef NEW.pdef

`layout` lists each field's byte offset and size; `--find` keeps fields whose
path contains NAME. `diff` reports enums, structs and top-level fields that
were added, removed or resized.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PRIMITIVES = {'int': 4, 'float': 4, 'bool': 1}
STRING = re.compile(r'string\{(\d+)\}$')


class PdefError(ValueError):
    pass


def parse_text(text):
    """Returns (top-level fields, structs, enums); fields are (type, name, count-expr)."""
    top, structs, enums = [], {}, {}
    current_struct = current_enum = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split('//')[0].strip()
        if not line:
            continue
        if line.startswith('$STRUCT_START'):
            current_struct = line.split()[1]
            structs[current_struct] = []
            continue
        if line.startswith('$STRUCT_END'):
            current_struct = None
            continue
        if line.startswith('$ENUM_START'):
            current_enum = line.split()[1]
            enums[current_enum] = []
            continue
        if line.startswith('$ENUM_END'):
            current_enum = None
            continue
        if current_enum:
            enums[current_enum].append(line.split()[0])
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        # Rejoined so "int x[ someEnum ]" reads the same as "int x[someEnum]".
        declaration = ''.join(parts[1:])
        name, count = declaration, None
        if '[' in declaration:
            name, count = declaration.split('[', 1)
            count = count.rstrip(']')
        (structs[current_struct] if current_struct else top).append((parts[0], name, count, number))
    return top, structs, enums


class Pdef:
    def __init__(self, text):
        self.fields, self.structs, self.enums = parse_text(text)
        self._sizes = {}

    @classmethod
    def load(cls, path):
        return cls(Path(path).read_text(encoding='utf-8', errors='replace'))

    def count(self, expression, line=None):
        if expression is None:
            return 1
        if expression.isdigit():
            return int(expression)
        if expression in self.enums:
            return len(self.enums[expression])
        raise PdefError(f'line {line}: unknown array size {expression!r}')

    def type_size(self, kind, line=None, stack=()):
        if kind in PRIMITIVES:
            return PRIMITIVES[kind]
        match = STRING.match(kind)
        if match:
            return int(match.group(1))
        if kind in self.enums:
            return 1
        if kind in self.structs:
            if kind in stack:
                raise PdefError(f'struct {kind} contains itself')
            if kind not in self._sizes:
                self._sizes[kind] = sum(self.type_size(t, n, stack + (kind,)) * self.count(c, n)
                                        for t, _, c, n in self.structs[kind])
            return self._sizes[kind]
        raise PdefError(f'line {line}: unknown type {kind!r}')

    def size(self):
        return sum(self.type_size(t, n) * self.count(c, n) for t, _, c, n in self.fields)

    def layout(self, depth=0):
        rows = []

        def walk(fields, base, prefix, level):
            offset = base
            for kind, name, count, line in fields:
                element = self.type_size(kind, line)
                total = element * self.count(count, line)
                path = prefix + name
                rows.append({'offset': offset, 'size': total, 'type': kind, 'path': path,
                             'count': self.count(count, line) if count else None})
                if level < depth and kind in self.structs:
                    if count is None:
                        walk(self.structs[kind], offset, path + '.', level + 1)
                    else:
                        walk(self.structs[kind], offset, f'{path}[0].', level + 1)
                offset += total
        walk(self.fields, 0, '', 0)
        return rows


def diff(old, new):
    def sizes(pdef, names):
        return {name: pdef.type_size(name) for name in names}
    report = {'size': {'old': old.size(), 'new': new.size()}}
    report['size']['delta'] = report['size']['new'] - report['size']['old']
    old_enums, new_enums = {k: len(v) for k, v in old.enums.items()}, {k: len(v) for k, v in new.enums.items()}
    report['enums'] = _compare(old_enums, new_enums)
    report['structs'] = _compare(sizes(old, old.structs), sizes(new, new.structs))
    old_top = {name: old.type_size(t) * old.count(c) for t, name, c, _ in old.fields}
    new_top = {name: new.type_size(t) * new.count(c) for t, name, c, _ in new.fields}
    report['fields'] = _compare(old_top, new_top)
    return report


def _compare(old, new):
    return {'added': sorted(set(new) - set(old)), 'removed': sorted(set(old) - set(new)),
            'changed': {k: {'old': old[k], 'new': new[k]} for k in sorted(set(old) & set(new)) if old[k] != new[k]}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--output', type=Path, help='Write the JSON here instead of stdout')
    sub = parser.add_subparsers(dest='command', required=True)
    p_size = sub.add_parser('size', parents=[common], help='Total serialized size of each file')
    p_size.add_argument('files', nargs='+', type=Path)
    p_layout = sub.add_parser('layout', parents=[common], help='Byte offset and size of each field')
    p_layout.add_argument('file', type=Path)
    p_layout.add_argument('--depth', type=int, default=0, help='Expand nested structs this many levels')
    p_layout.add_argument('--find', help='Keep fields whose path contains this text (case-insensitive)')
    p_diff = sub.add_parser('diff', parents=[common], help='Compare two definitions')
    p_diff.add_argument('old', type=Path)
    p_diff.add_argument('new', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'size':
            result = {'files': [{'path': str(f), 'size': Pdef.load(f).size()} for f in args.files]}
        elif args.command == 'layout':
            pdef = Pdef.load(args.file)
            rows = pdef.layout(args.depth)
            if args.find:
                rows = [r for r in rows if args.find.lower() in r['path'].lower()]
            result = {'path': str(args.file), 'size': pdef.size(), 'fields': rows}
        else:
            result = diff(Pdef.load(args.old), Pdef.load(args.new))
    except (OSError, PdefError) as error:
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
