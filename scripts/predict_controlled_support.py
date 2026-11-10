"""Offline controlled-English unary-logic model checking, not general NLP.

No training, model provider, runtime admission or canonical corpus is involved.
Only the exact documented grammar is interpreted; every passage is consumed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import evaluate_claim_support as evaluation

CANDIDATE = 'controlled_unary_v1'
MAX_CASES = 64
MAX_STATEMENTS = 48  # Supplied passage statements, excluding the single claim.
MAX_ENTITIES = 8
MAX_PREDICATES = 10
MAX_TRACE_BYTES = 2 * 1024 * 1024
_ENTITY = r'[A-Z][a-z]{0,31}'
_PROPERTY = r'[a-z]{1,24}'
_FACT = re.compile(rf'Object ({_ENTITY}) is (not )?({_PROPERTY})')
_EVERY = re.compile(rf'Every ({_PROPERTY}) object is (not )?({_PROPERTY})')
_NO = re.compile(rf'No ({_PROPERTY}) object is ({_PROPERTY})')
_RESERVED = frozenset(('object', 'is', 'not', 'every', 'no'))


def _hex(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _case(value):
    evaluation._object(value, ('id', 'passages', 'claim', 'citations'), 'candidate case')
    evaluation._id(value['id'], 'case ID')
    evaluation._text(value['claim'], 'claim', 2000)
    evaluation._array(value['passages'], 'passages', 5)
    passages = {}
    for passage in value['passages']:
        evaluation._object(passage, ('id', 'text'), 'passage')
        ident = evaluation._id(passage['id'], 'passage ID')
        if ident in passages:
            raise ValueError('duplicate passage ID')
        passages[ident] = evaluation._text(passage['text'], 'passage text', 8000)
    evaluation._array(value['citations'], 'citations', 5)
    seen = set()
    for citation in value['citations']:
        evaluation._object(citation, ('passage_id', 'quote'), 'citation')
        ident = evaluation._id(citation['passage_id'], 'citation passage ID')
        quote = evaluation._text(citation['quote'], 'quote', 1000)
        if (ident not in passages or quote not in passages[ident]
                or (ident, quote) in seen):
            raise ValueError('citation must be a unique exact excerpt of a supplied passage')
        seen.add((ident, quote))


def validate_inputs(value):
    evaluation._object(value, ('protocol', 'dataset_sha256', 'input_sha256', 'cases'), 'candidate input')
    if type(value['protocol']) is not int or value['protocol'] != 1:
        raise ValueError('unsupported candidate input protocol')
    if not _hex(value['dataset_sha256']) or not _hex(value['input_sha256']):
        raise ValueError('invalid candidate input hash')
    evaluation._array(value['cases'], 'cases', MAX_CASES)
    seen = set()
    for case in value['cases']:
        _case(case)
        if case['id'] in seen:
            raise ValueError('duplicate case ID')
        seen.add(case['id'])
    body = {key: value[key] for key in ('protocol', 'dataset_sha256', 'cases')}
    if hashlib.sha256(evaluation.canonical_bytes(body)).hexdigest() != value['input_sha256']:
        raise ValueError('candidate input content does not match its hash')
    return value


def _statements(text):
    # Only ASCII outer/inter-sentence spaces are insignificant. No partial parse,
    # ignored suffix, empty internal statement, implicit final period or newline.
    pieces = text.strip(' ').split('.')
    if not pieces or pieces[-1] != '' or any(not s.strip(' ') for s in pieces[:-1]):
        return None
    return [s.strip(' ') for s in pieces[:-1]]


def _parse(statement):
    match = _FACT.fullmatch(statement)
    if match:
        entity, negative, predicate = match.groups()
        if predicate not in _RESERVED:
            return {'kind': 'fact', 'entity': entity, 'predicate': predicate, 'positive': not bool(negative)}
    match = _EVERY.fullmatch(statement)
    if match:
        antecedent, negative, consequent = match.groups()
        if antecedent not in _RESERVED and consequent not in _RESERVED:
            return {'kind': 'rule', 'antecedent': antecedent, 'consequent': consequent, 'positive': not bool(negative)}
    match = _NO.fullmatch(statement)
    if match:
        antecedent, consequent = match.groups()
        if antecedent not in _RESERVED and consequent not in _RESERVED:
            return {'kind': 'rule', 'antecedent': antecedent, 'consequent': consequent, 'positive': False}
    return None


def _abstain(case_id, reason, **detail):
    return {'case_id': case_id, 'label': 'abstain', 'reason': reason, **detail}


def predict_case(case):
    """Classify a validated-schema case or explicitly abstain outside the fragment.

    A claim-only symbol is unknown, not false. Any inconsistent object causes
    global abstention. Material implication includes contraposition/vacuity.
    """
    _case(case)
    claim_statements = _statements(case['claim'])
    if claim_statements is None or len(claim_statements) != 1:
        return _abstain(case['id'], 'unsupported_claim_grammar')
    claim = _parse(claim_statements[0])
    if claim is None or claim['kind'] != 'fact':
        return _abstain(case['id'], 'unsupported_claim_grammar')
    all_statements = []
    for passage in case['passages']:
        statements = _statements(passage['text'])
        if statements is None:
            return _abstain(case['id'], 'unsupported_passage_grammar', passage_id=passage['id'])
        all_statements.extend((passage['id'], index, text) for index, text in enumerate(statements, 1))
    if len(all_statements) > MAX_STATEMENTS:
        return _abstain(case['id'], 'statement_limit', statement_count=len(all_statements))
    parsed = []
    for passage_id, index, statement in all_statements:
        node = _parse(statement)
        if node is None:
            return _abstain(case['id'], 'unsupported_passage_grammar', passage_id=passage_id, statement_index=index)
        parsed.append({**node, 'passage_id': passage_id, 'statement_index': index})
    predicates = {claim['predicate']}
    entities = {claim['entity']}
    for node in parsed:
        if node['kind'] == 'fact':
            entities.add(node['entity']); predicates.add(node['predicate'])
        else:
            predicates.update((node['antecedent'], node['consequent']))
    if len(entities) > MAX_ENTITIES or len(predicates) > MAX_PREDICATES:
        return _abstain(case['id'], 'symbol_limit', entity_count=len(entities), predicate_count=len(predicates))
    predicates, entities = sorted(predicates), sorted(entities)
    bits = {name: 1 << index for index, name in enumerate(predicates)}
    rules = [node for node in parsed if node['kind'] == 'rule']
    valid_rule_assignments = []
    for assignment in range(1 << len(predicates)):
        if all(not (assignment & bits[r['antecedent']])
               or bool(assignment & bits[r['consequent']]) == r['positive'] for r in rules):
            valid_rule_assignments.append(assignment)
    models, context_witness = {}, {}
    true_count = false_count = 0
    true_witness = false_witness = None
    def witness(assignment):
        return {name: bool(assignment & bits[name]) for name in predicates}
    for entity in entities:
        facts = [n for n in parsed if n['kind'] == 'fact' and n['entity'] == entity]
        assignments = [a for a in valid_rule_assignments
                       if all(bool(a & bits[n['predicate']]) == n['positive'] for n in facts)]
        models[entity] = len(assignments)
        if not assignments:
            return _abstain(case['id'], 'inconsistent_context', inconsistent_entity=entity,
                            parsed=parsed, claim=claim, predicates=predicates,
                            entities=entities, entity_model_counts=models, context_consistent=False,
                            consistency_scan_complete=len(models) == len(entities))
        context_witness[entity] = witness(assignments[0])
        if entity == claim['entity']:
            for assignment in assignments:
                truth = bool(assignment & bits[claim['predicate']]) == claim['positive']
                if truth:
                    true_count += 1
                    if true_witness is None: true_witness = witness(assignment)
                else:
                    false_count += 1
                    if false_witness is None: false_witness = witness(assignment)
    label = 'supported' if false_count == 0 else 'contradicted' if true_count == 0 else 'not_established'
    return {'case_id': case['id'], 'label': label, 'reason': 'complete_bounded_model_check',
            'parsed': parsed, 'claim': claim, 'predicates': predicates,
            'entities': entities, 'entity_model_counts': models, 'context_consistent': True,
            'consistency_scan_complete': True,
            'context_witness': context_witness,
            'query_models': {'true_count': true_count, 'false_count': false_count,
                             'true_witness': true_witness, 'false_witness': false_witness}}


def run(inputs):
    validate_inputs(inputs)
    traces = [predict_case(case) for case in inputs['cases']]
    predictions = {'protocol': 1, 'input_sha256': inputs['input_sha256'],
                   'predictions': [{'case_id': row['case_id'], 'label': row['label']} for row in traces]}
    detail = {'protocol': 1, 'candidate': CANDIDATE,
              'candidate_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'evaluator_source_sha256': hashlib.sha256(Path(evaluation.__file__).read_bytes()).hexdigest(),
              'input_sha256': inputs['input_sha256'], 'dataset_sha256': inputs['dataset_sha256'],
              'prediction_sha256': hashlib.sha256(evaluation.canonical_bytes(predictions)).hexdigest(),
              'scope': 'Exact controlled-English unary facts and universal implications only; exhaustive bounded model checking, not general natural-language support or a trained model.',
              'limits': {'cases': MAX_CASES, 'statements_excluding_claim': MAX_STATEMENTS,
                         'entities_including_claim': MAX_ENTITIES, 'predicates_including_claim': MAX_PREDICATES},
              'cases': traces}
    if len(evaluation.canonical_bytes(detail)) > MAX_TRACE_BYTES:
        raise ValueError('candidate trace exceeds output limit')
    return predictions, detail


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('predict', 'inspect'))
    parser.add_argument('--inputs', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inputs, _ = evaluation.read_json(args.inputs)
        predictions, detail = run(inputs)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        print(f'Invalid candidate input: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(predictions if args.operation == 'predict' else detail,
                     ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
