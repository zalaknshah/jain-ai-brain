"""Offline contrastive evaluation of supplied predictions, not a semantic model.

All input JSON is inert. This script imports no JACE runtime, calls no provider,
loads no candidate code and writes no files. Gold labels stay out of exports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import unicodedata

PROTOCOL = 1
LABELS = ('supported', 'contradicted', 'not_established')
PREDICTIONS = (*LABELS, 'abstain')
PHENOMENA = ('negation', 'quantity', 'quantifiers', 'time', 'location',
             'conditionals', 'attribution', 'cross_source')
MAX_BYTES = 2 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]


def _fail(message):
    raise ValueError(message)


def _object(value, keys, name):
    if not isinstance(value, dict) or set(value) != set(keys):
        _fail(f'{name} has an invalid object schema')


def _text(value, name, limit):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or any(unicodedata.category(c).startswith('C') for c in value)):
        _fail(f'{name} must be bounded nonempty text without control or surrogate characters')
    return value


def _id(value, name):
    _text(value, name, 64)
    if not value.isascii() or any(not (c.isalnum() or c in '-_.:') for c in value):
        _fail(f'{name} must be an ASCII identifier')
    return value


def _array(value, name, maximum):
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        _fail(f'{name} must be a nonempty bounded list')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail('duplicate JSON object key')
        result[key] = value
    return result


def read_json(path):
    # Reject special files before reading. Never block waiting for a FIFO writer.
    if not hasattr(os, 'O_NONBLOCK'):
        _fail('nonblocking input-file inspection is unavailable on this platform')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            _fail('input must be a regular file within the byte limit')
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        _fail('input exceeds byte limit')
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                       parse_constant=lambda _: _fail('non-finite JSON number'))
    return value, hashlib.sha256(raw).hexdigest()


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def validate_cases(value):
    _object(value, ('protocol', 'scope', 'cases'), 'dataset')
    if type(value['protocol']) is not int or value['protocol'] != PROTOCOL:
        _fail('unsupported dataset protocol')
    _text(value['scope'], 'scope', 1000)
    _array(value['cases'], 'cases', 512)
    seen, groups = set(), {}
    for case in value['cases']:
        _object(case, ('id', 'group_id', 'phenomenon', 'passages', 'claim',
                       'citations', 'label', 'rationale'), 'case')
        ident = _id(case['id'], 'case ID')
        if ident in seen:
            _fail('duplicate case ID')
        seen.add(ident)
        group = _id(case['group_id'], 'group ID')
        if case['phenomenon'] not in PHENOMENA or case['label'] not in LABELS:
            _fail('unknown phenomenon or gold label')
        _text(case['claim'], 'claim', 2000)
        _text(case['rationale'], 'rationale', 4000)
        _array(case['passages'], 'passages', 5)
        passages = {}
        for passage in case['passages']:
            _object(passage, ('id', 'text'), 'passage')
            pid = _id(passage['id'], 'passage ID')
            if pid in passages:
                _fail('duplicate passage ID')
            passages[pid] = _text(passage['text'], 'passage text', 8000)
        _array(case['citations'], 'citations', 5)
        cited = set()
        for citation in case['citations']:
            _object(citation, ('passage_id', 'quote'), 'citation')
            pid = _id(citation['passage_id'], 'citation passage ID')
            quote = _text(citation['quote'], 'quote', 1000)
            key = (pid, quote)
            if key in cited or pid not in passages or quote not in passages[pid]:
                _fail('citation must be a unique exact excerpt of its supplied passage')
            cited.add(key)
        groups.setdefault(group, []).append(case)
    for cases in groups.values():
        if len(cases) != 3 or {c['label'] for c in cases} != set(LABELS):
            _fail('each contrastive group must contain exactly one of each gold label')
        first = cases[0]
        if any(any(c[k] != first[k] for k in ('passages', 'citations', 'phenomenon')) for c in cases[1:]):
            _fail('matched claims must share identical passages, citations and phenomenon')
        if len({c['claim'] for c in cases}) != 3:
            _fail('matched claims must be distinct')
    return value


def candidate_inputs(dataset, dataset_sha256):
    validate_cases(dataset)
    if (not isinstance(dataset_sha256, str) or len(dataset_sha256) != 64
            or any(c not in '0123456789abcdef' for c in dataset_sha256)):
        _fail('invalid dataset hash')
    # Gold fields and grouping are never included. Hash order avoids exposing
    # fixture insertion order, but does not establish benchmark secrecy.
    cases = sorted(dataset['cases'], key=lambda c: hashlib.sha256(c['id'].encode()).hexdigest())
    result = {'protocol': PROTOCOL, 'dataset_sha256': dataset_sha256,
              'cases': [{key: c[key] for key in ('id', 'passages', 'claim', 'citations')} for c in cases]}
    result['input_sha256'] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    # A deep copy prevents a caller from mutating the gold through export aliases.
    return json.loads(canonical_bytes(result))


def validate_predictions(value, inputs):
    _object(value, ('protocol', 'input_sha256', 'predictions'), 'predictions')
    if type(value['protocol']) is not int or value['protocol'] != PROTOCOL:
        _fail('unsupported prediction protocol')
    if value['input_sha256'] != inputs['input_sha256']:
        _fail('predictions do not match the exact exported input hash')
    _array(value['predictions'], 'predictions', 512)
    result = {}
    for row in value['predictions']:
        _object(row, ('case_id', 'label'), 'prediction')
        ident = _id(row['case_id'], 'prediction case ID')
        if ident in result or row['label'] not in PREDICTIONS:
            _fail('duplicate case prediction or invalid predicted label')
        result[ident] = row['label']
    if set(result) != {c['id'] for c in inputs['cases']}:
        _fail('exactly one explicit prediction or abstention is required per case')
    return result


def baseline_predictions(inputs, label='abstain'):
    if label not in ('abstain', 'supported'):
        _fail('baseline must be abstain or supported')
    return {'protocol': PROTOCOL, 'input_sha256': inputs['input_sha256'],
            'predictions': [{'case_id': c['id'], 'label': label} for c in inputs['cases']]}


def score(dataset, dataset_sha256, predictions):
    inputs = candidate_inputs(dataset, dataset_sha256)
    by_id = validate_predictions(predictions, inputs)
    confusion = {gold: {pred: 0 for pred in PREDICTIONS} for gold in LABELS}
    cases, groups = [], {}
    for case in dataset['cases']:
        pred, gold = by_id[case['id']], case['label']
        confusion[gold][pred] += 1
        correct = pred == gold
        groups.setdefault(case['group_id'], []).append(correct)
        cases.append({**case, 'prediction': pred, 'correct': correct,
                      'mechanical_citations_valid': True})
    total = len(cases)
    predicted = sum(c['prediction'] != 'abstain' for c in cases)
    correct = sum(c['correct'] for c in cases)
    gold_supported = sum(c['label'] == 'supported' for c in cases)
    unsupported = total - gold_supported
    false_support = sum(confusion[g]['supported'] for g in ('contradicted', 'not_established'))
    return {
        'protocol': PROTOCOL, 'dataset_sha256': dataset_sha256,
        'input_sha256': inputs['input_sha256'],
        'prediction_sha256': hashlib.sha256(canonical_bytes(predictions)).hexdigest(),
        'scope': 'Offline scoring of supplied labels against author/reviewer judgments; not a semantic model, doctrinal qualification or unseen benchmark.',
        'observations': {
            'cases': total, 'mechanically_valid_citations': total,
            'semantic_predictions': predicted, 'abstentions': total - predicted,
            'correct_predictions': correct,
            'coverage': predicted / total,
            'accuracy_when_predicted': correct / predicted if predicted else None,
            'correct_fraction_all_cases': correct / total,
            'unsupported_as_supported': false_support,
            'unsupported_case_count': unsupported,
            'unsupported_as_supported_rate': false_support / unsupported,
            'supported_recall': confusion['supported']['supported'] / gold_supported,
            'matched_groups': len(groups),
            'complete_matched_groups_correct': sum(all(g) for g in groups.values()),
        },
        'confusion': confusion,
        'groups': [{'group_id': key, 'all_three_correct': all(value)} for key, value in sorted(groups.items())],
        'cases': cases,
        'limits': [
            'Mechanical citation validity is independent of semantic support and is not a semantic prediction.',
            'Abstention earns no correct prediction; zero false support at zero coverage is not demonstrated accuracy.',
            'Every result depends on the supplied gold labels; label review and candidate provenance are separate.',
            'Hashes bind data, not authorship, independence, execution, calibration or honesty of supplied predictions.',
            'Published challenge cases are disclosed regression data, not an unseen generalization test.',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('export', 'baseline', 'score'))
    parser.add_argument('--cases', type=Path, default=ROOT / 'evals' / 'claim_support_cases.json')
    parser.add_argument('--predictions', type=Path)
    parser.add_argument('--baseline', choices=('abstain', 'supported'))
    args = parser.parse_args(argv)
    if (args.operation == 'score') != (args.predictions is not None):
        parser.error('--predictions is required only for score')
    if (args.operation == 'baseline') != (args.baseline is not None):
        parser.error('--baseline is required only for baseline')
    try:
        data, sha = read_json(args.cases)
        inputs = candidate_inputs(data, sha)
        if args.operation == 'export':
            result = inputs
        elif args.operation == 'baseline':
            result = baseline_predictions(inputs, args.baseline)
        else:
            predictions, raw_sha = read_json(args.predictions)
            result = score(data, sha, predictions)
            result['prediction_file_sha256'] = raw_sha
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        print(f'Invalid evaluation input: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
