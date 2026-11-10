"""Replay the first disclosed paired trial using only the standard library.

No scorer/runner import, optional dependency, model load, inference, or network.
These tests establish retained-byte consistency and arithmetic, not independent
execution attestation, gold correctness, calibration, or generalization.
"""
import ast
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODELS = ('minilm', 'deberta')
LABELS = ('supported', 'contradicted', 'not_established')
MODEL_LABELS = ('contradicted', 'supported', 'not_established')
PHENOMENA = {'negation', 'quantity', 'quantifiers', 'time', 'location',
             'conditionals', 'attribution', 'cross_source'}
FIXED_HASHES = {
    'evals/paired_support_cases.json':
        '5efaa7095d8aa8403a2399ec4ce8818cde37f314beca833959b8ffe2d3995686',
    'evals/paired_support_minilm_frozen.json':
        '2db18a68e8aeb2e2d5a80747e3d49cdc9a0a5ceffad55f5fae2e9b4c763e9860',
    'evals/paired_support_deberta_frozen.json':
        '5fa17874f1ba72d511d1544cf3fb4dbe5827be473a8bfb50d136663a339436b6',
    'evals/paired_support_label_review.json':
        '33b7f55ff8d43844db5b45e65650b5825d77d1be179565eeca90b49a85e77a08',
    'scripts/predict_pretrained_support.py':
        '11217322391b15ff6dacb37947f6bafc31b30f9c0abae8d032cec9cf43532e2e',
    'scripts/predict_deberta_support.py':
        'ff0597ba1abbe56c1cdbd238b05c42fd239d220f50e669656a921eab7e208078',
    'scripts/evaluate_claim_support.py':
        'f24f017ad344d572e61979519730c5fc8dbd1be162fb24d648ab66deae04ae13',
    'evals/pretrained_support_requirements.lock':
        'b38cf78afe06f8ccb09d7a10df3c22a0cc45f5ae954ab359d4c87a7073d4a16f',
}
FIXTURE_SHA = FIXED_HASHES['evals/paired_support_cases.json']
INPUT_SHA = '2f5069bdbe645a789b9f18bf3816e363b753569bd4a3a15c462ff17db0ac3ccd'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError('nonfinite JSON value: ' + value)


def read(name):
    return json.loads((ROOT / 'evals' / name).read_text(encoding='utf-8'),
                      object_pairs_hook=unique_object,
                      parse_constant=invalid_constant)


def summarize(cases, predictions):
    """Recount directly; deliberately does not use the shipped evaluator."""
    matrix = {gold: {label: 0 for label in (*LABELS, 'abstain')}
              for gold in LABELS}
    groups = defaultdict(list)
    for case in cases:
        pred = predictions[case['id']]
        matrix[case['label']][pred] += 1
        groups[case['group_id']].append(pred == case['label'])
    total = len(cases)
    abstentions = sum(row['abstain'] for row in matrix.values())
    predicted = total - abstentions
    correct = sum(matrix[label][label] for label in LABELS)
    supported = sum(matrix['supported'].values())
    unsupported = total - supported
    false_support = sum(matrix[label]['supported']
                        for label in ('contradicted', 'not_established'))
    return {
        'cases': total, 'predictions': predicted, 'abstentions': abstentions,
        'correct': correct, 'coverage': predicted / total,
        'accuracy_when_predicted': correct / predicted if predicted else None,
        'unsupported_cases': unsupported,
        'unsupported_as_supported': false_support,
        'unsupported_as_supported_rate': false_support / unsupported,
        'supported_cases': supported,
        'supported_correct': matrix['supported']['supported'],
        'matched_groups': len(groups),
        # A partial group must never count as a successful complete triple.
        'complete_matched_groups_correct': sum(len(g) == 3 and all(g)
                                               for g in groups.values()),
        'confusion': matrix,
    }


def paired(cases, predictions):
    correctness = Counter()
    false_support = Counter()
    new, resolved = [], []
    for case in cases:
        cid, gold = case['id'], case['label']
        a, b = (predictions[m][cid] for m in MODELS)
        correctness[{
            (False, False): 'both_wrong', (True, True): 'both_correct',
            (False, True): 'deberta_only_correct',
            (True, False): 'minilm_only_correct',
        }[(a == gold, b == gold)]] += 1
        if gold != 'supported':
            false_support[{
                (False, False): 'neither_false_support',
                (True, True): 'both_false_support',
                (False, True): 'deberta_only_false_support',
                (True, False): 'minilm_only_false_support',
            }[(a == 'supported', b == 'supported')]] += 1
            if a != 'supported' and b == 'supported':
                new.append(cid)
            if a == 'supported' and b != 'supported':
                resolved.append(cid)
    return {
        'correctness': dict(correctness),
        'unsupported_false_support': dict(false_support),
        'deberta_new_false_support_case_ids': sorted(new),
        'deberta_resolved_false_support_case_ids': sorted(resolved),
    }


def source_constants(path):
    """Read literal pins without importing or executing either runner."""
    result = {}
    for node in ast.parse(path.read_text(encoding='utf-8')).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        try:
            if isinstance(node.value, ast.Dict):
                value = {ast.literal_eval(key):
                         result[val.id] if isinstance(val, ast.Name)
                         else ast.literal_eval(val)
                         for key, val in zip(node.value.keys, node.value.values)}
            else:
                value = ast.literal_eval(node.value)
            result[node.targets[0].id] = value
        except (ValueError, TypeError, KeyError):
            pass
    return result


class PairedSupportObservedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = read('paired_support_cases.json')
        cls.observed = read('paired_support_observed.json')
        cls.review = read('paired_support_label_review.json')
        cls.frozen = {m: read('paired_support_' + m + '_frozen.json')
                      for m in MODELS}
        cls.cases = cls.fixture['cases']
        cls.by_id = {case['id']: case for case in cls.cases}
        cls.predictions = {
            m: {row['case_id']: row['label']
                for row in cls.frozen[m]['predictions']['predictions']}
            for m in MODELS}
        cls.inputs = {
            'protocol': 1, 'dataset_sha256': FIXTURE_SHA,
            'cases': [{key: case[key] for key in
                       ('id', 'passages', 'claim', 'citations')}
                      for case in sorted(cls.cases,
                                         key=lambda c: sha(c['id'].encode()))],
        }
        cls.inputs['input_sha256'] = sha(canonical(cls.inputs))
        cls.groups = defaultdict(list)
        for case in cls.cases:
            cls.groups[case['group_id']].append(case)

    def test_fixed_bytes_and_complete_public_artifact_manifest(self):
        self.assertEqual(self.observed['artifacts'], FIXED_HASHES)
        for name, expected in FIXED_HASHES.items():
            with self.subTest(artifact=name):
                self.assertFalse(Path(name).is_absolute())
                self.assertNotIn('..', Path(name).parts)
                self.assertEqual(sha((ROOT / name).read_bytes()), expected)

    def test_original_fixture_balance_groups_and_citations(self):
        self.assertEqual(len(self.cases), 120)
        self.assertEqual(len(self.by_id), 120)
        self.assertEqual(Counter(c['label'] for c in self.cases),
                         Counter({label: 40 for label in LABELS}))
        self.assertEqual(len(self.groups), 40)
        self.assertEqual(Counter(g[0]['phenomenon'] for g in self.groups.values()),
                         Counter({phenomenon: 5 for phenomenon in PHENOMENA}))
        for group in self.groups.values():
            self.assertEqual(len(group), 3)
            self.assertEqual({c['label'] for c in group}, set(LABELS))
            self.assertEqual(len({c['claim'] for c in group}), 3)
            for case in group:
                self.assertEqual(set(case), {'id', 'group_id', 'phenomenon',
                                            'passages', 'claim', 'citations',
                                            'label', 'rationale'})
                for key in ('passages', 'citations', 'phenomenon'):
                    self.assertEqual(case[key], group[0][key])
                passages = {p['id']: p['text'] for p in case['passages']}
                self.assertEqual(len(passages), len(case['passages']))
                for cite in case['citations']:
                    self.assertIn(cite['quote'], passages[cite['passage_id']])

    def test_same_exact_gold_free_inputs_and_prediction_bindings(self):
        self.assertEqual(self.inputs['input_sha256'], INPUT_SHA)
        self.assertEqual(self.observed['dataset_sha256'], FIXTURE_SHA)
        self.assertEqual(self.observed['input_sha256'], INPUT_SHA)
        self.assertEqual(self.review['input_sha256'], INPUT_SHA)
        raw_inputs = (json.dumps(self.inputs, ensure_ascii=False, sort_keys=True,
                                 indent=2, allow_nan=False) + '\n').encode('utf-8')
        self.assertEqual(self.review['source_raw_sha256'], sha(raw_inputs))
        ids = [c['id'] for c in self.inputs['cases']]
        self.assertEqual(ids, [r['case_id'] for r in self.review['cases']])
        for case in self.inputs['cases']:
            self.assertEqual(set(case), {'id', 'passages', 'claim', 'citations'})
        for model in MODELS:
            with self.subTest(model=model):
                frozen = self.frozen[model]
                prediction = frozen['predictions']
                self.assertEqual(frozen['dataset_sha256'], FIXTURE_SHA)
                self.assertEqual(frozen['input_sha256'], INPUT_SHA)
                self.assertEqual(prediction['input_sha256'], INPUT_SHA)
                self.assertEqual(set(prediction),
                                 {'protocol', 'input_sha256', 'predictions'})
                self.assertEqual(prediction['protocol'], 1)
                self.assertEqual(len(prediction['predictions']), 120)
                self.assertEqual(len(self.predictions[model]), 120)
                self.assertEqual(set(self.predictions[model]), set(self.by_id))
                self.assertEqual(ids, [p['case_id'] for p in prediction['predictions']])
                self.assertEqual(ids, [t['case_id'] for t in frozen['traces']])
                self.assertEqual(self.observed['prediction_canonical_sha256'][model],
                                 sha(canonical(prediction)))

    def test_model_identity_and_frozen_source_pins_without_imports(self):
        names = {'minilm': 'predict_pretrained_support.py',
                 'deberta': 'predict_deberta_support.py'}
        for model in MODELS:
            identity = self.frozen[model]['identity']
            source = 'scripts/' + names[model]
            pins = source_constants(ROOT / source)
            self.assertEqual(identity['runner_sha256'], FIXED_HASHES[source])
            self.assertEqual(identity['schema_sha256'],
                             FIXED_HASHES['scripts/evaluate_claim_support.py'])
            for constant, field in (('MODEL_ID', 'model_id'),
                                    ('REVISION', 'revision'),
                                    ('ARTIFACT_HASHES', 'artifact_sha256')):
                self.assertEqual(pins[constant], identity[field])
            self.assertEqual(pins['WEIGHTS_SHA256'],
                             identity['artifact_sha256']['model.safetensors'])
            self.assertEqual(pins['LABELS'], MODEL_LABELS)
            self.assertEqual(pins['MAX_TOKENS'], 512)
            self.assertEqual(pins['SEPARATOR'], '\n\n')
            self.assertEqual(identity['device'], 'cpu')
            self.assertEqual(identity['threads'], 1)
            self.assertEqual(identity['seed'], 0)
            for flag in ('eval', 'offline', 'safetensors_only',
                         'deterministic_algorithms'):
                self.assertIs(identity[flag], True)
        deberta = self.frozen['deberta']['identity']
        self.assertEqual(deberta['common_runner_sha256'],
                         FIXED_HASHES['scripts/predict_pretrained_support.py'])
        pins = source_constants(ROOT / 'scripts/predict_deberta_support.py')
        self.assertEqual(deberta['artifact_bytes'], pins['ARTIFACT_SIZES'])
        self.assertEqual(deberta['loading_info'], {
            'error_msgs': [], 'missing_keys': [],
            'mismatched_keys': [], 'unexpected_keys': []})
        self.assertTrue(deberta['checkpoint_inventory'][
            'all_loaded_parameters_equal_checkpoint'])

    def test_all_240_logit_mappings_full_premises_and_token_bounds(self):
        expected_policy = {
            'mapping': list(MODEL_LABELS), 'max_pair_tokens': 512,
            'premise_separator': '\n\n', 'truncation': False,
            'decision': 'argmax; first index on ties; no thresholds',
        }
        for model in MODELS:
            self.assertEqual(self.frozen[model]['policy'], expected_policy)
            self.assertEqual(len(self.frozen[model]['traces']), 120)
            for trace in self.frozen[model]['traces']:
                with self.subTest(model=model, case=trace['case_id']):
                    case = self.by_id[trace['case_id']]
                    logits = trace['raw_logits']
                    self.assertEqual(len(logits), 3)
                    self.assertTrue(all(type(x) in (int, float) and math.isfinite(x)
                                        for x in logits))
                    label = MODEL_LABELS[max(range(3), key=lambda i: logits[i])]
                    self.assertEqual(trace['label'], label)
                    self.assertEqual(self.predictions[model][case['id']], label)
                    self.assertEqual(trace['reason'], 'three_class_argmax')
                    self.assertIs(trace['truncation'], False)
                    self.assertIs(type(trace['token_count']), int)
                    self.assertGreater(trace['token_count'], 0)
                    self.assertLessEqual(trace['token_count'], 512)
                    self.assertEqual(trace['passage_count'], len(case['passages']))
                    premise = '\n\n'.join(p['text'] for p in case['passages'])
                    self.assertEqual(trace['premise_sha256'], sha(premise.encode()))

    def test_original_metrics_and_confusion_independently_recount(self):
        expected = {'minilm': (73, 16, 7), 'deberta': (84, 9, 17)}
        for model in MODELS:
            result = summarize(self.cases, self.predictions[model])
            self.assertEqual(self.observed['full_result'][model], result)
            self.assertEqual((result['correct'], result['unsupported_as_supported'],
                              result['complete_matched_groups_correct']),
                             expected[model])
            self.assertEqual(result['cases'], 120)
            self.assertEqual(result['unsupported_cases'], 80)
            self.assertEqual(result['supported_correct'], 22)
            self.assertEqual(result['supported_cases'], 40)
            self.assertEqual(result['abstentions'], 0)

    def test_every_phenomenon_recounts_without_shipped_scorer(self):
        expected = {
            'minilm': {'negation': 14, 'quantity': 6, 'quantifiers': 9,
                       'time': 6, 'location': 10, 'conditionals': 8,
                       'attribution': 9, 'cross_source': 11},
            'deberta': {'negation': 13, 'quantity': 6, 'quantifiers': 13,
                        'time': 10, 'location': 12, 'conditionals': 8,
                        'attribution': 13, 'cross_source': 9},
        }
        for model in MODELS:
            self.assertEqual(set(self.observed['by_phenomenon'][model]), PHENOMENA)
            for phenomenon in PHENOMENA:
                with self.subTest(model=model, phenomenon=phenomenon):
                    cases = [c for c in self.cases if c['phenomenon'] == phenomenon]
                    result = summarize(cases, self.predictions[model])
                    self.assertEqual(result,
                                     self.observed['by_phenomenon'][model][phenomenon])
                    self.assertEqual(result['correct'], expected[model][phenomenon])
                    self.assertEqual(result['cases'], 15)
                    self.assertEqual(result['matched_groups'], 5)
                    self.assertEqual(result['unsupported_cases'], 10)

    def test_paired_correctness_and_false_support_reversals(self):
        result = paired(self.cases, self.predictions)
        self.assertEqual(self.observed['paired_full'], result)
        self.assertEqual(result['correctness'], {
            'both_correct': 64, 'both_wrong': 27,
            'deberta_only_correct': 20, 'minilm_only_correct': 9})
        self.assertEqual(result['unsupported_false_support'], {
            'both_false_support': 6, 'neither_false_support': 61,
            'deberta_only_false_support': 3, 'minilm_only_false_support': 10})
        self.assertEqual(len(result['deberta_new_false_support_case_ids']), 3)
        self.assertEqual(len(result['deberta_resolved_false_support_case_ids']), 10)
        self.assertEqual(84 - 73, 20 - 9)
        self.assertEqual(16 - 9, 10 - 3)

    def test_complete_group_paired_transitions(self):
        transitions = Counter()
        for group in self.groups.values():
            success = tuple(all(self.predictions[m][c['id']] == c['label']
                                for c in group) for m in MODELS)
            transitions[success] += 1
        self.assertEqual(transitions, Counter({
            (True, True): 6, (False, False): 22,
            (False, True): 11, (True, False): 1}))

    def test_one_review_per_case_disjoint_assignments_and_exact_order(self):
        rows = self.review['cases']
        self.assertEqual(len(rows), 120)
        self.assertEqual([r['index'] for r in rows], list(range(120)))
        self.assertEqual(len({r['case_id'] for r in rows}), 120)
        self.assertEqual({r['case_id'] for r in rows}, set(self.by_id))
        self.assertEqual(self.review['assignments'], [
            {'review': 'a', 'start_inclusive': 0, 'end_inclusive': 59},
            {'review': 'b', 'start_inclusive': 60, 'end_inclusive': 119}])
        ranges = [set(range(a['start_inclusive'], a['end_inclusive'] + 1))
                  for a in self.review['assignments']]
        self.assertFalse(ranges[0] & ranges[1])
        self.assertEqual(ranges[0] | ranges[1], set(range(120)))
        for row in rows:
            self.assertIn(row['primary_label'], LABELS)
            self.assertTrue(row['rationale'].strip())
            self.assertIsInstance(row['ambiguity_flags'], list)
            for flag in row['ambiguity_flags']:
                self.assertIn(flag['alternative_label'], LABELS)
                self.assertNotEqual(flag['alternative_label'], row['primary_label'])

    def test_review_primary_disagreements_and_all_flags_are_retained(self):
        rows = self.review['cases']
        disagreements = [
            {'case_id': r['case_id'],
             'original_label': self.by_id[r['case_id']]['label'],
             'review_primary_label': r['primary_label']}
            for r in rows
            if r['primary_label'] != self.by_id[r['case_id']]['label']]
        flags = {r['case_id'] for r in rows if r['ambiguity_flags']}
        affected = flags | {r['case_id'] for r in disagreements}
        groups = {self.by_id[cid]['group_id'] for cid in affected}
        summary = self.observed['label_review']
        self.assertEqual(summary['primary_disagreements'], disagreements)
        self.assertEqual(summary['primary_agreement'], 120 - len(disagreements))
        self.assertEqual(summary['flagged_case_ids'], sorted(flags))
        self.assertEqual(summary['flagged_groups'], sorted(groups))
        self.assertEqual((len(disagreements), len(flags), len(groups)), (8, 12, 6))
        self.assertTrue({r['case_id'] for r in disagreements} <= flags)
        for key in ('unresolved', 'one_independent_review_per_case',
                    'original_labels_and_text_unchanged'):
            self.assertIs(summary[key], True)
        self.assertEqual(summary['cases'], 120)

    def test_exclusion_uses_every_affected_complete_group_not_selected_errors(self):
        affected = {r['case_id'] for r in self.review['cases']
                    if r['ambiguity_flags'] or
                    r['primary_label'] != self.by_id[r['case_id']]['label']}
        groups = {self.by_id[cid]['group_id'] for cid in affected}
        excluded = [c for c in self.cases if c['group_id'] in groups]
        remaining = [c for c in self.cases if c['group_id'] not in groups]
        sensitivity = self.observed['ambiguity_excluded_sensitivity']
        self.assertEqual(sensitivity['excluded_groups'], sorted(groups))
        self.assertEqual(sensitivity['excluded_case_ids'],
                         sorted(c['id'] for c in excluded))
        self.assertEqual((len(excluded), len(remaining)), (18, 102))
        self.assertEqual(len(set(sensitivity['excluded_case_ids'])), 18)
        self.assertTrue(affected <= set(sensitivity['excluded_case_ids']))
        # Six unflagged companions are excluded too, rather than cherry-picked.
        self.assertEqual(len(set(sensitivity['excluded_case_ids']) - affected), 6)
        for group in self.groups.values():
            self.assertIn(sum(c in remaining for c in group), (0, 3))
        for model in MODELS:
            result = summarize(remaining, self.predictions[model])
            self.assertEqual(sensitivity['result'][model], result)
            self.assertEqual(result['matched_groups'], 34)
            self.assertEqual(result['unsupported_cases'], 68)
        self.assertEqual(sensitivity['paired'], paired(remaining, self.predictions))
        self.assertEqual(sensitivity['paired']['correctness'], {
            'both_correct': 54, 'both_wrong': 24,
            'deberta_only_correct': 17, 'minilm_only_correct': 7})

    def test_material_loss_of_cross_source_coverage_is_reproducible(self):
        excluded = set(self.observed['ambiguity_excluded_sensitivity'][
            'excluded_case_ids'])
        coverage = Counter(c['phenomenon'] for c in self.cases
                           if c['id'] not in excluded)
        self.assertEqual(dict(coverage), self.observed[
            'ambiguity_excluded_sensitivity']['remaining_cases_by_phenomenon'])
        self.assertEqual(coverage, Counter({
            'cross_source': 3, 'location': 12, 'quantifiers': 12,
            'negation': 15, 'quantity': 15, 'time': 15,
            'conditionals': 15, 'attribution': 15}))
        lost_groups = Counter(g[0]['phenomenon'] for g in self.groups.values()
                              if g[0]['id'] in excluded)
        self.assertEqual(lost_groups,
                         Counter({'cross_source': 4, 'location': 1, 'quantifiers': 1}))

    def test_two_new_false_supports_survive_every_flagged_group_exclusion(self):
        new = self.observed['ambiguity_excluded_sensitivity']['paired'][
            'deberta_new_false_support_case_ids']
        self.assertEqual(set(new), {'9cec964c26804fb3af471484a4856475',
                                    '644ecee72a2244bab786f3ceef6319fb'})
        reviews = {r['case_id']: r for r in self.review['cases']}
        for cid in new:
            self.assertFalse(reviews[cid]['ambiguity_flags'])
            self.assertEqual(reviews[cid]['primary_label'], self.by_id[cid]['label'])
            self.assertNotEqual(self.by_id[cid]['label'], 'supported')
            self.assertEqual(self.predictions['deberta'][cid], 'supported')
            self.assertNotEqual(self.predictions['minilm'][cid], 'supported')

    def test_runtime_health_recounts_traces_without_retokenizing(self):
        expected = {'minilm': (46, 82, 7386), 'deberta': (43, 78, 7067)}
        for model in MODELS:
            traces = self.frozen[model]['traces']
            health = self.observed['runtime_health'][model]
            tokens = [t['token_count'] for t in traces]
            self.assertEqual(health['trace_count'], len(traces))
            self.assertEqual(health['reason_counts'],
                             dict(Counter(t['reason'] for t in traces)))
            self.assertEqual((health['minimum_pair_tokens'],
                              health['maximum_pair_tokens'],
                              health['total_pair_tokens']),
                             (min(tokens), max(tokens), sum(tokens)))
            self.assertEqual((min(tokens), max(tokens), sum(tokens)), expected[model])
            self.assertIs(health['truncation'], False)
            resources = health['resources']
            self.assertEqual(resources['exit_code'], 0)
            self.assertIs(resources['timeout'], False)
            self.assertEqual(resources['address_space_limit_bytes'], 6 * 1024 ** 3)
            self.assertGreater(resources['wall_seconds'], 0)
            self.assertLess(resources['wall_seconds'], 600)
            self.assertGreater(resources['max_rss_kib_linux'], 0)
            self.assertIn('including checks/loading', resources['scope'])

    def test_recorded_chronology_and_authorship_caveats_do_not_claim_attestation(self):
        chronology = self.observed['chronology']
        commit = '03ae646fd8e30a7b3a50f6a38325e141296ecf17'
        self.assertEqual(chronology['candidate_freeze_commit'], commit)
        self.assertEqual(chronology['candidate_freeze_link'],
                         'https://github.com/zalaknshah/jain-ai-brain/commit/' + commit)
        self.assertLess(datetime.fromisoformat(chronology['pre_inference_utc']),
                        datetime.fromisoformat(chronology['post_inference_utc']))
        self.assertEqual(chronology['order'], list(MODELS))
        self.assertEqual(chronology['inference_runs_per_model'], 1)
        self.assertIs(chronology['first_outputs_preserved'], True)
        self.assertIn('not external execution attestation', chronology['limits'])
        author = self.observed['authorship']
        self.assertEqual((author['new_cases'], author['groups'], author['phenomena']),
                         (120, 40, 8))
        self.assertIn('model-family', author['blinding_limit'])
        self.assertIn('not claimed', author['blinding_limit'])
        self.assertIn('overstates', author['archived_scope_correction'])
        self.assertIn('historical input', author['archived_scope_correction'])

    def test_public_docs_preserve_limits_regressions_and_loss_of_coverage(self):
        doc = (ROOT / 'docs/PAIRED_SUPPORT_RESULTS.md').read_text(encoding='utf-8')
        text = ' '.join(doc.split())
        for required in ('73/120', '84/120', '16/80', '9/80', '61/102', '71/102',
                         '112/120', '12 flagged cases across six groups',
                         'four of five cross-source groups',
                         'Perfect model-identity blinding is not claimed',
                         'not 120 independent trials',
                         'not an OS network namespace',
                         'not extra performance samples'):
            self.assertIn(required, text)
        self.assertIn('PAIRED_SUPPORT_RESULTS.md',
                      (ROOT / 'docs/DEBERTA_SUPPORT_COMPARISON.md').read_text())
        for name in ('paired_support_cases.json', 'paired_support_minilm_frozen.json',
                     'paired_support_deberta_frozen.json',
                     'paired_support_label_review.json', 'paired_support_observed.json'):
            artifact = (ROOT / 'evals' / name).read_text(encoding='utf-8')
            for private_prefix in ('/workspace/', '/home/agent/', '/tmp/'):
                self.assertNotIn(private_prefix, artifact)
        for private_prefix in ('/workspace/', '/home/agent/', '/tmp/'):
            self.assertNotIn(private_prefix, doc)

    def test_replay_helpers_do_not_credit_partial_groups_or_zero_coverage(self):
        group = list(self.groups.values())[0]
        perfect = {c['id']: c['label'] for c in group}
        self.assertEqual(summarize(group, perfect)['complete_matched_groups_correct'], 1)
        self.assertEqual(summarize(group[:2], perfect)['complete_matched_groups_correct'], 0)
        abstain = {c['id']: 'abstain' for c in group}
        result = summarize(group, abstain)
        self.assertEqual((result['correct'], result['coverage'],
                          result['complete_matched_groups_correct']), (0, 0, 0))
        self.assertIsNone(result['accuracy_when_predicted'])


if __name__ == '__main__':
    unittest.main()
