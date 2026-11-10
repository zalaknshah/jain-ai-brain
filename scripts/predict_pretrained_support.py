"""Optional, offline CPU NLI experiment. Never imported by the JACE runtime."""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import sys

try:
    from . import evaluate_claim_support as schema
except ImportError:
    import evaluate_claim_support as schema

MODEL_ID = 'cross-encoder/nli-MiniLM2-L6-H768'
REVISION = 'b95119ce93d3e065de6214e38cd4a97b0f2f2c6d'
WEIGHTS_SHA256 = 'ec9c5b6a08b60d7a01b465c7ed44b496244dfd1bed3274c95875a74cea89ab35'
# SHA-256 pins from the immutable publisher revision. README pins license/card metadata.
ARTIFACT_HASHES = {'README.md': '1a6e3f880df3584acc1b209c7c667eb22cb7ddd98ab56a5905dda5cfc446ddd1', 'config.json': '8b0e41caff7567c0f53e6983f35591c3dec59507c9173ab125c5823394fb57f3', 'tokenizer.json': '82139106e603ee4e1d5bc99d056ccbed5a92bc24848b1b5a7137c26e00d0dbf6', 'tokenizer_config.json': 'e06f5c3c435fc0255b08b5574cd574eec685390f60c85b27f83d785eb8ecaaa1', 'special_tokens_map.json': '378eb3bf733eb16e65792d7e3fda5b8a4631387ca04d2015199c4d4f22ae554d', 'model.safetensors': 'ec9c5b6a08b60d7a01b465c7ed44b496244dfd1bed3274c95875a74cea89ab35'}
LABELS = ('contradicted', 'supported', 'not_established')
MAX_CASES = 128
MAX_TOKENS = 512
SEPARATOR = '\n\n'
OFFLINE_ENV = {'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
               'HF_HUB_DISABLE_TELEMETRY': '1', 'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1',
               'DO_NOT_TRACK': '1',
               'TOKENIZERS_PARALLELISM': 'false'}


def validate_inputs(value):
    schema._object(value, ('protocol', 'dataset_sha256', 'input_sha256', 'cases'), 'inputs')
    if type(value['protocol']) is not int or value['protocol'] != schema.PROTOCOL:
        raise ValueError('unsupported input protocol')
    for key in ('dataset_sha256', 'input_sha256'):
        digest = value[key]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('invalid input or dataset hash')
    unhashed = {key: val for key, val in value.items() if key != 'input_sha256'}
    if hashlib.sha256(schema.canonical_bytes(unhashed)).hexdigest() != value['input_sha256']:
        raise ValueError('input hash mismatch')
    schema._array(value['cases'], 'cases', MAX_CASES)
    seen = set()
    for case in value['cases']:
        schema._object(case, ('id', 'passages', 'claim', 'citations'), 'case')
        ident = schema._id(case['id'], 'case ID')
        if ident in seen:
            raise ValueError('duplicate case ID')
        seen.add(ident)
        schema._text(case['claim'], 'claim', 2000)
        schema._array(case['passages'], 'passages', 5)
        passages = {}
        for passage in case['passages']:
            schema._object(passage, ('id', 'text'), 'passage')
            pid = schema._id(passage['id'], 'passage ID')
            if pid in passages:
                raise ValueError('duplicate passage ID')
            passages[pid] = schema._text(passage['text'], 'passage text', 8000)
        schema._array(case['citations'], 'citations', 5)
        cited = set()
        for citation in case['citations']:
            schema._object(citation, ('passage_id', 'quote'), 'citation')
            pid = schema._id(citation['passage_id'], 'citation passage ID')
            quote = schema._text(citation['quote'], 'quote', 1000)
            key = (pid, quote)
            if key in cited or pid not in passages or quote not in passages[pid]:
                raise ValueError('citation must be a unique exact excerpt of its supplied passage')
            cited.add(key)
    return value


def verify_artifacts(model_dir):
    """Reject unexpected files, symlinks and any non-pinned artifact bytes."""
    model_dir = Path(model_dir)
    if not ARTIFACT_HASHES or ARTIFACT_HASHES.get('model.safetensors') != WEIGHTS_SHA256:
        raise ValueError('artifact manifest not frozen')
    if not model_dir.is_dir() or model_dir.is_symlink():
        raise ValueError('model directory must be an explicit local directory')
    if {p.name for p in model_dir.iterdir()} != set(ARTIFACT_HASHES):
        raise ValueError('model directory must contain exactly the pinned artifact manifest')
    for name, expected in ARTIFACT_HASHES.items():
        path = model_dir / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('artifact must be a regular non-symlink file')
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f'artifact hash mismatch: {name}')
    return model_dir.resolve()


class LocalBackend:
    """Lazy optional dependencies; no downloads, pickle weights or custom code."""
    def __init__(self, model_dir):
        model_dir = verify_artifacts(model_dir)
        os.environ.update(OFFLINE_ENV)
        import torch
        import transformers
        from transformers import AutoTokenizer, RobertaForSequenceClassification
        torch.set_num_threads(1)
        torch.manual_seed(0)
        torch.use_deterministic_algorithms(True)
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(model_dir), local_files_only=True, trust_remote_code=False,
            use_fast=True)
        self.model = RobertaForSequenceClassification.from_pretrained(
            str(model_dir), local_files_only=True, trust_remote_code=False,
            use_safetensors=True).to('cpu')
        self.model.eval()
        if self.model.config.num_labels != 3 or self.model.config.model_type != 'roberta':
            raise ValueError('unexpected model architecture or label count')
        self.identity = {'backend': 'local_pretrained_cpu', 'model_id': MODEL_ID,
                         'revision': REVISION, 'artifact_sha256': dict(ARTIFACT_HASHES),
                         'python': platform.python_version(), 'torch': torch.__version__,
                         'transformers': transformers.__version__,
                         'tokenizers': version('tokenizers'),
                         'safetensors': version('safetensors'),
                         'platform': platform.platform(),
                         'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         'schema_sha256': hashlib.sha256(Path(schema.__file__).read_bytes()).hexdigest(),
                         'device': 'cpu',
                         'threads': 1, 'seed': 0, 'deterministic_algorithms': True,
                         'eval': True, 'offline': True, 'safetensors_only': True}

    def tokenize(self, premise, hypothesis):
        return dict(self.tokenizer(premise, hypothesis, add_special_tokens=True,
                                   truncation=False, padding=False))

    def logits(self, encoded):
        tensors = {key: self.torch.tensor([value], device='cpu')
                   for key, value in encoded.items()}
        with self.torch.inference_mode():
            return self.model(**tensors).logits.detach().cpu().tolist()


def _token_count(encoded):
    if not isinstance(encoded, dict) or set(encoded) - {'input_ids', 'attention_mask', 'token_type_ids'}:
        raise ValueError('malformed_tokenization')
    ids = encoded.get('input_ids')
    if not isinstance(ids, list) or not ids or any(type(t) is not int or t < 0 for t in ids):
        raise ValueError('malformed_tokenization')
    for value in encoded.values():
        if not isinstance(value, list) or len(value) != len(ids) or any(type(t) is not int or t < 0 for t in value):
            raise ValueError('malformed_tokenization')
    return len(ids)


def _logits(value):
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], list) or len(value[0]) != 3:
        raise ValueError('malformed_logits')
    row = value[0]
    if any(type(x) not in (int, float) for x in row):
        raise ValueError('malformed_logits')
    try:
        finite = all(math.isfinite(x) for x in row)
    except (OverflowError, ValueError):
        finite = False
    if not finite:
        raise ValueError('nonfinite_logits')
    return row


def run(inputs, backend):
    """Injected backend contract: identity, tokenize(pair), logits(encoded)->[1,3]."""
    validate_inputs(inputs)
    identity = json.loads(schema.canonical_bytes(backend.identity))
    if not isinstance(identity, dict) or len(schema.canonical_bytes(identity)) > 16384:
        raise ValueError('invalid backend identity')
    predictions, traces = [], []
    for case in inputs['cases']:
        premise = SEPARATOR.join(p['text'] for p in case['passages'])
        trace = {'case_id': case['id'], 'label': 'abstain', 'reason': None,
                 'token_count': None, 'truncation': False, 'raw_logits': None,
                 'passage_count': len(case['passages']),
                 'premise_sha256': hashlib.sha256(premise.encode()).hexdigest()}
        try:
            encoded = backend.tokenize(premise, case['claim'])
            count = _token_count(encoded)
            trace['token_count'] = count
        except Exception:
            trace['reason'] = 'tokenization_failed_or_malformed'
        else:
            if count > MAX_TOKENS:
                trace['reason'] = 'pair_token_limit_exceeded'
            else:
                try:
                    raw = backend.logits(encoded)
                except Exception:
                    trace['reason'] = 'inference_failed'
                else:
                    try:
                        logits = _logits(raw)
                    except ValueError as exc:
                        trace['reason'] = str(exc)
                    else:
                        trace['raw_logits'] = logits
                        # Ties deterministically choose the first model class index.
                        trace['label'] = LABELS[max(range(3), key=lambda i: logits[i])]
                        trace['reason'] = 'three_class_argmax'
        predictions.append({'case_id': case['id'], 'label': trace['label']})
        traces.append(trace)
    prediction = {'protocol': schema.PROTOCOL, 'input_sha256': inputs['input_sha256'],
                  'predictions': predictions}
    schema.validate_predictions(prediction, inputs)
    return {'protocol': schema.PROTOCOL, 'input_sha256': inputs['input_sha256'],
            'dataset_sha256': inputs['dataset_sha256'], 'identity': identity,
            'policy': {'mapping': list(LABELS), 'max_pair_tokens': MAX_TOKENS,
                       'premise_separator': SEPARATOR, 'truncation': False,
                       'decision': 'argmax; first index on ties; no thresholds'},
            'predictions': prediction, 'traces': traces,
            'scope': 'Experimental textual NLI only; no source truth, calibrated confidence, doctrinal competence or runtime admission.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('predict', 'inspect'))
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inputs, _ = schema.read_json(args.inputs)
        validate_inputs(inputs)  # Reject invalid exports before loading dependencies.
        result = run(inputs, LocalBackend(args.model_dir))
        output = result['predictions'] if args.operation == 'predict' else result
        raw = schema.canonical_bytes(output)
        if len(raw) > schema.MAX_BYTES:
            raise ValueError('output exceeds byte limit')
    except (ValueError, OSError, ImportError, RuntimeError) as exc:
        print(f'pretrained experiment refused: {exc}', file=sys.stderr)
        return 2
    sys.stdout.buffer.write(raw + b'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
