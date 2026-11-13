"""Offline score/margin abstention research; never a runtime or semantic safety gate."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_router_challenge import inspect_challenge
from jace.evidence_router import digest, encoded, evaluate, load_dataset, load_model, ranked, scores
from jace.training import _json, _read

POLICY = 'zero-development-incorrect-selections-then-maximum-correct-coverage-v1'
GRID_SCORE = tuple(x / 20 for x in range(3, 20)) + (1.000001,)
GRID_MARGIN = tuple(x / 20 for x in range(0, 7))


def query_hash(text):
    return digest(' '.join(unicodedata.normalize('NFKC', text).casefold().split()).encode('utf-8'))


def cached_scores(model, corpus, rows):
    result = []
    for row in rows:
        values = scores(model, corpus, row['query'], 'trained')
        order = ranked(model['ids'], values)
        descending = sorted(values, reverse=True)
        result.append({'id': row['id'], 'relevant': row['relevant'], 'top': order[0],
                       'score': descending[0], 'margin': descending[0] - descending[1]})
    return result


def selected_results(cached, threshold, margin):
    cases = []
    for row in cached:
        selected = row['top'] if row['score'] >= threshold and row['margin'] >= margin else None
        cases.append(dict(row, selected=selected,
                          correct=selected in row['relevant'] if row['relevant'] else selected is None))
    accepted = [row for row in cases if row['selected'] is not None]
    positives = [row for row in cases if row['relevant']]
    negatives = [row for row in cases if not row['relevant']]
    return {'case_count': len(cases), 'positive_count': len(positives), 'negative_count': len(negatives),
            'accepted': len(accepted), 'correct_accepted': sum(row['correct'] for row in accepted),
            'incorrect_accepted': sum(not row['correct'] for row in accepted),
            'positive_abstentions': sum(row['selected'] is None for row in positives),
            'negative_rejected': sum(row['selected'] is None for row in negatives),
            'correct_decisions': sum(row['correct'] for row in cases), 'cases': cases}


def calibrate_selection(data, model, development, development_sha256):
    cached = cached_scores(model, data['corpus'], development)
    options = []
    for threshold in GRID_SCORE:
        for margin in GRID_MARGIN:
            result = selected_results(cached, threshold, margin)
            if result['incorrect_accepted'] == 0:
                options.append((result['correct_accepted'], threshold, margin, result))
    # Above-one threshold guarantees an all-abstain candidate. This is not a pass.
    _, threshold, margin, result = max(options, key=lambda row: row[:3])
    return {'schema_version': 1, 'policy': POLICY, 'model_sha256': digest(encoded(model)),
            'development_sha256': development_sha256,
            'development_query_hashes': sorted(query_hash(row['query']) for row in development),
            'threshold': threshold, 'margin': margin, 'development': result,
            'runtime_admitted': False, 'semantic_quality_verified': False}


def validate_selection(selection, model, heldout):
    keys = {'schema_version', 'policy', 'model_sha256', 'development_sha256', 'development_query_hashes',
            'threshold', 'margin', 'development', 'runtime_admitted', 'semantic_quality_verified'}
    if not isinstance(selection, dict) or set(selection) != keys:
        raise ValueError('invalid selection schema')
    if type(selection['schema_version']) is not int or selection['schema_version'] != 1 or selection['policy'] != POLICY:
        raise ValueError('unsupported selection policy')
    if selection['runtime_admitted'] is not False or selection['semantic_quality_verified'] is not False:
        raise ValueError('selection must remain research only')
    if selection['model_sha256'] != digest(encoded(model)):
        raise ValueError('selection bound to different model')
    threshold, margin = selection['threshold'], selection['margin']
    if type(threshold) not in (int, float) or threshold not in GRID_SCORE or type(margin) not in (int, float) or margin not in GRID_MARGIN:
        raise ValueError('selection outside frozen grid')
    hashes = selection['development_query_hashes']
    if not isinstance(hashes, list) or not 2 <= len(hashes) <= 256 or len(set(hashes)) != len(hashes):
        raise ValueError('invalid development query bindings')
    import re
    if any(not isinstance(x, str) or not re.fullmatch('[a-f0-9]{64}', x) for x in hashes):
        raise ValueError('invalid development query hash')
    if {query_hash(row['query']) for row in heldout} & set(hashes):
        raise ValueError('heldout query overlaps development')
    return threshold, margin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'training/evidence_router')
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--challenge', type=Path, required=True)
    parser.add_argument('--challenge-sha256', required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--calibrate', action='store_true', help='Print inert development-calibrated selection; redirect to a new private file')
    modes.add_argument('--selection', type=Path, help='Read a previously frozen selection and score a fresh heldout')
    args = parser.parse_args()
    try:
        data = load_dataset(args.dataset)
        rows = inspect_challenge(args.challenge, args.challenge_sha256, data)
        model = load_model(args.model, data)
        if args.calibrate:
            report = calibrate_selection(data, model, rows, args.challenge_sha256)
        else:
            raw = _read(args.selection.absolute(), 2 * 1024 * 1024)
            selection = _json(raw)
            threshold, margin = validate_selection(selection, model, rows)
            report = {'challenge_sha256': args.challenge_sha256, 'selection_sha256': digest(raw),
                      'model_sha256': digest(encoded(model)), 'threshold': threshold, 'margin': margin,
                      'candidate': selected_results(cached_scores(model, data['corpus'], rows), threshold, margin),
                      'original': {method: evaluate(model, data['corpus'], rows, method, model['thresholds'][method])
                                   for method in ('lexical', 'tfidf', 'trained')},
                      'training_started': False, 'thresholds_retuned': False,
                      'runtime_admitted': False, 'semantic_quality_verified': False}
    except (ValueError, OSError, TypeError, RecursionError):
        parser.exit(2, 'Invalid frozen selection or challenge; no training or runtime change performed.\n')
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__': raise SystemExit(main())
