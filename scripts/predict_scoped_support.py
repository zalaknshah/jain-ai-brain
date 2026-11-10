"""Offline scoped unary support; exact language and limits are in the contract.

This is a standalone candidate, not a JACE runtime or a natural-language model.
The only non-stdlib dependency is the byte-verified frozen evaluator, used for
its input transport, envelope primitives, and canonical JSON interface.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = Path(__file__).resolve()
EVALUATOR_PATH = ROOT / 'scripts' / 'evaluate_claim_support.py'
CONTRACT_PATH = ROOT / 'docs' / 'SCOPED_SUPPORT_CONTRACT.md'
EVALUATOR_SHA256 = 'f24f017ad344d572e61979519730c5fc8dbd1be162fb24d648ab66deae04ae13'
CONTRACT_SHA256 = '0facb37c40a72b34dd93420453acc60def3292ee8a27fd6cef9f080a6a655e46'
TRACE_LIMIT = 2_097_152
ARTIFACT_LIMIT = 2_097_152
DIMENSIONS = ('entities', 'properties', 'frames', 'source_keys')
LIMITS = (8, 10, 4, 4)
TOKEN = r'[a-z][a-z0-9_]{0,15}'
KEY = rf'{TOKEN}/{TOKEN}/{TOKEN}'
REF = rf'{KEY}#{TOKEN}'
PROPERTY = r'[a-z]{1,24}'
RESERVED = frozenset(('object', 'is', 'not', 'every', 'no'))
FACT_RE = re.compile(rf'Object ([A-Z][a-z]{{0,31}}) is (not )?({PROPERTY})')
EVERY_RE = re.compile(rf'Every ({PROPERTY}) object is (not )?({PROPERTY})')
NO_RE = re.compile(rf'No ({PROPERTY}) object is ({PROPERTY})')
WORLD_RE = re.compile(rf'World ({TOKEN}): (.+)')
REPORT_RE = re.compile(rf'Report ({REF}) ({TOKEN}): (.+)')
TRUE_RE = re.compile(rf'True ({REF})')
COMPLETE_RE = re.compile(rf'Complete ({KEY})')
ASSERT_RE = re.compile(rf'(Asserts|Not-asserts) ({KEY}) ({TOKEN}): (.+)')
ACCOUNT_RE = re.compile(rf'Account \[([^\]]+)\] ({TOKEN}): (.+)')
KEY_RE = re.compile(KEY)
HASH_RE = re.compile(r'[0-9a-f]{64}')


class InvalidInput(Exception):
    """A request transport, envelope, binding, or command-line error."""


class TraceOverflow(Exception):
    """The complete required canonical inspection artifact exceeds the cap."""


class ExecutionFailure(Exception):
    """A required computation or source binding could not be completed."""


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def artifact_bytes(path):
    """Read only a bounded regular source artifact, without blocking on a FIFO."""
    if not hasattr(os, 'O_NONBLOCK'):
        raise ExecutionFailure()
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > ARTIFACT_LIMIT:
            raise ExecutionFailure()
        raw = stream.read(ARTIFACT_LIMIT + 1)
    if len(raw) > ARTIFACT_LIMIT:
        raise ExecutionFailure()
    return raw


def load_evaluator():
    """Execute the exact verified evaluator bytes, never a cached .pyc file."""
    raw = artifact_bytes(EVALUATOR_PATH)
    if sha256(raw) != EVALUATOR_SHA256:
        raise ExecutionFailure()
    module = types.ModuleType('_scoped_support_frozen_evaluator')
    module.__file__ = str(EVALUATOR_PATH)
    exec(compile(raw, str(EVALUATOR_PATH), 'exec'), module.__dict__)
    return module


def validate_inputs(value, evaluator):
    """Validate the whole envelope before permitting any case semantics."""
    evaluator._object(value, ('protocol', 'dataset_sha256', 'input_sha256', 'cases'), 'input')
    if type(value['protocol']) is not int or value['protocol'] != 1:
        raise ValueError('invalid protocol')
    for key in ('dataset_sha256', 'input_sha256'):
        if not isinstance(value[key], str) or not HASH_RE.fullmatch(value[key]):
            raise ValueError('invalid hash')
    evaluator._array(value['cases'], 'cases', 64)
    seen = set()
    for case in value['cases']:
        evaluator._object(case, ('id', 'passages', 'claim', 'citations'), 'case')
        ident = evaluator._id(case['id'], 'case ID')
        if ident in seen:
            raise ValueError('duplicate case ID')
        seen.add(ident)
        evaluator._text(case['claim'], 'claim', 2000)
        evaluator._array(case['passages'], 'passages', 5)
        passages = {}
        for passage in case['passages']:
            evaluator._object(passage, ('id', 'text'), 'passage')
            pid = evaluator._id(passage['id'], 'passage ID')
            if pid in passages:
                raise ValueError('duplicate passage ID')
            passages[pid] = evaluator._text(passage['text'], 'passage text', 8000)
        evaluator._array(case['citations'], 'citations', 5)
        cited = set()
        for citation in case['citations']:
            evaluator._object(citation, ('passage_id', 'quote'), 'citation')
            pid = evaluator._id(citation['passage_id'], 'citation passage ID')
            quote = evaluator._text(citation['quote'], 'quote', 1000)
            pair = (pid, quote)
            if pair in cited or pid not in passages or quote not in passages[pid]:
                raise ValueError('invalid citation')
            cited.add(pair)
    payload = {key: value[key] for key in ('protocol', 'dataset_sha256', 'cases')}
    if value['input_sha256'] != sha256(evaluator.canonical_bytes(payload)):
        raise ValueError('input hash mismatch')
    return value


def parse_body(text):
    match = FACT_RE.fullmatch(text)
    if match:
        entity, negative, predicate = match.groups()
        if predicate not in RESERVED:
            return ['fact', entity, predicate, negative is None]
        return None
    match = EVERY_RE.fullmatch(text)
    if match:
        antecedent, negative, consequent = match.groups()
        if antecedent not in RESERVED and consequent not in RESERVED:
            return ['rule', antecedent, consequent, negative is None]
        return None
    match = NO_RE.fullmatch(text)
    if match:
        antecedent, consequent = match.groups()
        if antecedent not in RESERVED and consequent not in RESERVED:
            return ['rule', antecedent, consequent, False]
    return None


def parse_premise(text):
    match = WORLD_RE.fullmatch(text)
    if match:
        frame, raw_body = match.groups()
        body = parse_body(raw_body)
        return ['world', frame, body] if body is not None else None
    match = REPORT_RE.fullmatch(text)
    if match:
        ref, frame, raw_body = match.groups()
        body = parse_body(raw_body)
        return ['report', ref, frame, body] if body is not None else None
    match = TRUE_RE.fullmatch(text)
    if match:
        return ['true', match[1]]
    match = COMPLETE_RE.fullmatch(text)
    if match:
        return ['complete', match[1]]
    return None


def parse_claim(text):
    statement = text.strip(' ')
    if not statement.endswith('.') or statement.count('.') != 1:
        return None
    text = statement[:-1]
    match = WORLD_RE.fullmatch(text)
    if match:
        frame, raw_body = match.groups()
        body = parse_body(raw_body)
        if body is not None and body[0] == 'fact':
            return ['world', frame, body]
        return None
    match = ASSERT_RE.fullmatch(text)
    if match:
        family, key, frame, raw_body = match.groups()
        body = parse_body(raw_body)
        if body is not None and body[0] == 'fact':
            kind = 'asserts' if family == 'Asserts' else 'not_asserts'
            return [kind, key, frame, body]
        return None
    match = ACCOUNT_RE.fullmatch(text)
    if match:
        raw_keys, frame, raw_body = match.groups()
        keys = raw_keys.split(',')
        if (not 1 <= len(keys) <= 4 or len(set(keys)) != len(keys)
                or any(not KEY_RE.fullmatch(key) for key in keys)):
            return None
        body = parse_body(raw_body)
        if body is not None and body[0] == 'fact':
            return ['account', sorted(keys), frame, body]
    return None


def parse_passages(passages):
    records = []
    for passage_index, passage in enumerate(passages, 1):
        start, statement_index = 0, 0
        text = passage['text']
        for end, char in enumerate(text):
            if char != '.':
                continue
            statement_index += 1
            completed = text[start:end + 1].strip(' ')
            segment = completed[:-1]
            node = parse_premise(segment)
            if node is None:
                return None, {'passage_index': passage_index, 'passage_id': passage['id'],
                              'statement_index': statement_index}
            records.append({'ordinal': len(records) + 1, 'passage_index': passage_index,
                            'passage_id': passage['id'], 'statement_index': statement_index,
                            'text': segment, 'node': node})
            start = end + 1
        if statement_index == 0 or text[start:].strip(' '):
            return None, {'passage_index': passage_index, 'passage_id': passage['id'],
                          'statement_index': statement_index + 1}
    return records, None


def collect_symbols(query, records):
    symbols = {name: set() for name in (*DIMENSIONS, 'references')}

    def add_body(body):
        if body[0] == 'fact':
            symbols['entities'].add(body[1])
            symbols['properties'].add(body[2])
        else:
            symbols['properties'].update(body[1:3])

    add_body(query[-1])
    symbols['frames'].add(query[-2])
    if query[0] == 'account':
        symbols['source_keys'].update(query[1])
    elif query[0] != 'world':
        symbols['source_keys'].add(query[1])
    for record in records:
        node = record['node']
        if node[0] in ('world', 'report'):
            symbols['frames'].add(node[-2])
            add_body(node[-1])
        if node[0] in ('report', 'true'):
            symbols['references'].add(node[1])
            symbols['source_keys'].add(node[1].split('#')[0])
        elif node[0] == 'complete':
            symbols['source_keys'].add(node[1])
    return {name: sorted(values) for name, values in symbols.items()}


def resolve_references(records):
    entries, conflicts, true_ordinals = {}, set(), {}
    for record in records:
        node, ordinal = record['node'], record['ordinal']
        if node[0] == 'report':
            ref, frame, body = node[1:]
            if ref not in entries:
                entries[ref] = {'ref': ref, 'frame': frame, 'body': body,
                                'report_ordinals': [], 'true_ordinals': []}
            entry = entries[ref]
            if entry['frame'] != frame or entry['body'] != body:
                conflicts.add(ref)
            entry['report_ordinals'].append(ordinal)
        elif node[0] == 'true':
            true_ordinals.setdefault(node[1], []).append(ordinal)
    dangling = sorted(set(true_ordinals) - set(entries))
    for ref, entry in entries.items():
        entry['true_ordinals'] = true_ordinals.get(ref, [])
    return entries, sorted(conflicts), dangling


def sat(variable_count, clauses, assumptions=()):
    """Complete 2-SAT via independently written iterative Kosaraju SCCs.

    Literal 2*i means not-x_i; 2*i+1 means x_i. Each binary clause
    adds both implications, and a unit is a repeated binary literal.
    A formula is unsatisfiable exactly when x and not-x share an SCC.
    """
    size = 2 * variable_count
    graph = [[] for _ in range(size)]
    reverse = [[] for _ in range(size)]
    for left, right in (*clauses, *((literal, literal) for literal in assumptions)):
        for source, target in ((left ^ 1, right), (right ^ 1, left)):
            graph[source].append(target)
            reverse[target].append(source)
    visited, finish = set(), []
    for root in range(size):
        if root in visited:
            continue
        visited.add(root)
        stack = [(root, 0)]
        while stack:
            vertex, offset = stack[-1]
            if offset == len(graph[vertex]):
                finish.append(vertex)
                stack.pop()
            else:
                target = graph[vertex][offset]
                stack[-1] = (vertex, offset + 1)
                if target not in visited:
                    visited.add(target)
                    stack.append((target, 0))
    component = [-1] * size
    for root in reversed(finish):
        if component[root] != -1:
            continue
        component[root] = root
        stack = [root]
        while stack:
            vertex = stack.pop()
            for target in reverse[vertex]:
                if component[target] == -1:
                    component[target] = root
                    stack.append(target)
    return all(component[2 * index] != component[2 * index + 1]
               for index in range(variable_count))


def smallest_witness(variable_count, clauses, target_literal):
    """Greedily fix false-first coordinates using a complete SAT check."""
    fixed = [target_literal]
    if not sat(variable_count, clauses, fixed):
        return None
    result = []
    for index in range(variable_count):
        if sat(variable_count, clauses, (*fixed, 2 * index)):
            fixed.append(2 * index)
            result.append(False)
        else:
            fixed.append(2 * index + 1)
            result.append(True)
    return result


def graph_components(bodies, query_predicate):
    graph = {query_predicate: set()}
    for body in bodies:
        if body[0] == 'fact':
            graph.setdefault(body[2], set())
        else:
            left, right = body[1:3]
            graph.setdefault(left, set()).add(right)
            graph.setdefault(right, set()).add(left)
    seen, result = set(), []
    for root in sorted(graph):
        if root in seen:
            continue
        seen.add(root)
        stack, predicates = [root], []
        while stack:
            vertex = stack.pop()
            predicates.append(vertex)
            for neighbor in graph[vertex]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        result.append(sorted(predicates))
    return result


def local_problem(bodies, predicates, entity, canonical_bytes):
    positions = {predicate: index for index, predicate in enumerate(predicates)}
    selected = {}
    for body in bodies:
        if ((body[0] == 'fact' and body[1] == entity and body[2] in positions)
                or (body[0] == 'rule' and body[1] in positions and body[2] in positions)):
            selected[canonical_bytes(body)] = body
    constraints = [selected[key] for key in sorted(selected)]
    clauses = []
    for body in constraints:
        if body[0] == 'fact':
            literal = 2 * positions[body[2]] + int(body[3])
            clauses.append((literal, literal))
        else:
            clauses.append((2 * positions[body[1]],
                            2 * positions[body[2]] + int(body[3])))
    return constraints, clauses


def inventory_scopes(query, records, frames):
    accounts = set()
    for record in records:
        node = record['node']
        if node[0] == 'report':
            accounts.add(((node[1].split('#')[0],), node[2]))
    if query[0] != 'world':
        keys = query[1] if query[0] == 'account' else [query[1]]
        accounts.update(((key,), query[-2]) for key in keys)
        if query[0] == 'account':
            accounts.add((tuple(keys), query[-2]))
    return ([['world', frame] for frame in frames]
            + [['account', list(keys), frame] for keys, frame in sorted(accounts)])


def effective_theory(scope, records, references):
    bodies, admissions = [], []
    for record in records:
        node, ordinal = record['node'], record['ordinal']
        if scope[0] == 'world':
            if node[0] == 'world' and node[1] == scope[1]:
                bodies.append(node[2])
                admissions.append(['world', ordinal])
            elif node[0] == 'true':
                entry = references[node[1]]
                if entry['frame'] == scope[1]:
                    bodies.append(entry['body'])
                    admissions.append(['bridge', ordinal, node[1]])
        elif (node[0] == 'report' and node[2] == scope[2]
              and node[1].split('#')[0] in scope[1]):
            bodies.append(node[3])
            admissions.append(['report', ordinal])
    return bodies, admissions


def inspect_diagnostics(query, records, references, symbols, canonical_bytes):
    predicate = query[-1][2]
    inventory, theories = [], {}
    for scope in inventory_scopes(query, records, symbols['frames']):
        bodies, admissions = effective_theory(scope, records, references)
        components = graph_components(bodies, predicate)
        checked = []
        for predicates in components:
            inconsistent = []
            for entity in symbols['entities']:
                _, clauses = local_problem(bodies, predicates, entity, canonical_bytes)
                if not sat(len(predicates), clauses):
                    inconsistent.append(entity)
            checked.append({'predicates': predicates, 'inconsistent_entities': inconsistent})
        inventory.append({'scope': scope, 'admissions': admissions, 'components': checked,
                          'consistent': all(not row['inconsistent_entities'] for row in checked)})
        theories[canonical_bytes(scope)] = (bodies, components)
    diagnostics = {'entity_universe': symbols['entities'], 'query_predicate': predicate,
                   'scan_complete': True, 'inventory': inventory}
    return diagnostics, theories


def evaluate_membership(query, records):
    kind, key, frame, fact = query
    matching, complete = [], []
    for record in records:
        node, ordinal = record['node'], record['ordinal']
        if (node[0] == 'report' and node[1].split('#')[0] == key
                and node[2] == frame and node[3] == fact):
            matching.append(ordinal)
        elif node == ['complete', key]:
            complete.append(ordinal)
    label = 'supported' if matching else ('contradicted' if complete else 'not_established')
    if kind == 'not_asserts':
        label = {'supported': 'contradicted', 'contradicted': 'supported',
                 'not_established': 'not_established'}[label]
    return label, {'kind': 'assertion', 'key': key, 'frame': frame, 'fact': fact,
                   'outer_negated': kind == 'not_asserts', 'matching_report_ordinals': matching,
                   'complete_ordinals': complete, 'present': bool(matching),
                   'complete': bool(complete)}


def evaluate_logic(query, theories, canonical_bytes):
    scope = query[:-1]
    fact = query[-1]
    entity, predicate, positive = fact[1:]
    bodies, components = theories[canonical_bytes(scope)]
    predicates = next(component for component in components if predicate in component)
    constraints, clauses = local_problem(bodies, predicates, entity, canonical_bytes)
    satisfiable = sat(len(predicates), clauses)
    true_witness = false_witness = None
    if satisfiable:
        literal = 2 * predicates.index(predicate) + int(positive)
        true_witness = smallest_witness(len(predicates), clauses, literal)
        false_witness = smallest_witness(len(predicates), clauses, literal ^ 1)
    true_possible, false_possible = true_witness is not None, false_witness is not None
    if not satisfiable:
        label = 'abstain'
    elif not false_possible:
        label = 'supported'
    elif not true_possible:
        label = 'contradicted'
    else:
        label = 'not_established'
    return label, {'kind': 'logic', 'scope': scope, 'entity': entity,
                   'component': predicates, 'target_constraints': constraints,
                   'satisfiable': satisfiable, 'true_possible': true_possible,
                   'false_possible': false_possible, 'true_witness': true_witness,
                   'false_witness': false_witness}


def rejected_case(case_id, reason, details):
    return {'case_id': case_id, 'label': 'abstain', 'reason': reason, 'details': details,
            **{key: None for key in ('query', 'counts', 'symbols', 'records', 'references',
                                    'diagnostics', 'evaluation')}}


def inspect_case(case, canonical_bytes):
    ident = case['id']
    query = parse_claim(case['claim'])
    if query is None:
        return rejected_case(ident, 'unsupported_claim_grammar', {})
    records, error = parse_passages(case['passages'])
    if error is not None:
        return rejected_case(ident, 'unsupported_passage_grammar', error)
    if len(records) > 64:
        return rejected_case(ident, 'statement_limit', {'statement_count': len(records), 'maximum': 64})
    symbols = collect_symbols(query, records)
    symbol_counts = {name: len(symbols[name]) for name in DIMENSIONS}
    exceeded = [name for name, limit in zip(DIMENSIONS, LIMITS) if symbol_counts[name] > limit]
    if exceeded:
        return rejected_case(ident, 'symbol_limit', {'counts': symbol_counts, 'exceeded': exceeded})
    if len(symbols['references']) > 32:
        return rejected_case(ident, 'reference_limit',
                             {'reference_count': len(symbols['references']), 'maximum': 32})
    references, conflicts, dangling = resolve_references(records)
    if conflicts:
        return rejected_case(ident, 'conflicting_report_reference', {'references': conflicts})
    if dangling:
        return rejected_case(ident, 'unresolved_truth_reference', {'references': dangling})
    diagnostics, theories = inspect_diagnostics(query, records, references, symbols, canonical_bytes)
    if query[0] in ('asserts', 'not_asserts'):
        label, evaluation = evaluate_membership(query, records)
        reason = 'direct_assertion_membership'
    else:
        label, evaluation = evaluate_logic(query, theories, canonical_bytes)
        reason = 'relevant_inconsistent_context' if label == 'abstain' else 'complete_component_check'
    return {'case_id': ident, 'label': label, 'reason': reason, 'details': {}, 'query': query,
            'counts': {'statements': len(records), **symbol_counts,
                       'references': len(symbols['references'])},
            'symbols': symbols, 'records': records,
            'references': [references[ref] for ref in sorted(references)],
            'diagnostics': diagnostics, 'evaluation': evaluation}


def build_outputs(inputs, evaluator):
    """Return both complete canonical artifacts, or fail without publishing."""
    try:
        validate_inputs(inputs, evaluator)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise InvalidInput() from exc
    source = artifact_bytes(SOURCE_PATH)
    contract = artifact_bytes(CONTRACT_PATH)
    if sha256(contract) != CONTRACT_SHA256:
        raise ExecutionFailure()
    cases = [inspect_case(case, evaluator.canonical_bytes) for case in inputs['cases']]
    predictions = {'protocol': 1, 'input_sha256': inputs['input_sha256'],
                   'predictions': [{'case_id': case['case_id'], 'label': case['label']} for case in cases]}
    prediction_bytes = evaluator.canonical_bytes(predictions)
    trace = {'trace_protocol': 1, 'candidate': 'scoped_unary_v1',
             'contract': 'scoped_unary_contract_v1',
             'bindings': {'candidate_source_sha256': sha256(source),
                          'evaluator_source_sha256': EVALUATOR_SHA256,
                          'contract_sha256': sha256(contract),
                          'input_sha256': inputs['input_sha256'],
                          'dataset_sha256': inputs['dataset_sha256'],
                          'prediction_sha256': sha256(prediction_bytes)}, 'cases': cases}
    trace_bytes = evaluator.canonical_bytes(trace)
    if len(trace_bytes) > TRACE_LIMIT:
        raise TraceOverflow()
    return prediction_bytes, trace_bytes


class RequestParser(argparse.ArgumentParser):
    def error(self, message):
        raise InvalidInput()


def main(argv=None):
    try:
        parser = RequestParser(description=__doc__, add_help=False)
        parser.add_argument('operation', choices=('predict', 'inspect'))
        parser.add_argument('--inputs', '--input', type=Path, required=True)
        args = parser.parse_args(argv)
        if not hasattr(os, 'O_NONBLOCK'):
            raise InvalidInput()
        evaluator = load_evaluator()
        try:
            inputs, _ = evaluator.read_json(args.inputs)
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise InvalidInput() from exc
        predictions, trace = build_outputs(inputs, evaluator)
        output = predictions if args.operation == 'predict' else trace
    except InvalidInput:
        sys.stderr.write('{"error":"invalid_input"}\n')
        return 2
    except TraceOverflow:
        sys.stderr.write('{"error":"trace_overflow"}\n')
        return 2
    except Exception:
        sys.stderr.write('{"error":"execution_failure"}\n')
        return 2
    sys.stdout.buffer.write(output + b'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
