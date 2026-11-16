"""Native atlas NPC support probes, with explicit per-runtime settings names.

Copyright (C) 2026 MRVN-Radiant contributors. GPL-2.0-or-later.
Sampled standing support is not titan piloting, navigation or combat acceptance.
"""
import json
import math
import re


SETTINGS = {'r1': 'titan_atlas', 'tfo': 'titan_atlas_tier0'}


def validate_titans(rows):
    if not isinstance(rows, list) or len(rows) > 8:
        raise ValueError('titans must contain at most eight probes')
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'origin', 'team', 'floor_z', 'wait', 'samples', 'tolerance', 'max_translation'}:
            raise ValueError('unsupported titan probe fields')
        origin = row.get('origin')
        if not isinstance(origin, list) or len(origin) != 3 or any(
                type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 16384 for v in origin):
            raise ValueError('titan origin must be finite XYZ within world bounds')
        if type(row.get('team')) is not int or row['team'] not in (2, 3):
            raise ValueError('titan team must be 2 or 3')
        if type(row.get('samples', 5)) is not int or not 2 <= row.get('samples', 5) <= 10:
            raise ValueError('titan samples must be within [2, 10]')
        for key, default, low, high in [('floor_z', None, -16384, 16384), ('wait', 1, .25, 2),
                                       ('tolerance', 1, .01, 8), ('max_translation', .25, .01, 8)]:
            value = row.get(key, default)
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'titan {key} outside [{low}, {high}]')
    return rows


VECTOR = r'\(vector : \(([^)]+)\)\)'
SAMPLE = re.compile(r'valid=true alive=true titan=true origin=' + VECTOR + r' velocity=' + VECTOR +
                    r' mins=' + VECTOR + r' maxs=' + VECTOR)


def titan_errors(events, rows):
    errors = []
    for index, row in enumerate(validate_titans(rows)):
        positions = []
        if any(e.startswith(f'TITAN {index} ERROR') for e in events):
            errors.append(f'TITAN {index}: native script error')
        if sum(e.startswith(f'TITAN {index} SAMPLE ') for e in events) != row.get('samples', 5):
            errors.append(f'TITAN {index}: unexpected sample count')
        for sample in range(row.get('samples', 5)):
            prefix = f'TITAN {index} SAMPLE {sample} '
            values = [e[len(prefix):] for e in events if e.startswith(prefix)]
            match = SAMPLE.fullmatch(values[0]) if len(values) == 1 else None
            valid = False
            if match:
                try:
                    origin, velocity, mins, maxs = [[float(v.strip()) for v in g.split(',')] for g in match.groups()]
                    valid = (all(len(v) == 3 and all(math.isfinite(n) for n in v) for v in (origin, velocity, mins, maxs)) and
                             all(a < b for a,b in zip(mins,maxs)) and
                             abs(origin[2] + mins[2] - row['floor_z']) <= row.get('tolerance', 1) and
                             all(abs(origin[a] - row['origin'][a]) <= row.get('tolerance', 1) for a in (0,1)))
                    if valid:
                        positions.append(origin)
                except ValueError:
                    pass
            if not valid:
                errors.append(f'TITAN {index} SAMPLE {sample}: missing, duplicate, invalid, dead or unsupported sample')
        if any(math.dist(a,b) > row.get('max_translation', .25) for a in positions for b in positions):
            errors.append(f'TITAN {index}: sampled translation exceeds {row.get("max_translation", .25)}')
    return errors


def titan_script(rows, runtime):
    if runtime not in SETTINGS:
        raise ValueError('unsupported titan runtime')
    rows = validate_titans(rows)
    probes = [[r['origin'], r['team'], r.get('wait',1), r.get('samples',5)] for r in rows]
    return r'''
::ARES_TitanProbes <- %PROBES%
::ARES_TitanEvents <- []
::ARES_TitanDone <- false
function ARES_RunTitans() {
 foreach(i,probe in ARES_TitanProbes) {
  local titan=null
  try {
   local template=CreateSpawnNPCTitanTemplate(probe[1],"%SETTINGS%")
   template.origin=Vector(probe[0][0],probe[0][1],probe[0][2])
   template.angles=Vector(0,0,0)
   template.weapon="mp_titanweapon_xo16"
   template.title="ARES collision probe"
   titan=SpawnNPCTitan(template)
   for(local sample=0;sample<probe[3];sample++) {
    wait probe[2]
    ARES_TitanEvents.append("TITAN "+i+" SAMPLE "+sample+" valid="+IsValid(titan)+" alive="+IsAlive(titan)+" titan="+titan.IsTitan()+" origin="+titan.GetOrigin()+" velocity="+titan.GetVelocity()+" mins="+titan.GetBoundingMins()+" maxs="+titan.GetBoundingMaxs())
   }
  } catch(e) { ARES_TitanEvents.append("TITAN "+i+" ERROR "+e) }
  if(IsValid(titan)) titan.Destroy()
 }
 ::ARES_TitanDone = true
}
'''.replace('%PROBES%', json.dumps(probes, allow_nan=False)).replace('%SETTINGS%', SETTINGS[runtime])
