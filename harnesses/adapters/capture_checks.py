"""Natural neutral Hardpoint capture and sampled team-score acceptance.

Copyright (C) 2026 MRVN-Radiant contributors. GPL-2.0-or-later.
Uses one initial placement; never sets match state, objective ownership or score.
Not a contested/recapture, combat, respawn, network or AI-navigation test.
"""
import json
import math
import re


def validate_capture(probe, mode=None):
    if probe is None:
        return None
    if mode!='cp' or not isinstance(probe,dict) or set(probe)-{'targetname','origin','wait','samples','ready_wait','min_score','tolerance'}:
        raise ValueError('cp_capture requires explicit cp mode and supported fields')
    name=probe.get('targetname')
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,128}',name):
        raise ValueError('cp_capture targetname must be a simple name')
    origin=probe.get('origin')
    if not isinstance(origin,list) or len(origin)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>16384 for v in origin):
        raise ValueError('cp_capture origin must be finite XYZ within world bounds')
    for key,default,low,high in [('samples',10,2,20),('min_score',1,1,100)]:
        value=probe.get(key,default)
        if type(value) is not int or not low<=value<=high:
            raise ValueError(f'cp_capture {key} outside [{low}, {high}]')
    for key,default,low,high in [('wait',2,.25,5),('ready_wait',30,0,30),('tolerance',4,.01,16)]:
        value=probe.get(key,default)
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'cp_capture {key} outside [{low}, {high}]')
    if probe.get('samples',10)*probe.get('wait',2)>60:
        raise ValueError('cp_capture sampling exceeds 60 seconds')
    return probe


def capture_errors(events,probe):
    if probe is None:return []
    validate_capture(probe,'cp')
    errors=[]
    ready=[e for e in events if e.startswith('CAPTURE_READY ')]
    if len(ready)!=1 or not re.fullmatch(r'CAPTURE_READY state=(\d+) playing=\1',ready[0]):
        errors.append('CAPTURE: match did not naturally reach Playing')
    before=[e for e in events if e.startswith('CAPTURE_BEFORE ')]
    match=re.fullmatch(r'CAPTURE_BEFORE owner=0 playerTeam=([23]) progress=(\S+) score=(\d+)',before[0]) if len(before)==1 else None
    team,score=None,None
    try:
        if match and math.isfinite(float(match[2])) and abs(float(match[2]))<.0001:
            team,score=int(match[1]),int(match[3])
    except ValueError:pass
    if team is None:errors.append('CAPTURE: expected a neutral starting objective')
    rows=[e for e in events if e.startswith('CAPTURE ')]
    if len(rows)!=probe.get('samples',10):errors.append('CAPTURE: wrong sample count')
    scores=[];owners=[]
    pattern=re.compile(r'CAPTURE (\d+) owner=(\d+) playerTeam=([23]) progress=(\S+) score=(\d+) alive=true touching=true origin=\(vector : \(([^)]+)\)\)')
    for index in range(probe.get('samples',10)):
        matches=[m for e in rows if (m:=pattern.fullmatch(e)) and int(m[1])==index]
        valid=False
        if len(matches)==1:
            m=matches[0]
            try:
                owner,actor,progress,value=int(m[2]),int(m[3]),float(m[4]),int(m[5])
                xyz=[float(v.strip()) for v in m[6].split(',')]
                expected_progress=-1 if team==2 else 1
                valid=(actor==team and owner in (0,team) and math.isfinite(progress) and len(xyz)==3 and
                       all(math.isfinite(v) and abs(v-p)<=probe.get('tolerance',4) for v,p in zip(xyz,probe['origin'])) and
                       (abs(progress)<.0001 if owner==0 else abs(progress-expected_progress)<.0001))
                if valid:scores.append(value);owners.append(owner)
            except ValueError:pass
        if not valid:errors.append(f'CAPTURE {index}: missing/duplicate, dead, outside trigger or invalid pose/ownership')
    if any(e.startswith('CAPTURE_ERROR') for e in events):errors.append('CAPTURE: native script error')
    if team in owners and any(owner!=team for owner in owners[owners.index(team):]):
        errors.append('CAPTURE: owned objective was lost during the hold')
    if scores and score is not None:
        if any(b<a for a,b in zip([score]+scores,scores)):errors.append('CAPTURE: team score decreased')
        if owners[-1]!=team or scores[-1]-score<probe.get('min_score',1):errors.append('CAPTURE: ownership and required score gain not reached')
    return errors


def capture_script(probe):
    if probe is not None:validate_capture(probe,'cp')
    config=[] if probe is None else [probe['targetname'],probe['origin'],probe.get('wait',2),probe.get('samples',10),probe.get('ready_wait',30)]
    return r'''
::ARES_CaptureConfig <- %CONFIG%
::ARES_CaptureEvents <- []
::ARES_CaptureDone <- false
function ARES_RunCapture(player) {
 if(!ARES_CaptureConfig.len()) { ::ARES_CaptureDone=true;return }
 try {
  local cfg=ARES_CaptureConfig
  local stop=Time()+cfg[4]
  while(GetGameState()!=eGameState.Playing && Time()<stop) wait 1
  if(GetGameState()!=eGameState.Playing) {
   ARES_CaptureEvents.append("CAPTURE_NOT_PLAYING")
   ::ARES_CaptureDone=true;return
  }
  ARES_CaptureEvents.append("CAPTURE_READY state="+GetGameState()+" playing="+eGameState.Playing)
  local hp=GetEnt(cfg[0])
  if(!IsValid(hp)) { ARES_CaptureEvents.append("CAPTURE_ERROR missing target");::ARES_CaptureDone=true;return }
  ARES_CaptureEvents.append("CAPTURE_BEFORE owner="+hp.GetTeam()+" playerTeam="+player.GetTeam()+" progress="+hp.GetHardpointProgressRefPoint()+" score="+GameRules.GetTeamScore(player.GetTeam()))
  player.SetOrigin(Vector(cfg[1][0],cfg[1][1],cfg[1][2]))
  player.SetVelocity(Vector(0,0,0))
  for(local i=0;i<cfg[3];i++) {
   wait cfg[2]
   ARES_CaptureEvents.append("CAPTURE "+i+" owner="+hp.GetTeam()+" playerTeam="+player.GetTeam()+" progress="+hp.GetHardpointProgressRefPoint()+" score="+GameRules.GetTeamScore(player.GetTeam())+" alive="+IsAlive(player)+" touching="+hp.s.trigger.IsTouching(player)+" origin="+player.GetOrigin())
  }
 } catch(e) { ARES_CaptureEvents.append("CAPTURE_ERROR "+e) }
 ::ARES_CaptureDone=true
}
'''.replace('%CONFIG%',json.dumps(config,allow_nan=False))
