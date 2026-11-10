"""Independent global 2-SAT oracle, calibrated against full joint truth tables.

No fixture, candidate parser or candidate inference helper supplies the oracle.
Seeded theories are symbolic and planted to avoid predominantly inconsistent trials.
"""
import collections
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
import predict_controlled_support as candidate

_spec = importlib.util.spec_from_file_location('small_joint_reference', ROOT / 'tests/test_controlled_support_oracle.py')
small = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(small)
SEED = 2026111017
HASH = '2ad4fd5c50d681f62dcc94fc3ba2f994e23fbd0bd7ebf31409703bdf18fb0262'
ENTITIES = tuple('A' + chr(97 + i) for i in range(8))
PROPS = tuple(chr(97 + i) for i in range(10))
STATS = {}


def symbols(theory, query):
    entities = {query[1]}
    props = {query[2]}
    for kind, left, right, positive in theory:
        if kind == 'f':
            entities.add(left)
            props.add(right)
        else:
            props.update((left, right))
    return sorted(entities), sorted(props)


def ground(theory, query):
    """Translate independent symbolic statements into GLOBAL two-literal clauses."""
    entities, props = symbols(theory, query)
    variables = {pair: index + 1 for index, pair in enumerate(itertools.product(entities, props))}
    clauses = []
    for kind, left, right, positive in theory:
        if kind == 'f':
            literal = variables[left, right] * (1 if positive else -1)
            clauses.append((literal, literal))
        else:
            for entity in entities:
                clauses.append((-variables[entity, left], variables[entity, right] * (1 if positive else -1)))
    literal = variables[query[1], query[2]] * (1 if query[3] else -1)
    return len(variables), clauses, literal


def satisfiable(variable_count, clauses):
    """Iterative Kosaraju SCC on the complete global implication graph."""
    edges = [[] for _ in range(2 * variable_count)]
    reverse = [[] for _ in edges]
    def node(literal):
        return 2 * (abs(literal) - 1) + (literal < 0)
    for left, right in clauses:
        a, b = node(left), node(right)
        for source, dest in ((a ^ 1, b), (b ^ 1, a)):
            edges[source].append(dest)
            reverse[dest].append(source)
    seen, finish = set(), []
    for start in range(len(edges)):
        if start in seen:
            continue
        seen.add(start)
        stack = [(start, 0)]
        while stack:
            vertex, index = stack[-1]
            if index == len(edges[vertex]):
                stack.pop()
                finish.append(vertex)
            else:
                stack[-1] = (vertex, index + 1)
                neighbor = edges[vertex][index]
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append((neighbor, 0))
    component = [-1] * len(edges)
    for start in reversed(finish):
        if component[start] != -1:
            continue
        component[start] = start
        stack = [start]
        while stack:
            vertex = stack.pop()
            for neighbor in reverse[vertex]:
                if component[neighbor] == -1:
                    component[neighbor] = start
                    stack.append(neighbor)
    return all(component[2*i] != component[2*i+1] for i in range(variable_count))


def classify(theory, query):
    count, clauses, literal = ground(theory, query)
    if not satisfiable(count, clauses):
        return 'abstain'
    true_possible = satisfiable(count, clauses + [(literal, literal)])
    false_possible = satisfiable(count, clauses + [(-literal, -literal)])
    if true_possible and false_possible:
        return 'not_established'
    return 'supported' if true_possible else 'contradicted'


def render(node, alternate=False):
    kind, left, right, positive = node
    if kind == 'f':
        tokens = ['Object', left, 'is']
    elif not positive and alternate:
        return ' '.join(['No', left, 'object', 'is', right]) + '.'
    else:
        tokens = ['Every', left, 'object', 'is']
    if not positive:
        tokens.append('not')
    return ' '.join(tokens + [right]) + '.'


def to_case(theory, query, ident):
    # Several full passages, while citations reference just one statement.
    chunks = [theory[i:i+12] for i in range(0, len(theory), 12)]
    passages = [dict(id='p'+str(i), text=' '.join(render(n, i % 2 == 0) for n in chunk))
                for i, chunk in enumerate(chunks)]
    return dict(id=ident, passages=passages, claim=render(query),
                citations=[dict(passage_id='p0', quote=render(chunks[0][0], True))])


def planted_rule(rule, planting):
    _, left, right, positive = rule
    return all(not planting[e, left] or planting[e, right] == positive for e in ENTITIES)


def larger_trials():
    rng = random.Random(SEED)
    trials = []
    # Nontrivial five-edge implication/negative chain; two unconstrained queries.
    for index in range(80):
        planting = {(e, p): (p in 'abcde' if p in 'abcdef' else bool(rng.getrandbits(1)))
                    for e in ENTITIES for p in PROPS}
        theory = [('r', a, b, True) for a, b in zip('abcd', 'bcde')]
        theory += [('r', 'e', 'f', False), ('r', 'j', 'j', True)]
        theory += [('f', e, p, planting[e, p]) for e in ENTITIES for p in ('a', 'g', 'h')]
        theory += [('f', e, 'i', planting[e, 'i']) for e in ENTITIES[1:]]
        pool = [('r', a, b, sign) for a in 'abcdefgh' for b in 'abcdefgh' for sign in (False, True)]
        choices = [r for r in pool if r not in theory and planted_rule(r, planting)]
        theory += rng.sample(choices, 48-len(theory))
        rng.shuffle(theory)
        queries = [('f', e, p, sign) for e,p in ((ENTITIES[0],'b'), (ENTITIES[0],'f'),
                   (ENTITIES[-1],'e'), (ENTITIES[0],'i'), (ENTITIES[0],'j')) for sign in (False, True)]
        trials.append(('planted_chain', theory, queries))
    # More varied planted worlds, rules, and arbitrary atomic queries.
    for index in range(20):
        planting = {(e,p): bool(rng.getrandbits(1)) for e in ENTITIES for p in PROPS}
        theory = [('f', e, p, planting[e,p]) for e in ENTITIES for p in rng.sample(PROPS,4)]
        pool = [('r', a,b,sign) for a in PROPS for b in PROPS for sign in (False,True)]
        choices = [r for r in pool if planted_rule(r,planting)]
        # Ten tautologies always qualify; sampling with replacement is permitted
        # but recorded as raw versus unique statements in the report.
        theory += [rng.choice(choices) for _ in range(48-len(theory))]
        # Ensure all ten predicates occur, without constraining the planting.
        theory[-10:] = [('r',p,p,True) for p in PROPS]
        rng.shuffle(theory)
        queries = [('f',e,p,sign) for e,p in rng.sample(list(itertools.product(ENTITIES,PROPS)),5)
                   for sign in (False,True)]
        trials.append(('planted_random', theory, queries))
    # Deliberate contradictions retain all bounds and are a minority of trials.
    for index in range(20):
        base = trials[index][1]
        positive = next(n for n in base if n[0]=='f' and n[2]=='a')
        remove = next(i for i,n in enumerate(base) if n[0]=='r' and n[1]!='j')
        theory = base[:remove]+base[remove+1:]+[('f',positive[1],positive[2],False)]
        trials.append(('contradiction',theory,trials[index][2]))
    # Exact 8/10/48 boundary includes an object AND property found only in query.
    for index in range(10):
        theory = [('f',e,p,True) for e in ENTITIES[:-1] for p in 'abcdef']
        theory += [('r',p,p,True) for p in 'abcdefghi'[3:]]
        rng.shuffle(theory)
        trials.append(('query_only_symbols',theory,[('f',ENTITIES[-1],'j',sign) for sign in (False,True)]))
    # Nine-edge chains; only first property is a fact. Fillers are tautologies
    # and repeated premises, never shortcuts to the final inferred property.
    for index in range(10):
        sign = index % 2 == 0
        theory = [('r',a,b,True) for a,b in zip('abcdefgh','bcdefghi')]
        theory += [('r','i','j',sign)]
        theory += [('f',e,'a',True) for e in ENTITIES]
        theory += [('r',p,p,True) for p in PROPS]
        theory += [theory[rng.randrange(9,17)] for _ in range(48-len(theory))]
        rng.shuffle(theory)
        queries = [('f',e,'j',s) for e in (ENTITIES[0],ENTITIES[-1]) for s in (False,True)]
        trials.append(('long_chain',theory,queries))
    return trials


class GlobalLargeOracleTests(unittest.TestCase):
    def test_01_validate_scc_against_full_joint_truth_tables(self):
        pool = [('f',e,p,s) for e in ('Aster','Birch') for p in ('amber','blue','warm') for s in (False,True)]
        pool += [('r',p,q,s) for p in ('amber','blue','warm') for q in ('amber','blue','warm') for s in (False,True)]
        theories = [(n,) for n in pool] + list(itertools.combinations(pool,2))
        rng = random.Random(SEED)
        theories += [tuple(rng.sample(pool,rng.randrange(3,9))) for _ in range(32)]
        outcomes = collections.Counter()
        count = 0
        for theory in theories:
            for e,p,s in itertools.product(('Aster','Birch'),('amber','blue','warm'),(False,True)):
                query = ('f',e,p,s)
                expected = small.oracle(theory,query)[0]
                self.assertEqual(classify(theory,query),expected,(theory,query))
                outcomes[expected] += 1
                count += 1
        STATS['calibration'] = dict(theories=len(theories),query_comparisons=count,labels=dict(outcomes),discrepancies=0)
        self.assertEqual(count,5964)

    def test_02_large_bound_candidate_comparison(self):
        self.assertEqual(hashlib.sha256((ROOT/'scripts/predict_controlled_support.py').read_bytes()).hexdigest(),HASH)
        trials = larger_trials()
        counts = collections.Counter()
        by_family = collections.defaultdict(collections.Counter)
        bounds = collections.Counter()
        unique_theories = set()
        logical_theories, logical_queries = set(), set()
        distinct_query_labels, distinct_max_labels = {}, {}
        distinct_statement_counts, global_clause_counts = collections.Counter(), collections.Counter()
        nontrivial = collections.Counter()
        family_theories = collections.defaultdict(set)
        max_distinct_labels = collections.Counter()
        min_unique = 48
        for index,(family,theory,queries) in enumerate(trials):
            self.assertEqual(len(theory),48)
            unique_theories.add(tuple(sorted(theory)))
            logical_key = tuple(sorted(set(theory)))
            logical_theories.add(logical_key)
            family_theories[family].add(logical_key)
            distinct_statement_counts[len(set(theory))] += 1
            min_unique = min(min_unique,len(set(theory)))
            for j,query in enumerate(queries):
                entities,props = symbols(theory,query)
                self.assertEqual((len(entities),len(props)),(8,10))
                expected = classify(theory,query)
                logical_queries.add((logical_key,query))
                distinct_query_labels[logical_key,query] = expected
                if len(set(theory)) == 48: distinct_max_labels[logical_key,query] = expected
                _, clauses, _ = ground(theory,query)
                unique_clauses = {tuple(sorted(c)) for c in clauses}
                non_tautological = {c for c in unique_clauses if c[0] != -c[1]}
                global_clause_counts[(len(unique_clauses),len(non_tautological))] += 1
                if len(set(theory)) == 48: max_distinct_labels[expected] += 1
                direct = any(n[0]=='f' and n[1:3]==query[1:3] for n in theory)
                if expected in ('supported','contradicted') and not direct:
                    nontrivial[expected + '_without_direct_query_fact'] += 1
                if expected == 'not_established':
                    context_props = {p for n in theory for p in ((n[2],) if n[0]=='f' else n[1:3])}
                    nontrivial['unknown_with_property_in_context' if query[2] in context_props else 'unknown_query_only_property'] += 1
                value = to_case(theory,query,f'large-{index}-{j}')
                row = candidate.predict_case(value)
                self.assertEqual(row['label'],expected,json.dumps(dict(case=value,expected=expected,actual=row)))
                if family != 'contradiction': self.assertNotEqual(expected,'abstain')
                counts[expected] += 1
                by_family[family][expected] += 1
                bounds[(len(entities),len(props),len(theory))] += 1
        STATS['large'] = dict(seed=SEED,theory_trials=len(trials),distinct_theories=len(unique_theories),
                             query_comparisons=sum(counts.values()),labels=dict(counts),
                             by_family={k:dict(v) for k,v in by_family.items()},
                             boundaries={str(k):v for k,v in bounds.items()},
                             minimum_unique_statements=min_unique,
                             distinct_statement_multisets=len(unique_theories),
                             distinct_statement_sets=len(logical_theories),
                             distinct_statement_set_query_pairs=len(logical_queries),
                             distinct_query_labels=dict(collections.Counter(distinct_query_labels.values())),
                             distinct_query_labels_at_48_distinct_statements=dict(collections.Counter(distinct_max_labels.values())),
                             distinct_statement_sets_by_family={k:len(v) for k,v in family_theories.items()},
                             distinct_statement_count_histogram=dict(sorted(distinct_statement_counts.items())),
                             global_clause_count_histogram_including_and_excluding_tautologies={str(k):v for k,v in sorted(global_clause_counts.items())},
                             labels_at_48_distinct_statements=dict(max_distinct_labels),
                             nontrivial_outcomes=dict(nontrivial),discrepancies=0)
        self.assertEqual(len(trials),140)
        self.assertEqual(sum(counts.values()),1260)
        self.assertGreater(counts['supported'],200)
        self.assertGreater(counts['contradicted'],200)
        self.assertGreater(counts['not_established'],300)
        self.assertEqual(counts['abstain'],200)


if __name__ == '__main__':
    unittest.main()
