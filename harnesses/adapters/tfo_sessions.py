"""Repeat a TFO physics drop test over several launches and label each launch.

Titanfall Online physics can differ per launch: in one launch every dropped prop
rests on a face, in the next the same BSP lets every prop sink into the floor and
come to rest tilted or below it, so a single launch cannot tell a fix from a good
launch. This runs tfo_harness.py once per launch into OUTPUT/launchNN (or reads
reports that already exist) and labels each one:

  good    every drop rests within --max-tilt of a face and meets any --floor
  bad     any drop is tilted, off its floor, or still moving
  unclear the only tilted drops may be leaning on another drop: simultaneous drops
          whose bounding spheres (origin to farthest bounds corner) overlap, or
          lie within --contact. Use drop_sequential or spaced drops instead.
  failed  the map did not load, the run did not finish, or there were no drops

Tilt assumes box-like drop models (crates, barrels standing or on their side).
Copyright (C) 2026 MRVN-Radiant contributors. GPL-2.0-or-later.

  python harnesses/adapters/tfo_sessions.py --launches 6 --output RUNS -- \\
      --game "D:/Games/Titanfall Online" --maps BUILD_DIR --map mp_name --checks checks.json

  python harnesses/adapters/tfo_sessions.py --reports RUNS/a RUNS/b --output RUNS
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from physics_observations import observations, rest_tilt  # noqa: E402

HARNESS = Path(__file__).resolve().parent / 'tfo_harness.py'


def classify(report, max_tilt=5., floors=None, floor_tolerance=1., max_speed=.1, contact=None):
    """Return (label, drops, reasons) for one tfo_harness report."""
    floors = floors or {}
    leaning = []
    if report is None:
        return 'failed', [], ['no report.json']
    reasons = []
    if not report.get('loaded'):
        reasons.append('map did not load')
    if not report.get('finished'):
        reasons.append('run did not finish')
    rows = observations(report)
    if not rows and not reasons:
        reasons.append('no DROP events')
    if reasons:
        return 'failed', [], reasons
    drops = []
    for row in rows:
        index = row['index']
        drop = {'index': index}
        if 'diagnostic_error' in row:
            reasons.append(f'DROP {index}: {row["diagnostic_error"]}')
        if 'origin' in row:
            drop['z'] = row['origin'][2]
        if 'angles' in row:
            drop['tilt'] = round(rest_tilt(row['angles']), 3)
            if drop['tilt'] > max_tilt:
                reason = f'DROP {index}: rests {drop["tilt"]:.1f} degrees from any face'
                # Sequential drops are removed before the next spawns, so only simultaneous drops can touch.
                if not report.get('drop_sequential') and any(touching(row, other, contact)
                                                             for other in rows if other is not row):
                    leaning.append(reason + ' beside another drop')
                else:
                    reasons.append(reason)
        if 'speed' in row:
            drop['speed'] = row['speed']
            if row['speed'] > max_speed:
                reasons.append(f'DROP {index}: still moving at {row["speed"]:.2f}')
        if index in floors:
            bottom = row.get('world_bounds_bottom')
            if bottom is None:
                reasons.append(f'DROP {index}: no bounds to compare with floor {floors[index]}')
            else:
                drop['bounds_bottom'] = round(bottom, 3)
                if abs(bottom - floors[index]) > floor_tolerance:
                    reasons.append(f'DROP {index}: bounds bottom {bottom:.2f} is not within '
                                   f'{floor_tolerance} of floor {floors[index]}')
        drops.append(drop)
    missing = sorted(set(floors) - {row['index'] for row in rows})
    reasons.extend(f'DROP {index}: no final observation' for index in missing)
    if reasons:
        return 'bad', drops, reasons + leaning
    return ('unclear' if leaning else 'good'), drops, leaning


def radius(row):
    """Distance from the origin to the farthest corner of the model bounds."""
    if 'bounds_mins' not in row or 'bounds_maxs' not in row:
        return None
    return math.sqrt(sum(max(abs(lo), abs(hi)) ** 2 for lo, hi in zip(row['bounds_mins'], row['bounds_maxs'])))


def touching(row, other, contact=None):
    if 'origin' not in row or 'origin' not in other:
        return False
    if contact is None:
        reach = (radius(row), radius(other))
        if None in reach:
            return False
        contact = sum(reach) + 1.
    return math.dist(row['origin'], other['origin']) <= contact


def read_report(folder):
    path = Path(folder) / 'report.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def summarize(folders, **options):
    launches = []
    for folder in folders:
        label, drops, reasons = classify(read_report(folder), **options)
        launches.append({'folder': str(folder), 'label': label, 'drops': drops, 'reasons': reasons})
    counts = {label: sum(launch['label'] == label for launch in launches)
              for label in ('good', 'bad', 'unclear', 'failed')}
    return {'launches': launches, 'counts': counts,
            'note': 'Launches differ, so compare builds over several launches each, never one.'}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--output', type=Path, required=True, help='Folder for launchNN reports and sessions.json')
    p.add_argument('--launches', type=int, help='Run tfo_harness.py this many times; its arguments follow --')
    p.add_argument('--reports', type=Path, nargs='+', help='Classify these existing report folders instead')
    p.add_argument('--max-tilt', type=float, default=5., help='Degrees from a face a resting drop may lean (default 5)')
    p.add_argument('--contact', type=float,
                   help='Distance between final origins at which simultaneous drops may be touching '
                        '(default: their bounding spheres overlap)')
    p.add_argument('--floor', nargs=2, type=float, action='append', default=[], metavar=('INDEX', 'Z'),
                   help="Also require this drop's bounds bottom within 1 unit of a flat floor")
    args, harness_args = p.parse_known_args()
    if harness_args[:1] == ['--']:
        harness_args = harness_args[1:]
    if (args.launches is None) == (args.reports is None):
        p.error('give either --launches with tfo_harness.py arguments, or --reports')
    if args.reports and harness_args:
        p.error('--reports takes no tfo_harness.py arguments')
    if args.launches is not None and (args.launches < 1 or not harness_args):
        p.error('--launches must be positive and followed by tfo_harness.py arguments')
    if '--output' in harness_args:
        p.error("tfo_sessions.py chooses each launch's --output")
    if not all(math.isfinite(v) and v >= 0 for v in (args.max_tilt, 0. if args.contact is None else args.contact)):
        p.error('--max-tilt and --contact must be finite and nonnegative')
    floors = {}
    for index, height in args.floor:
        if not index.is_integer() or index < 0 or not math.isfinite(height) or int(index) in floors:
            p.error('--floor needs unique nonnegative integer indices and finite heights')
        floors[int(index)] = height
    options = {'max_tilt': args.max_tilt, 'floors': floors, 'contact': args.contact}
    args.output.mkdir(parents=True, exist_ok=True)
    folders = list(args.reports or [])
    for launch in range(args.launches or 0):
        folder = args.output / f'launch{launch + 1:02d}'
        # tfo_harness exits nonzero for any failed expectation; the report decides the label.
        subprocess.run([sys.executable, str(HARNESS), *harness_args, '--output', str(folder)],
                       stdout=subprocess.DEVNULL)
        folders.append(folder)
        label, _, reasons = classify(read_report(folder), **options)
        print(f'launch {launch + 1}: {label}' + (f' ({reasons[0]})' if reasons else ''), flush=True)
    summary = summarize(folders, **options)
    (args.output / 'sessions.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    for launch in summary['launches']:
        tilts = ', '.join(f'{d["tilt"]:.1f}' for d in launch['drops'] if 'tilt' in d)
        print(f'{launch["label"]:6} {launch["folder"]}' + (f'  tilt [{tilts}]' if tilts else ''))
    print('good {good}, bad {bad}, unclear {unclear}, failed {failed}'.format(**summary['counts']))
    return 0 if summary['counts']['good'] == len(folders) else 1


if __name__ == '__main__':
    sys.exit(main())
