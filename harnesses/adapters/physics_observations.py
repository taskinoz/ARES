"""Decode final prop poses from R1/TFO reports. Bounds are diagnostics, not contact meshes.

Copyright (C) 2026 MRVN-Radiant contributors. GPL-2.0-or-later.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

VECTOR = r'\(vector\s*:\s*\(([^()]*)\)\)'


def vector(event, name):
    match = re.search(r'\b' + re.escape(name) + '=' + VECTOR, event)
    if not match:
        raise ValueError(f'missing {name} vector')
    values = [float(value.strip()) for value in match[1].split(',')]
    if len(values) != 3 or not all(math.isfinite(v) for v in values):
        raise ValueError(f'invalid {name} vector')
    return values


def bounds_bottom(origin, angles, mins, maxs):
    """Source pitch/yaw/roll: yaw does not change the projected vertical extent."""
    if any(lo > hi for lo, hi in zip(mins, maxs)):
        raise ValueError('inverted local bounds')
    pitch, _, roll = map(math.radians, angles)
    weights = [-math.sin(pitch), math.cos(pitch) * math.sin(roll),
               math.cos(pitch) * math.cos(roll)]
    return origin[2] + sum(min(a * low, a * high) for a, low, high in zip(weights, mins, maxs))


def hull_bottom(origin, angles, points):
    """Rigid single-body PHY vertices, converted to Source model-space units."""
    if not points or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError('physics hull requires finite 3D vertices')
    pitch, _, roll = map(math.radians, angles)
    weights = [-math.sin(pitch), math.cos(pitch) * math.sin(roll),
               math.cos(pitch) * math.cos(roll)]
    bottom = origin[2] + min(sum(a * v for a, v in zip(weights, point)) for point in points)
    if not math.isfinite(bottom):
        raise ValueError('nonfinite transformed physics hull')
    return bottom


def rest_tilt(angles):
    """Degrees between world up and the nearest model axis, for Source pitch/yaw/roll.

    A box-like prop resting on a flat floor lies on a face, side or end, so this is
    near zero; a prop wedged in collision or propped on an edge is not. Yaw is ignored.
    """
    pitch, _, roll = map(math.radians, angles)
    # World Z components of the model's forward, right and up axes.
    alignment = max(abs(math.sin(pitch)), abs(math.sin(roll) * math.cos(pitch)),
                    abs(math.cos(roll) * math.cos(pitch)))
    return math.degrees(math.acos(min(1., alignment)))


def support_errors(rows, floors, tolerance=1., max_speed=.1):
    errors = []
    for index, floor in floors.items():
        matches = [row for row in rows if row['index'] == index]
        if not matches:
            errors.append(f'DROP {index}: no final observation')
        for row in matches:
            if ('physics_bottom' not in row or not math.isfinite(row['physics_bottom']) or
                    abs(row['physics_bottom'] - floor) > tolerance):
                errors.append(f'DROP {index}: physics hull bottom is not within {tolerance} of floor {floor}')
            if 'speed' not in row or not math.isfinite(row['speed']) or row['speed'] > max_speed:
                errors.append(f'DROP {index}: linear speed exceeds {max_speed} or is unavailable')
    return errors


def observations(report):
    result = []
    for event in report['events']:
        match = re.match(r'DROP (\d+) z=', event)
        if not match:
            continue
        row = {'index': int(match[1]), 'event': event}
        errors = []
        for name in ('origin', 'velocity', 'angles', 'bounds_mins', 'bounds_maxs'):
            try:
                row[name] = vector(event, name)
            except ValueError as exc:
                errors.append(str(exc))
        if 'velocity' in row:
            row['speed'] = math.hypot(*row['velocity'])
        if all(name in row for name in ('origin', 'angles', 'bounds_mins', 'bounds_maxs')):
            try:
                bottom = bounds_bottom(row['origin'], row['angles'], row['bounds_mins'], row['bounds_maxs'])
                if not math.isfinite(bottom):
                    raise ValueError('nonfinite transformed bounds')
                row['world_bounds_bottom'] = bottom
            except ValueError as exc:
                errors.append(str(exc))
        if errors:
            row['diagnostic_error'] = '; '.join(errors)
        result.append(row)
    return result


def sample_motion(events, window=2.):
    """Tail-window translation from samples, independent of entity velocity.

    Finite differences are interval averages, not instantaneous body velocity.
    Rotation, events between samples and motion after the last sample are not measured.
    """
    if not math.isfinite(window) or window <= 0:
        raise ValueError('motion window must be positive and finite')
    groups, invalid = {}, {}
    for event in events:
        match = re.match(r'SAMPLE (\d+)\b', event)
        if not match:
            continue
        index = int(match[1])
        try:
            stamp = re.search(r'\bt=(\S+)', event)
            t = float(stamp[1]) if stamp else float('nan')
            if not math.isfinite(t) or t < 0:
                raise ValueError('invalid sample timestamp')
            origin = vector(event, 'origin')
            rows = groups.setdefault(index, [])
            if rows and t <= rows[-1][0]:
                raise ValueError('sample timestamps must increase within each drop')
            rows.append((t, origin))
        except ValueError as exc:
            invalid[index] = str(exc)
    result = []
    for index in sorted(groups.keys() | invalid.keys()):
        rows = groups.get(index, [])
        row = {'index': index, 'sample_count': len(rows)}
        if index in invalid:
            row['diagnostic_error'] = invalid[index]
        elif len(rows) < 2 or rows[-1][0] - rows[0][0] < window:
            row['diagnostic_error'] = 'insufficient sample duration for motion window'
        else:
            start = 0
            while start + 1 < len(rows) and rows[start + 1][0] <= rows[-1][0] - window:
                start += 1
            tail = rows[start:]
            row.update(start_time=tail[0][0], end_time=tail[-1][0],
                       duration=tail[-1][0] - tail[0][0],
                       origin_min=[min(sample[1][axis] for sample in tail) for axis in range(3)],
                       origin_max=[max(sample[1][axis] for sample in tail) for axis in range(3)],
                       translation=max(math.dist(a[1], b[1]) for a in tail for b in tail),
                       max_interval_speed=max(math.dist(a[1], b[1]) / (b[0] - a[0])
                                              for a, b in zip(tail, tail[1:])))
        result.append(row)
    return result


def motion_errors(rows, indices, max_translation=.25):
    if not math.isfinite(max_translation) or max_translation < 0:
        raise ValueError('maximum translation must be finite and nonnegative')
    errors = []
    for index in indices:
        matches = [row for row in rows if row['index'] == index]
        if len(matches) != 1 or 'translation' not in matches[0] or 'diagnostic_error' in matches[0]:
            errors.append(f'DROP {index}: sampled translation is unavailable or invalid')
        elif not math.isfinite(matches[0]['translation']) or matches[0]['translation'] > max_translation:
            errors.append(f'DROP {index}: sampled translation exceeds {max_translation}')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phy', type=Path, help='Optional rigid single-solid Source/Titanfall companion PHY')
    parser.add_argument('--floor', nargs=2, type=float, action='append', default=[], metavar=('INDEX', 'Z'),
                        help='Check actual hull support against a flat floor (requires --phy)')
    parser.add_argument('--motion', type=int, action='append', default=[], metavar='INDEX',
                        help='Require tail-window sampled translation for this drop')
    parser.add_argument('--motion-window', type=float, default=2.)
    parser.add_argument('--max-translation', type=float, default=.25)
    args = parser.parse_args()
    if (len(set(args.motion)) != len(args.motion) or any(i < 0 for i in args.motion) or
            not math.isfinite(args.motion_window) or args.motion_window <= 0 or
            not math.isfinite(args.max_translation) or args.max_translation < 0):
        parser.error('motion indices must be unique/nonnegative, window positive and translation nonnegative/finite')
    if args.floor and not args.phy:
        parser.error('--floor requires --phy')
    floors = {}
    for index, height in args.floor:
        if not math.isfinite(index) or not index.is_integer() or index < 0 or not math.isfinite(height) or int(index) in floors:
            parser.error('--floor requires unique nonnegative integer indices and finite heights')
        floors[int(index)] = height
    report = json.loads(args.report.read_text(encoding='utf-8'))
    result = {'scope': 'Rigid pose/support and sampled translation; not angular rest or broad physics/buoyancy parity.',
              'velocity_note': 'speed is entity-reported; it may be zero while a VPhysics body moves. '
                               'Use requested sampled translation checks for observed positional motion.',
              'drops': observations(report), 'motion': sample_motion(report['events'], args.motion_window)}
    if args.phy:
        if args.phy.suffix.lower() != '.phy':
            parser.error('--phy requires the standalone .phy file so its fingerprint covers the inspected data')
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from ares.source.ivp_phy import load, ivp_to_hl
        phy = load(args.phy)
        if phy['solidCount'] != 1:
            parser.error('--phy requires one rigid solid, not an articulated/multi-body model')
        points = [ivp_to_hl(p[:3]) for p in phy['solids'][0].get('points', [])]
        for row in result['drops']:
            if 'origin' in row and 'angles' in row:
                row['physics_bottom'] = hull_bottom(row['origin'], row['angles'], points)
        result['phy'] = {'path': str(args.phy.resolve()), 'sha256': hashlib.sha256(args.phy.read_bytes()).hexdigest(),
                         'vertex_count': len(points)}
    result['errors'] = support_errors(result['drops'], floors)
    result['errors'] += motion_errors(result['motion'], args.motion, args.max_translation)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return int(bool(result['errors']))


if __name__ == '__main__':
    raise SystemExit(main())
