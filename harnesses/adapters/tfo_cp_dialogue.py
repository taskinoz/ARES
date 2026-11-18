"""Original bounded transform for Core135's duplicate Hardpoint dialogue load.

Copyright (C) 2026 MRVN-Radiant contributors. GPL-2.0-or-later.
Contains no game script. Callers stage the result only in an owned mod and must
label the runtime compatibility intervention in their report.
"""
import hashlib
import re


def patch_dialogue(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= 2*1024*1024:
        raise ValueError('unsupported game_state_dialog source size')
    data.decode('utf-8')
    if b'\0' in data:
        raise ValueError('NUL in Hardpoint dialogue source')
    route = re.compile(rb'IncludeScript\(\s*"_gamemode_cp_dialogue"\s*\)')
    shared = re.compile(rb'GameMode_RunSharedDialogueScripts\(\s*GAMETYPE\s*\)')
    block = re.compile(rb'(case ATTRITION:[ \t]*(\r?\n))([ \t]*)case CAPTURE_THE_FLAG:')
    if (len(route.findall(data)) != 1 or len(shared.findall(data)) != 1 or
            len(block.findall(data)) != 1 or re.search(rb'case\s+CAPTURE_POINT\s*:', data)):
        raise ValueError('unsupported or already fixed Hardpoint dialogue routing')
    patched = block.sub(lambda m: m[1]+m[3]+b'case CAPTURE_POINT:'+m[2]+m[3]+b'case CAPTURE_THE_FLAG:', data)
    names = [b'MFDPFriendlyPilotsLeftTwoMarkedPlayer', b'MFDPFriendlyPilotsLeftTwo',
             b'MFDPEnemyPilotsLeftTwo', b'MFDPBothTeamsPilotsLeftOne', b'MFDPEnemyMarkIsAlone']
    calls = re.compile(rb'(?m)^([ \t]*)(AddVDULineForBish\([ \t]*"(' + b'|'.join(names) + rb')"[^\r\n]*)(\r?)$')
    found = list(calls.finditer(patched))
    if found and (len(found) != 5 or {m[3] for m in found} != set(names)):
        raise ValueError('unsupported partial MFDP conversation registration')
    patched = calls.sub(lambda m: m[1]+b'if ( GAMETYPE == MARKED_FOR_DEATH_PRO )'+m[4]+b'\n'+m[1]+b'\t'+m[2]+m[4], patched)
    return patched, {'kind':'tfo_cp_dialogue', 'base_sha256':hashlib.sha256(data).hexdigest(),
                     'patched_sha256':hashlib.sha256(patched).hexdigest(),
                     'guarded_mfdp_conversations':len(found),
                     'scope':'Avoid duplicate CP dialogue load and unrelated MFDP registration; owned temporary mod only'}


def validate_compat(checks):
    enabled = checks.get('tfo_cp_dialogue_compat', False)
    if type(enabled) is not bool:
        raise ValueError('tfo_cp_dialogue_compat must be a boolean')
    mode = checks.get('mode_check')
    if enabled and (not isinstance(mode, dict) or mode.get('mode') != 'cp'):
        raise ValueError('Hardpoint dialogue compatibility requires explicit mode_check cp')
    return enabled
