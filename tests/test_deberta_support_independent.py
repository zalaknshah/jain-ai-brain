"""Independent, stdlib-only adapter contract tests with invented inert inputs.

No evaluation files, actual checkpoint, optional ML imports or network are used.
Run only this file with unittest discovery to preserve review data separation.
"""
from __future__ import annotations

import builtins
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
from scripts import predict_deberta_support as adapter


ROOT = Path(__file__).resolve().parents[1]
PINS = {
    'README.md': ('b6a6dd82d5fee7036e3b815ce1d28458df294d8525fc234fb7e7277b6b79d878', 2856),
    'config.json': ('897e756eb59d3183adb505952e7910e7cbc7750a43f3b3747a96b688d2b02a47', 1052),
    'tokenizer_config.json': ('f3eecd07c370ef0bf7dd3780d3cd68cf9c8b00c267e21a208ddcd8f82bfec1a6', 1346),
    'special_tokens_map.json': ('ed7c099c988dbb414b18a6980d20cb57b91b7cd119f6f6941eb364b0e892e712', 301),
    'added_tokens.json': ('a4b6bfe668f2b3cf6f0cd535e98a0663d2d0d4a4a15f13075ad3597d33985a23', 26),
    'tokenizer.json': ('5124ef2ead1a10a717703bc436de7f353da76d6340e4587719b42b1693707964', 8656624),
    'model.safetensors': ('d8148c6d49e0a7925134294c56326c71fe0ab1dc390e37355e00c7efbb488afa', 737726552),
}
COMMON_SHA = '11217322391b15ff6dacb37947f6bafc31b30f9c0abae8d032cec9cf43532e2e'
SCHEMA_SHA = 'f24f017ad344d572e61979519730c5fc8dbd1be162fb24d648ab66deae04ae13'
BUFFER = 'deberta.embeddings.position_ids'


def bind(value):
    value = copy.deepcopy(value)
    value.pop('input_sha256', None)
    value['input_sha256'] = hashlib.sha256(adapter.schema.canonical_bytes(value)).hexdigest()
    return value


def inputs():
    return bind({'protocol': 1, 'dataset_sha256': 'c' * 64, 'cases': [{
        'id': 'invented-independent-1',
        'passages': [{'id': 'p1', 'text': 'Invented amber disk.'},
                     {'id': 'p2', 'text': 'Invented blue cube.'}],
        'claim': 'Invented test claim.',
        'citations': [{'passage_id': 'p1', 'quote': 'amber disk'}],
    }]})


class StubBackend:
    identity = {'backend': 'independent_synthetic_only'}

    def __init__(self, count=7, logits=None, encoded=None):
        self.count = count
        self.raw = [[1.0, 2.0, 3.0]] if logits is None else logits
        self.encoded = encoded
        self.calls = []

    def tokenize(self, premise, hypothesis):
        self.calls.append(('tokenize', premise, hypothesis))
        if isinstance(self.encoded, Exception):
            raise self.encoded
        if self.encoded is not None:
            return self.encoded
        return {'input_ids': [7] * self.count, 'attention_mask': [1] * self.count}

    def logits(self, encoded):
        self.calls.append(('logits', encoded))
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw


class SyntheticTokenizer:
    is_fast = True
    model_max_length = 512
    vocab_size = 128000
    do_lower_case = False
    pad_token_id, cls_token_id, bos_token_id = 0, 1, 1
    sep_token_id, eos_token_id, unk_token_id, mask_token_id = 2, 2, 3, 128000

    def __init__(self):
        self.backend_tokenizer = SimpleNamespace(truncation=None, padding=None)
        self.calls = []

    def __len__(self):
        return 128001

    def build_inputs_with_special_tokens(self, first, second):
        return [1, *first, 2, *second, 2]

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {'input_ids': [1, 7, 2, 8, 2]}


class FakeTensor:
    def __init__(self, shape, dtype='float32', data='trained', device='cpu', is_meta=False):
        self.shape, self.dtype, self.data = tuple(shape), dtype, data
        self.device, self.is_meta = SimpleNamespace(type=device), is_meta

    def numel(self):
        return math.prod(self.shape)

    def detach(self):
        return self

    def reshape(self, *shape):
        return FakeTensor(shape, self.dtype, self.data, self.device.type)


class FakeTorch:
    float32, int64 = 'float32', 'int64'

    @staticmethod
    def equal(a, b):
        return (a.shape, a.dtype, a.data) == (b.shape, b.dtype, b.data)

    @staticmethod
    def arange(n, dtype, device):
        return FakeTensor((n,), dtype, tuple(range(n)), device)


class FakeCheckpoint:
    def __init__(self, tensors):
        self.tensors = tensors

    def keys(self):
        return self.tensors.keys()

    def get_tensor(self, name):
        return self.tensors[name]

    def get_slice(self, name):
        tensor = self.tensors[name]
        return SimpleNamespace(get_shape=lambda: list(tensor.shape),
                               get_dtype=lambda: {'float32': 'F32', 'int64': 'I64'}.get(tensor.dtype, 'BAD'))


def checkpoint_fixture():
    parameters = {'invented.weight': FakeTensor((184424448,)),
                  'invented.bias': FakeTensor((3,))}
    buffer = FakeTensor((1, 512), 'int64', tuple(range(512)))
    buffers = {BUFFER: buffer}
    state = dict(parameters)
    model = SimpleNamespace(named_parameters=lambda: parameters.items(),
                            named_buffers=lambda: buffers.items(), state_dict=lambda: state)
    checkpoint = FakeCheckpoint(copy.deepcopy({**parameters, **buffers}))
    return model, checkpoint, parameters, buffers, state


class IndependentIdentityTests(unittest.TestCase):
    def test_exact_independently_recorded_manifest_and_identity(self):
        self.assertEqual(adapter.MODEL_ID, 'cross-encoder/nli-deberta-v3-base')
        self.assertEqual(adapter.REVISION, '6c749ce3425cd33b46d187e45b92bbf96ee12ec7')
        self.assertEqual(adapter.ARTIFACT_HASHES, {k: v[0] for k, v in PINS.items()})
        self.assertEqual(adapter.ARTIFACT_SIZES, {k: v[1] for k, v in PINS.items()})
        self.assertEqual(adapter.WEIGHTS_SHA256, PINS['model.safetensors'][0])
        self.assertEqual(sum(adapter.ARTIFACT_SIZES.values()), 746388757)
        self.assertEqual(adapter.MODEL_LABELS, {0: 'contradiction', 1: 'entailment', 2: 'neutral'})
        self.assertEqual(adapter.LABELS, ('contradicted', 'supported', 'not_established'))
        self.assertEqual((adapter.MAX_CASES, adapter.MAX_TOKENS, adapter.SEPARATOR), (128, 512, '\n\n'))

    def test_actual_separate_source_fingerprints(self):
        identity = adapter.source_identity()
        self.assertEqual(identity, {
            'runner_version': 'deberta-support-v1',
            'runner_sha256': hashlib.sha256(Path(adapter.__file__).read_bytes()).hexdigest(),
            'common_runner_sha256': COMMON_SHA, 'schema_sha256': SCHEMA_SHA})
        self.assertNotEqual(identity['runner_sha256'], identity['common_runner_sha256'])

    def test_changed_shared_source_or_policy_refuses_before_tokenization(self):
        original = adapter._sha256
        for target in (adapter.common.__file__, adapter.schema.__file__):
            with self.subTest(target=target):
                backend = StubBackend()
                with patch.object(adapter, '_sha256', side_effect=lambda p: '0' * 64 if str(p) == target else original(p)):
                    with self.assertRaises(ValueError):
                        adapter.run(inputs(), backend)
                self.assertEqual(backend.calls, [])
        with patch.object(adapter.common, 'MAX_TOKENS', 513), self.assertRaises(ValueError):
            adapter.source_identity()

    def test_optional_dependencies_not_imported_on_module_import(self):
        code = """
import builtins, importlib, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'torch', 'transformers', 'safetensors', 'tokenizers', 'numpy'}:
        raise AssertionError('optional import attempted: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
importlib.import_module('scripts.predict_deberta_support')
"""
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


class IndependentManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='deberta-independent-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root / 'model'
        self.model.mkdir()
        hashes, sizes = {}, {}
        for name in PINS:
            data = ('independent inert bytes for ' + name).encode()
            (self.model / name).write_bytes(data)
            hashes[name] = hashlib.sha256(data).hexdigest()
            sizes[name] = len(data)
        for key, value in [('ARTIFACT_HASHES', hashes), ('ARTIFACT_SIZES', sizes),
                           ('WEIGHTS_SHA256', hashes['model.safetensors'])]:
            patcher = patch.object(adapter, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_tiny_exact_manifest_passes(self):
        self.assertEqual(adapter.verify_artifacts(self.model), self.model)

    def test_same_size_tampering_fails_hash(self):
        path = self.model / 'README.md'
        path.write_bytes(b'X' * path.stat().st_size)
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            adapter.verify_artifacts(self.model)

    def test_size_tampering_fails_before_hash(self):
        (self.model / 'config.json').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError, 'pinned size'):
            adapter.verify_artifacts(self.model)

    def test_missing_extra_and_directory_artifact_refuse(self):
        extra = self.model / 'spm.model'
        extra.write_bytes(b'extra')
        with self.assertRaises(ValueError):
            adapter.verify_artifacts(self.model)
        extra.unlink()
        path = self.model / 'README.md'
        path.unlink()
        with self.assertRaises(ValueError):
            adapter.verify_artifacts(self.model)
        path.mkdir()
        with self.assertRaises(ValueError):
            adapter.verify_artifacts(self.model)

    def test_file_leaf_and_ancestor_symlinks_refuse(self):
        original = self.model / 'README.md'
        target = self.root / 'outside-readme'
        original.rename(target)
        original.symlink_to(target)
        with self.assertRaises(ValueError):
            adapter.verify_artifacts(self.model)
        original.unlink()
        target.rename(original)
        alias = self.root / 'alias'
        alias.symlink_to(self.model, target_is_directory=True)
        with self.assertRaises(ValueError):
            adapter.verify_artifacts(alias)
        ancestor = self.root / 'ancestor'
        ancestor.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            adapter.verify_artifacts(ancestor / 'model')

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO required')
    def test_fifo_artifact_refuses_without_opening(self):
        path = self.model / 'README.md'
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(ValueError):
            adapter.verify_artifacts(self.model)

    def test_invalid_artifacts_fail_before_optional_imports(self):
        original = builtins.__import__
        attempts = []
        def guarded(name, *args, **kwargs):
            if name.split('.')[0] in {'torch', 'transformers', 'safetensors'}:
                attempts.append(name)
                raise AssertionError('ML import before artifact validation')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=guarded):
            with self.assertRaises(ValueError):
                adapter.LocalBackend(self.root / 'absent')
        self.assertEqual(attempts, [])


class IndependentConfigAndLoadingTests(unittest.TestCase):
    def config(self):
        return SimpleNamespace(**copy.deepcopy(adapter.EXPECTED_CONFIG), num_labels=3,
                               id2label={0: 'contradiction', 1: 'entailment', 2: 'neutral'},
                               label2id={'contradiction': 0, 'entailment': 1, 'neutral': 2})

    def test_every_configuration_field_fails_closed_on_change(self):
        adapter.validate_config(self.config())
        for field in adapter.EXPECTED_CONFIG:
            with self.subTest(field=field):
                config = self.config()
                setattr(config, field, None)
                with self.assertRaises(ValueError):
                    adapter.validate_config(config)
        config = self.config()
        config.hidden_size = 768.0
        with self.assertRaises(ValueError):
            adapter.validate_config(config)

    def test_wrong_labels_num_labels_and_custom_code_refuse(self):
        for field, value in [('num_labels', 2), ('id2label', {0: 'entailment', 1: 'contradiction', 2: 'neutral'}),
                             ('label2id', {'entailment': 0, 'contradiction': 1, 'neutral': 2}),
                             ('auto_map', {'AutoModel': 'untrusted.custom'})]:
            with self.subTest(field=field):
                config = self.config()
                setattr(config, field, value)
                with self.assertRaises(ValueError):
                    adapter.validate_config(config)

    def test_fast_tokenizer_inventory_and_no_stored_truncation(self):
        adapter.validate_tokenizer(SyntheticTokenizer())
        for field, value in [('is_fast', False), ('model_max_length', 1024), ('vocab_size', 128001),
                             ('do_lower_case', True), ('pad_token_id', 9), ('mask_token_id', 3)]:
            with self.subTest(field=field):
                tokenizer = SyntheticTokenizer()
                setattr(tokenizer, field, value)
                with self.assertRaises(ValueError):
                    adapter.validate_tokenizer(tokenizer)
        for field in ('truncation', 'padding'):
            tokenizer = SyntheticTokenizer()
            setattr(tokenizer.backend_tokenizer, field, {})
            with self.assertRaises(ValueError):
                adapter.validate_tokenizer(tokenizer)
        tokenizer = SyntheticTokenizer()
        tokenizer.build_inputs_with_special_tokens = lambda a, b: [1, *b, 2, *a, 2]
        with self.assertRaises(ValueError):
            adapter.validate_tokenizer(tokenizer)

    def test_tokenize_explicit_pair_and_full_length_flags(self):
        backend = object.__new__(adapter.LocalBackend)
        backend.tokenizer = SyntheticTokenizer()
        self.assertEqual(backend.tokenize('first entire premise', 'second claim'), {'input_ids': [1, 7, 2, 8, 2]})
        self.assertEqual(backend.tokenizer.calls, [(('first entire premise', 'second claim'),
                                                  {'add_special_tokens': True, 'truncation': False, 'padding': False})])

    def test_diagnostics_only_allow_empty_or_exact_legacy_unexpected_buffer(self):
        empty = {'missing_keys': [], 'unexpected_keys': [], 'mismatched_keys': [], 'error_msgs': []}
        self.assertEqual(adapter.validate_loading_info(empty), empty)
        allowed = {**empty, 'unexpected_keys': [BUFFER]}
        self.assertEqual(adapter.validate_loading_info(allowed), allowed)
        self.assertIsNot(adapter.validate_loading_info(empty)['missing_keys'], empty['missing_keys'])
        changes = [('missing_keys', ['classifier.weight']), ('missing_keys', [BUFFER]),
                   ('unexpected_keys', ['deberta.embeddings.position_embeddings.weight']),
                   ('unexpected_keys', [BUFFER, BUFFER]), ('mismatched_keys', ['classifier.bias']),
                   ('error_msgs', ['failed']), ('missing_keys', ())]
        for field, value in changes:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                adapter.validate_loading_info({**empty, field: value})
        for value in (None, [], {}, {**empty, 'extra': []}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                adapter.validate_loading_info(value)

    def test_checkpoint_equal_parameters_and_exact_legacy_buffer(self):
        model, checkpoint, _, _, _ = checkpoint_fixture()
        result = adapter.validate_checkpoint(model, checkpoint, FakeTorch)
        self.assertTrue(result['all_loaded_parameters_equal_checkpoint'])
        self.assertEqual(result['learned_elements'], 184424451)
        self.assertEqual(result['verified_nonlearned_buffer'], BUFFER)

    def test_checkpoint_missing_extra_and_wrong_state_or_buffer_inventory_refuse(self):
        mutations = [lambda cp, p, b, s: cp.tensors.pop('invented.bias'),
                     lambda cp, p, b, s: cp.tensors.update(extra=FakeTensor((1,))),
                     lambda cp, p, b, s: s.pop('invented.bias'),
                     lambda cp, p, b, s: s.update(extra=FakeTensor((1,))),
                     lambda cp, p, b, s: b.clear(),
                     lambda cp, p, b, s: b.update(extra=FakeTensor((1,)))]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                model, cp, params, buffers, state = checkpoint_fixture()
                mutate(cp, params, buffers, state)
                with self.assertRaises(ValueError):
                    adapter.validate_checkpoint(model, cp, FakeTorch)

    def test_checkpoint_reinitialized_wrong_dtype_shape_device_meta_and_total_refuse(self):
        mutations = [lambda cp, p: setattr(p['invented.bias'], 'data', 'random-initialization'),
                     lambda cp, p: setattr(p['invented.bias'], 'dtype', 'float16'),
                     lambda cp, p: setattr(cp.tensors['invented.bias'], 'dtype', 'float16'),
                     lambda cp, p: setattr(cp.tensors['invented.bias'], 'shape', (4,)),
                     lambda cp, p: setattr(p['invented.bias'].device, 'type', 'cuda'),
                     lambda cp, p: setattr(p['invented.bias'], 'is_meta', True),
                     lambda cp, p: (setattr(p['invented.bias'], 'shape', (2,)),
                                    setattr(cp.tensors['invented.bias'], 'shape', (2,)))]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                model, cp, params, _, _ = checkpoint_fixture()
                mutate(cp, params)
                with self.assertRaises(ValueError):
                    adapter.validate_checkpoint(model, cp, FakeTorch)

    def test_both_checkpoint_and_runtime_legacy_buffer_values_are_checked(self):
        for location in ('checkpoint', 'runtime'):
            for field, value in [('shape', (512,)), ('dtype', 'float32'), ('data', tuple(reversed(range(512))))]:
                with self.subTest(location=location, field=field):
                    model, cp, _, buffers, _ = checkpoint_fixture()
                    target = cp.tensors[BUFFER] if location == 'checkpoint' else buffers[BUFFER]
                    setattr(target, field, value)
                    with self.assertRaises(ValueError):
                        adapter.validate_checkpoint(model, cp, FakeTorch)


class IndependentDecisionAndInputTests(unittest.TestCase):
    def test_all_complete_passages_order_and_exact_output_contract(self):
        data, backend = inputs(), StubBackend()
        result = adapter.run(data, backend)
        self.assertEqual(backend.calls[0], ('tokenize', 'Invented amber disk.\n\nInvented blue cube.', 'Invented test claim.'))
        self.assertEqual(result['predictions'], {'protocol': 1, 'input_sha256': data['input_sha256'],
                                                'predictions': [{'case_id': 'invented-independent-1', 'label': 'not_established'}]})
        self.assertEqual(result['policy'], {'mapping': ['contradicted', 'supported', 'not_established'],
                                           'max_pair_tokens': 512, 'premise_separator': '\n\n', 'truncation': False,
                                           'decision': 'argmax; first index on ties; no thresholds'})
        self.assertEqual(set(result['predictions']), {'protocol', 'input_sha256', 'predictions'})

    def test_512_allowed_513_abstains_without_logits(self):
        for count in (512, 513):
            with self.subTest(count=count):
                backend = StubBackend(count=count)
                trace = adapter.run(inputs(), backend)['traces'][0]
                self.assertEqual(trace['token_count'], count)
                self.assertFalse(trace['truncation'])
                self.assertEqual(len(backend.calls), 2 if count == 512 else 1)
                self.assertEqual(trace['reason'], 'three_class_argmax' if count == 512 else 'pair_token_limit_exceeded')
                self.assertEqual(trace['label'], 'not_established' if count == 512 else 'abstain')

    def test_all_classes_negative_logits_and_first_index_ties_without_threshold(self):
        for logits, label in [([3, 2, 1], 'contradicted'), ([1, 3, 2], 'supported'), ([1, 2, 3], 'not_established'),
                              ([0, 0, 0], 'contradicted'), ([0, 2, 2], 'supported'), ([-9, -8, -7], 'not_established'),
                              ([0.0, 1e-200, 0.0], 'supported')]:
            with self.subTest(logits=logits):
                trace = adapter.run(inputs(), StubBackend(logits=[logits]))['traces'][0]
                self.assertEqual(trace['label'], label)
                self.assertEqual(trace['raw_logits'], logits)

    def test_malformed_and_failed_tokenization_never_calls_logits(self):
        values = [{}, {'input_ids': []}, {'input_ids': [True]}, {'input_ids': [-1]}, {'input_ids': [1.0]},
                  {'input_ids': [1, 2], 'attention_mask': [1]}, {'input_ids': [1], 'extra': [1]},
                  {'input_ids': [1], 'attention_mask': [False]}, RuntimeError('synthetic tokenizer failure')]
        for value in values:
            with self.subTest(value=value):
                backend = StubBackend(encoded=value)
                trace = adapter.run(inputs(), backend)['traces'][0]
                self.assertEqual((trace['label'], trace['reason']), ('abstain', 'tokenization_failed_or_malformed'))
                self.assertEqual(len(backend.calls), 1)

    def test_malformed_nonfinite_and_failed_logits_abstain(self):
        cases = [([], 'malformed_logits'), ([[1, 2]], 'malformed_logits'), ([[True, 1, 2]], 'malformed_logits'),
                 ([[1, 2, '3']], 'malformed_logits'), ([[float('nan'), 0, 1]], 'nonfinite_logits'),
                 ([[float('inf'), 0, 1]], 'nonfinite_logits'), ([[10 ** 1000, 0, 1]], 'nonfinite_logits'),
                 (RuntimeError('synthetic inference failure'), 'inference_failed')]
        for value, reason in cases:
            with self.subTest(reason=reason):
                trace = adapter.run(inputs(), StubBackend(logits=value))['traces'][0]
                self.assertEqual((trace['label'], trace['reason']), ('abstain', reason))
                self.assertIsNone(trace['raw_logits'])

    def test_extra_gold_and_metadata_fields_rejected_at_every_object_boundary(self):
        for location in ('root', 'case', 'passage', 'citation'):
            for field in ('label', 'group_id', 'rationale', 'extra'):
                with self.subTest(location=location, field=field):
                    value = inputs()
                    targets = {'root': value, 'case': value['cases'][0], 'passage': value['cases'][0]['passages'][0],
                               'citation': value['cases'][0]['citations'][0]}
                    targets[location][field] = 'forbidden synthetic field'
                    with self.assertRaises(ValueError):
                        adapter.validate_inputs(bind(value))

    def test_invalid_hash_protocol_duplicates_citations_text_and_limits(self):
        mutations = [lambda v: v.update(protocol=True), lambda v: v.update(dataset_sha256='z' * 64),
                     lambda v: v['cases'].append(copy.deepcopy(v['cases'][0])),
                     lambda v: v['cases'][0]['passages'].append(copy.deepcopy(v['cases'][0]['passages'][0])),
                     lambda v: v['cases'][0]['citations'].append(copy.deepcopy(v['cases'][0]['citations'][0])),
                     lambda v: v['cases'][0]['citations'][0].update(quote='absent excerpt'),
                     lambda v: v['cases'][0]['citations'][0].update(passage_id='absent'),
                     lambda v: v['cases'][0].update(claim='x\x00y'),
                     lambda v: v['cases'][0].update(claim='x' * 2001),
                     lambda v: v['cases'][0]['passages'][0].update(text='x' * 8001),
                     lambda v: v['cases'][0].update(citations=[]), lambda v: v.update(cases=[])]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                value = inputs()
                mutate(value)
                with self.assertRaises(ValueError):
                    adapter.validate_inputs(bind(value))
        value = inputs()
        value['cases'][0]['claim'] = 'changed without rebinding'
        with self.assertRaises(ValueError):
            adapter.validate_inputs(value)
        value = inputs()
        case = value['cases'][0]
        value['cases'] = [{**copy.deepcopy(case), 'id': 'synthetic-' + str(i)} for i in range(129)]
        with self.assertRaises(ValueError):
            adapter.validate_inputs(bind(value))

    def test_cli_invalid_json_never_initializes_backend_or_emits_success(self):
        with tempfile.TemporaryDirectory(prefix='deberta-cli-independent-') as directory:
            path = Path(directory) / 'synthetic.json'
            for raw in (b'{"protocol":1,"protocol":1}', b'NaN', b'\xff', b'{}', b'['):
                with self.subTest(raw=raw):
                    path.write_bytes(raw)
                    with patch.object(adapter, 'LocalBackend') as constructor, patch('sys.stdout', io.StringIO()) as out, patch('sys.stderr', io.StringIO()):
                        code = adapter.main(['predict', '--inputs', str(path), '--model-dir', directory])
                    self.assertEqual(code, 2)
                    self.assertEqual(out.getvalue(), '')
                    constructor.assert_not_called()

    def test_cli_predict_and_inspect_emit_one_bounded_canonical_record(self):
        with tempfile.TemporaryDirectory(prefix='deberta-cli-independent-') as directory:
            path = Path(directory) / 'synthetic.json'
            path.write_bytes(adapter.schema.canonical_bytes(inputs()))
            for operation in ('predict', 'inspect'):
                with self.subTest(operation=operation):
                    stream = io.BytesIO()
                    output = SimpleNamespace(buffer=stream)
                    with patch.object(adapter, 'LocalBackend', return_value=StubBackend()), patch('sys.stdout', output):
                        code = adapter.main([operation, '--inputs', str(path), '--model-dir', directory])
                    self.assertEqual(code, 0)
                    raw = stream.getvalue()
                    self.assertLessEqual(len(raw), adapter.schema.MAX_BYTES)
                    self.assertEqual(raw.count(b'\n'), 1)
                    parsed = json.loads(raw)
                    self.assertEqual(raw, adapter.schema.canonical_bytes(parsed) + b'\n')
                    if operation == 'predict':
                        self.assertEqual(set(parsed), {'protocol', 'input_sha256', 'predictions'})


if __name__ == '__main__':
    unittest.main()
