"""Convert harness reports into the ARES result contract
(`harnesses/contracts/result.schema.json`).

Each in-game harness writes its own detailed report; this module maps it onto the shared
contract so agents can treat every harness alike. Verification is never upgraded: a
prepared-but-not-run session is `tool`, a run whose screenshots still need review is
`partial`, and only a finished game run is `runtime`.

usage: python -m ares.result <kind> report.json [--out result.json]
kinds: r5reloaded, northstar, tfo, r1delta, r1delta-compare
"""
import argparse
import json
import sys
from pathlib import Path

SCHEMA_VERSION = '1'
TARGETS = ('r1', 'tfo', 'r2', 'r5')
STATUSES = ('success', 'failure', 'partial')
LEVELS = ('static', 'tool', 'integration', 'runtime')


def _result(tool, target, operation, status, verification, checks, errors, artifacts, duration_ms=0, details=None):
    out = dict(schema_version=SCHEMA_VERSION, tool=tool, target=target, operation=operation, status=status,
               verification=verification, duration_ms=int(max(0, duration_ms)), artifacts=artifacts,
               checks=[dict(name=n, passed=bool(p)) for n, p in checks], errors=[str(e) for e in errors])
    if details:
        out['details'] = details
    validate(out)
    return out


def _shots(items):
    paths = [s['path'] if isinstance(s, dict) else s for s in items or []]
    return [dict(path=str(p), type='screenshot') for p in paths]


def from_r5reloaded(report, path=None):
    """ares.harness.r5reloaded (`r5c-report.json`)."""
    failures = list(report.get('failures') or [])
    if report.get('error'):
        failures.append(report['error'])
    finished = report.get('state') == 'finished'
    checks = [('game started and the probe finished', finished),
              ('spawns, sequences and samples', finished and not [f for f in failures if 'collision' not in f])]
    collision = report.get('collision')
    if collision is not None:
        checks.append(('collision traces, drops and ragdolls', collision.get('passed', False)))
    artifacts = _shots(report.get('screenshots')) + ([dict(path=str(path), type='report')] if path else [])
    return _result('ares.harness.r5reloaded', 'r5', 'ingame-test', 'success' if report.get('passed') else 'failure',
                   'runtime' if finished else 'tool', checks, failures, artifacts,
                   1000 * (report.get('elapsed_seconds') or 0),
                   dict(runtime_sha256=report.get('runtime_sha256'), exit_code=report.get('exit_code')))


def from_northstar(report, path=None):
    """ares.harness.northstar (`--report`)."""
    failures = list(report.get('failures') or [])
    checks = [('spawns', bool(report.get('spawns'))), ('validation', report.get('success', False))]
    artifacts = _shots(report.get('screenshots')) + [dict(path=str(p), type='log') for p in report.get('logs') or []]
    if path:
        artifacts.append(dict(path=str(path), type='report'))
    return _result('ares.harness.northstar', 'r2', 'ingame-test', 'success' if report.get('success') else 'failure',
                   'runtime', checks, failures, artifacts)


def from_tfo(report, path=None):
    """ares.harness.tfo (`--report`). A prepare-only report is a tool-level result."""
    issues = list(report.get('issues') or [])
    prepared_only = report.get('status') in ('preparing', 'prepared')
    checks = [('game run completed', not prepared_only and report.get('status') not in ('failed', 'error')),
              ('telemetry passed', report.get('passed', False))]
    artifacts = _shots(report.get('screenshots')) + ([dict(path=str(path), type='report')] if path else [])
    status = 'success' if report.get('passed') else 'partial' if prepared_only and not issues else 'failure'
    return _result('ares.harness.tfo', 'tfo', 'ingame-test', status, 'tool' if prepared_only else 'runtime',
                   checks, issues, artifacts, details=dict(coverage=report.get('coverage')))


def from_r1delta(report, path=None):
    """ares.harness.r1delta `collect`. Server telemetry can pass before the screenshots are
    reviewed; that is a partial result, never a pass."""
    issues = list(report.get('issues') or [])
    server, visual = report.get('server_passed', False), report.get('visual_passed', False)
    checks = [('server telemetry', server), ('screenshots reviewed', visual)]
    status = 'success' if report.get('passed') else 'partial' if server and not issues else 'failure'
    artifacts = _shots(report.get('screenshots'))
    for key, kind in (('log', 'log'), ('console_snapshot', 'log')):
        if report.get(key):
            artifacts.append(dict(path=str(report[key]), type=kind))
    if path:
        artifacts.append(dict(path=str(path), type='report'))
    return _result('ares.harness.r1delta', 'r1', 'ingame-test', status, 'runtime' if report.get('status') == 'collected' else 'tool',
                   checks, issues, artifacts)


def from_r1delta_compare(report, path=None):
    """ares.harness.r1delta_compare: original/rebuilt pairs compared in a running match."""
    results = report.get('results') or []
    checks = [(r.get('name', 'pair %d' % i), not r.get('issues')) for i, r in enumerate(results)]
    errors = ['%s: %s' % (r.get('name'), issue) for r in results for issue in r.get('issues') or []]
    total, passed = report.get('total', len(results)), report.get('passed', 0)
    status = 'success' if total and passed == total else 'partial' if passed else 'failure'
    artifacts = [dict(path=str(path), type='report')] if path else []
    return _result('ares.harness.r1delta_compare', 'r1', 'retail-comparison', status, 'runtime', checks, errors, artifacts)


CONVERTERS = {'r5reloaded': from_r5reloaded, 'northstar': from_northstar, 'tfo': from_tfo,
              'r1delta': from_r1delta, 'r1delta-compare': from_r1delta_compare}


def validate(result):
    """Check a result against the contract without third-party packages."""
    required = ('schema_version', 'tool', 'target', 'operation', 'status', 'verification', 'duration_ms',
                'artifacts', 'checks', 'errors')
    missing = [k for k in required if k not in result]
    if missing:
        raise ValueError('result is missing ' + ', '.join(missing))
    if result['target'] not in TARGETS or result['status'] not in STATUSES or result['verification'] not in LEVELS:
        raise ValueError('result target/status/verification out of range')
    if not isinstance(result['duration_ms'], int) or result['duration_ms'] < 0:
        raise ValueError('duration_ms must be a non-negative integer')
    for a in result['artifacts']:
        if not isinstance(a.get('path'), str) or not isinstance(a.get('type'), str):
            raise ValueError('artifact needs a path and a type')
    for c in result['checks']:
        if not isinstance(c.get('name'), str) or not isinstance(c.get('passed'), bool):
            raise ValueError('check needs a name and a boolean')
    if not all(isinstance(e, str) for e in result['errors']):
        raise ValueError('errors must be strings')
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('kind', choices=sorted(CONVERTERS))
    p.add_argument('report', type=Path)
    p.add_argument('--out', type=Path, help='write the result here (default: print it)')
    a = p.parse_args(argv)
    result = CONVERTERS[a.kind](json.loads(a.report.read_text(encoding='utf-8')), a.report)
    text = json.dumps(result, indent=2) + '\n'
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding='utf-8')
    else:
        sys.stdout.write(text)
    return 0 if result['status'] == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
