"""Offline, explicitly requested training. Never connected to runtime memory."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

MAX_DATA_BYTES = 2 * 1024 * 1024
MAX_MODEL_BYTES = 64 * 1024 * 1024
MAX_STEPS = 20
MAX_SEQUENCE = 256
WALL_SECONDS = 180
ADDRESS_BYTES = 4 * 1024**3
CPU_SECONDS = 120
FILES = {'config.json', 'tokenizer.json', 'model.safetensors'}


def _read(path: Path, limit: int) -> bytes:
    if path.absolute() != path.resolve() or path.is_symlink() or not path.is_file():
        raise ValueError(f'{path.name}: require a regular, non-symlink file')
    with path.open('rb') as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'{path.name}: file exceeds size limit')
    return data


def _json(raw: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON keys are not accepted')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('invalid UTF-8 JSON') from error


def _text(value, name: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f'{name} must be nonempty text of at most {maximum} characters')
    try:
        value.encode('utf-8')
    except UnicodeError as error:
        raise ValueError(f'{name} must contain valid Unicode') from error
    return value


def _integer(value, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer from {low} to {high}')
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def admit_dataset(train_path: str | Path, evaluation_path: str | Path, manifest_path: str | Path) -> dict:
    """Only explicit synthetic datasets are admitted in this initial lane."""
    raw = [_read(Path(path), MAX_DATA_BYTES) for path in (train_path, evaluation_path)]
    manifest_raw = _read(Path(manifest_path), 16384)
    manifest = _json(manifest_raw)
    required = {'schema_version', 'data_kind', 'source', 'license', 'rights_reviewed', 'content_reviewed',
                'contains_personal_data', 'train_sha256', 'evaluation_sha256'}
    if not isinstance(manifest, dict) or set(manifest) != required or type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
        raise ValueError('unsupported dataset manifest schema')
    if manifest['data_kind'] != 'synthetic' or manifest['rights_reviewed'] is not True or manifest['content_reviewed'] is not True or manifest['contains_personal_data'] is not False:
        raise ValueError('only explicitly reviewed synthetic, non-personal data is supported; memory and collected corpora are not admitted')
    for name in ('source', 'license'):
        _text(manifest[name], name, 512)
    if [manifest['train_sha256'], manifest['evaluation_sha256']] != [_sha(value) for value in raw]:
        raise ValueError('dataset hashes do not match the reviewed manifest')
    splits = []
    seen_ids, seen_prompts = set(), set()
    for payload in raw:
        rows = []
        for line in payload.splitlines():
            if not line.strip():
                raise ValueError('blank JSONL records are not accepted')
            row = _json(line)
            if not isinstance(row, dict) or set(row) != {'id', 'instruction', 'response'}:
                raise ValueError('each record requires only id, instruction and response')
            if not isinstance(row['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', row['id']):
                raise ValueError('invalid record ID')
            _text(row['instruction'], 'instruction'); _text(row['response'], 'response')
            key = ' '.join(unicodedata.normalize('NFKC', row['instruction']).casefold().split())
            if row['id'] in seen_ids or key in seen_prompts:
                raise ValueError('duplicate record ID or normalized prompt across/within splits')
            seen_ids.add(row['id']); seen_prompts.add(key); rows.append(row)
            if len(rows) > 256:
                raise ValueError('at most 256 records per split are supported')
        if not rows:
            raise ValueError('both training and held-out evaluation must be nonempty')
        splits.append(rows)
    return {'train': splits[0], 'evaluation': splits[1], 'manifest': manifest,
            'manifest_sha256': _sha(manifest_raw)}


def admit_model(model_path: str | Path, manifest_path: str | Path) -> dict:
    directory = Path(model_path)
    if directory.absolute() != directory.resolve() or directory.is_symlink() or not directory.is_dir():
        raise ValueError('model must be a local non-symlink directory, never a Hub ID')
    if {entry.name for entry in directory.iterdir()} != FILES:
        raise ValueError('model directory must contain only config.json, tokenizer.json and model.safetensors; no code, pickle or extra files')
    manifest_raw = _read(Path(manifest_path), 16384)
    manifest = _json(manifest_raw)
    if not isinstance(manifest, dict) or set(manifest) != {'source', 'license', 'rights_reviewed', 'files'} or manifest['rights_reviewed'] is not True:
        raise ValueError('a separate reviewed model-rights manifest is required')
    _text(manifest['source'], 'model source', 512); _text(manifest['license'], 'model license', 512)
    raw = {name: _read(directory / name, MAX_MODEL_BYTES if name.endswith('.safetensors') else MAX_DATA_BYTES) for name in FILES}
    hashes = {name: _sha(data) for name, data in raw.items()}
    if manifest['files'] != hashes:
        raise ValueError('model hashes do not match the reviewed manifest')
    config = _json(raw['config.json'])
    if not isinstance(config, dict) or config.get('model_type') != 'llama' or 'auto_map' in config:
        raise ValueError('only the built-in Llama architecture without custom code is supported')
    allowed = {'model_type', 'architectures', 'hidden_size', 'intermediate_size', 'num_hidden_layers', 'num_attention_heads',
               'num_key_value_heads', 'max_position_embeddings', 'vocab_size', 'rms_norm_eps', 'rope_theta',
               'attention_bias', 'tie_word_embeddings', 'bos_token_id', 'eos_token_id', 'pad_token_id', 'torch_dtype',
               'transformers_version', '_name_or_path', 'initializer_range', 'use_cache', 'attention_dropout', 'mlp_bias'}
    if set(config) - allowed:
        raise ValueError('unsupported model configuration fields')
    for key, lo, hi in [('hidden_size', 8, 512), ('intermediate_size', 8, 2048), ('num_hidden_layers', 1, 8),
                        ('num_attention_heads', 1, 16), ('num_key_value_heads', 1, 16), ('max_position_embeddings', 32, 4096), ('vocab_size', 8, 8192)]:
        _integer(config.get(key), key, lo, hi)
    if config['hidden_size'] % config['num_attention_heads'] or config['num_attention_heads'] % config['num_key_value_heads']:
        raise ValueError('incompatible attention dimensions')
    h, inter, layers, vocab = (config[k] for k in ('hidden_size', 'intermediate_size', 'num_hidden_layers', 'vocab_size'))
    if 2 * h * vocab + layers * (4 * h * h + 3 * h * inter + 2 * h) > 16_000_000:
        raise ValueError('model configuration exceeds the allocation budget')
    if config.get('architectures', ['LlamaForCausalLM']) != ['LlamaForCausalLM']:
        raise ValueError('unsupported architecture class')
    for key in ('rms_norm_eps', 'rope_theta', 'initializer_range', 'attention_dropout'):
        if key in config and (type(config[key]) not in (int, float) or not 0 <= config[key] <= 1_000_000 or not math.isfinite(config[key])):
            raise ValueError('invalid model numeric configuration')
    # Parse inert safetensors metadata, never deserialize pickle or executable objects.
    weights = raw['model.safetensors']
    if len(weights) < 8:
        raise ValueError('invalid safetensors header')
    header_length = int.from_bytes(weights[:8], 'little')
    if not 2 <= header_length <= MAX_DATA_BYTES or 8 + header_length > len(weights):
        raise ValueError('invalid safetensors header size')
    header = _json(weights[8:8 + header_length])
    if not isinstance(header, dict) or not 1 <= len(header) <= 1024:
        raise ValueError('invalid safetensors tensor inventory')
    total = 0
    widths = {'F32': 4, 'F16': 2, 'BF16': 2}
    ranges = []
    for name, spec in header.items():
        if name == '__metadata__':
            if not isinstance(spec, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in spec.items()):
                raise ValueError('invalid safetensors metadata')
            continue
        if not isinstance(spec, dict) or set(spec) != {'dtype', 'shape', 'data_offsets'} or not isinstance(spec['dtype'], str) or spec['dtype'] not in widths:
            raise ValueError('only ordinary floating-point base weights are supported')
        shape = spec['shape']; offsets = spec['data_offsets']
        if not isinstance(shape, list) or not 1 <= len(shape) <= 4:
            raise ValueError('invalid tensor shape')
        count = math.prod(_integer(n, 'tensor dimension', 1, 8192) for n in shape)
        total += count
        if total > 16_000_000 or not isinstance(offsets, list) or len(offsets) != 2:
            raise ValueError('model exceeds the bounded tensor budget')
        start, end = [_integer(n, 'tensor offset', 0, len(weights) - 8 - header_length) for n in offsets]
        if end - start != count * widths[spec['dtype']]:
            raise ValueError('tensor bytes do not match shape')
        ranges.append((start, end))
    position = 0
    for start, end in sorted(ranges):
        if start != position:
            raise ValueError('tensor bytes must be contiguous and non-overlapping')
        position = end
    if not ranges or position != len(weights) - 8 - header_length:
        raise ValueError('unaccounted safetensors data')
    tokenizer = _json(raw['tokenizer.json'])
    if not isinstance(tokenizer, dict) or not isinstance(tokenizer.get('model'), dict) or tokenizer['model'].get('type') not in ('WordLevel', 'BPE'):
        raise ValueError('a self-contained tokenizer JSON is required')
    return {'config': config, 'files': hashes, 'manifest_sha256': _sha(manifest_raw), 'tensor_parameters': total}


def prepare_training(train_path, evaluation_path, dataset_manifest, model_path, model_manifest, *, steps=5, sequence_length=128) -> dict:
    _integer(steps, 'steps', 1, MAX_STEPS)
    _integer(sequence_length, 'sequence_length', 32, MAX_SEQUENCE)
    data = admit_dataset(train_path, evaluation_path, dataset_manifest)
    model = admit_model(model_path, model_manifest)
    if sequence_length > model['config']['max_position_embeddings']:
        raise ValueError('sequence length exceeds model context')
    return {'data': data, 'model': model, 'steps': steps, 'sequence_length': sequence_length}


def run_training(train_path, evaluation_path, dataset_manifest, model_path, model_manifest, output_path, *,
                 steps=5, sequence_length=128, confirm_training=False) -> dict:
    if confirm_training is not True:
        raise ValueError('explicit --confirm-training is required; no training has started')
    if sys.platform != 'linux':
        raise RuntimeError('bounded training worker currently requires Linux resource limits')
    plan = prepare_training(train_path, evaluation_path, dataset_manifest, model_path, model_manifest,
                            steps=steps, sequence_length=sequence_length)
    output = Path(output_path).absolute()
    if output.parent.absolute() != output.parent.resolve() or output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError('output must be a new directory under an existing parent; nothing is overwritten')
    # Revalidate the exact admitted hashes inside the worker immediately before loading.
    job = {'train': str(Path(train_path).absolute()), 'evaluation': str(Path(evaluation_path).absolute()),
           'dataset_manifest': str(Path(dataset_manifest).absolute()), 'model': str(Path(model_path).absolute()),
           'model_manifest': str(Path(model_manifest).absolute()), 'output': str(output),
           'steps': steps, 'sequence_length': sequence_length,
           'expected_dataset': plan['data']['manifest_sha256'], 'expected_model': plan['model']['manifest_sha256'],
           'confirm_training': True}
    env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR') if key in os.environ}
    env.update({'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'HF_HUB_OFFLINE': '1', 'HF_DATASETS_OFFLINE': '1',
                'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1', 'DO_NOT_TRACK': '1',
                'WANDB_MODE': 'disabled', 'PYTHONNOUSERSITE': '1', 'TOKENIZERS_PARALLELISM': 'false', 'OMP_NUM_THREADS': '1',
                'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'CUDA_VISIBLE_DEVICES': '0'})
    try:
        result = subprocess.run([sys.executable, '-m', 'jace.training_worker'], input=json.dumps(job), text=True,
                                capture_output=True, timeout=WALL_SECONDS, env=env, check=False,
                                cwd=str(Path(__file__).resolve().parents[1]))
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('training worker exceeded its wall-time limit; no completed run is claimed') from error
    if result.returncode != 0:
        raise RuntimeError('training worker did not complete; inspect the local failure marker if created. No automatic retry or resource expansion. ' + result.stderr[-1200:])
    report = _json(result.stdout.encode())
    if not isinstance(report, dict) or report.get('completed') is not True:
        raise RuntimeError('worker did not provide a completed training report')
    return report
