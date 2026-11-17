"""A sampled native grunt route; not general AI, combat or navigation parity.

Copyright (C) 2026 MRVN-Radiant contributors. GPL-2.0-or-later.
"""
import json
import math
import re


def validate_navigation(probe):
    if probe is None:
        return None
    if not isinstance(probe, dict) or set(probe) - {
            'start', 'goal', 'nodes', 'samples', 'wait', 'radius', 'floor_z', 'forbidden_box'}:
        raise ValueError('unsupported navigation_probe fields')
    def xyz(value):
        return (isinstance(value, list) and len(value) == 3 and
                all(type(v) in (int, float) and math.isfinite(v) and abs(v) <= 16384 for v in value))
    if not xyz(probe.get('start')) or not xyz(probe.get('goal')):
        raise ValueError('navigation start/goal must be finite XYZ within world bounds')
    if math.dist(probe['start'], probe['goal']) < 64:
        raise ValueError('navigation start and goal must be at least 64 units apart')
    for key, default, low, high in [('nodes', None, 2, 32767), ('samples', 12, 5, 30)]:
        if type(probe.get(key, default)) is not int or not low <= probe.get(key, default) <= high:
            raise ValueError(f'navigation {key} outside bounds')
    for key, default, low, high in [('wait', 1, .25, 2), ('radius', 24, 1, 32),
                                   ('floor_z', None, -16384, 16384)]:
        value = probe.get(key, default)
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'navigation {key} outside bounds')
    if 'forbidden_box' in probe:
        box = probe['forbidden_box']
        if (not isinstance(box, list) or len(box) != 2 or not all(xyz(p) for p in box) or
                any(a >= b for a, b in zip(*box))):
            raise ValueError('navigation forbidden_box requires ordered finite min/max XYZ')
    return probe


def navigation_script(probe):
    if validate_navigation(probe) is None:
        return ''
    config = [probe['start'], probe['goal'], probe.get('samples', 12), probe.get('wait', 1), probe.get('radius', 24)]
    return r'''
::ARES_NavigationEvents <- []
::ARES_NavigationDone <- false
function ARES_RunNavigation(player) {
 local npc=null
 try {
  local ready=false
  for(local i=0;i<90;i++) {
   if(GetGameState()==eGameState.Playing) { ready=true; break }
   wait 1
  }
  if(!ready) throw "match did not reach Playing"
  local config=%CONFIG%
  local start=Vector(config[0][0],config[0][1],config[0][2])
  local goal=Vector(config[1][0],config[1][1],config[1][2])
  local count=GetNodeCount()
  local neighbors=count>0 ? GetNeighborNodes(0,32,HULL_HUMAN).len() : 0
  ARES_NavigationEvents.append("NAVIGATION CONTEXT nodes="+count+" neighbors="+neighbors)
  SetEnableNPCs(true)
  npc=SpawnGrunt(player.GetTeam(),"ares_navigation",start,Vector(0,0,0),false,"mp_weapon_rspn101")
  npc.StayCloseToSquad(false)
  npc.DisableStarts()
  wait 1
  ARES_NavigationEvents.append("NAVIGATION START valid="+IsValid(npc)+" alive="+IsAlive(npc)+" origin="+npc.GetOrigin())
  thread SendAIToAssaultPoint(npc,goal,Vector(0,0,0),config[4])
  for(local i=0;i<config[2];i++) {
   wait config[3]
   ARES_NavigationEvents.append("NAVIGATION SAMPLE "+i+" valid="+IsValid(npc)+" alive="+IsAlive(npc)+" origin="+npc.GetOrigin())
  }
 } catch(e) { ARES_NavigationEvents.append("NAVIGATION ERROR "+e) }
 if(IsValid(npc)) npc.Destroy()
 ::ARES_NavigationDone=true
}
'''.replace('%CONFIG%', json.dumps(config, allow_nan=False))


def navigation_errors(events, probe):
    if validate_navigation(probe) is None:
        return []
    errors = []
    rows = [e for e in events if e.startswith('NAVIGATION ')]
    samples = probe.get('samples', 12)
    if len(rows) != samples + 2:
        errors.append('NAVIGATION: unexpected, missing or duplicate events')
    context = [e for e in rows if e.startswith('NAVIGATION CONTEXT ')]
    match = re.fullmatch(r'NAVIGATION CONTEXT nodes=(\d+) neighbors=(\d+)', context[0]) if len(context) == 1 else None
    if not match or int(match[1]) != probe['nodes'] or not 2 <= int(match[2]) <= min(probe['nodes'], 32):
        errors.append('NAVIGATION: missing or unexpected node connectivity')
    positions = []
    for label in ['START'] + [f'SAMPLE {i}' for i in range(samples)]:
        prefix = f'NAVIGATION {label} '
        found = [e[len(prefix):] for e in rows if e.startswith(prefix)]
        match = re.fullmatch(r'valid=true alive=true origin=\(vector : \(([^)]+)\)\)', found[0]) if len(found) == 1 else None
        try:
            xyz = [float(v.strip()) for v in match[1].split(',')] if match else []
            if len(xyz) != 3 or not all(math.isfinite(v) and abs(v) <= 16384 for v in xyz):
                raise ValueError()
            if abs(xyz[2] - probe['floor_z']) > 2:
                raise ValueError()
            if label == 'START' and math.dist(xyz, probe['start']) > 2:
                raise ValueError()
            if 'forbidden_box' in probe and all(a <= v <= b for a, v, b in zip(probe['forbidden_box'][0], xyz, probe['forbidden_box'][1])):
                raise ValueError()
            positions.append(xyz)
        except ValueError:
            errors.append(f'NAVIGATION {label}: missing, duplicate, dead or invalid sampled pose')
    if len(positions) == samples + 1:
        if any(math.dist(p, probe['goal']) > probe.get('radius', 24) for p in positions[-2:]):
            errors.append('NAVIGATION: final two samples did not reach/hold goal')
    return errors
