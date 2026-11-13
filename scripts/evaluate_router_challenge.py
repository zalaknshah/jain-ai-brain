"""Offline frozen-query challenge for a saved fixed-catalogue router, not Jain reasoning."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.evidence_router import LIMITS, digest, evaluate, load_dataset, load_model, words
from jace.training import _json, _read


def inspect_challenge(path, expected_sha256, data):
    if not isinstance(expected_sha256, str) or not re.fullmatch('[a-f0-9]{64}', expected_sha256):
        raise ValueError('an explicit frozen challenge SHA-256 is required')
    raw = _read(Path(path).absolute(), 2 * 1024 * 1024)
    if digest(raw) != expected_sha256:
        raise ValueError('challenge differs from declared frozen bytes')
    rows = _json(raw)
    if not isinstance(rows, list) or not 2 <= len(rows) <= 256:
        raise ValueError('challenge requires two through 256 cases')
    normalize = lambda text: ' '.join(unicodedata.normalize('NFKC', text).casefold().split())
    known = {normalize(row['query']) for split in ('train', 'development', 'heldout') for row in data[split]}
    ids, queries = set(), set()
    catalogue = {row['id'] for row in data['corpus']}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id', 'family', 'query', 'relevant'}:
            raise ValueError('invalid challenge row')
        for key in ('id', 'family'):
            if not isinstance(row[key], str) or not re.fullmatch('[a-z0-9_-]{1,64}', row[key]):
                raise ValueError('invalid challenge identifier')
        words(row['query'])
        query = normalize(row['query'])
        if row['id'] in ids or query in queries or query in known:
            raise ValueError('duplicate or previously exposed query')
        relevant = row['relevant']
        if (not isinstance(relevant, list) or any(not isinstance(x, str) or x not in catalogue for x in relevant)
                or len(set(relevant)) != len(relevant)):
            raise ValueError('invalid challenge relevance labels')
        ids.add(row['id']); queries.add(query)
    if not any(row['relevant'] for row in rows) or not any(not row['relevant'] for row in rows):
        raise ValueError('challenge requires positive and no-relevant-note cases')
    return rows


def challenge_report(data, model, rows, challenge_sha256):
    results = {method: evaluate(model, data['corpus'], rows, method, model['thresholds'][method])
               for method in ('lexical', 'tfidf', 'trained')}
    return {'challenge_sha256': challenge_sha256, 'case_count': len(rows),
            'dataset_manifest_sha256': data['manifest_sha256'],
            'model_parameters_sha256': digest(json.dumps({'weights': model['weights'], 'bias': model['bias']},
                                                        sort_keys=True, separators=(',', ':')).encode()),
            'training_started': False, 'thresholds_retuned': False,
            'semantic_quality_verified': False, 'runtime_admitted': False,
            'results': results, 'scope': LIMITS,
            'limits': 'Exact normalized query overlap is rejected; semantic leakage, author independence and label correctness are not verified.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'training/evidence_router')
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--challenge', required=True, type=Path)
    parser.add_argument('--challenge-sha256', required=True)
    args = parser.parse_args()
    try:
        data = load_dataset(args.dataset)
        rows = inspect_challenge(args.challenge, args.challenge_sha256, data)
        model = load_model(args.model, data)
        report = challenge_report(data, model, rows, args.challenge_sha256)
    except (ValueError, OSError, TypeError, RecursionError):
        parser.exit(2, 'Invalid local model, dataset or frozen challenge; no training performed.\n')
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__': raise SystemExit(main())
