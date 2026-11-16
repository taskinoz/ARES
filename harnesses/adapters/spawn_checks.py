"""Validate one actual initial player spawn before any harness repositioning.

Copyright (C) 2026 MRVN-Radiant contributors. GPL-2.0-or-later.
"""
import math
import re


def validate_spawn(probe):
    if probe is None:
        return None
    if not isinstance(probe, dict) or set(probe) - {'origins', 'tolerance', 'team'}:
        raise ValueError('spawn_probe must contain origins, optional tolerance and team')
    origins = probe.get('origins')
    if not isinstance(origins, list) or not 1 <= len(origins) <= 64 or any(
            not isinstance(row, list) or len(row) != 3 or any(
                type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 16384
                for v in row) for row in origins):
        raise ValueError('spawn_probe origins must contain 1..64 finite XYZ rows within world bounds')
    tolerance = probe.get('tolerance', 4)
    if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or not .01 <= tolerance <= 64:
        raise ValueError('spawn_probe tolerance must be within [0.01, 64]')
    if 'team' in probe and (type(probe['team']) is not int or probe['team'] not in (2, 3)):
        raise ValueError('spawn_probe team must be 2 or 3')
    return probe


def spawn_script(probe):
    if validate_spawn(probe) is None:
        return ''
    return 'printl("[ARES] SPAWN alive="+IsAlive(player)+" team="+player.GetTeam()+" origin="+player.GetOrigin());'


def spawn_errors(events, probe):
    if validate_spawn(probe) is None:
        return []
    rows = [e for e in events if e.startswith('SPAWN ')]
    if len(rows) != 1:
        return ['SPAWN: expected exactly one initial spawn result']
    match = re.fullmatch(r'SPAWN alive=true team=(\d+) origin=\(vector : \(([^)]+)\)\)', rows[0])
    try:
        xyz = [float(v.strip()) for v in match[2].split(',')] if match else []
        valid = (match and len(xyz) == 3 and all(math.isfinite(v) for v in xyz) and
                 int(match[1]) in (2, 3) and ('team' not in probe or int(match[1]) == probe['team']) and
                 any(all(abs(a-b) <= probe.get('tolerance', 4) for a, b in zip(xyz, origin))
                     for origin in probe['origins']))
    except ValueError:
        valid = False
    return [] if valid else [f'SPAWN: expected alive at one of {probe["origins"]}; observed {rows[0]}']
