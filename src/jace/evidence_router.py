"""Offline CPU experiment: a learned router for one fixed synthetic catalogue.

Not a language model, scripture interpreter, runtime retriever, or safety policy.
The module has no network, memory-store, canonical-admission, or model-provider path.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata

from .text import lexical_terms
from .training import _json, _read

FILES = {'corpus.json', 'train.json', 'development.json', 'heldout.json'}
STEPS = 400
LEARNING_RATE = 0.5
L2 = 0.002
MAX_VOCAB = 2048
MAX_BYTES = 2 * 1024 * 1024
STOPWORDS = frozenset('a an the i me my we our you your it its this that these those is are was were be been am to of for and or in on at with by as from which what how should would can could do does did have has had before after about rather than more all one no not'.split())
LIMITS = 'Original synthetic fixed-catalogue routing only; no Agama training, scholarly validation, language generation, unseen-document retrieval, or runtime activation.'


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def words(value: str) -> set[str]:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError('require nonempty text of at most 4096 characters')
    value.encode('utf-8')
    return lexical_terms(value) - STOPWORDS


def load_dataset(directory: str | Path) -> dict:
    root = Path(directory).absolute()
    manifest_raw = _read(root / 'manifest.json', 16384)
    manifest = _json(manifest_raw)
    required = {'schema_version', 'data_kind', 'source', 'license', 'contains_personal_data',
                'canonical_or_scholarly_reviewed', 'split_policy', 'files'}
    if not isinstance(manifest, dict) or set(manifest) != required or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
        raise ValueError('unsupported synthetic router manifest')
    if manifest['data_kind'] != 'original_synthetic' or manifest['contains_personal_data'] is not False or manifest['canonical_or_scholarly_reviewed'] is not False:
        raise ValueError('only original synthetic nonpersonal, noncanonical fixtures are supported')
    for field in ('source', 'license', 'split_policy'):
        words(manifest[field])
    if not isinstance(manifest['files'], dict) or set(manifest['files']) != FILES:
        raise ValueError('manifest must pin exactly corpus/train/development/heldout files')
    payloads = {name: _read(root / name, MAX_BYTES) for name in FILES}
    if manifest['files'] != {name: digest(raw) for name, raw in payloads.items()}:
        raise ValueError('fixture hashes differ from the declared manifest')
    data = {name.removesuffix('.json'): _json(raw) for name, raw in payloads.items()}
    cards = data['corpus']
    if not isinstance(cards, list) or not 2 <= len(cards) <= 32:
        raise ValueError('catalogue must contain 2 through 32 notes')
    ids = set()
    for card in cards:
        if not isinstance(card, dict) or set(card) != {'id', 'title', 'text', 'kind', 'canonical'}:
            raise ValueError('invalid editorial note')
        if not isinstance(card['id'], str) or not re.fullmatch('[a-z0-9_-]{1,64}', card['id']) or card['id'] in ids:
            raise ValueError('invalid or repeated note ID')
        if card['kind'] != 'original_synthetic_editorial_note' or card['canonical'] is not False:
            raise ValueError('religious source material is not admitted by this experiment')
        words(card['title']); words(card['text']); ids.add(card['id'])
    seen_ids, seen_queries, seen_families = set(), set(), set()
    for split in ('train', 'development', 'heldout'):
        rows = data[split]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 256:
            raise ValueError('each split must contain 1 through 256 cases')
        families = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {'id', 'family', 'query', 'relevant'}:
                raise ValueError('invalid routing case')
            for field in ('id', 'family'):
                if not isinstance(row[field], str) or not re.fullmatch('[a-z0-9_-]{1,64}', row[field]):
                    raise ValueError('invalid case ID or family')
            words(row['query'])
            normalized = ' '.join(unicodedata.normalize('NFKC', row['query']).casefold().split())
            if row['id'] in seen_ids or normalized in seen_queries:
                raise ValueError('duplicate ID or normalized query within/across splits')
            if not isinstance(row['relevant'], list) or any(not isinstance(x, str) or x not in ids for x in row['relevant']) or len(set(row['relevant'])) != len(row['relevant']):
                raise ValueError('invalid relevance labels')
            if split == 'train' and len(row['relevant']) != 1:
                raise ValueError('training requires exactly one routing label per case')
            seen_ids.add(row['id']); seen_queries.add(normalized); families.add(row['family'])
        if seen_families & families:
            raise ValueError('scenario families must be separated between splits')
        seen_families |= families
    if {row['relevant'][0] for row in data['train']} != ids:
        raise ValueError('every catalogue note needs training coverage')
    for split in ('development', 'heldout'):
        if not any(row['relevant'] for row in data[split]) or not any(not row['relevant'] for row in data[split]):
            raise ValueError('development and heldout need positives and abstention cases')
    return {**data, 'manifest': manifest, 'manifest_sha256': digest(manifest_raw)}


def vector(query: str, vocabulary: list[str], idf: list[float]) -> dict[int, float]:
    terms = words(query)
    result = {i: idf[i] for i, term in enumerate(vocabulary) if term in terms}
    norm = math.sqrt(sum(value * value for value in result.values()))
    return {key: value / norm for key, value in result.items()} if norm else {}


def softmax(logits: list[float]) -> list[float]:
    maximum = max(logits)
    exp = [math.exp(x - maximum) for x in logits]
    total = sum(exp)
    return [x / total for x in exp]


def probabilities(features: dict[int, float], weights: list[list[float]], bias: list[float]) -> list[float]:
    return softmax([bias[c] + sum(weights[c][i] * value for i, value in features.items()) for c in range(len(bias))])


def objective_gradient(xs, labels, weights, bias, l2=L2):
    """Mean multiclass cross entropy + L2; exact full-batch analytic gradient."""
    count = len(xs)
    gradient = [[l2 * x for x in row] for row in weights]
    bias_gradient = [0.0] * len(bias)
    loss = 0.5 * l2 * sum(x * x for row in weights for x in row)
    for features, label in zip(xs, labels):
        probs = probabilities(features, weights, bias)
        loss -= math.log(max(probs[label], 1e-300)) / count
        for c, probability in enumerate(probs):
            error = (probability - (c == label)) / count
            bias_gradient[c] += error
            for i, value in features.items():
                gradient[c][i] += error * value
    if not math.isfinite(loss) or any(not math.isfinite(x) for row in gradient for x in row):
        raise ValueError('nonfinite optimization result')
    return loss, gradient, bias_gradient


def fit(train: list[dict], corpus: list[dict]) -> tuple[dict, dict]:
    """Only training queries and the fixed catalogue enter vocabulary or gradients.

    Zero initialization is deliberate and deterministic. Hyperparameters are
    fixed here, not selected using development or heldout performance.
    """
    texts = [words(row['query']) for row in train] + [words(card['title'] + ' ' + card['text']) for card in corpus]
    frequencies = Counter(term for text in texts for term in text)
    vocabulary = sorted(frequencies)
    if not 1 <= len(vocabulary) <= MAX_VOCAB:
        raise ValueError('vocabulary exceeds the bounded experiment')
    idf = [math.log((1 + len(texts)) / (1 + frequencies[term])) + 1 for term in vocabulary]
    ids = [card['id'] for card in corpus]
    xs = [vector(row['query'], vocabulary, idf) for row in train]
    labels = [ids.index(row['relevant'][0]) for row in train]
    weights = [[0.0] * len(vocabulary) for _ in ids]
    bias = [0.0] * len(ids)
    initial_sha = digest(encoded({'weights': weights, 'bias': bias}))
    trace = []
    for step in range(STEPS):
        loss, gradient, bias_gradient = objective_gradient(xs, labels, weights, bias)
        grad_norm = math.sqrt(sum(x * x for row in gradient for x in row) + sum(x * x for x in bias_gradient))
        if not math.isfinite(grad_norm) or grad_norm == 0:
            raise ValueError('optimization needs finite nonzero gradients')
        if step == 0 or (step + 1) % 50 == 0:
            trace.append({'update': step, 'regularized_train_loss': loss, 'gradient_l2': grad_norm})
        for c in range(len(ids)):
            weights[c] = [x - LEARNING_RATE * g for x, g in zip(weights[c], gradient[c])]
            bias[c] -= LEARNING_RATE * bias_gradient[c]
    final_loss, _, _ = objective_gradient(xs, labels, weights, bias)
    final_sha = digest(encoded({'weights': weights, 'bias': bias}))
    if final_sha == initial_sha or final_loss >= trace[0]['regularized_train_loss']:
        raise ValueError('training did not change weights and lower training loss')
    model = {'schema_version': 1, 'model_kind': 'fixed_catalogue_softmax_router', 'vocabulary': vocabulary,
             'idf': idf, 'ids': ids, 'weights': weights, 'bias': bias}
    proof = {'algorithm': f'Full-batch analytic-gradient descent on TF-IDF query features, {len(ids)}-way softmax for the fixed catalogue',
             'steps': STEPS, 'learning_rate': LEARNING_RATE, 'l2': L2, 'initialization': 'all zeros; no random seed required',
             'parameter_count': sum(map(len, weights)) + len(bias), 'initial_weights_sha256': initial_sha,
             'final_weights_sha256': final_sha, 'changed_weight_count': sum(x != 0 for row in weights for x in row),
             'weight_delta_l2': math.sqrt(sum(x*x for row in weights for x in row) + sum(x*x for x in bias)),
             'initial_train_loss': trace[0]['regularized_train_loss'], 'final_train_loss': final_loss, 'trace': trace}
    return model, proof


def scores(model: dict, corpus: list[dict], query: str, method: str) -> list[float]:
    if method == 'trained':
        return probabilities(vector(query, model['vocabulary'], model['idf']), model['weights'], model['bias'])
    if method == 'lexical':
        # Raw lexical matching follows the existing store's intersection-count idea.
        terms = lexical_terms(query)
        return [float(len(terms & lexical_terms(card['title'] + ' ' + card['text']))) for card in corpus]
    if method == 'tfidf':
        q = vector(query, model['vocabulary'], model['idf'])
        return [sum(value * q.get(i, 0) for i, value in vector(card['title'] + ' ' + card['text'], model['vocabulary'], model['idf']).items()) for card in corpus]
    raise ValueError('unknown routing method')


def ranked(ids: list[str], values: list[float]) -> list[str]:
    return [ids[i] for i in sorted(range(len(ids)), key=lambda i: (-values[i], ids[i]))]


def evaluate(model: dict, corpus: list[dict], cases: list[dict], method: str, threshold: float) -> dict:
    results = []
    for row in cases:
        values = scores(model, corpus, row['query'], method)
        order = ranked(model['ids'], values)
        selected = order[0] if max(values) >= threshold else None
        relevant = row['relevant']
        results.append({'id': row['id'], 'family': row['family'], 'query': row['query'], 'relevant': relevant,
                        'ranking': order, 'top_score': max(values), 'selected': selected,
                        'top1_correct': order[0] in relevant if relevant else None,
                        'reciprocal_rank': 1 / (min(order.index(x) for x in relevant) + 1) if relevant else None,
                        'decision_correct': selected in relevant if relevant else selected is None})
    positive = [x for x in results if x['relevant']]
    negative = [x for x in results if not x['relevant']]
    accepted = [x for x in results if x['selected'] is not None]
    correct = sum(x['top1_correct'] for x in positive)
    n = len(positive)
    # Wilson interval is descriptive, not a claim of random/independent sampling.
    z = 1.96
    denominator = 1 + z*z/n
    center = (correct/n + z*z/(2*n)) / denominator
    radius = z * math.sqrt(correct/n*(1-correct/n)/n + z*z/(4*n*n)) / denominator
    return {'method': method, 'threshold_from_development': threshold, 'positive_cases': n, 'negative_cases': len(negative),
            'top1_correct': correct, 'top1_accuracy': correct/n, 'top1_wilson_95_descriptive': [center-radius, center+radius],
            'mrr': sum(x['reciprocal_rank'] for x in positive)/n,
            'accepted': len(accepted), 'accepted_correct': sum(x['decision_correct'] for x in accepted),
            'accepted_precision': sum(x['decision_correct'] for x in accepted)/len(accepted) if accepted else None,
            'positive_coverage': sum(x['selected'] is not None for x in positive)/n,
            'negative_rejected': sum(x['selected'] is None for x in negative),
            'decision_accuracy': sum(x['decision_correct'] for x in results)/len(results),
            'family_top1': {family: {'correct': sum(x['top1_correct'] for x in positive if x['family'] == family),
                                    'total': sum(x['family'] == family for x in positive)} for family in sorted({x['family'] for x in positive})},
            'cases': results}


def calibrate(model: dict, corpus: list[dict], development: list[dict], method: str) -> float:
    # Fixed grid; maximize development decision accuracy, conservatively prefer
    # higher rejection on ties. Heldout cases never enter this function.
    grid = {'trained': [x/20 for x in range(4, 20)], 'tfidf': [x/20 for x in range(1, 21)],
            'lexical': [float(x) for x in range(1, 21)]}[method]
    return max(grid, key=lambda threshold: (evaluate(model, corpus, development, method, threshold)['decision_accuracy'], threshold))


def load_model(path: str | Path, data: dict) -> dict:
    model = _json(_read(Path(path).absolute(), MAX_BYTES))
    required = {'schema_version', 'model_kind', 'vocabulary', 'idf', 'ids', 'weights', 'bias', 'manifest_sha256', 'corpus_sha256', 'thresholds'}
    if not isinstance(model, dict) or set(model) != required or type(model['schema_version']) is not int or model['schema_version'] != 1 or model['model_kind'] != 'fixed_catalogue_softmax_router':
        raise ValueError('unsupported inert JSON model')
    if model['manifest_sha256'] != data['manifest_sha256'] or model['corpus_sha256'] != data['manifest']['files']['corpus.json'] or model['ids'] != [x['id'] for x in data['corpus']]:
        raise ValueError('model is bound to a different fixture catalogue or split manifest')
    vocabulary = model['vocabulary']
    if not isinstance(vocabulary, list) or not 1 <= len(vocabulary) <= MAX_VOCAB or any(not isinstance(x, str) or not 1 <= len(x) <= 4096 for x in vocabulary) or sorted(set(vocabulary)) != vocabulary:
        raise ValueError('invalid vocabulary')
    def numeric(values, length, positive=False):
        return isinstance(values, list) and len(values) == length and all(type(x) in (int,float) and abs(x) <= 10000 and math.isfinite(x) and (not positive or x > 0) for x in values)
    if not numeric(model['idf'], len(vocabulary), True) or not numeric(model['bias'], len(model['ids'])) or not isinstance(model['weights'], list) or len(model['weights']) != len(model['ids']) or not all(numeric(row, len(vocabulary)) for row in model['weights']):
        raise ValueError('invalid bounded numeric parameters')
    if not isinstance(model['thresholds'], dict) or set(model['thresholds']) != {'trained','lexical','tfidf'} or any(type(x) not in (int,float) or not math.isfinite(x) or not 0 < x <= 20 for x in model['thresholds'].values()):
        raise ValueError('invalid rejection thresholds')
    return model
