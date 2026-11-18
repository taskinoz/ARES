"""Bounded syntax inspection of explicitly supplied Source sound definitions.

Copyright (C) 2026 MRVN-Radiant contributors. GPL-2.0-or-later.
No audio extraction, conversion or playback certification.
"""
import hashlib
import re

TOKEN = re.compile(r'\s+|//[^\n]*|/\*.*?\*/|"((?:\\.|[^"\\])*)"|([{}])', re.S)


def inspect_sound_definitions(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= 4*1024*1024 or b'\0' in data:
        raise ValueError('invalid or oversized sound definition source')
    text = data.decode('utf-8-sig')
    tokens=[];offset=0
    for match in TOKEN.finditer(text):
        if match.start() != offset:
            raise ValueError('unsupported unquoted sound definition syntax')
        offset=match.end()
        if match[1] is not None:
            tokens.append(('value',re.sub(r'\\(["\\])',r'\1',match[1])))
        elif match[2]:
            tokens.append(match[2])
        if len(tokens)>200000:
            raise ValueError('oversized sound definition token stream')
    if offset!=len(text):
        raise ValueError('unterminated sound definition string/comment')
    index=0
    def pairs(depth=0):
        nonlocal index
        if depth>16:
            raise ValueError('sound definition nesting exceeds 16')
        result=[]
        while index<len(tokens) and tokens[index]!='}':
            key=tokens[index];index+=1
            if not isinstance(key,tuple) or index==len(tokens):
                raise ValueError('incomplete sound definition pair')
            value=tokens[index];index+=1
            if value=='{':
                value=pairs(depth+1)
                if index==len(tokens) or tokens[index]!='}':
                    raise ValueError('unterminated sound definition block')
                index+=1
            elif isinstance(value,tuple):value=value[1]
            else:raise ValueError('invalid sound definition value')
            result.append((key[1],value))
        return result
    roots=pairs()
    if index!=len(tokens) or not roots:
        raise ValueError('unmatched or empty sound definitions')
    names=set();waves=[]
    def collect(rows):
        for key,value in rows:
            if isinstance(value,list):collect(value)
            elif key.casefold()=='wave':waves.append(value)
    for name,body in roots:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,255}',name) or not isinstance(body,list):
            raise ValueError('unsupported sound alias declaration')
        if name.casefold() in names:
            raise ValueError('duplicate sound alias declaration')
        names.add(name.casefold());collect(body)
    if not waves or any(not wave or '\n' in wave or '\r' in wave for wave in waves):
        raise ValueError('missing or empty wave references')
    return {'sha256':hashlib.sha256(data).hexdigest(),'alias_count':len(roots),
            'wave_reference_count':len(waves),'unique_wave_count':len(set(waves)),
            'scope':'Syntax and references only; audio payloads and playback unverified'}


def repair_hardpoint_definitions(data):
    """Repair only the known commented brace in the supplied Hardpoint file."""
    if not isinstance(data, bytes) or not 0 < len(data) <= 4*1024*1024:
        raise ValueError('invalid or oversized Hardpoint sound definition source')
    original = hashlib.sha256(data).hexdigest()
    try:
        info = inspect_sound_definitions(data)
        info.update(base_sha256=original, repaired=False)
        return data, info
    except ValueError:
        pass
    first = b'"diag_hp_mcor_bish_generalpurpose_02"'
    last = b'"diag_hp_mcor_bish_generalpurpose_03"'
    if data.count(first) != 1 or data.count(last) != 1:
        raise ValueError('unsupported malformed Hardpoint sound definitions')
    start, end = data.index(first), data.index(last)
    if end <= start:
        raise ValueError('unsupported Hardpoint alias order')
    region = data[start:end]
    close = re.compile(rb'(?m)^([ \t]*)//[ \t]*\}([ \t]*\r?)$')
    if (len(close.findall(region)) != 1 or
            b'dialogue/hardpoints/diag_hp_mcor_bish_generalpurpose_02.wav' not in region):
        raise ValueError('unsupported Hardpoint missing-brace signature')
    fixed = data[:start] + close.sub(lambda m: m[1]+b'}'+m[2], region) + data[end:]
    info = inspect_sound_definitions(fixed)
    info.update(base_sha256=original, repaired=True)
    return fixed, info


def load_sound_sources(paths, repair_hardpoint=False, mode=None):
    from pathlib import Path
    if type(repair_hardpoint) is not bool or repair_hardpoint and mode != 'cp':
        raise ValueError('Hardpoint sound repair requires explicit cp mode')
    paths = paths or []
    if not isinstance(paths, list) or len(paths) > 32:
        raise ValueError('at most 32 explicit sound source files are supported')
    results=[];seen=set();total=0
    for raw in paths:
        path=Path(raw)
        if (path.is_symlink() or not path.is_file() or not re.fullmatch(r'[A-Za-z0-9_]{1,128}\.txt',path.name)
                or not 0 < path.stat().st_size <= 4*1024*1024 or path.name.casefold() in seen):
            raise ValueError('missing, linked, duplicate or unsupported sound source')
        seen.add(path.name.casefold())
        data=path.read_bytes();total+=len(data)
        if total>16*1024*1024:
            raise ValueError('sound sources exceed 16 MiB')
        if repair_hardpoint and path.name.casefold()=='mp_hardpoints.txt':
            payload,info=repair_hardpoint_definitions(data)
        else:
            info=inspect_sound_definitions(data);payload=data
            info.update(base_sha256=info['sha256'],repaired=False)
        results.append((path.name,payload,info))
    if repair_hardpoint and 'mp_hardpoints.txt' not in seen:
        raise ValueError('Hardpoint sound repair requires supplied mp_hardpoints.txt')
    return results
