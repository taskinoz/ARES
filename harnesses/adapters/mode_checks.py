"""Explicit mode and optional native hardpoint-initialization checks.

Copyright (C) 2026 MRVN-Radiant contributors. GPL-2.0-or-later.
Initialization is not a capture, score, respawn or multiplayer acceptance test.
"""
import re


def validate_mode(probe):
    if probe is None:
        return None
    if not isinstance(probe, dict) or set(probe) - {'mode', 'hardpoints'}:
        raise ValueError('mode_check must contain mode and optional hardpoints')
    mode=probe.get('mode')
    if not isinstance(mode,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}',mode):
        raise ValueError('mode_check mode must be a simple lowercase identifier')
    if 'hardpoints' in probe and (type(probe['hardpoints']) is not int or not 1 <= probe['hardpoints'] <= 32):
        raise ValueError('mode_check hardpoints must be within [1, 32]')
    if 'hardpoints' in probe and mode != 'cp':
        raise ValueError('hardpoint initialization checks currently require cp mode')
    return probe


def mode_script(probe, capture=False):
    if validate_mode(probe) is None:
        return ''
    script='printl("[ARES] MODE actual="+GameRules.GetGameMode()+" gametype="+GAMETYPE);'
    if 'hardpoints' in probe:
        script+='''
local points=GetEntArrayByClass_Expensive("info_hardpoint");
printl("[ARES] MODE_OBJECTIVES count="+points.len()+" initialized="+("hardpointModeInitialized" in level ? level.hardpointModeInitialized : false));
foreach(i,p in points) printl("[ARES] MODE_HARDPOINT "+i+" id="+p.GetHardpointID()+" terminal="+IsValid(p.GetTerminal()));
'''
    return script.replace('printl("[ARES] ', '::ARES_ModeEvents.append("') if capture else script


def mode_errors(events,probe):
    if validate_mode(probe) is None:
        return []
    errors=[]
    rows=[e for e in events if e.startswith('MODE ')]
    expected=f'MODE actual={probe["mode"]} gametype={probe["mode"]}'
    if rows != [expected]:
        errors.append(f'MODE: expected {probe["mode"]}, observed {rows}')
    if 'hardpoints' not in probe:
        return errors
    count=probe['hardpoints']
    rows=[e for e in events if e.startswith('MODE_OBJECTIVES ')]
    if rows != [f'MODE_OBJECTIVES count={count} initialized=true']:
        errors.append(f'MODE: expected {count} initialized hardpoints, observed {rows}')
    rows=[e for e in events if e.startswith('MODE_HARDPOINT ')]
    values=[]
    for row in rows:
        match=re.fullmatch(r'MODE_HARDPOINT (\d+) id=(\d+) terminal=true',row)
        if match:
            values.append(tuple(map(int,match.groups())))
    if (len(rows)!=count or len(values)!=count or sorted(i for i,_ in values)!=list(range(count)) or
            sorted(j for _,j in values)!=list(range(count))):
        errors.append('MODE: missing, duplicate, invalid hardpoint IDs or terminals')
    return errors
