"""Disclosed development tests, not held-out or independent-oracle evidence."""
import copy
import hashlib
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('scoped_support_candidate',
                                             ROOT / 'scripts' / 'predict_scoped_support.py')
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)
E = C.load_evaluator()


def make_case(text='World f: Object A is p.', claim='World f: Object A is p.', ident='dev'):
    texts = [text] if isinstance(text, str) else text
    passages = [{'id': f'p{i}', 'text': value} for i, value in enumerate(texts, 1)]
    return {'id': ident, 'passages': passages, 'claim': claim,
            'citations': [{'passage_id': 'p1', 'quote': texts[0][:1]}]}


def envelope(cases=None):
    value = {'protocol': 1, 'dataset_sha256': '0' * 64,
             'cases': [make_case()] if cases is None else cases}
    value['input_sha256'] = hashlib.sha256(E.canonical_bytes(value)).hexdigest()
    return value


def row(text='World f: Object A is p.', claim='World f: Object A is p.'):
    return C.inspect_case(make_case(text, claim), E.canonical_bytes)


def invoke(path, operation='inspect', script=None):
    return subprocess.run([sys.executable, '-B', str(script or C.SOURCE_PATH), operation,
                           '--inputs', str(path)], capture_output=True, timeout=30,
                          env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})


def overflow_envelope():
    """A disclosed packaging stress fixture, not hidden evaluation material."""
    keys = [letter * 16 + '/' + 'v' * 16 + '/' + 'e' * 16 for letter in 'abcd']
    entity, predicate = 'A' + 'a' * 31, 'p' * 24
    statements = []
    for index in range(32):
        ref = keys[index % 4] + '#r' + str(index).zfill(15)
        frame = chr(102 + index % 4) * 16
        statements.extend([f'Report {ref} {frame}: Object {entity} is {predicate}.'] * 2)
    texts = [' '.join(statements[index * 32:(index + 1) * 32]) for index in range(2)]
    claim = f'Account [{",".join(keys)}] {"f" * 16}: Object {entity} is {predicate}.'
    return envelope([make_case(texts, claim, f'dev-overflow-{index}') for index in range(64)])


class SolverTests(unittest.TestCase):
    def test_complete_two_variable_clause_families(self):
        # A small exhaustive development check of this solver, not an input oracle.
        clauses = list(itertools.combinations_with_replacement(range(4), 2))
        for count in range(4):
            for selected in itertools.combinations_with_replacement(clauses, count):
                models = [values for values in itertools.product((False, True), repeat=2)
                          if all(any(values[lit // 2] == bool(lit % 2) for lit in clause)
                                 for clause in selected)]
                self.assertEqual(C.sat(2, selected), bool(models), selected)
                for literal in range(4):
                    possible = [values for values in models
                                if values[literal // 2] == bool(literal % 2)]
                    expected = list(min(possible)) if possible else None
                    self.assertEqual(C.smallest_witness(2, selected, literal), expected, selected)

    def test_long_implication_cycle_and_contradiction(self):
        clauses = [(2 * i, 2 * ((i + 1) % 10) + 1) for i in range(10)]
        self.assertTrue(C.sat(10, clauses))
        self.assertEqual(C.smallest_witness(10, clauses, 1), [True] * 10)
        self.assertFalse(C.sat(10, clauses + [(1, 1), (18, 18)]))


class GrammarAndIntegrityTests(unittest.TestCase):
    def test_claim_family_normalization_and_key_order(self):
        parsed = C.parse_claim('  Account [z/v/e,a/v/e] f: Object Ada is not red.  ')
        self.assertEqual(parsed, ['account', ['a/v/e', 'z/v/e'], 'f',
                                  ['fact', 'Ada', 'red', False]])
        self.assertEqual(C.parse_claim('Not-asserts a/v/e f: Object A is p.')[0], 'not_asserts')

    def test_claim_rejects_every_unsupported_suffix_and_constructor(self):
        invalid = ['Object A is p.', 'World f: Every p object is q.',
                   'Report a/v/e#x f: Object A is p.', 'True a/v/e#x.', 'Complete a/v/e.',
                   'World f: Object A is p', 'World f: Object A is p..',
                   'World f: Object A is p. World f: Object A is q.',
                   'World f: Object A is p .', '\u00a0World f: Object A is p.',
                   'Account [a/v/e,a/v/e] f: Object A is p.',
                   'Account [a/v/e, b/v/e] f: Object A is p.',
                   'Account [a/v/e,b/v/e,c/v/e,d/v/e,e/v/e] f: Object A is p.']
        for claim in invalid:
            with self.subTest(claim=claim):
                result = row(claim=claim)
                self.assertEqual(result['reason'], 'unsupported_claim_grammar')
                self.assertEqual(result['details'], {})
                self.assertTrue(all(result[name] is None for name in (
                    'query', 'counts', 'symbols', 'records', 'references', 'diagnostics', 'evaluation')))

    def test_token_bounds_and_reserved_predicates(self):
        self.assertIsNotNone(C.parse_body('Object ' + 'A' + 'a' * 31 + ' is ' + 'p' * 24))
        for body in ['Object ' + 'A' + 'a' * 32 + ' is p', 'Object A is ' + 'p' * 25,
                     'Object a is p', 'Object AB is p', 'Object A is P', 'Object A is p2',
                     'Object A  is p', 'Every p object is  q']:
            self.assertIsNone(C.parse_body(body), body)
        for predicate in C.RESERVED:
            self.assertIsNone(C.parse_body('Object A is ' + predicate))
            self.assertIsNone(C.parse_body('Every p object is ' + predicate))
            self.assertIsNone(C.parse_body('No ' + predicate + ' object is p'))
        self.assertIsNotNone(C.parse_claim('World ' + 'a' * 16 + ': Object A is p.'))
        self.assertIsNone(C.parse_claim('World ' + 'a' * 17 + ': Object A is p.'))

    def test_passages_consumed_in_order_even_when_uncited(self):
        result = row(['World f: Object A is p.',
                      'World f: Object A is q. Unsupported. World f: Object A is p'])
        self.assertEqual(result['reason'], 'unsupported_passage_grammar')
        self.assertEqual(result['details'], {'passage_index': 2, 'passage_id': 'p2', 'statement_index': 2})
        for text, index in [('World f: Object A is p..', 2), ('.', 1),
                            ('World f: Object A is p', 1),
                            ('World f: Object A is p. World f: Object A is q', 2),
                            ('World f: Object A is p .', 1)]:
            self.assertEqual(row(text)['details']['statement_index'], index)

    def test_record_positions_whitespace_aliases_and_zero_separator(self):
        result = row(['  World f: Object A is p.World f: Every p object is not q. ',
                      ' World f: No p object is q.  '])
        self.assertEqual(result['counts']['statements'], 3)
        self.assertEqual([r['ordinal'] for r in result['records']], [1, 2, 3])
        self.assertEqual([r['statement_index'] for r in result['records']], [1, 2, 1])
        self.assertEqual(result['records'][2]['text'], 'World f: No p object is q')
        self.assertEqual(result['records'][1]['node'], result['records'][2]['node'])

    def test_first_stage_wins_and_no_partial_trace(self):
        self.assertEqual(row('Malformed.', 'bad')['reason'], 'unsupported_claim_grammar')
        text = 'World f: Object A is p.' * 65 + 'Malformed.'
        result = row(text)
        self.assertEqual(result['reason'], 'unsupported_passage_grammar')
        self.assertEqual(result['details']['statement_index'], 66)
        result = row('World f: Object A is p.' * 65)
        self.assertEqual(result['reason'], 'statement_limit')
        self.assertEqual(result['details'], {'statement_count': 65, 'maximum': 64})
        self.assertEqual(row('World f: Object A is p.' * 64)['counts']['statements'], 64)

    def test_all_symbol_dimensions_count_before_reference_errors(self):
        text = ' '.join(f'Report s{i % 5}/v/e#r f{i % 5}: Object {chr(65 + i)} is a{chr(97 + i)}.'
                        for i in range(11)) + ' True missing/v/e#x.'
        result = row(text, 'World f0: Object A is aa.')
        self.assertEqual(result['reason'], 'symbol_limit')
        self.assertEqual(result['details'], {'counts': {'entities': 11, 'properties': 11,
                                                       'frames': 5, 'source_keys': 6},
                                             'exceeded': ['entities', 'properties', 'frames', 'source_keys']})

    def test_query_only_and_true_only_symbols_are_counted(self):
        text = ' '.join(f'World f: Object {chr(65 + i)} is p.' for i in range(8))
        self.assertEqual(row(text, 'World f: Object I is p.')['details']['exceeded'], ['entities'])
        text = ' '.join(f'Complete k{i}/v/e.' for i in range(4)) + ' True k4/v/e#x.'
        self.assertEqual(row(text)['details']['exceeded'], ['source_keys'])

    def test_exact_symbol_limits_are_admitted(self):
        text = ' '.join(f'Report s{i % 4}/v/e#r{i} f{i % 4}: '
                        f'Object {chr(65 + i)} is {chr(97 + i)}.' for i in range(8))
        text += ' World f0: Every i object is j.'
        result = row(text, 'World f0: Object A is a.')
        self.assertEqual({name: result['counts'][name] for name in C.DIMENSIONS},
                         {'entities': 8, 'properties': 10, 'frames': 4, 'source_keys': 4})
        self.assertTrue(result['diagnostics']['scan_complete'])

    def test_reference_limit_and_conflict_precedence(self):
        text = ' '.join(f'True a/v/e#r{i}.' for i in range(33))
        result = row(text)
        self.assertEqual(result['reason'], 'reference_limit')
        self.assertEqual(result['details'], {'reference_count': 33, 'maximum': 32})
        text = ('Report a/v/e#x f: Object A is p. Report a/v/e#x g: Object A is p. '
                'Report a/v/e#y f: No p object is q. Report a/v/e#y f: No q object is p. '
                'True a/v/e#z.')
        result = row(text)
        self.assertEqual(result['reason'], 'conflicting_report_reference')
        self.assertEqual(result['details'], {'references': ['a/v/e#x', 'a/v/e#y']})
        self.assertEqual(row('True a/v/e#z. True a/v/e#b.')['details'],
                         {'references': ['a/v/e#b', 'a/v/e#z']})

    def test_alias_duplicate_payload_and_complete_provenance(self):
        text = ('True a/v/e#x. Report a/v/e#x f: No p object is q. '
                'Report a/v/e#x f: Every p object is not q. True a/v/e#x. '
                'World f: Object A is p.')
        result = row(text, 'World f: Object A is not q.')
        self.assertEqual(result['label'], 'supported')
        self.assertEqual(result['references'], [{'ref': 'a/v/e#x', 'frame': 'f',
            'body': ['rule', 'p', 'q', False], 'report_ordinals': [2, 3], 'true_ordinals': [1, 4]}])
        self.assertEqual(result['diagnostics']['inventory'][0]['admissions'],
                         [['bridge', 1, 'a/v/e#x'], ['bridge', 4, 'a/v/e#x'], ['world', 5]])
        self.assertEqual(len(result['evaluation']['target_constraints']), 2)


class ScopeAndSemanticsTests(unittest.TestCase):
    def test_world_account_and_bridge_isolation(self):
        samples = [
            ('Report a/v/e#x f: Object A is p.', 'World f: Object A is p.', 'not_established'),
            ('Report a/v/e#x f: Object A is p. True a/v/e#x.', 'World f: Object A is p.', 'supported'),
            ('World f: Object A is p.', 'Account [a/v/e] f: Object A is p.', 'not_established'),
            ('Report a/v/e#x f: Object A is p.', 'Account [a/v/e] f: Object A is p.', 'supported'),
            ('Report a/v/e#x g: Object A is p. True a/v/e#x.', 'World f: Object A is p.', 'not_established'),
            ('Report a/v/e#x f: Object A is p. Report a/v/e#y f: Object A is q. True a/v/e#x.',
             'World f: Object A is q.', 'not_established'),
            ('Report a/v/e#x f: Every p object is q. True a/v/e#x. World f: Object A is p.',
             'World f: Object A is q.', 'supported'),
            ('Report a/v/e#x f: Object A is p. Report b/v/e#y f: Every p object is q.',
             'Account [a/v/e,b/v/e] f: Object A is q.', 'supported'),
            ('Report a/v/e#x f: Object A is p.', 'Account [a/v/whole] f: Object A is p.', 'not_established'),
            ('Complete a/v/e.', 'Account [a/v/e] f: Object A is p.', 'not_established'),
        ]
        for text, claim, expected in samples:
            with self.subTest(claim=claim, text=text):
                self.assertEqual(row(text, claim)['label'], expected)

    def test_material_implication_contraposition_vacuity_and_self_rules(self):
        samples = [
            ('World f: Object A is not q. World f: Every p object is q.', 'Object A is not p', 'supported'),
            ('World f: Object A is q. World f: Every p object is q.', 'Object A is p', 'not_established'),
            ('World f: Every p object is q.', 'Object A is q', 'not_established'),
            ('World f: Object A is p. World f: No p object is q.', 'Object A is q', 'contradicted'),
            ('World f: Every p object is p.', 'Object A is p', 'not_established'),
            ('World f: No p object is p.', 'Object A is not p', 'supported'),
            ('World f: No p object is p. World f: Object A is p.', 'Object A is p', 'abstain'),
            ('World f: No p object is q. World f: Object A is q.', 'Object A is not p', 'supported'),
        ]
        for text, fact, expected in samples:
            self.assertEqual(row(text, f'World f: {fact}.')['label'], expected)

    def test_direct_membership_not_inference_or_opposite_literal(self):
        text = ('Report a/v/e#x f: Object A is p. Report a/v/e#y f: Every p object is q. '
                'Complete a/v/e.')
        self.assertEqual(row(text, 'Asserts a/v/e f: Object A is q.')['label'], 'contradicted')
        self.assertEqual(row(text, 'Account [a/v/e] f: Object A is q.')['label'], 'supported')
        self.assertEqual(row(text, 'Asserts a/v/e f: Object A is not p.')['label'], 'contradicted')
        self.assertEqual(row(text.replace('Complete a/v/e.', ''),
                             'Asserts a/v/e f: Object A is not p.')['label'], 'not_established')

    def test_outer_negation_and_complete_snapshot_across_frames(self):
        for prefix, expected in [('Asserts', 'contradicted'), ('Not-asserts', 'supported')]:
            result = row('Complete a/v/e.', f'{prefix} a/v/e other: Object A is not p.')
            self.assertEqual(result['label'], expected)
            self.assertEqual(result['evaluation']['complete_ordinals'], [1])
        text = 'Complete a/v/e. Report a/v/e#x f: Object A is p. Complete a/v/e.'
        result = row(text, 'Not-asserts a/v/e f: Object A is p.')
        self.assertEqual(result['label'], 'contradicted')
        self.assertEqual(result['evaluation']['matching_report_ordinals'], [2])
        self.assertEqual(result['evaluation']['complete_ordinals'], [1, 3])
        self.assertEqual(row(text, 'Asserts a/v2/e f: Object A is p.')['label'], 'not_established')

    def test_local_conflict_policy_and_connecting_rule(self):
        text = ('World f: Object A is p. World f: Object A is q. '
                'World f: Object A is not q. World f: Object B is not p.')
        result = row(text)
        self.assertEqual(result['label'], 'supported')
        self.assertEqual(result['evaluation']['component'], ['p'])
        self.assertEqual(result['evaluation']['true_witness'], [True])
        components = result['diagnostics']['inventory'][0]['components']
        self.assertEqual(components, [{'predicates': ['p'], 'inconsistent_entities': []},
                                      {'predicates': ['q'], 'inconsistent_entities': ['A']}])
        connected = row(text + ' World f: Every q object is p.')
        self.assertEqual(connected['label'], 'abstain')
        self.assertEqual(connected['reason'], 'relevant_inconsistent_context')
        for key in ('satisfiable', 'true_possible', 'false_possible'):
            self.assertIs(connected['evaluation'][key], False)
        self.assertIsNone(connected['evaluation']['true_witness'])
        self.assertIsNone(connected['evaluation']['false_witness'])

    def test_membership_retains_answer_with_inconsistent_account(self):
        text = 'Report a/v/e#x f: Object A is p. Report a/v/e#y f: Object A is not p.'
        result = row(text, 'Asserts a/v/e f: Object A is p.')
        self.assertEqual(result['label'], 'supported')
        self.assertTrue(result['diagnostics']['scan_complete'])
        self.assertFalse(result['diagnostics']['inventory'][1]['consistent'])

    def test_mandatory_inventory_exact_scope_order_and_all_entities(self):
        text = ('Report b/v/e#x g: Object B is p. Report a/v/e#x f: Object C is q. '
                'Report a/v/e#y f: Object C is not q. Complete d/v/e. '
                'World z: Object D is r.')
        result = row(text, 'Account [b/v/e,a/v/e] h: Object A is s.')
        inventory = result['diagnostics']['inventory']
        self.assertEqual([entry['scope'] for entry in inventory], [
            ['world', 'f'], ['world', 'g'], ['world', 'h'], ['world', 'z'],
            ['account', ['a/v/e'], 'f'], ['account', ['a/v/e'], 'h'],
            ['account', ['a/v/e', 'b/v/e'], 'h'],
            ['account', ['b/v/e'], 'g'], ['account', ['b/v/e'], 'h']])
        self.assertEqual(result['diagnostics']['entity_universe'], ['A', 'B', 'C', 'D'])
        self.assertEqual(inventory[0]['components'], [{'predicates': ['s'], 'inconsistent_entities': []}])
        self.assertEqual(inventory[4]['components'], [
            {'predicates': ['q'], 'inconsistent_entities': ['C']},
            {'predicates': ['s'], 'inconsistent_entities': []}])
        self.assertEqual(result['label'], 'not_established')

    def test_union_conflict_does_not_change_individual_account_diagnostics(self):
        text = 'Report a/v/e#x f: Object A is p. Report b/v/e#x f: Object A is not p.'
        result = row(text, 'Account [b/v/e,a/v/e] f: Object A is p.')
        self.assertEqual(result['label'], 'abstain')
        self.assertEqual([entry['consistent'] for entry in result['diagnostics']['inventory']],
                         [True, True, False, True])

    def test_witnesses_false_first_in_predicate_order_and_negative_query(self):
        text = 'World f: Every p object is q. World f: Every q object is r.'
        positive = row(text, 'World f: Object A is q.')['evaluation']
        self.assertEqual(positive['component'], ['p', 'q', 'r'])
        self.assertEqual(positive['true_witness'], [False, True, True])
        self.assertEqual(positive['false_witness'], [False, False, False])
        negative = row(text, 'World f: Object A is not q.')['evaluation']
        self.assertEqual(negative['true_witness'], positive['false_witness'])
        self.assertEqual(negative['false_witness'], positive['true_witness'])

    def test_equivalent_distinct_rule_tuples_survive_deduplication(self):
        text = ('World f: No p object is q. World f: No q object is p. '
                'World f: Every p object is not q. World f: Every p object is p.')
        result = row(text)
        constraints = result['evaluation']['target_constraints']
        self.assertEqual(len(constraints), 3)
        self.assertEqual(constraints, sorted(constraints, key=E.canonical_bytes))
        self.assertEqual(len(result['diagnostics']['inventory'][0]['admissions']), 4)


class EnvelopeAndPackagingTests(unittest.TestCase):
    def test_envelope_shape_text_ids_citations_hashes_and_duplicate_ids(self):
        valid = envelope()
        self.assertEqual(C.validate_inputs(valid, E), valid)
        variants = []
        for key, value in [('protocol', True), ('dataset_sha256', 'A' * 64),
                           ('input_sha256', '0' * 64), ('cases', []), ('extra', 1)]:
            item = copy.deepcopy(valid)
            item[key] = value
            variants.append(item)
        for mutate in [
            lambda x: x['cases'].append(copy.deepcopy(x['cases'][0])),
            lambda x: x['cases'][0].update(label='supported'),
            lambda x: x['cases'][0].update(id='non ascii\u00e9'),
            lambda x: x['cases'][0].update(claim='x' * 2001),
            lambda x: x['cases'][0].update(claim='\ue000'),
            lambda x: x['cases'][0].update(claim='\u200b'),
            lambda x: x['cases'][0].update(citations=[]),
            lambda x: x['cases'][0]['passages'].append(copy.deepcopy(x['cases'][0]['passages'][0])),
            lambda x: x['cases'][0]['citations'].append(copy.deepcopy(x['cases'][0]['citations'][0])),
            lambda x: x['cases'][0]['citations'][0].update(quote='not an excerpt'),
            lambda x: x['cases'][0]['citations'][0].update(passage_id='missing'),
        ]:
            item = copy.deepcopy(valid)
            mutate(item)
            variants.append(item)
        for value in variants:
            with self.assertRaises(ValueError):
                C.validate_inputs(value, E)

    def test_prediction_shape_hashes_complete_trace_and_determinism(self):
        inputs = envelope([make_case(ident='z'), make_case(claim='bad', ident='a')])
        prediction_bytes, trace_bytes = C.build_outputs(inputs, E)
        self.assertEqual(C.build_outputs(inputs, E), (prediction_bytes, trace_bytes))
        prediction, trace = json.loads(prediction_bytes), json.loads(trace_bytes)
        self.assertEqual(prediction, {'protocol': 1, 'input_sha256': inputs['input_sha256'],
                                     'predictions': [{'case_id': 'z', 'label': 'supported'},
                                                     {'case_id': 'a', 'label': 'abstain'}]})
        self.assertEqual(set(trace), {'trace_protocol', 'candidate', 'contract', 'bindings', 'cases'})
        self.assertEqual(trace['bindings'], {
            'candidate_source_sha256': hashlib.sha256(C.SOURCE_PATH.read_bytes()).hexdigest(),
            'evaluator_source_sha256': hashlib.sha256(C.EVALUATOR_PATH.read_bytes()).hexdigest(),
            'contract_sha256': hashlib.sha256(C.CONTRACT_PATH.read_bytes()).hexdigest(),
            'input_sha256': inputs['input_sha256'], 'dataset_sha256': inputs['dataset_sha256'],
            'prediction_sha256': hashlib.sha256(prediction_bytes).hexdigest()})
        self.assertEqual(trace_bytes, E.canonical_bytes(trace))
        E.validate_predictions(prediction, inputs)

    def test_trace_cap_excludes_newline_and_applies_before_both_outputs(self):
        inputs = envelope()
        expected = C.build_outputs(inputs, E)
        with mock.patch.object(C, 'TRACE_LIMIT', len(expected[1])):
            self.assertEqual(C.build_outputs(inputs, E), expected)
        with mock.patch.object(C, 'TRACE_LIMIT', len(expected[1]) - 1):
            with self.assertRaises(C.TraceOverflow):
                C.build_outputs(inputs, E)
        invalid = copy.deepcopy(inputs)
        invalid['cases'][-1]['extra'] = True
        with mock.patch.object(C, 'TRACE_LIMIT', 1):
            with self.assertRaises(C.InvalidInput):
                C.build_outputs(invalid, E)

    def test_cli_success_canonical_newline_and_same_prediction_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.json'
            path.write_bytes(E.canonical_bytes(envelope()))
            prediction, trace = invoke(path, 'predict'), invoke(path)
            for result in (prediction, trace):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, b'')
                self.assertEqual(result.stdout, E.canonical_bytes(json.loads(result.stdout)) + b'\n')
            self.assertEqual(json.loads(trace.stdout)['bindings']['prediction_sha256'],
                             hashlib.sha256(prediction.stdout[:-1]).hexdigest())

    def test_cli_invalid_transport_and_json_fail_atomically(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.json'
            bad = [b'\xff', b'{', b'{"protocol":1,"protocol":1}', b'NaN', b'Infinity',
                   b'[' * 2000 + b'0' + b']' * 2000, b' ' * (2_097_152 + 1),
                   E.canonical_bytes({**envelope(), 'input_sha256': 'f' * 64})]
            for raw in bad:
                path.write_bytes(raw)
                result = invoke(path)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (2, b'', b'{"error":"invalid_input"}\n'))
            for missing in (Path(temp), Path(temp) / 'missing'):
                result = invoke(missing)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (2, b'', b'{"error":"invalid_input"}\n'))

    def test_actual_size_trace_overflow_is_atomic_for_both_operations(self):
        inputs = overflow_envelope()
        C.validate_inputs(inputs, E)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.json'
            original = E.canonical_bytes(inputs)
            self.assertLess(len(original), 2_097_152)
            path.write_bytes(original)
            for operation in ('predict', 'inspect'):
                result = invoke(path, operation)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (2, b'', b'{"error":"trace_overflow"}\n'))
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(list(Path(temp).iterdir()), [path])
            inputs['cases'][-1]['extra'] = True
            path.write_bytes(E.canonical_bytes(inputs))
            result = invoke(path, 'predict')
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (2, b'', b'{"error":"invalid_input"}\n'))

    @unittest.skipUnless(hasattr(os, 'mkfifo') and hasattr(os, 'O_NONBLOCK'), 'requires POSIX FIFO')
    def test_fifo_is_not_read_and_regular_file_symlink_is_eligible(self):
        with tempfile.TemporaryDirectory() as temp:
            fifo = Path(temp) / 'fifo'
            os.mkfifo(fifo)
            result = invoke(fifo)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (2, b'', b'{"error":"invalid_input"}\n'))
            target, link = Path(temp) / 'input.json', Path(temp) / 'link.json'
            target.write_bytes(E.canonical_bytes(envelope()))
            link.symlink_to(target)
            self.assertEqual(invoke(link).returncode, 0)

    def test_missing_nonblocking_capability_and_binding_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.json'
            path.write_bytes(E.canonical_bytes(envelope()))
            flag = os.O_NONBLOCK
            del os.O_NONBLOCK
            try:
                with self.assertRaises(ValueError):
                    E.read_json(path)
                with mock.patch.object(sys, 'stderr', io.StringIO()) as stderr:
                    self.assertEqual(C.main(['predict', '--inputs', str(path)]), 2)
                    self.assertEqual(stderr.getvalue(), '{"error":"invalid_input"}\n')
            finally:
                os.O_NONBLOCK = flag
            # A relocated standalone script must not silently use an absent or changed contract.
            scripts, docs = Path(temp) / 'scripts', Path(temp) / 'docs'
            scripts.mkdir()
            docs.mkdir()
            script = scripts / C.SOURCE_PATH.name
            script.write_bytes(C.SOURCE_PATH.read_bytes())
            (scripts / C.EVALUATOR_PATH.name).write_bytes(C.EVALUATOR_PATH.read_bytes())
            for contract_bytes in (None, b'changed contract'):
                if contract_bytes is not None:
                    (docs / C.CONTRACT_PATH.name).write_bytes(contract_bytes)
                result = invoke(path, script=script)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (2, b'', b'{"error":"execution_failure"}\n'))
            (docs / C.CONTRACT_PATH.name).write_bytes(C.CONTRACT_PATH.read_bytes())
            (scripts / C.EVALUATOR_PATH.name).write_text('raise AssertionError("must not execute")')
            result = invoke(path, script=script)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (2, b'', b'{"error":"execution_failure"}\n'))


if __name__ == '__main__':
    unittest.main()
