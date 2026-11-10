"""Replay disclosed frozen evidence with stdlib only, without model inference.

These checks establish artifact consistency and arithmetic, not provenance,
independent execution, label correctness, calibration, or generalization.
"""
import ast
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import unittest
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
LABELS = ('supported', 'contradicted', 'not_established')
MODEL_LABELS = ('contradicted', 'supported', 'not_established')
PHENOMENA = {'negation', 'quantity', 'quantifiers', 'time', 'location',
             'conditionals', 'attribution', 'cross_source'}
FIXTURE_SHA = 'beb7d4c46bd2f72143030044348094ddd382549ee95bc3d90f663d014ee06334'
FROZEN_SHA = '75b55e42d59532f14341a09358a3b73c01e25a891956ce814403f3a0cf84d3d0'
RUNNER_SHA = '11217322391b15ff6dacb37947f6bafc31b30f9c0abae8d032cec9cf43532e2e'
SCHEMA_SHA = 'f24f017ad344d572e61979519730c5fc8dbd1be162fb24d648ab66deae04ae13'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def pretty(value, sort_keys=False):
    return (json.dumps(value, ensure_ascii=False, sort_keys=sort_keys,
                       indent=2, allow_nan=False) + '\n').encode('utf-8')


def read(name):
    return json.loads((ROOT / 'evals' / name).read_text(encoding='utf-8'))


def summarize(cases, predictions):
    """Independent recount; deliberately does not use the shipped scorer."""
    matrix = {gold: {label: 0 for label in (*LABELS, 'abstain')}
              for gold in LABELS}
    groups = defaultdict(list)
    for case in cases:
        predicted = predictions[case['id']]
        matrix[case['label']][predicted] += 1
        groups[case['group_id']].append(predicted == case['label'])
    n = len(cases)
    abstentions = sum(row['abstain'] for row in matrix.values())
    correct = sum(matrix[label][label] for label in LABELS)
    supported = sum(matrix['supported'].values())
    unsupported = n - supported
    false_support = sum(matrix[label]['supported']
                        for label in ('contradicted', 'not_established'))
    return {
        'cases': n, 'predictions': n - abstentions, 'abstentions': abstentions,
        'correct': correct, 'coverage': (n - abstentions) / n,
        'accuracy_when_predicted': correct / (n - abstentions)
        if n != abstentions else None,
        'unsupported_cases': unsupported,
        'unsupported_as_supported': false_support,
        'unsupported_as_supported_rate': false_support / unsupported,
        'supported_cases': supported,
        'supported_correct': matrix['supported']['supported'],
        'matched_groups': len(groups),
        'complete_matched_groups_correct': sum(all(g) for g in groups.values()),
        'confusion': matrix,
    }


class PretrainedSupportObservedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = read('pretrained_support_cases.json')
        cls.frozen = read('pretrained_support_frozen.json')
        cls.observed = read('pretrained_support_observed.json')
        cls.review = read('pretrained_support_label_review.json')
        cls.cases = cls.fixture['cases']
        cls.by_id = {case['id']: case for case in cls.cases}
        cls.prediction_object = cls.frozen['predictions']
        cls.predictions = {row['case_id']: row['label']
                           for row in cls.prediction_object['predictions']}
        # Reconstruct the documented label-free export, independently of its
        # implementation and without importing runner or optional dependencies.
        cls.inputs = {
            'protocol': 1, 'dataset_sha256': FIXTURE_SHA,
            'cases': [{key: case[key]
                       for key in ('id', 'passages', 'claim', 'citations')}
                      for case in sorted(cls.cases,
                                         key=lambda c: sha(c['id'].encode()))],
        }
        cls.inputs['input_sha256'] = sha(canonical(cls.inputs))

    def test_fixed_bytes_and_all_public_artifact_hashes(self):
        fixed = {
            'evals/pretrained_support_cases.json': FIXTURE_SHA,
            'evals/pretrained_support_frozen.json': FROZEN_SHA,
            'scripts/predict_pretrained_support.py': RUNNER_SHA,
            'scripts/evaluate_claim_support.py': SCHEMA_SHA,
        }
        for path, expected in {**self.observed['artifacts'], **fixed}.items():
            with self.subTest(path=path):
                self.assertFalse(Path(path).is_absolute())
                self.assertNotIn('..', Path(path).parts)
                self.assertEqual(sha((ROOT / path).read_bytes()), expected)
                self.assertEqual(self.observed['artifacts'][path], expected)

    def test_dataset_has_complete_matched_groups_and_exact_citations(self):
        self.assertEqual(len(self.cases), 120)
        self.assertEqual(len(self.by_id), 120)
        self.assertEqual(Counter(c['label'] for c in self.cases),
                         Counter({label: 40 for label in LABELS}))
        groups = defaultdict(list)
        for case in self.cases:
            self.assertEqual(set(case), {'id', 'group_id', 'phenomenon',
                                         'passages', 'claim', 'citations',
                                         'label', 'rationale'})
            groups[case['group_id']].append(case)
            passages = {p['id']: p['text'] for p in case['passages']}
            self.assertEqual(len(passages), len(case['passages']))
            for citation in case['citations']:
                self.assertIn(citation['quote'], passages[citation['passage_id']])
        self.assertEqual(len(groups), 40)
        self.assertEqual(Counter(rows[0]['phenomenon'] for rows in groups.values()),
                         Counter({phenomenon: 5 for phenomenon in PHENOMENA}))
        for rows in groups.values():
            self.assertEqual(len(rows), 3)
            self.assertEqual({row['label'] for row in rows}, set(LABELS))
            self.assertEqual(len({row['claim'] for row in rows}), 3)
            for row in rows[1:]:
                for key in ('passages', 'citations', 'phenomenon'):
                    self.assertEqual(row[key], rows[0][key])

    def test_raw_and_canonical_hashes_and_exact_input_ids(self):
        input_hash = self.inputs['input_sha256']
        for container in (self.frozen, self.observed, self.review,
                          self.prediction_object):
            self.assertEqual(container['input_sha256'], input_hash)
        self.assertEqual(self.frozen['dataset_sha256'], FIXTURE_SHA)
        raw_input_hash = sha(pretty(self.inputs, sort_keys=True))
        self.assertEqual(self.review['source_raw_sha256'], raw_input_hash)
        self.assertNotEqual(raw_input_hash, input_hash)
        self.assertEqual(self.observed['prediction_canonical_sha256'],
                         sha(canonical(self.prediction_object)))
        self.assertEqual(len(self.prediction_object['predictions']), 120)
        self.assertEqual(len(self.predictions), 120)
        self.assertEqual(set(self.predictions), set(self.by_id))
        ids = [case['id'] for case in self.inputs['cases']]
        self.assertEqual(ids, [p['case_id'] for p in self.prediction_object['predictions']])
        self.assertEqual(ids, [t['case_id'] for t in self.frozen['traces']])
        self.assertEqual(ids, [r['case_id'] for r in self.review['cases']])
        for case in self.inputs['cases']:
            self.assertEqual(set(case), {'id', 'passages', 'claim', 'citations'})

    def test_recorded_freeze_binds_actual_identity(self):
        before = self.observed['freeze']['pre_inference']
        after = self.observed['freeze']['post_inference']
        identity = self.frozen['identity']
        self.assertEqual(before['hashes']['runner'], RUNNER_SHA)
        self.assertEqual(before['hashes']['schema'], SCHEMA_SHA)
        self.assertEqual(before['hashes']['fresh_fixture'], FIXTURE_SHA)
        self.assertEqual(before['hashes']['label_free_input'],
                         sha(pretty(self.inputs, sort_keys=True)))
        self.assertEqual(before['hashes']['requirements_lock'], sha(
            (ROOT / 'evals/pretrained_support_requirements.lock').read_bytes()))
        self.assertEqual(identity['runner_sha256'], RUNNER_SHA)
        self.assertEqual(identity['schema_sha256'], SCHEMA_SHA)
        self.assertEqual(after['pre_inference_freeze_sha256'], sha(pretty(before)))
        self.assertEqual(after['files']['fresh-inspect-frozen.json'], FROZEN_SHA)
        self.assertEqual(after['files']['fresh-inputs.json'],
                         before['hashes']['label_free_input'])
        self.assertEqual(after['files']['fresh-predictions-frozen.json'],
                         sha(pretty(self.prediction_object, sort_keys=True)))
        self.assertEqual(after['count'], 120)
        self.assertLess(datetime.fromisoformat(before['time_utc']),
                        datetime.fromisoformat(after['frozen_utc']))
        # These assertions check a recorded claim, not an independent timestamp.
        self.assertTrue(after['candidate_results_not_viewed_before_freeze'])
        self.assertTrue(after['gold_not_read_or_scored_before_freeze'])

    def test_every_logit_argmax_and_full_premise_hash_replays(self):
        policy = self.frozen['policy']
        self.assertEqual(policy['mapping'], list(MODEL_LABELS))
        self.assertEqual(policy['max_pair_tokens'], 512)
        self.assertEqual(policy['premise_separator'], '\n\n')
        self.assertIs(policy['truncation'], False)
        self.assertEqual(policy['decision'], 'argmax; first index on ties; no thresholds')
        self.assertEqual(len(self.frozen['traces']), 120)
        for trace in self.frozen['traces']:
            with self.subTest(case=trace['case_id']):
                case = self.by_id[trace['case_id']]
                raw = trace['raw_logits']
                self.assertEqual(len(raw), 3)
                self.assertTrue(all(type(x) in (int, float) and math.isfinite(x)
                                    for x in raw))
                label = MODEL_LABELS[max(range(3), key=lambda i: raw[i])]
                self.assertEqual(trace['label'], label)
                self.assertEqual(self.predictions[trace['case_id']], label)
                self.assertEqual(trace['reason'], 'three_class_argmax')
                self.assertIs(trace['truncation'], False)
                self.assertIs(type(trace['token_count']), int)
                self.assertGreater(trace['token_count'], 0)
                self.assertLessEqual(trace['token_count'], 512)
                self.assertEqual(trace['passage_count'], len(case['passages']))
                premise = '\n\n'.join(p['text'] for p in case['passages'])
                self.assertEqual(trace['premise_sha256'], sha(premise.encode('utf-8')))

    def test_main_and_every_phenomenon_recount_without_shipped_scorer(self):
        result = summarize(self.cases, self.predictions)
        self.assertEqual(result, self.observed['full_result'])
        self.assertEqual((result['correct'], result['cases']), (73, 120))
        self.assertEqual((result['unsupported_as_supported'],
                          result['unsupported_cases']), (11, 80))
        self.assertEqual((result['supported_correct'], result['supported_cases']), (22, 40))
        self.assertEqual(result['complete_matched_groups_correct'], 9)
        self.assertEqual(result['abstentions'], 0)
        self.assertEqual(set(self.observed['by_phenomenon']), PHENOMENA)
        expected_correct = {'negation': 10, 'quantity': 8, 'quantifiers': 11,
                            'time': 6, 'location': 10, 'conditionals': 9,
                            'attribution': 8, 'cross_source': 11}
        for phenomenon in PHENOMENA:
            cases = [c for c in self.cases if c['phenomenon'] == phenomenon]
            result = summarize(cases, self.predictions)
            self.assertEqual(result, self.observed['by_phenomenon'][phenomenon])
            self.assertEqual(result['correct'], expected_correct[phenomenon])

    def test_split_label_review_agreement_and_all_four_unresolved_flags(self):
        rows = self.review['cases']
        self.assertEqual(len(rows), 120)
        self.assertEqual([row['index'] for row in rows], list(range(120)))
        ranges = [set(range(a['start_inclusive'], a['end_inclusive'] + 1))
                  for a in self.review['assignments']]
        self.assertEqual([len(indices) for indices in ranges], [60, 60])
        self.assertFalse(ranges[0] & ranges[1])
        self.assertEqual(ranges[0] | ranges[1], set(range(120)))
        agreement = sum(row['primary_label'] == self.by_id[row['case_id']]['label']
                        for row in rows)
        self.assertEqual(agreement, 120)
        self.assertEqual(self.observed['label_review']['primary_agreement'], agreement)
        flags = {row['case_id']: row for row in rows if row['ambiguity_flags']}
        self.assertEqual(set(flags), {'xea6c69a8ca13d5b7', 'xf53ad7a513770885',
                                     'x29e7ab12109a5987', 'x10503330bc7b8ce9'})
        self.assertEqual(sorted(flags), self.observed['label_review']['flagged_case_ids'])
        self.assertEqual(Counter(flag['kind'] for row in flags.values()
                                 for flag in row['ambiguity_flags']),
                         Counter({'agency_in_paraphrase': 1,
                                  'earned_versus_received': 2,
                                  'numeral_exhaustivity': 1}))
        for row in flags.values():
            for flag in row['ambiguity_flags']:
                self.assertEqual(flag['alternative_label'], 'not_established')
                self.assertTrue(flag['detail'])
        self.assertIs(self.observed['label_review']['unresolved'], True)

    def test_sensitivity_excludes_every_flagged_whole_group_without_relabeling(self):
        flagged = {row['case_id'] for row in self.review['cases']
                   if row['ambiguity_flags']}
        excluded_groups = {self.by_id[ident]['group_id'] for ident in flagged}
        excluded = [c for c in self.cases if c['group_id'] in excluded_groups]
        kept = [c for c in self.cases if c['group_id'] not in excluded_groups]
        sensitivity = self.observed['ambiguity_excluded_sensitivity']
        self.assertEqual(len(excluded_groups), 3)
        self.assertEqual(len(excluded), 9)
        self.assertEqual(sensitivity['excluded_groups'], sorted(excluded_groups))
        self.assertEqual(self.observed['label_review']['flagged_groups'], sorted(excluded_groups))
        self.assertEqual(sensitivity['excluded_case_ids'], sorted(c['id'] for c in excluded))
        self.assertEqual(sensitivity['result'], summarize(kept, self.predictions))
        result = sensitivity['result']
        self.assertEqual((result['correct'], result['cases']), (69, 111))
        self.assertEqual((result['unsupported_as_supported'],
                          result['unsupported_cases']), (10, 74))
        # Both correct and incorrect outcomes were removed, not just errors.
        self.assertEqual(sum(self.predictions[c['id']] == c['label'] for c in excluded), 4)
        self.assertEqual((result['complete_matched_groups_correct'], result['matched_groups']),
                         (9, 37))

    def test_model_manifest_policy_and_dependency_lock_identity(self):
        tree = ast.parse((ROOT / 'scripts/predict_pretrained_support.py').read_text())
        needed = {'MODEL_ID', 'REVISION', 'WEIGHTS_SHA256', 'ARTIFACT_HASHES',
                  'LABELS', 'MAX_TOKENS', 'SEPARATOR'}
        constants = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id in needed:
                    constants[target.id] = ast.literal_eval(node.value)
        self.assertEqual(set(constants), needed)
        identity = self.frozen['identity']
        self.assertEqual(identity['model_id'], constants['MODEL_ID'])
        self.assertEqual(identity['revision'], constants['REVISION'])
        self.assertEqual(tuple(constants['LABELS']), MODEL_LABELS)
        self.assertEqual(constants['MAX_TOKENS'], 512)
        self.assertEqual(constants['SEPARATOR'], '\n\n')
        manifest = read('pretrained_support_model_manifest.json')
        artifacts = {row['file']: row['sha256'] for row in manifest}
        self.assertEqual(len(manifest), 6)
        self.assertEqual(artifacts, identity['artifact_sha256'])
        self.assertEqual(artifacts, constants['ARTIFACT_HASHES'])
        self.assertEqual(artifacts['model.safetensors'], constants['WEIGHTS_SHA256'])
        for row in manifest:
            self.assertEqual(row['url'], 'https://huggingface.co/' + constants['MODEL_ID']
                             + '/resolve/' + constants['REVISION'] + '/' + row['file'])
            self.assertGreater(row['size'], 0)
        normalize = lambda name: re.sub(r'[-_.]+', '-', name).lower()
        lock = {}
        for line in (ROOT / 'evals/pretrained_support_requirements.lock').read_text().splitlines():
            match = re.fullmatch(r'([A-Za-z0-9_.-]+)==(\S+) --hash=sha256:([a-f0-9]{64})', line)
            self.assertIsNotNone(match)
            name, version, digest = match.groups()
            name = normalize(name)
            self.assertNotIn(name, lock)
            lock[name] = (version, digest)
        wheels = read('pretrained_support_wheels.json')
        self.assertEqual(len(wheels), 25)
        self.assertEqual(len(lock), 25)
        self.assertEqual({normalize(w['name']): (w['version'], w['sha256'])
                          for w in wheels}, lock)
        for wheel in wheels:
            self.assertTrue(wheel['wheel'].endswith('.whl'))
            self.assertGreater(wheel['size'], 0)
            url = urlparse(wheel['source'])
            self.assertEqual(url.scheme, 'https')
            self.assertIn(url.hostname, {'files.pythonhosted.org', 'download.pytorch.org',
                                         'download-r2.pytorch.org'})
        for package in ('torch', 'transformers', 'tokenizers', 'safetensors'):
            self.assertEqual(identity[package], lock[package][0])
        self.assertEqual(identity['device'], 'cpu')
        self.assertEqual((identity['threads'], identity['seed']), (1, 0))
        for key in ('deterministic_algorithms', 'eval', 'offline', 'safetensors_only'):
            self.assertIs(identity[key], True)

    def test_recorded_token_health_and_overflow_are_not_accuracy_claims(self):
        traces = self.frozen['traces']
        health = self.observed['runtime_health']
        counts = [trace['token_count'] for trace in traces]
        self.assertEqual(health['trace_count'], len(traces))
        self.assertEqual(health['reason_counts'], dict(Counter(t['reason'] for t in traces)))
        self.assertEqual((health['minimum_pair_tokens'], health['maximum_pair_tokens']),
                         (min(counts), max(counts)))
        self.assertEqual((min(counts), max(counts), sum(counts)), (44, 96, 7488))
        self.assertEqual(health['pair_limit'], 512)
        self.assertIs(health['truncation'], False)
        self.assertEqual(health['resources']['exit_code'], 0)
        self.assertGreater(health['resources']['wall_seconds'], 0)
        self.assertLess(health['resources']['wall_seconds'], 600)
        overflow = self.observed['real_tokenizer_overflow_control']
        self.assertEqual(overflow['pair_tokens'], 1211)
        self.assertEqual(overflow['label'], 'abstain')
        self.assertEqual(overflow['reason'], 'pair_token_limit_exceeded')
        self.assertEqual(overflow['model_forward_calls'], 0)
        self.assertIs(overflow['truncation'], False)


if __name__ == '__main__':
    unittest.main()
