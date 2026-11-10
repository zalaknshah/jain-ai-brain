"""Versioned, optional, offline DeBERTa CPU NLI experiment; never a runtime gate."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import random
import stat
import sys

# Importing this optional runner must not create local bytecode artifacts.
sys.dont_write_bytecode = True
try:
    from . import predict_pretrained_support as common
except ImportError:
    import predict_pretrained_support as common

schema = common.schema
RUNNER_VERSION = 'deberta-support-v1'
MODEL_ID = 'cross-encoder/nli-deberta-v3-base'
REVISION = '6c749ce3425cd33b46d187e45b92bbf96ee12ec7'
WEIGHTS_SHA256 = 'd8148c6d49e0a7925134294c56326c71fe0ab1dc390e37355e00c7efbb488afa'
ARTIFACT_HASHES = {
    'README.md': 'b6a6dd82d5fee7036e3b815ce1d28458df294d8525fc234fb7e7277b6b79d878',
    'config.json': '897e756eb59d3183adb505952e7910e7cbc7750a43f3b3747a96b688d2b02a47',
    'tokenizer_config.json': 'f3eecd07c370ef0bf7dd3780d3cd68cf9c8b00c267e21a208ddcd8f82bfec1a6',
    'special_tokens_map.json': 'ed7c099c988dbb414b18a6980d20cb57b91b7cd119f6f6941eb364b0e892e712',
    'added_tokens.json': 'a4b6bfe668f2b3cf6f0cd535e98a0663d2d0d4a4a15f13075ad3597d33985a23',
    'tokenizer.json': '5124ef2ead1a10a717703bc436de7f353da76d6340e4587719b42b1693707964',
    'model.safetensors': WEIGHTS_SHA256,
}
ARTIFACT_SIZES = {
    'README.md': 2856, 'config.json': 1052, 'tokenizer_config.json': 1346,
    'special_tokens_map.json': 301, 'added_tokens.json': 26,
    'tokenizer.json': 8656624, 'model.safetensors': 737726552,
}
LABELS = ('contradicted', 'supported', 'not_established')
MAX_CASES = 128
MAX_TOKENS = 512
SEPARATOR = '\n\n'
FROZEN_COMMON_SHA256 = '11217322391b15ff6dacb37947f6bafc31b30f9c0abae8d032cec9cf43532e2e'
FROZEN_SCHEMA_SHA256 = 'f24f017ad344d572e61979519730c5fc8dbd1be162fb24d648ab66deae04ae13'
OFFLINE_ENV = {
    **common.OFFLINE_ENV, 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1',
    'OPENBLAS_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1',
    'PYTHONDONTWRITEBYTECODE': '1',
}
LEGACY_BUFFER = 'deberta.embeddings.position_ids'
EXPECTED_CONFIG = {
    'architectures': ['DebertaV2ForSequenceClassification'],
    'model_type': 'deberta-v2', 'hidden_size': 768, 'intermediate_size': 3072,
    'num_attention_heads': 12, 'num_hidden_layers': 12, 'vocab_size': 128100,
    'max_position_embeddings': 512, 'pad_token_id': 0, 'type_vocab_size': 0,
    'relative_attention': True, 'position_biased_input': False,
    'position_buckets': 256, 'max_relative_positions': -1,
    'norm_rel_ebd': 'layer_norm', 'share_att_key': True,
    'pos_att_type': ['p2c', 'c2p'], 'hidden_act': 'gelu',
    'attention_probs_dropout_prob': 0.1, 'hidden_dropout_prob': 0.1,
    'layer_norm_eps': 1e-7, 'initializer_range': 0.02,
    'pooler_dropout': 0, 'pooler_hidden_act': 'gelu', 'pooler_hidden_size': 768,
}
MODEL_LABELS = {0: 'contradiction', 1: 'entailment', 2: 'neutral'}
SPECIAL_IDS = {'pad_token_id': 0, 'cls_token_id': 1, 'bos_token_id': 1,
               'sep_token_id': 2, 'eos_token_id': 2, 'unk_token_id': 3,
               'mask_token_id': 128000}


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_identity():
    """Bind shared behavior to frozen sources, never the MiniLM model identity."""
    shared = _sha256(common.__file__)
    contract = _sha256(schema.__file__)
    if shared != FROZEN_COMMON_SHA256 or contract != FROZEN_SCHEMA_SHA256:
        raise ValueError('frozen common runner or schema changed')
    if (common.LABELS, common.MAX_CASES, common.MAX_TOKENS, common.SEPARATOR) != (
            LABELS, MAX_CASES, MAX_TOKENS, SEPARATOR):
        raise ValueError('frozen decision policy changed')
    return {'runner_version': RUNNER_VERSION, 'runner_sha256': _sha256(__file__),
            'common_runner_sha256': shared, 'schema_sha256': contract}


def verify_artifacts(model_dir):
    """Verify every exact size and SHA before any optional dependency/model load."""
    path = Path(os.path.abspath(model_dir))
    if not ARTIFACT_HASHES or set(ARTIFACT_HASHES) != set(ARTIFACT_SIZES):
        raise ValueError('artifact manifest not frozen')
    if ARTIFACT_HASHES.get('model.safetensors') != WEIGHTS_SHA256:
        raise ValueError('artifact manifest not frozen')
    # Reject symlink directories anywhere in the supplied path, not just its leaf.
    if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_dir():
        raise ValueError('model path must contain only non-symlink directories')
    if {p.name for p in path.iterdir()} != set(ARTIFACT_HASHES):
        raise ValueError('model directory must contain exactly the pinned artifact manifest')
    for name, expected in ARTIFACT_HASHES.items():
        artifact = path / name
        info = artifact.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != ARTIFACT_SIZES[name]:
            raise ValueError(f'artifact must be a regular non-symlink file of pinned size: {name}')
        if _sha256(artifact) != expected:
            raise ValueError(f'artifact hash mismatch: {name}')
    return path


def validate_config(config):
    for key, expected in EXPECTED_CONFIG.items():
        value = getattr(config, key, None)
        if type(value) is not type(expected) or value != expected:
            raise ValueError(f'unexpected model configuration: {key}')
    if (config.num_labels != 3 or config.id2label != MODEL_LABELS
            or config.label2id != {v: k for k, v in MODEL_LABELS.items()}
            or getattr(config, 'auto_map', None)):
        raise ValueError('unexpected model labels or custom-code configuration')


def validate_tokenizer(tokenizer):
    if (getattr(tokenizer, 'is_fast', False) is not True
            or tokenizer.model_max_length != MAX_TOKENS
            or tokenizer.vocab_size != 128000 or len(tokenizer) != 128001
            or getattr(tokenizer, 'do_lower_case', None) is not False):
        raise ValueError('unexpected tokenizer type, limits or vocabulary')
    if any(getattr(tokenizer, key, None) != value for key, value in SPECIAL_IDS.items()):
        raise ValueError('unexpected tokenizer special IDs')
    if tokenizer.build_inputs_with_special_tokens([7], [8]) != [1, 7, 2, 8, 2]:
        raise ValueError('unexpected premise-first pair template')
    if (tokenizer.backend_tokenizer.truncation is not None
            or tokenizer.backend_tokenizer.padding is not None):
        raise ValueError('serialized tokenizer enables truncation or padding')


def validate_loading_info(info):
    """No ignored learned-weight warnings; allow only the inspected legacy buffer."""
    expected_keys = {'missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs'}
    if not isinstance(info, dict) or set(info) != expected_keys:
        raise ValueError('malformed model loading diagnostics')
    if any(not isinstance(info[key], list) for key in expected_keys):
        raise ValueError('malformed model loading diagnostics')
    if info['missing_keys'] or info['mismatched_keys'] or info['error_msgs']:
        raise ValueError('missing, mismatched or failed learned-weight loading')
    if info['unexpected_keys'] not in ([], [LEGACY_BUFFER]):
        raise ValueError('unexpected checkpoint weights')
    return json.loads(schema.canonical_bytes(info))


def validate_checkpoint(model, checkpoint, torch):
    """Cross-check keys, shapes, dtypes and values despite loader ignore lists.

    The old checkpoint persisted position_ids. Modern Transformers reconstructs
    that deterministic, nonlearned buffer. Inspect its bytes and runtime value;
    never broaden loader ignore patterns to suppress its warning.
    """
    state = model.state_dict()
    parameters = dict(model.named_parameters())
    buffers = dict(model.named_buffers())
    checkpoint_keys = set(checkpoint.keys())
    learned_keys = set(parameters)
    if (set(state) - learned_keys not in (set(), {LEGACY_BUFFER})
            or not learned_keys.issubset(state)
            or set(buffers) != {LEGACY_BUFFER}
            or checkpoint_keys != learned_keys | {LEGACY_BUFFER}):
        raise ValueError('checkpoint learned-weight or buffer inventory mismatch')
    elements = 0
    for name, parameter in parameters.items():
        sliced = checkpoint.get_slice(name)
        if (list(parameter.shape) != sliced.get_shape() or sliced.get_dtype() != 'F32'
                or parameter.device.type != 'cpu' or parameter.dtype != torch.float32
                or getattr(parameter, 'is_meta', False)):
            raise ValueError(f'checkpoint learned-weight shape, dtype or device mismatch: {name}')
        if not torch.equal(parameter.detach(), checkpoint.get_tensor(name)):
            raise ValueError(f'loaded learned-weight values do not match checkpoint: {name}')
        elements += parameter.numel()
    if elements != 184424451:
        raise ValueError('unexpected learned parameter count')
    saved = checkpoint.get_tensor(LEGACY_BUFFER)
    expected = torch.arange(MAX_TOKENS, dtype=torch.int64, device='cpu').reshape(1, MAX_TOKENS)
    actual = buffers[LEGACY_BUFFER]
    for tensor in (saved, actual):
        if (tuple(tensor.shape) != (1, MAX_TOKENS) or tensor.dtype != torch.int64
                or tensor.device.type != 'cpu' or not torch.equal(tensor, expected)):
            raise ValueError('unexpected nonlearned position_ids buffer')
    return {'learned_elements': elements, 'learned_dtype': 'F32',
            'all_loaded_parameters_equal_checkpoint': True,
            'verified_nonlearned_buffer': LEGACY_BUFFER, 'buffer_dtype': 'I64',
            'buffer_shape': [1, MAX_TOKENS], 'buffer_values': '0..511'}


class LocalBackend:
    """Explicit standard classes, serialized fast tokenizer and safetensors only."""
    def __init__(self, model_dir):
        sources = source_identity()
        model_dir = verify_artifacts(model_dir)
        os.environ.update(OFFLINE_ENV)
        random.seed(0)
        import torch
        import transformers
        from safetensors import safe_open
        from transformers import DebertaV2ForSequenceClassification, DebertaV2TokenizerFast

        torch.set_num_threads(1)
        if torch.get_num_interop_threads() != 1:
            torch.set_num_interop_threads(1)
        torch.manual_seed(0)
        torch.use_deterministic_algorithms(True)
        self.torch = torch
        self.tokenizer = DebertaV2TokenizerFast.from_pretrained(
            str(model_dir), local_files_only=True, trust_remote_code=False,
            use_fast=True, from_slow=False)
        if type(self.tokenizer) is not DebertaV2TokenizerFast:
            raise ValueError('unexpected tokenizer class')
        validate_tokenizer(self.tokenizer)
        self.model, loading_info = DebertaV2ForSequenceClassification.from_pretrained(
            str(model_dir), local_files_only=True, trust_remote_code=False,
            use_safetensors=True, output_loading_info=True, torch_dtype=torch.float32)
        if type(self.model) is not DebertaV2ForSequenceClassification:
            raise ValueError('unexpected model architecture')
        diagnostics = validate_loading_info(loading_info)
        validate_config(self.model.config)
        self.model.to('cpu')
        self.model.eval()
        with safe_open(str(model_dir / 'model.safetensors'), framework='pt', device='cpu') as checkpoint:
            inventory = validate_checkpoint(self.model, checkpoint, torch)
        self.identity = {
            **sources, 'backend': 'local_pretrained_deberta_cpu', 'model_id': MODEL_ID,
            'revision': REVISION, 'artifact_sha256': dict(ARTIFACT_HASHES),
            'artifact_bytes': dict(ARTIFACT_SIZES), 'python': platform.python_version(),
            'torch': torch.__version__, 'transformers': transformers.__version__,
            'tokenizers': version('tokenizers'), 'safetensors': version('safetensors'),
            'huggingface_hub': version('huggingface-hub'), 'numpy': version('numpy'),
            'platform': platform.platform(), 'device': 'cpu', 'dtype': 'float32',
            'threads': torch.get_num_threads(), 'interop_threads': torch.get_num_interop_threads(),
            'seed': 0, 'deterministic_algorithms': torch.are_deterministic_algorithms_enabled(),
            'eval': not self.model.training, 'offline': True, 'safetensors_only': True,
            'fast_tokenizer': True, 'loading_info': diagnostics, 'checkpoint_inventory': inventory,
        }

    def tokenize(self, premise, hypothesis):
        return dict(self.tokenizer(premise, hypothesis, add_special_tokens=True,
                                   truncation=False, padding=False))

    def logits(self, encoded):
        tensors = {key: self.torch.tensor([value], device='cpu')
                   for key, value in encoded.items()}
        with self.torch.inference_mode():
            return self.model(**tensors).logits.detach().cpu().tolist()


def validate_inputs(value):
    return common.validate_inputs(value)


def run(inputs, backend):
    source_identity()
    return common.run(inputs, backend)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('predict', 'inspect'))
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inputs, _ = schema.read_json(args.inputs)
        validate_inputs(inputs)
        # Keep optional-library notices off the single, bounded JSON stdout record.
        with redirect_stdout(sys.stderr):
            result = run(inputs, LocalBackend(args.model_dir))
        output = result['predictions'] if args.operation == 'predict' else result
        raw = schema.canonical_bytes(output)
        if len(raw) + 1 > schema.MAX_BYTES:
            raise ValueError('output exceeds byte limit')
    except (ValueError, OSError, ImportError, RuntimeError, TypeError, RecursionError) as exc:
        print(f'DeBERTa experiment refused: {exc}', file=sys.stderr)
        return 2
    sys.stdout.buffer.write(raw + b'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
