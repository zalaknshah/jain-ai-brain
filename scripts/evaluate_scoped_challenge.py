"""Run a frozen synthetic challenge through both actual scoped-support CLIs.

This runner checks disclosed expectations; it is not a semantic oracle. It
retains every attempted input, output, and failure without retry or rebatching.
No network, corpus, learned model, or JACE runtime is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BATCH_SIZE = 16
MAX_BYTES = 2 * 1024 * 1024
SOURCE_HASHES = {
    'scripts/predict_scoped_support.py': '6890eda45c4d679c6499011ddb779b2cbd07fde36d837248ec3e7e89f8e38316',
    'scripts/evaluate_claim_support.py': 'f24f017ad344d572e61979519730c5fc8dbd1be162fb24d648ab66deae04ae13',
    'docs/SCOPED_SUPPORT_CONTRACT.md': '0facb37c40a72b34dd93420453acc60def3292ee8a27fd6cef9f080a6a655e46',
}
LABELS = {'supported', 'contradicted', 'not_established', 'abstain'}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def typed_equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(typed_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate JSON key')
        obj[key] = value
    return obj


def decode(raw):
    return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def read_regular(path):
    if not hasattr(os, 'O_NONBLOCK'):
        raise ValueError('nonblocking file inspection unavailable')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError('expected bounded regular file')
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('file exceeds byte bound')
    return raw


def at_path(value, path):
    for part in path:
        if type(part) is int:
            if type(value) is not list or part < 0:
                raise ValueError('invalid list assertion path')
        elif type(part) is str:
            if type(value) is not dict:
                raise ValueError('invalid object assertion path')
        else:
            raise ValueError('invalid assertion path type')
        value = value[part]
    return value


def validate_challenge(value):
    if type(value) is not dict or type(value.get('protocol')) is not int or value['protocol'] != 1:
        raise ValueError('invalid challenge protocol')
    rows = value.get('cases')
    if type(rows) is not list or not 1 <= len(rows) <= 512:
        raise ValueError('challenge requires 1 through 512 cases')
    seen = set()
    for row in rows:
        if type(row) is not dict or set(row) != {'input', 'expected', 'rationale', 'family'}:
            raise ValueError('invalid challenge row')
        item, exp = row['input'], row['expected']
        if type(item) is not dict or set(item) != {'id', 'passages', 'claim', 'citations'}:
            raise ValueError('invalid input projection')
        ident = item['id']
        if type(ident) is not str or not ident or ident in seen:
            raise ValueError('invalid or repeated case ID')
        seen.add(ident)
        if type(exp) is not dict or set(exp) != {'label', 'reason', 'checks'}:
            raise ValueError('invalid expected row')
        if exp['label'] not in LABELS or type(exp['reason']) is not str or not exp['reason']:
            raise ValueError('invalid expected result')
        if any(type(row[key]) is not str or not row[key] for key in ('family', 'rationale')):
            raise ValueError('missing rationale or family')
        if type(exp['checks']) is not list:
            raise ValueError('invalid checks')
        for check in exp['checks']:
            if type(check) is not dict or set(check) != {'path', 'value'} or type(check['path']) is not list:
                raise ValueError('invalid check')
            if not check['path'] or any(type(p) not in (str, int) or (type(p) is int and p < 0) for p in check['path']):
                raise ValueError('invalid check path')
    return rows


def write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def check_operation(raw, operation, inputs, rows, hashes):
    errors = []
    try:
        value = decode(raw)
        if raw != canonical(value) + b'\n':
            errors.append('output is not canonical JSON plus LF')
        predictions = {'protocol': 1, 'input_sha256': inputs['input_sha256'],
                       'predictions': [{'case_id': row['input']['id'], 'label': row['expected']['label']} for row in rows]}
        if operation == 'predict':
            if not typed_equal(value, predictions):
                errors.append('prediction object differs from exact expected object')
            return errors
        expected_bindings = {
            'candidate_source_sha256': hashes['scripts/predict_scoped_support.py'],
            'evaluator_source_sha256': hashes['scripts/evaluate_claim_support.py'],
            'contract_sha256': hashes['docs/SCOPED_SUPPORT_CONTRACT.md'],
            'input_sha256': inputs['input_sha256'], 'dataset_sha256': inputs['dataset_sha256'],
            'prediction_sha256': digest(canonical(predictions)),
        }
        if type(value) is not dict or set(value) != {'trace_protocol', 'candidate', 'contract', 'bindings', 'cases'}:
            return errors + ['invalid trace top-level schema']
        for key, expected in [('trace_protocol', 1), ('candidate', 'scoped_unary_v1'),
                              ('contract', 'scoped_unary_contract_v1'), ('bindings', expected_bindings)]:
            if not typed_equal(value[key], expected):
                errors.append('trace ' + key + ' mismatch')
        actual_rows = value['cases']
        if type(actual_rows) is not list or len(actual_rows) != len(rows):
            return errors + ['trace row count mismatch']
        for actual, row in zip(actual_rows, rows):
            ident, expected = row['input']['id'], row['expected']
            if type(actual) is not dict:
                errors.append(ident + ': non-object trace row')
                continue
            for key, exp in [('case_id', ident), ('label', expected['label']), ('reason', expected['reason'])]:
                if not typed_equal(actual.get(key), exp):
                    errors.append(ident + ': ' + key + ' mismatch')
            for check in expected['checks']:
                try:
                    matched = typed_equal(at_path(actual, check['path']), check['value'])
                except (ValueError, KeyError, IndexError, TypeError):
                    matched = False
                if not matched:
                    errors.append(ident + ': failed assertion ' + json.dumps(check['path']))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        errors.append('malformed output JSON')
    return errors


def run_challenge(cases_path, output_dir, *, timeout=30.0, expected_sha256=None):
    raw = read_regular(cases_path)
    corpus_sha = digest(raw)
    if expected_sha256 is not None and corpus_sha != expected_sha256:
        raise ValueError('challenge hash differs from expected frozen SHA-256')
    rows = validate_challenge(decode(raw))
    hashes = {name: digest(read_regular(ROOT / name)) for name in SOURCE_HASHES}
    if hashes != SOURCE_HASHES:
        raise ValueError('frozen candidate, evaluator, or contract changed')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError('output directory must be empty; no evidence is overwritten')
    write_new(output_dir / 'challenge.json', raw)
    summary = {
        'protocol': 1, 'status': 'running', 'scope': 'disclosed synthetic expectation challenge, not a complete semantic oracle or broad capability result',
        'challenge_sha256': corpus_sha, 'source_sha256': hashes,
        'runner_sha256': digest(Path(__file__).read_bytes()), 'python': platform.python_version(),
        'batch_size': BATCH_SIZE, 'case_count': len(rows),
        'distinct_payload_count': len({canonical({k: v for k, v in r['input'].items() if k != 'id'}) for r in rows}),
        'assertion_count': sum(len(r['expected']['checks']) for r in rows),
        'attempted_case_count': 0, 'verified_case_count': 0, 'requests': [], 'failed_batches': [],
        'all_raw_request_artifacts_retained': True, 'retries': 0,
    }
    fatal = False
    for batch_index, start in enumerate(range(0, len(rows), BATCH_SIZE)):
        batch = rows[start:start + BATCH_SIZE]
        inputs = {'protocol': 1, 'dataset_sha256': corpus_sha, 'cases': [r['input'] for r in batch]}
        inputs['input_sha256'] = digest(canonical(inputs))
        prefix = f'batch-{batch_index:03d}'
        input_path = output_dir / (prefix + '.inputs.json')
        write_new(input_path, canonical(inputs) + b'\n')
        summary['attempted_case_count'] += len(batch)
        batch_failed = False
        for operation in ('predict', 'inspect'):
            command = [sys.executable, '-B', str(ROOT / 'scripts/predict_scoped_support.py'), operation, '--inputs', str(input_path.resolve())]
            returncode, timed_out, launch_error = None, False, None
            stdout = stderr = b''
            try:
                result = subprocess.run(command, capture_output=True, timeout=timeout,
                                        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                returncode, stdout, stderr = result.returncode, result.stdout, result.stderr
            except subprocess.TimeoutExpired as exc:
                timed_out, stdout, stderr = True, exc.stdout or b'', exc.stderr or b''
            except OSError as exc:
                launch_error = type(exc).__name__
            stdout_name, stderr_name = f'{prefix}.{operation}.stdout.json', f'{prefix}.{operation}.stderr.txt'
            write_new(output_dir / stdout_name, stdout)
            write_new(output_dir / stderr_name, stderr)
            errors = []
            if returncode != 0 or timed_out or launch_error:
                errors.append('candidate request did not complete successfully')
                fatal = True
            if stderr:
                errors.append('nonempty stderr on expected successful request')
            if not errors:
                errors = check_operation(stdout, operation, inputs, batch, hashes)
            summary['requests'].append({
                'batch': batch_index, 'operation': operation, 'case_count': len(batch),
                'input_file': input_path.name, 'input_sha256': digest(input_path.read_bytes()),
                'stdout_file': stdout_name, 'stdout_sha256': digest(stdout), 'stdout_bytes': len(stdout),
                'stderr_file': stderr_name, 'stderr_sha256': digest(stderr), 'stderr_bytes': len(stderr),
                'returncode': returncode, 'timed_out': timed_out, 'launch_error': launch_error, 'errors': errors,
            })
            batch_failed |= bool(errors)
            if fatal:
                break
        if batch_failed:
            summary['failed_batches'].append(batch_index)
        else:
            summary['verified_case_count'] += len(batch)
        if fatal:
            break
    summary['status'] = 'failed' if summary['failed_batches'] else 'passed'
    write_new(output_dir / 'summary.json', canonical(summary) + b'\n')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--timeout', type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        if not 0 < args.timeout <= 300:
            raise ValueError('timeout must be positive and at most 300 seconds')
        summary = run_challenge(args.cases, args.output_dir, timeout=args.timeout,
                                expected_sha256=args.expected_sha256)
    except (ValueError, OSError, RecursionError, TypeError) as exc:
        print(json.dumps({'error': str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps({'status': summary['status'], 'verified_cases': summary['verified_case_count'],
                      'case_count': summary['case_count']}, sort_keys=True))
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
