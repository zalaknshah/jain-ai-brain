"""Independent offline evaluator tests: only reviewer-authored tiny fiction.

Never reads the author's challenge fixture or its annotations. Expected counts
are derived by hand from six cases, not by calling the implementation twice.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/evaluate_claim_support.py'
spec = importlib.util.spec_from_file_location('independent_claim_evaluator', SCRIPT)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


def fiction():
    cases = []
    for group, text, claims in (
        ('g1', 'The invented town of Pell has exactly two copper bells.',
         ('Pell has two copper bells.', 'Pell has three copper bells.', 'Pell has a stone bridge.')),
        ('g2', 'In the invented village of Venn, Mira arrived on Tuesday.',
         ('Mira arrived in Venn on Tuesday.', 'Mira did not arrive in Venn on Tuesday.', 'Mira owns a blue coat.')),
    ):
        for index, (claim, label) in enumerate(zip(claims, ('supported', 'contradicted', 'not_established'))):
            cases.append({'id': f'{group}c{index}', 'group_id': group,
                          'phenomenon': 'quantity' if group == 'g1' else 'time',
                          'passages': [{'id': 'p1', 'text': text}], 'claim': claim,
                          'citations': [{'passage_id': 'p1', 'quote': text}],
                          'label': label, 'rationale': 'Independent fictional reference judgment.'})
    return {'protocol': 1, 'scope': 'Tiny original fiction for independent arithmetic checks.', 'cases': cases}


class IndependentEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.data = fiction()
        self.sha = hashlib.sha256(json.dumps(self.data).encode()).hexdigest()
        self.inputs = e.candidate_inputs(self.data, self.sha)

    def predictions(self, labels):
        return {'protocol': 1, 'input_sha256': self.inputs['input_sha256'],
                'predictions': [{'case_id': c['id'], 'label': label}
                                for c, label in zip(self.data['cases'], labels)]}

    def test_export_exact_allowlist_and_hash(self):
        self.assertEqual(set(self.inputs), {'protocol', 'dataset_sha256', 'input_sha256', 'cases'})
        for row in self.inputs['cases']:
            self.assertEqual(set(row), {'id', 'passages', 'claim', 'citations'})
        exported = copy.deepcopy(self.inputs)
        supplied = exported.pop('input_sha256')
        independent_bytes = json.dumps(exported, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        self.assertEqual(supplied, hashlib.sha256(independent_bytes).hexdigest())
        self.assertEqual(self.inputs['dataset_sha256'], self.sha)

    def test_export_does_not_alias_gold(self):
        self.inputs['cases'][0]['passages'][0]['text'] = 'tampered'
        self.inputs['cases'][0]['citations'][0]['quote'] = 'tampered'
        self.assertEqual(self.data, fiction())

    def test_export_order_independent_of_dataset_insertion(self):
        reversed_data = copy.deepcopy(self.data)
        reversed_data['cases'].reverse()
        self.assertEqual(self.inputs, e.candidate_inputs(reversed_data, self.sha))

    def test_hash_requires_exact_lowercase_hex(self):
        for bad in (None, 3, [], '0' * 63, 'G' * 64, 'A' * 64, '0' * 65):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                e.candidate_inputs(self.data, bad)

    def test_missing_duplicate_extra_and_invalid_predictions(self):
        good = self.predictions(['abstain'] * 6)
        bads = []
        p = copy.deepcopy(good); p['predictions'].pop(); bads.append(p)
        p = copy.deepcopy(good); p['predictions'].append(copy.deepcopy(p['predictions'][0])); bads.append(p)
        p = copy.deepcopy(good); p['predictions'].append({'case_id': 'extra', 'label': 'supported'}); bads.append(p)
        p = copy.deepcopy(good); p['predictions'][0]['case_id'] = 'extra'; bads.append(p)
        for invalid in ('unknown', '', None, True, [], {}, 1):
            p = copy.deepcopy(good); p['predictions'][0]['label'] = invalid; bads.append(p)
        for p in bads:
            with self.subTest(predictions=p), self.assertRaises(ValueError):
                e.validate_predictions(p, self.inputs)

    def test_prediction_hash_protocol_schema(self):
        for key, value in (('input_sha256', '0' * 64), ('input_sha256', None), ('protocol', True), ('protocol', 1.0), ('protocol', 2), ('extra', 1)):
            p = self.predictions(['abstain'] * 6); p[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                e.validate_predictions(p, self.inputs)

    def test_changed_content_or_dataset_bytes_reject_old_predictions(self):
        p = self.predictions(['abstain'] * 6)
        changed = copy.deepcopy(self.data); changed['cases'][0]['claim'] += ' Definitely.'
        with self.assertRaises(ValueError):
            e.score(changed, self.sha, p)
        with self.assertRaises(ValueError):
            e.score(self.data, 'f' * 64, p)

    def test_zero_coverage_is_not_accuracy(self):
        r = e.score(self.data, self.sha, self.predictions(['abstain'] * 6))
        o = r['observations']
        self.assertEqual(o['semantic_predictions'], 0)
        self.assertEqual(o['abstentions'], 6)
        self.assertEqual(o['coverage'], 0)
        self.assertIsNone(o['accuracy_when_predicted'])
        self.assertEqual(o['correct_predictions'], 0)
        self.assertEqual(o['correct_fraction_all_cases'], 0)
        self.assertEqual(o['unsupported_as_supported'], 0)
        self.assertEqual(o['complete_matched_groups_correct'], 0)
        for row in r['confusion'].values():
            self.assertEqual(row, {'supported': 0, 'contradicted': 0, 'not_established': 0, 'abstain': 2})

    def test_always_supported_reference_counts(self):
        r = e.score(self.data, self.sha, self.predictions(['supported'] * 6))
        self.assertEqual(r['observations'], {
            'cases': 6, 'mechanically_valid_citations': 6, 'semantic_predictions': 6,
            'abstentions': 0, 'correct_predictions': 2, 'coverage': 1.0,
            'accuracy_when_predicted': 1/3, 'correct_fraction_all_cases': 1/3,
            'unsupported_as_supported': 4, 'unsupported_case_count': 4,
            'unsupported_as_supported_rate': 1.0, 'supported_recall': 1.0,
            'matched_groups': 2, 'complete_matched_groups_correct': 0})
        for row in r['confusion'].values():
            self.assertEqual(row, {'supported': 2, 'contradicted': 0, 'not_established': 0, 'abstain': 0})

    def test_partial_group_reference_counts(self):
        labels = ['supported', 'contradicted', 'not_established', 'abstain', 'supported', 'not_established']
        r = e.score(self.data, self.sha, self.predictions(labels)); o = r['observations']
        for key, expected in {'semantic_predictions': 5, 'abstentions': 1, 'correct_predictions': 4,
                              'coverage': 5/6, 'accuracy_when_predicted': 4/5,
                              'correct_fraction_all_cases': 4/6, 'unsupported_as_supported': 1,
                              'unsupported_as_supported_rate': 1/4, 'supported_recall': 1/2,
                              'complete_matched_groups_correct': 1}.items():
            self.assertEqual(o[key], expected, key)
        self.assertEqual(r['groups'], [{'group_id': 'g1', 'all_three_correct': True}, {'group_id': 'g2', 'all_three_correct': False}])
        self.assertEqual(r['confusion'], {
            'supported': {'supported': 1, 'contradicted': 0, 'not_established': 0, 'abstain': 1},
            'contradicted': {'supported': 1, 'contradicted': 1, 'not_established': 0, 'abstain': 0},
            'not_established': {'supported': 0, 'contradicted': 0, 'not_established': 2, 'abstain': 0}})

    def test_perfect_predictions_and_baselines(self):
        r = e.score(self.data, self.sha, self.predictions(['supported', 'contradicted', 'not_established'] * 2))
        self.assertEqual(r['observations']['complete_matched_groups_correct'], 2)
        self.assertEqual(r['observations']['accuracy_when_predicted'], 1)
        for label in ('supported', 'abstain'):
            self.assertEqual(set(e.validate_predictions(e.baseline_predictions(self.inputs, label), self.inputs).values()), {label})
        with self.assertRaises(ValueError):
            e.baseline_predictions(self.inputs, 'contradicted')

    def test_invalid_dataset_schema_and_bounds(self):
        mutations = [lambda d: d.update(protocol=True), lambda d: d.update(protocol=1.0),
                     lambda d: d.update(extra=1), lambda d: d.update(scope=''),
                     lambda d: d.update(cases=[]), lambda d: d.update(cases=d['cases'] * 86),
                     lambda d: d['cases'][0].update(id=d['cases'][1]['id']),
                     lambda d: d['cases'][0].update(id='bad id'),
                     lambda d: d['cases'][0].update(id='é'),
                     lambda d: d['cases'][0].update(id='x' * 65),
                     lambda d: d['cases'][0].update(claim='x' * 2001),
                     lambda d: d['cases'][0].update(claim='bad\nline'),
                     lambda d: d['cases'][0].update(claim='\ud800'),
                     lambda d: d['cases'][0].update(label='abstain'),
                     lambda d: d['cases'][0].update(phenomenon='unknown'),
                     lambda d: d['cases'][0].update(passages=[]),
                     lambda d: d['cases'][0]['passages'][0].update(text='x' * 8001),
                     lambda d: d['cases'][0].update(rationale='x' * 4001)]
        for index, mutate in enumerate(mutations):
            d = fiction(); mutate(d)
            with self.subTest(index=index), self.assertRaises(ValueError):
                e.validate_cases(d)

    def test_group_integrity_and_citations(self):
        mutations = [lambda d: d['cases'].pop(),
                     lambda d: d['cases'][0].update(group_id='orphan'),
                     lambda d: d['cases'][0].update(label='contradicted'),
                     lambda d: d['cases'][0].update(claim=d['cases'][1]['claim']),
                     lambda d: d['cases'][0].update(phenomenon='negation'),
                     lambda d: d['cases'][0]['passages'].append(copy.deepcopy(d['cases'][0]['passages'][0])),
                     lambda d: d['cases'][0]['citations'].append(copy.deepcopy(d['cases'][0]['citations'][0])),
                     lambda d: d['cases'][0]['citations'][0].update(passage_id='missing'),
                     lambda d: d['cases'][0]['citations'][0].update(quote='invented quotation'),
                     lambda d: d['cases'][0]['citations'][0].update(quote='Pell'),
                     lambda d: d['cases'][0]['passages'][0].update(text=d['cases'][0]['passages'][0]['text'] + ' Extra.')]
        for index, mutate in enumerate(mutations):
            d = fiction(); mutate(d)
            with self.subTest(index=index), self.assertRaises(ValueError):
                e.validate_cases(d)

    def test_file_parser_rejects_duplicate_keys_nonfinite_and_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.json'
            for raw in (b'{"a":1,"a":2}', b'{"a":{"b":1,"b":2}}', b'{"a":NaN}', b'{"a":Infinity}', b'\xff', b'[] trailing'):
                p.write_bytes(raw)
                with self.subTest(raw=raw), self.assertRaises((ValueError, UnicodeError)):
                    e.read_json(p)
            raw = b'{ "hello": "fiction" }\n'; p.write_bytes(raw)
            self.assertEqual(e.read_json(p), ({'hello': 'fiction'}, hashlib.sha256(raw).hexdigest()))

    def test_file_bounds_and_special_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'input.json'
            with patch.object(e, 'MAX_BYTES', 128):
                p.write_bytes(b'{}' + b' ' * 126)
                self.assertEqual(e.read_json(p)[0], {})
                p.write_bytes(b'{}' + b' ' * 127)
                with self.assertRaises(ValueError): e.read_json(p)
            if hasattr(os, 'mkfifo'):
                fifo = Path(tmp) / 'fifo'; os.mkfifo(fifo)
                with self.assertRaises(ValueError): e.read_json(fifo)
            with self.assertRaises((ValueError, OSError)): e.read_json(Path(tmp))

    def test_missing_nonblocking_capability_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            casefile = Path(tmp) / 'cases.json'
            casefile.write_text(json.dumps(self.data), encoding='utf8')
            with patch.object(e.os, 'O_NONBLOCK', create=True):
                delattr(e.os, 'O_NONBLOCK')
                with patch.object(e.os, 'open') as opened:
                    with self.assertRaisesRegex(ValueError, '(?i)(nonblock|posix)'):
                        e.read_json(casefile)
                    opened.assert_not_called()
            # Exercise the real CLI in a fresh process with that capability removed.
            code = ("import os,runpy,sys; "
                    "os.__dict__.pop('O_NONBLOCK', None); "
                    "sys.argv = [sys.argv[1], 'export', '--cases', sys.argv[2]]; "
                    "runpy.run_path(sys.argv[0], run_name='__main__')")
            result = subprocess.run([sys.executable, '-c', code, str(SCRIPT), str(casefile)],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertIn('Invalid evaluation input:', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

    def test_cli_roundtrip_and_error_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            casefile = Path(tmp) / 'cases.json'; predfile = Path(tmp) / 'predictions.json'
            casefile.write_text(json.dumps(self.data), encoding='utf8')
            def run(*args):
                return subprocess.run([sys.executable, str(SCRIPT), *args, '--cases', str(casefile)], capture_output=True, text=True, timeout=5)
            exported = run('export'); self.assertEqual(exported.returncode, 0, exported.stderr)
            exported_data = json.loads(exported.stdout)
            baseline = run('baseline', '--baseline', 'supported'); self.assertEqual(baseline.returncode, 0, baseline.stderr)
            predfile.write_text(baseline.stdout, encoding='utf8')
            scored = run('score', '--predictions', str(predfile)); self.assertEqual(scored.returncode, 0, scored.stderr)
            r = json.loads(scored.stdout)
            self.assertEqual(r['observations']['unsupported_as_supported'], 4)
            self.assertEqual(r['input_sha256'], exported_data['input_sha256'])
            self.assertEqual(r['prediction_file_sha256'], hashlib.sha256(predfile.read_bytes()).hexdigest())
            for args in (('score',), ('export', '--predictions', str(predfile)), ('baseline',), ('export', '--baseline', 'supported')):
                self.assertEqual(run(*args).returncode, 2)
            for raw in (b'null', b'{"protocol":1,"protocol":1}', b'\xff', b'[' * 2000 + b']' * 2000):
                casefile.write_bytes(raw)
                failure = run('export')
                self.assertEqual(failure.returncode, 2, failure.stderr)
                self.assertEqual(failure.stdout, '')
                self.assertNotIn('Traceback', failure.stderr)


if __name__ == '__main__':
    unittest.main()
