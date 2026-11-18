"""Bounded native trigger touch probes shared by the two v29 runtimes.

Controlled player repositioning tests authored trigger volumes and output delivery;
it does not establish normal movement, objective or multiplayer correctness.

Copyright (C) 2026 MRVN-Radiant contributors. GPL-2.0-or-later.
"""
import json
import math
import re


def validate_triggers(rows):
    if not isinstance(rows, list) or len(rows) > 16:
        raise ValueError('triggers must be a list of at most 16 probes')
    names = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'targetname', 'points', 'counts', 'wait', 'tolerance'}:
            raise ValueError('unsupported trigger probe fields')
        name = row.get('targetname')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,128}', name) or name in names:
            raise ValueError('trigger targetnames must be unique simple names')
        names.add(name)
        points, counts = row.get('points'), row.get('counts')
        if not isinstance(points, list) or not 2 <= len(points) <= 16 or any(
                not isinstance(p, list) or len(p) != 3 or any(
                    type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 16384 for v in p) for p in points):
            raise ValueError('trigger points must be 2..16 finite XYZ rows within world bounds')
        if not isinstance(counts, list) or len(counts) != len(points) or any(
                not isinstance(p, list) or len(p) != 2 or any(type(v) is not int or not 0 <= v <= 1024 for v in p)
                for p in counts):
            raise ValueError('trigger counts must give cumulative [start, end] for each point')
        if any(counts[i][j] < counts[i-1][j] for i in range(1, len(counts)) for j in (0, 1)):
            raise ValueError('trigger counts must be cumulative')
        for key, default, low, high in [('wait', 1, .1, 5), ('tolerance', 16, .01, 64)]:
            value = row.get(key, default)
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'trigger {key} outside [{low}, {high}]')
    return rows


def trigger_errors(events, rows):
    errors = []
    for i, row in enumerate(validate_triggers(rows)):
        for step, (point, expected) in enumerate(zip(row['points'], row['counts'])):
            prefix = f'TRIGGER {i} STEP {step} '
            observed = [e[len(prefix):] for e in events if e.startswith(prefix)]
            valid = len(observed) == 1
            match = re.fullmatch(r'start=(\d+) end=(\d+) alive=true origin=\(vector : \(([^)]+)\)\)', observed[0]) if valid else None
            try:
                xyz = [float(v.strip()) for v in match[3].split(',')] if match else []
                valid = bool(match and [int(match[1]), int(match[2])] == expected and len(xyz) == 3 and
                             all(math.isfinite(v) and abs(v-p) <= row.get('tolerance', 16) for v,p in zip(xyz,point)))
            except ValueError:
                valid = False
            if not valid:
                errors.append(f'TRIGGER {i} STEP {step}: expected counts {expected}, alive and pose near {point}; observed {observed}')
    return errors


def trigger_script(rows):
    rows = validate_triggers(rows)
    probes = [[r['targetname'], r['points'], r.get('wait', 1)] for r in rows]
    return r'''
::ARES_TriggerProbes <- %PROBES%
::ARES_TriggerEvents <- []
::ARES_TriggerCounters <- []
::ARES_TriggerDone <- false
function ARES_TriggerStart(t,e,c,v) {
 if(IsValid(e) && e.IsPlayer()) foreach(row in ARES_TriggerCounters) if(row[0] == t) row[1]++
}
function ARES_TriggerEnd(t,e,c,v) {
 if(IsValid(e) && e.IsPlayer()) foreach(row in ARES_TriggerCounters) if(row[0] == t) row[2]++
}
function ARES_RunTriggers(player) {
 foreach(i,probe in ARES_TriggerProbes) {
  local t=GetEnt(probe[0])
  if(!IsValid(t)) { ARES_TriggerEvents.append("TRIGGER " + i + " MISSING"); continue }
  local row=[t,0,0]
  ARES_TriggerCounters.append(row)
  t.ConnectOutput("OnStartTouch",ARES_TriggerStart)
  t.ConnectOutput("OnEndTouch",ARES_TriggerEnd)
  foreach(step,point in probe[1]) {
   player.SetOrigin(Vector(point[0],point[1],point[2]))
   player.SetVelocity(Vector(0,0,0))
   wait probe[2]
   ARES_TriggerEvents.append("TRIGGER " + i + " STEP " + step + " start="+row[1]+" end="+row[2]+" alive="+IsAlive(player)+" origin="+player.GetOrigin())
  }
 }
 ::ARES_TriggerDone = true
}
'''.replace('%PROBES%', json.dumps(probes, allow_nan=False))
