"""Independent global truth-table oracle. No candidate parser/solver helpers.

Theories are symbolic first, then rendered. No challenge fixtures are read.
"""
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('controlled_candidate_oracle_target', ROOT / 'scripts/predict_controlled_support.py')
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)
EXPECTED_HASH = '2ad4fd5c50d681f62dcc94fc3ba2f994e23fbd0bd7ebf31409703bdf18fb0262'
ENTITIES = ('Aster', 'Birch')
PROPERTIES = ('amber', 'blue', 'warm')


def render(node, no=False):
    kind, left, right, positive = node
    if kind == 'f':
        return f'Object {left} is {"" if positive else "not "}{right}.'
    if no and not positive:
        return f'No {left} object is {right}.'
    return f'Every {left} object is {"" if positive else "not "}{right}.'


def ast(node):
    kind, left, right, positive = node
    if kind == 'f':
        return dict(kind='fact', entity=left, predicate=right, positive=positive)
    return dict(kind='rule', antecedent=left, consequent=right, positive=positive)


def case(theory, query, no=False):
    return dict(id='oracle', passages=[dict(id='p', text=' '.join(render(n, no) for n in theory))],
                claim=render(query), citations=[dict(passage_id='p', quote=render(theory[0], no))])


def holds(node, world, entity=None):
    kind, left, right, positive = node
    if kind == 'f':
        return world[left, right] == positive
    return all(not world[e, left] or world[e, right] == positive
               for e in ({entity} if entity is not None else {e for e, _ in world}))


def oracle(theory, query):
    entities = sorted({n[1] for n in (*theory, query) if n[0] == 'f'})
    props = sorted({p for n in (*theory, query) for p in ((n[2],) if n[0] == 'f' else n[1:3])})
    keys = list(itertools.product(entities, props))
    worlds = [dict(zip(keys, bits)) for bits in itertools.product((False, True), repeat=len(keys))]
    models = [w for w in worlds if all(holds(n, w) for n in theory)]
    # Projections of a FULL global truth table, filtered with local constraints.
    local = {e: {tuple(w[e, p] for p in props) for w in worlds
                 if all(holds(n, w, e) for n in theory if n[0] == 'r' or n[1] == e)}
             for e in entities}
    if not models:
        label = 'abstain'
    else:
        truths = {holds(query, w) for w in models}
        label = {frozenset([True]): 'supported', frozenset([False]): 'contradicted',
                 frozenset([True, False]): 'not_established'}[frozenset(truths)]
    return label, entities, props, local, models


class IndependentGlobalOracleTests(unittest.TestCase):
    def check_theory(self, theory, query, no=False):
        expected, entities, props, local, worlds = oracle(theory, query)
        row = C.predict_case(case(theory, query, no))
        self.assertEqual(row['label'], expected, (theory, query, row))
        self.assertEqual(row['claim'], ast(query))
        self.assertEqual(row['parsed'], [{**ast(n), 'passage_id': 'p', 'statement_index': i}
                                         for i, n in enumerate(theory, 1)])
        self.assertEqual(row['predicates'], props)
        self.assertEqual(row['entities'], entities)
        self.assertEqual(row['context_consistent'], bool(worlds))
        if expected == 'abstain':
            bad = next(e for e in entities if not local[e])
            self.assertEqual(row['reason'], 'inconsistent_context')
            self.assertEqual(row['inconsistent_entity'], bad)
            self.assertEqual(row['consistency_scan_complete'], entities.index(bad) == len(entities) - 1)
            self.assertEqual(row['entity_model_counts'], {e: len(local[e]) for e in entities[:entities.index(bad)+1]})
            return
        self.assertTrue(row['consistency_scan_complete'])
        self.assertEqual(row['entity_model_counts'], {e: len(local[e]) for e in entities})
        self.assertEqual(set(row['context_witness']), set(entities))
        combined = {}
        for e, witness in row['context_witness'].items():
            self.assertEqual(set(witness), set(props))
            self.assertTrue(all(type(v) is bool for v in witness.values()))
            self.assertIn(tuple(witness[p] for p in props), local[e])
            combined.update({(e, p): v for p, v in witness.items()})
        self.assertIn(combined, worlds)
        index = props.index(query[2])
        q = row['query_models']
        for truth, name in ((True, 'true'), (False, 'false')):
            choices = {bits for bits in local[query[1]] if (bits[index] == query[3]) == truth}
            self.assertEqual(q[name + '_count'], len(choices))
            witness = q[name + '_witness']
            if not choices:
                self.assertIsNone(witness)
            else:
                self.assertEqual(set(witness), set(props))
                self.assertTrue(all(type(v) is bool for v in witness.values()))
                self.assertIn(tuple(witness[p] for p in props), choices)
                extended = dict(combined)
                extended.update({(query[1], p): v for p, v in witness.items()})
                self.assertIn(extended, worlds)

    def test_frozen_source(self):
        self.assertEqual(hashlib.sha256((ROOT / 'scripts/predict_controlled_support.py').read_bytes()).hexdigest(), EXPECTED_HASH)

    def test_exhaustive_small_theories_and_seeded_larger_theories(self):
        pool = [('f', e, p, b) for e in ENTITIES for p in PROPERTIES for b in (False, True)]
        pool += [('r', p, q, b) for p in PROPERTIES for q in PROPERTIES for b in (False, True)]
        theories = [(n,) for n in pool] + list(itertools.combinations(pool, 2))
        rng = random.Random(20261110)
        theories += [tuple(rng.sample(pool, rng.randrange(3, 9))) for _ in range(128)]
        self.assertEqual(len(theories), 593)
        for theory in theories:
            for e, p, b in itertools.product(ENTITIES, PROPERTIES, (False, True)):
                self.check_theory(theory, ('f', e, p, b))

    def test_named_semantic_edges(self):
        samples = [
            [('f', 'Aster', 'warm', False), ('r', 'amber', 'warm', True)],
            [('f', 'Aster', 'warm', True), ('r', 'amber', 'warm', True)],
            [('f', 'Aster', 'amber', False), ('r', 'amber', 'warm', True)],
            [('r', 'amber', 'amber', False)],
            [('f', 'Birch', 'blue', True), ('f', 'Birch', 'blue', False)],
            [('f', 'Aster', 'blue', True)],
            [('r', 'amber', 'warm', True), ('r', 'warm', 'blue', True), ('f', 'Aster', 'blue', False)],
        ]
        for theory in samples:
            for e, p, b in itertools.product(ENTITIES, PROPERTIES, (False, True)):
                self.check_theory(theory, ('f', e, p, b), no=True)

    def test_invariances(self):
        theory = [('f', 'Aster', 'amber', True), ('r', 'amber', 'blue', True), ('r', 'blue', 'warm', False)]
        for b in (False, True):
            query = ('f', 'Aster', 'warm', b)
            for variant in (theory, list(reversed(theory)), theory + theory):
                self.check_theory(variant, query)
            renamed = [('f', 'Cedar', 'green', True), ('r', 'green', 'cold', True), ('r', 'cold', 'pale', False)]
            self.check_theory(renamed, ('f', 'Cedar', 'pale', b))
            base = case(theory, query)
            row = C.predict_case(base)
            base['citations'] = [dict(passage_id='p', quote='object')]
            self.assertEqual(C.predict_case(base), row)
            base['passages'] = [dict(id='p', text=render(theory[0])), dict(id='other', text=' '.join(map(render, theory[1:])))]
            base['citations'] = [dict(passage_id='p', quote='Object')]
            self.assertEqual(C.predict_case(base)['label'], row['label'])

    def test_grammar_mutations(self):
        valid = 'Object Aster is amber.'
        bad = [valid[:-1], valid + '.', valid + ' junk', 'Object  Aster is amber.',
               'object Aster is amber.', 'Object ASTER is amber.', 'Object Aster is Amber.',
               'Object Aster is not not amber.', 'Object Aster is not.', 'Object Aster is no.',
               'Object Åster is amber.', 'Object Aster is am\u200bber.', '"' + valid + '"',
               'Every not amber object is warm.', 'No amber object is not warm.',
               'Object Aster is ' + 'a'*25 + '.', 'Object ' + 'A'+'a'*32 + ' is amber.']
        for text in bad:
            value = case([('f', 'Aster', 'amber', True)], ('f', 'Aster', 'amber', True))
            value['passages'][0]['text'] = text
            value['citations'][0]['quote'] = text
            if '\u200b' in text:
                with self.assertRaises(ValueError): C.predict_case(value)
            else:
                self.assertEqual(C.predict_case(value)['label'], 'abstain', text)
        value = case([('f', 'Aster', 'amber', True)], ('f', 'Aster', 'amber', True))
        value['claim'] += ' Object Birch is blue.'
        self.assertEqual(C.predict_case(value)['reason'], 'unsupported_claim_grammar')
        for text in (' ' + valid + ' ', valid + 'Object Birch is blue.', valid + '  Object Birch is blue.'):
            value['claim'] = valid
            value['passages'][0]['text'] = text
            self.assertEqual(C.predict_case(value)['label'], 'supported')

    def test_semantic_boundaries(self):
        fact = ('f', 'Aster', 'amber', True)
        self.assertEqual(C.predict_case(case([fact]*48, fact))['label'], 'supported')
        self.assertEqual(C.predict_case(case([fact]*49, fact))['reason'], 'statement_limit')
        names = ['A'+chr(97+i) for i in range(9)]
        for count in (8, 9):
            theory = [('f', n, 'amber', True) for n in names[:count-1]]
            row = C.predict_case(case(theory, ('f', names[count-1], 'amber', True)))
            self.assertEqual(row['label'], 'not_established' if count == 8 else 'abstain')
        props = [chr(97+i) for i in range(11)]
        for count in (10, 11):
            theory = [('f', 'Aster', p, True) for p in props[:count-1]]
            row = C.predict_case(case(theory, ('f', 'Aster', props[count-1], True)))
            self.assertEqual(row['label'], 'not_established' if count == 10 else 'abstain')
        self.assertEqual(C.predict_case(case([('f', 'A'+'a'*31, 'b'*24, True)], ('f', 'A'+'a'*31, 'b'*24, True)))['label'], 'supported')

    def test_batch_schema_binding_and_caps(self):
        def bound(cases):
            body = dict(protocol=1, dataset_sha256='0'*64, cases=cases)
            raw = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
            return {**body, 'input_sha256': hashlib.sha256(raw).hexdigest()}
        cases = []
        for i in range(64):
            value = case([('f', 'Aster', 'amber', True)], ('f', 'Aster', 'amber', True))
            value['id'] = str(i)
            cases.append(value)
        predictions, trace = C.run(bound(cases))
        self.assertEqual(len(predictions['predictions']), 64)
        self.assertEqual(trace['candidate_source_sha256'], EXPECTED_HASH)
        dependency_hash = hashlib.sha256((ROOT / 'scripts/evaluate_claim_support.py').read_bytes()).hexdigest()
        self.assertEqual(dependency_hash, 'f24f017ad344d572e61979519730c5fc8dbd1be162fb24d648ab66deae04ae13')
        self.assertEqual(trace['evaluator_source_sha256'], dependency_hash)
        raw = json.dumps(predictions, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        self.assertEqual(trace['prediction_sha256'], hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError): C.run(bound(cases + [{**cases[0], 'id': 'extra'}]))
        bad = bound(cases); bad['input_sha256'] = 'f'*64
        with self.assertRaises(ValueError): C.run(bad)
        bad = bound(cases); bad['protocol'] = True
        with self.assertRaises(ValueError): C.run(bad)
        badcase = {**cases[0], 'gold': 'supported'}
        with self.assertRaises(ValueError): C.run(bound([badcase]))


if __name__ == '__main__':
    unittest.main()
