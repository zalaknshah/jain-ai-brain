"""Synthetic runner checks only: no authored challenge corpus is inspected here."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('challenge_runner_review', ROOT / 'scripts/evaluate_scoped_challenge.py')
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


def fixture(count=1):
    text = 'World f: Object A is p.'
    return {'protocol': 1, 'cases': [
        {'input': {'id': f'synthetic-{i}', 'passages': [{'id': 'p1', 'text': text}],
                   'claim': text, 'citations': [{'passage_id': 'p1', 'quote': text}]},
         'expected': {'label': 'supported', 'reason': 'complete_component_check',
                      'checks': [{'path': ['evaluation', 'true_possible'], 'value': True},
                                 {'path': ['evaluation', 'false_possible'], 'value': False}]},
         'rationale': 'Synthetic direct fact only.', 'family': 'synthetic_runner_test'}
        for i in range(count)]}


class RunnerReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.cases = self.base / 'cases.json'
        self.out = self.base / 'out'

    def prepare(self, count=1, value=None, raw=None):
        raw = R.canonical(fixture(count) if value is None else value) + b'\n' if raw is None else raw
        self.cases.write_bytes(raw)
        return R.digest(raw)

    def run_fixture(self, **kwargs):
        return R.run_challenge(self.cases, self.out, expected_sha256=R.digest(self.cases.read_bytes()), **kwargs)

    def test_real_cli_round_trip_fixed_batches_bindings_and_denominators(self):
        sha = self.prepare(17)
        summary = self.run_fixture()
        self.assertEqual(summary['status'], 'passed')
        self.assertEqual(summary['case_count'], 17)
        self.assertEqual(summary['attempted_case_count'], 17)
        self.assertEqual(summary['verified_case_count'], 17)
        self.assertEqual(summary['distinct_payload_count'], 1)
        self.assertEqual(summary['assertion_count'], 34)
        self.assertEqual(summary['retries'], 0)
        self.assertEqual([r['case_count'] for r in summary['requests']], [16, 16, 1, 1])
        self.assertEqual((self.out / 'challenge.json').read_bytes(), self.cases.read_bytes())
        self.assertEqual(R.decode((self.out / 'summary.json').read_bytes()), summary)
        for request in summary['requests']:
            raw = (self.out / request['input_file']).read_bytes()
            inputs = R.decode(raw)
            self.assertEqual(inputs['dataset_sha256'], sha)
            self.assertEqual(request['input_sha256'], R.digest(raw))
            projection = {k: v for k, v in inputs.items() if k != 'input_sha256'}
            self.assertEqual(inputs['input_sha256'], R.digest(R.canonical(projection)))
            self.assertEqual(set(inputs['cases'][0]), {'id', 'passages', 'claim', 'citations'})
            for stream in ('stdout', 'stderr'):
                retained = (self.out / request[stream + '_file']).read_bytes()
                self.assertEqual(request[stream + '_sha256'], R.digest(retained))
                self.assertEqual(request[stream + '_bytes'], len(retained))

    def test_typed_comparison_does_not_equate_booleans_integers_or_floats(self):
        for a, b in [(True, 1), (False, 0), (1, 1.0), ({'x': [True]}, {'x': [1]})]:
            self.assertFalse(R.typed_equal(a, b))
        self.assertTrue(R.typed_equal({'x': [False, 1, None]}, {'x': [False, 1, None]}))

    def test_assertion_boolean_is_not_numeric(self):
        value = fixture()
        value['cases'][0]['expected']['checks'][0]['value'] = 1
        self.prepare(value=value)
        summary = self.run_fixture()
        self.assertEqual(summary['status'], 'failed')
        self.assertEqual(summary['verified_case_count'], 0)
        self.assertIn('failed assertion', str(summary['requests'][1]['errors']))

    def test_semantic_mismatch_continues_original_batches_without_retry(self):
        value = fixture(17)
        value['cases'][0]['expected']['label'] = 'contradicted'
        self.prepare(value=value)
        summary = self.run_fixture()
        self.assertEqual(summary['status'], 'failed')
        self.assertEqual(summary['attempted_case_count'], 17)
        self.assertEqual(summary['verified_case_count'], 1)
        self.assertEqual(summary['failed_batches'], [0])
        self.assertEqual(len(summary['requests']), 4)
        self.assertEqual(summary['retries'], 0)

    def test_nonzero_exit_retains_bytes_and_stops_without_rebatching(self):
        self.prepare(33)
        result = subprocess.CompletedProcess([], 2, b'partial stdout', b'{"error":"trace_overflow"}\n')
        with mock.patch.object(R.subprocess, 'run', return_value=result) as run:
            summary = self.run_fixture()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(summary['attempted_case_count'], 16)
        self.assertEqual(summary['case_count'], 33)
        self.assertEqual(summary['verified_case_count'], 0)
        self.assertEqual(summary['failed_batches'], [0])
        self.assertEqual((self.out / summary['requests'][0]['stdout_file']).read_bytes(), result.stdout)
        self.assertEqual((self.out / summary['requests'][0]['stderr_file']).read_bytes(), result.stderr)
        self.assertEqual(summary['requests'][0]['returncode'], 2)

    def test_timeout_retains_partial_bytes_and_no_retry(self):
        self.prepare(17)
        failure = subprocess.TimeoutExpired(['synthetic'], .01, output=b'partial', stderr=b'diagnostic')
        with mock.patch.object(R.subprocess, 'run', side_effect=failure) as run:
            summary = self.run_fixture(timeout=.01)
        self.assertEqual(run.call_count, 1)
        request = summary['requests'][0]
        self.assertTrue(request['timed_out'])
        self.assertIsNone(request['returncode'])
        self.assertEqual((self.out / request['stdout_file']).read_bytes(), b'partial')
        self.assertEqual((self.out / request['stderr_file']).read_bytes(), b'diagnostic')
        self.assertEqual(summary['verified_case_count'], 0)
        self.assertTrue(summary['all_raw_request_artifacts_retained'])

    def test_launch_failure_retains_empty_artifacts_and_summary(self):
        self.prepare()
        with mock.patch.object(R.subprocess, 'run', side_effect=OSError('synthetic')) as run:
            summary = self.run_fixture()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(summary['requests'][0]['launch_error'], 'OSError')
        self.assertEqual(summary['status'], 'failed')
        self.assertTrue((self.out / 'summary.json').exists())

    def test_stderr_on_success_prevents_verification(self):
        self.prepare()
        result = subprocess.CompletedProcess([], 0, b'{}\n', b'warning')
        with mock.patch.object(R.subprocess, 'run', return_value=result) as run:
            summary = self.run_fixture()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(summary['verified_case_count'], 0)
        self.assertIn('nonempty stderr', str(summary['requests']))

    def test_input_hash_and_each_frozen_source_mismatch_prevent_execution(self):
        self.prepare()
        with mock.patch.object(R.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                R.run_challenge(self.cases, self.out, expected_sha256='0' * 64)
            for source in R.SOURCE_HASHES:
                changed = dict(R.SOURCE_HASHES, **{source: '0' * 64})
                with mock.patch.object(R, 'SOURCE_HASHES', changed), self.assertRaises(ValueError):
                    self.run_fixture()
            run.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_existing_evidence_never_overwritten(self):
        self.prepare()
        self.out.mkdir()
        sentinel = self.out / 'summary.json'
        sentinel.write_bytes(b'old evidence')
        with mock.patch.object(R.subprocess, 'run') as run, self.assertRaises(ValueError):
            self.run_fixture()
        run.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b'old evidence')
        with self.assertRaises(FileExistsError):
            R.write_new(sentinel, b'new')
        self.assertEqual(sentinel.read_bytes(), b'old evidence')

    def test_invalid_json_and_corpus_shapes_never_execute(self):
        invalid = [b'{"protocol":1,"protocol":1,"cases":[]}', b'\xff', b'NaN', b'[]']
        for mutate in [lambda x: x.update(protocol=True), lambda x: x.update(cases=[]),
                       lambda x: x['cases'].append(copy.deepcopy(x['cases'][0])),
                       lambda x: x['cases'][0]['input'].update(gold='supported'),
                       lambda x: x['cases'][0]['expected']['checks'][0].update(path=[True]),
                       lambda x: x['cases'][0]['expected']['checks'][0].update(path=[-1]),
                       lambda x: x['cases'][0]['expected']['checks'][0].update(path=[]),
                       lambda x: x['cases'][0]['expected'].update(label='invented')]:
            value = fixture()
            mutate(value)
            invalid.append(R.canonical(value))
        for raw in invalid:
            with self.subTest(raw=raw[:60]):
                self.prepare(raw=raw)
                with mock.patch.object(R.subprocess, 'run') as run, self.assertRaises((ValueError, TypeError)):
                    self.run_fixture()
                run.assert_not_called()
                self.assertFalse(self.out.exists())

    def test_invalid_candidate_input_is_retained_as_failed_request_not_dropped(self):
        value = fixture(17)
        value['cases'][0]['input']['citations'] = []
        self.prepare(value=value)
        summary = self.run_fixture()
        self.assertEqual(summary['case_count'], 17)
        self.assertEqual(summary['attempted_case_count'], 16)
        self.assertEqual(summary['verified_case_count'], 0)
        self.assertEqual(len(summary['requests']), 1)
        self.assertEqual((self.out / summary['requests'][0]['stderr_file']).read_bytes(), b'{"error":"invalid_input"}\n')

    def test_file_limits_and_fifo_are_rejected_without_blocking(self):
        self.cases.write_bytes(b' ' * (R.MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            R.read_regular(self.cases)
        if hasattr(os, 'mkfifo'):
            pipe = self.base / 'fifo'
            os.mkfifo(pipe)
            with self.assertRaises(ValueError):
                R.read_regular(pipe)

    def test_output_schema_binding_and_serialization_tampering(self):
        rows = fixture()['cases']
        inputs = {'input_sha256': 'a' * 64, 'dataset_sha256': 'b' * 64}
        good = {'protocol': 1, 'input_sha256': inputs['input_sha256'],
                'predictions': [{'case_id': rows[0]['input']['id'], 'label': 'supported'}]}
        self.assertEqual(R.check_operation(R.canonical(good) + b'\n', 'predict', inputs, rows, R.SOURCE_HASHES), [])
        variants = [b'{}\n', R.canonical(good), json.dumps(good).encode() + b'\n', b'NaN\n', b'\xff']
        for key, value in [('protocol', True), ('input_sha256', 'c' * 64), ('extra', 1)]:
            changed = dict(good)
            changed[key] = value
            variants.append(R.canonical(changed) + b'\n')
        for raw in variants:
            self.assertTrue(R.check_operation(raw, 'predict', inputs, rows, R.SOURCE_HASHES))

    def test_trace_binding_drift_and_typed_assertions_are_rejected(self):
        self.prepare()
        self.run_fixture()
        inputs = R.decode((self.out / 'batch-000.inputs.json').read_bytes())
        trace = R.decode((self.out / 'batch-000.inspect.stdout.json').read_bytes())
        rows = fixture()['cases']
        self.assertEqual(R.check_operation(R.canonical(trace) + b'\n', 'inspect', inputs, rows, R.SOURCE_HASHES), [])
        for field in trace['bindings']:
            changed = copy.deepcopy(trace)
            changed['bindings'][field] = '0' * 64
            self.assertTrue(R.check_operation(R.canonical(changed) + b'\n', 'inspect', inputs, rows, R.SOURCE_HASHES), field)
        for field, value in [('trace_protocol', True), ('candidate', 'wrong'), ('contract', 'wrong'), ('cases', [])]:
            changed = copy.deepcopy(trace)
            changed[field] = value
            self.assertTrue(R.check_operation(R.canonical(changed) + b'\n', 'inspect', inputs, rows, R.SOURCE_HASHES), field)
        changed = copy.deepcopy(trace)
        changed['cases'][0]['evaluation']['true_possible'] = 1
        self.assertTrue(R.check_operation(R.canonical(changed) + b'\n', 'inspect', inputs, rows, R.SOURCE_HASHES))

    def test_assertion_path_requires_container_type_and_present_value(self):
        for value, path in [({}, ['absent']), ([], [0]), ([1], [-1]), ({'0': 1}, [0]), ([1], ['0']), ([1], [True])]:
            with self.assertRaises((ValueError, KeyError, IndexError)):
                R.at_path(value, path)


if __name__ == '__main__':
    unittest.main()
