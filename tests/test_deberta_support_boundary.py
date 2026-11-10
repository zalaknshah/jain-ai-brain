"""Synthetic, stdlib-only boundaries. No model, challenge or outcome files read."""
from contextlib import nullcontext
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import predict_deberta_support as candidate


def inputs(count=1):
    value = {'protocol': 1, 'dataset_sha256': 'a' * 64, 'cases': [
        {'id': f'synthetic-{i}', 'passages': [
            {'id': 'p1', 'text': 'First complete supplied passage.'},
            {'id': 'p2', 'text': 'Second complete supplied passage.'}],
         'claim': 'A synthetic test claim.',
         'citations': [{'passage_id': 'p1', 'quote': 'First'}]}
        for i in range(count)]}
    return rehash(value)


def rehash(value):
    value.pop('input_sha256', None)
    value['input_sha256'] = hashlib.sha256(candidate.schema.canonical_bytes(value)).hexdigest()
    return value


class StubBackend:
    identity = {'backend': 'stdlib_stub_only', 'no_model_inference': True}

    def __init__(self, count=7, logits=None):
        self.count = count
        self.output = [[0.0, 1.0, 0.0]] if logits is None else logits
        self.pairs = []
        self.calls = 0

    def tokenize(self, premise, hypothesis):
        self.pairs.append((premise, hypothesis))
        return {'input_ids': [1] * self.count, 'attention_mask': [1] * self.count}

    def logits(self, encoded):
        self.calls += 1
        return self.output


class FakeTokenizer:
    is_fast = True
    model_max_length = 512
    vocab_size = 128000
    do_lower_case = False
    backend_tokenizer = SimpleNamespace(truncation=None, padding=None)

    def __init__(self):
        self.__dict__.update(candidate.SPECIAL_IDS)

    def __len__(self):
        return 128001

    def build_inputs_with_special_tokens(self, first, second):
        return [1, *first, 2, *second, 2]


def config():
    return SimpleNamespace(**copy.deepcopy(candidate.EXPECTED_CONFIG), num_labels=3,
                           id2label=dict(candidate.MODEL_LABELS),
                           label2id={v: k for k, v in candidate.MODEL_LABELS.items()})


def loading_info():
    return {'missing_keys': [], 'unexpected_keys': [candidate.LEGACY_BUFFER],
            'mismatched_keys': [], 'error_msgs': []}


class PolicyTests(unittest.TestCase):
    def test_import_is_optional_and_creates_no_bytecode(self):
        command = "from scripts import predict_deberta_support; import sys; " \
                  "assert not {'torch', 'transformers', 'safetensors', 'tokenizers'} & sys.modules.keys(); " \
                  "assert sys.dont_write_bytecode"
        result = subprocess.run([sys.executable, '-B', '-S', '-c', command],
                                cwd=Path(candidate.__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')

    def test_separate_identity_and_frozen_shared_hashes(self):
        identity = candidate.source_identity()
        self.assertEqual(identity['runner_version'], 'deberta-support-v1')
        for field, path in [('runner_sha256', candidate.__file__),
                            ('common_runner_sha256', candidate.common.__file__),
                            ('schema_sha256', candidate.schema.__file__)]:
            self.assertEqual(identity[field], hashlib.sha256(Path(path).read_bytes()).hexdigest())
        self.assertEqual(candidate.MODEL_ID, 'cross-encoder/nli-deberta-v3-base')
        self.assertEqual(candidate.REVISION, '6c749ce3425cd33b46d187e45b92bbf96ee12ec7')
        self.assertNotEqual(candidate.MODEL_ID, candidate.common.MODEL_ID)
        self.assertEqual(len(candidate.ARTIFACT_HASHES), 7)
        self.assertEqual(sum(candidate.ARTIFACT_SIZES.values()), 746388757)
        with patch.object(candidate, 'FROZEN_COMMON_SHA256', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'frozen'):
                candidate.run(inputs(), StubBackend())

    def test_full_context_pair_order_and_bound_output(self):
        source = inputs()
        backend = StubBackend()
        result = candidate.run(source, backend)
        self.assertEqual(backend.pairs, [('First complete supplied passage.\n\n'
                                         'Second complete supplied passage.',
                                         'A synthetic test claim.')])
        self.assertEqual(result['input_sha256'], source['input_sha256'])
        self.assertEqual(result['dataset_sha256'], source['dataset_sha256'])
        self.assertEqual(result['policy']['mapping'], list(candidate.LABELS))
        self.assertEqual(result['policy']['decision'], 'argmax; first index on ties; no thresholds')
        self.assertFalse(result['policy']['truncation'])
        self.assertEqual(result['traces'][0]['passage_count'], 2)
        self.assertEqual(result['traces'][0]['premise_sha256'],
                         hashlib.sha256(backend.pairs[0][0].encode()).hexdigest())
        candidate.schema.validate_predictions(result['predictions'], source)

    def test_argmax_mapping_negative_logits_and_first_index_ties(self):
        for row, label in [([4, 1, 2], 'contradicted'), ([1, 4, 2], 'supported'),
                           ([1, 2, 4], 'not_established'), ([0, 0, 0], 'contradicted'),
                           ([-3, -2, -2], 'supported'), ([-1e-50, 0, -1], 'supported')]:
            with self.subTest(row=row):
                result = candidate.run(inputs(), StubBackend(logits=[row]))
                self.assertEqual(result['traces'][0]['label'], label)
                self.assertEqual(result['traces'][0]['reason'], 'three_class_argmax')
                self.assertEqual(result['traces'][0]['raw_logits'], row)

    def test_token_limit_includes_complete_pair_and_never_runs_long_pair(self):
        for length, reason, calls in [(512, 'three_class_argmax', 1),
                                      (513, 'pair_token_limit_exceeded', 0)]:
            with self.subTest(length=length):
                backend = StubBackend(count=length)
                trace = candidate.run(inputs(), backend)['traces'][0]
                self.assertEqual(trace['token_count'], length)
                self.assertEqual(trace['reason'], reason)
                self.assertEqual(backend.calls, calls)
                self.assertFalse(trace['truncation'])
                if not calls:
                    self.assertEqual(trace['label'], 'abstain')
                    self.assertIsNone(trace['raw_logits'])

    def test_case_limit(self):
        self.assertEqual(len(candidate.run(inputs(128), StubBackend())['traces']), 128)
        backend = StubBackend()
        with self.assertRaises(ValueError):
            candidate.run(inputs(129), backend)
        self.assertEqual(backend.pairs, [])

    def test_malformed_tokenizations_abstain(self):
        for encoding in [None, {}, {'input_ids': []}, {'input_ids': [True]},
                         {'input_ids': [-1]}, {'input_ids': [[1]]},
                         {'input_ids': [1], 'attention_mask': []},
                         {'input_ids': [1], 'attention_mask': [1.0]},
                         {'input_ids': [1], 'secret': [1]}]:
            with self.subTest(encoding=encoding):
                backend = StubBackend()
                backend.tokenize = lambda *args: encoding
                trace = candidate.run(inputs(), backend)['traces'][0]
                self.assertEqual(trace['label'], 'abstain')
                self.assertEqual(trace['reason'], 'tokenization_failed_or_malformed')
                self.assertEqual(backend.calls, 0)

    def test_inference_failures_and_invalid_logits_abstain(self):
        for value, reason in [([], 'malformed_logits'), ([[1, 2]], 'malformed_logits'),
                              ([[1, 2, True]], 'malformed_logits'),
                              ([[1, 2, '3']], 'malformed_logits'),
                              ([[1, 2, float('nan')]], 'nonfinite_logits'),
                              ([[float('inf'), 2, 3]], 'nonfinite_logits'),
                              ([[10 ** 1000, 2, 3]], 'nonfinite_logits')]:
            with self.subTest(reason=reason):
                trace = candidate.run(inputs(), StubBackend(logits=value))['traces'][0]
                self.assertEqual(trace['label'], 'abstain')
                self.assertEqual(trace['reason'], reason)
                self.assertIsNone(trace['raw_logits'])
        backend = StubBackend()
        backend.logits = lambda _: (_ for _ in ()).throw(RuntimeError('synthetic failure'))
        self.assertEqual(candidate.run(inputs(), backend)['traces'][0]['reason'], 'inference_failed')

    def test_invalid_input_rejected_before_backend_access(self):
        variants = []
        value = inputs(); value['cases'][0]['label'] = 'supported'; variants.append(rehash(value))
        value = inputs(); value['protocol'] = True; variants.append(rehash(value))
        value = inputs(); value['input_sha256'] = '0' * 64; variants.append(value)
        value = inputs(); value['cases'][0]['claim'] = 'bad\ncontrol'; variants.append(rehash(value))
        value = inputs(); value['cases'][0]['citations'][0]['quote'] = 'Absent'; variants.append(rehash(value))
        value = inputs(); value['cases'] *= 2; variants.append(rehash(value))
        value = inputs(); value['cases'][0]['passages'].append(value['cases'][0]['passages'][0]); variants.append(rehash(value))
        for value in variants:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    candidate.run(value, object())


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / 'model'
        self.directory.mkdir()
        blobs = {name: f'inert test artifact {name}'.encode() for name in candidate.ARTIFACT_HASHES}
        self.hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in blobs.items()}
        self.sizes = {name: len(raw) for name, raw in blobs.items()}
        for name, raw in blobs.items():
            (self.directory / name).write_bytes(raw)
        for key, value in [('ARTIFACT_HASHES', self.hashes), ('ARTIFACT_SIZES', self.sizes),
                           ('WEIGHTS_SHA256', self.hashes['model.safetensors'])]:
            patcher = patch.object(candidate, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_all_seven_pins_are_verified(self):
        self.assertEqual(candidate.verify_artifacts(self.directory), self.directory)
        for name in self.hashes:
            with self.subTest(name=name):
                original = (self.directory / name).read_bytes()
                (self.directory / name).write_bytes(b'x' * len(original))
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    candidate.verify_artifacts(self.directory)
                (self.directory / name).write_bytes(original)

    def test_size_missing_extra_and_nonregular_fail_closed(self):
        path = self.directory / 'config.json'
        raw = path.read_bytes()
        path.write_bytes(raw + b'x')
        with self.assertRaisesRegex(ValueError, 'pinned size'):
            candidate.verify_artifacts(self.directory)
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'exactly'):
            candidate.verify_artifacts(self.directory)
        path.mkdir()
        with self.assertRaisesRegex(ValueError, 'regular'):
            candidate.verify_artifacts(self.directory)
        path.rmdir()
        path.write_bytes(raw)
        (self.directory / 'spm.model').write_bytes(b'not allowed')
        with self.assertRaisesRegex(ValueError, 'exactly'):
            candidate.verify_artifacts(self.directory)

    def test_symlink_file_directory_and_ancestor_are_rejected(self):
        outside = Path(self.temp.name) / 'outside'
        outside.write_bytes((self.directory / 'config.json').read_bytes())
        (self.directory / 'config.json').unlink()
        (self.directory / 'config.json').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'non-symlink'):
            candidate.verify_artifacts(self.directory)
        linked = Path(self.temp.name) / 'link'
        linked.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'non-symlink'):
            candidate.verify_artifacts(linked)
        parent_link = Path(self.temp.name) / 'parent-link'
        parent_link.symlink_to(Path(self.temp.name), target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'non-symlink'):
            candidate.verify_artifacts(parent_link / 'model')

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO boundary')
    def test_fifo_artifact_is_rejected_without_reading(self):
        path = self.directory / 'config.json'
        path.unlink()
        os.mkfifo(path)
        with self.assertRaisesRegex(ValueError, 'regular'):
            candidate.verify_artifacts(self.directory)

    def test_bad_manifest_fails_before_optional_imports(self):
        (self.directory / 'config.json').write_bytes(b'bad')
        import builtins
        real_import = builtins.__import__
        def guard(name, *args, **kwargs):
            if name.split('.')[0] in ('torch', 'transformers', 'safetensors'):
                self.fail('dependency import happened before full manifest verification')
            return real_import(name, *args, **kwargs)
        with patch('builtins.__import__', guard):
            with self.assertRaises(ValueError):
                candidate.LocalBackend(self.directory)


class LoadingBoundaryTests(unittest.TestCase):
    def test_config_architecture_labels_and_custom_code(self):
        candidate.validate_config(config())
        changes = {'architectures': ['RobertaForSequenceClassification'], 'model_type': 'roberta',
                   'num_labels': 2, 'id2label': {0: 'entailment', 1: 'contradiction', 2: 'neutral'},
                   'label2id': {}, 'vocab_size': 128001, 'relative_attention': False,
                   'max_position_embeddings': 1024, 'auto_map': {'AutoModel': 'custom.Model'}}
        for name, value in changes.items():
            with self.subTest(name=name):
                changed = config(); setattr(changed, name, value)
                with self.assertRaises(ValueError):
                    candidate.validate_config(changed)

    def test_fast_tokenizer_identity_and_no_silent_truncation(self):
        candidate.validate_tokenizer(FakeTokenizer())
        for name, value in [('is_fast', False), ('vocab_size', 128100), ('model_max_length', 1024),
                            ('mask_token_id', 4), ('do_lower_case', True),
                            ('backend_tokenizer', SimpleNamespace(truncation={'max_length': 512}, padding=None))]:
            with self.subTest(name=name):
                tokenizer = FakeTokenizer(); setattr(tokenizer, name, value)
                with self.assertRaises(ValueError):
                    candidate.validate_tokenizer(tokenizer)
        tokenizer = FakeTokenizer()
        tokenizer.build_inputs_with_special_tokens = lambda a, b: [1, *b, 2, *a, 2]
        with self.assertRaisesRegex(ValueError, 'pair template'):
            candidate.validate_tokenizer(tokenizer)

    def test_loading_diagnostics_allow_only_known_nonlearned_buffer(self):
        self.assertEqual(candidate.validate_loading_info(loading_info()), loading_info())
        empty = loading_info(); empty['unexpected_keys'] = []
        candidate.validate_loading_info(empty)
        for field in ('missing_keys', 'mismatched_keys', 'error_msgs', 'unexpected_keys'):
            with self.subTest(field=field):
                info = loading_info(); info[field] = ['classifier.weight']
                with self.assertRaises(ValueError):
                    candidate.validate_loading_info(info)
        for info in [None, {}, {**loading_info(), 'unreviewed': []},
                     {**loading_info(), 'missing_keys': None}]:
            with self.assertRaises(ValueError):
                candidate.validate_loading_info(info)

    def test_local_loading_flags_cpu_determinism_and_identity(self):
        events = []
        class Tokenizer(FakeTokenizer):
            @classmethod
            def from_pretrained(cls, path, **kwargs):
                events.append(('tokenizer', path, kwargs)); return cls()
        class Model:
            training = True
            config = config()
            @classmethod
            def from_pretrained(cls, path, **kwargs):
                events.append(('model', path, kwargs)); return cls(), loading_info()
            def to(self, device):
                events.append(('device', device)); return self
            def eval(self):
                self.training = False
        torch = SimpleNamespace(__version__='stub', float32='float32',
                                set_num_threads=lambda n: events.append(('threads', n)),
                                get_num_threads=lambda: 1, get_num_interop_threads=lambda: 1,
                                manual_seed=lambda n: events.append(('seed', n)),
                                use_deterministic_algorithms=lambda b: events.append(('determinism', b)),
                                are_deterministic_algorithms_enabled=lambda: True)
        transformers = SimpleNamespace(__version__='stub', DebertaV2TokenizerFast=Tokenizer,
                                       DebertaV2ForSequenceClassification=Model)
        safetensors = SimpleNamespace(safe_open=lambda *a, **k: nullcontext(object()))
        with patch.dict(sys.modules, {'torch': torch, 'transformers': transformers, 'safetensors': safetensors}), \
                patch.object(candidate, 'verify_artifacts', return_value=Path('/inert/model')), \
                patch.object(candidate, 'validate_checkpoint', return_value={'test': 'inventory'}), \
                patch.object(candidate, 'version', return_value='stub'), patch.dict(os.environ, {}, clear=True):
            backend = candidate.LocalBackend('/inert/model')
            for key, value in candidate.OFFLINE_ENV.items():
                self.assertEqual(os.environ[key], value)
        tokenizer_kwargs = next(e[2] for e in events if e[0] == 'tokenizer')
        model_kwargs = next(e[2] for e in events if e[0] == 'model')
        for kwargs in (tokenizer_kwargs, model_kwargs):
            self.assertTrue(kwargs['local_files_only'])
            self.assertFalse(kwargs['trust_remote_code'])
        self.assertTrue(tokenizer_kwargs['use_fast'])
        self.assertFalse(tokenizer_kwargs['from_slow'])
        self.assertTrue(model_kwargs['use_safetensors'])
        self.assertTrue(model_kwargs['output_loading_info'])
        self.assertNotIn('ignore_mismatched_sizes', model_kwargs)
        self.assertNotIn('device_map', model_kwargs)
        self.assertIn(('device', 'cpu'), events)
        self.assertIn(('threads', 1), events)
        self.assertIn(('seed', 0), events)
        self.assertIn(('determinism', True), events)
        self.assertEqual(backend.identity['model_id'], candidate.MODEL_ID)
        self.assertEqual(backend.identity['backend'], 'local_pretrained_deberta_cpu')
        self.assertEqual(backend.identity['loading_info'], loading_info())
        self.assertTrue(backend.identity['eval'])


class CheckpointInventoryTests(unittest.TestCase):
    def setUp(self):
        class Tensor:
            device = SimpleNamespace(type='cpu')
            is_meta = False
            def __init__(self, shape, dtype, values=None):
                self.shape, self.dtype, self.values = shape, dtype, values
            def reshape(self, *shape):
                self.shape = shape; return self
            def numel(self):
                return 184424451
            def detach(self):
                return self
        self.parameter = Tensor((184424451,), 'float32', ['stub trained values'])
        self.saved_parameter = Tensor((184424451,), 'float32', ['stub trained values'])
        self.buffer = Tensor((1, 512), 'int64', list(range(512)))
        self.saved = Tensor((1, 512), 'int64', list(range(512)))
        self.parameters = {'classifier.weight': self.parameter}
        self.buffers = {candidate.LEGACY_BUFFER: self.buffer}
        self.keys = ['classifier.weight', candidate.LEGACY_BUFFER]
        self.slice = SimpleNamespace(get_shape=lambda: [184424451], get_dtype=lambda: 'F32')
        self.model = SimpleNamespace(state_dict=lambda: dict(self.parameters),
                                     named_parameters=lambda: self.parameters.items(),
                                     named_buffers=lambda: self.buffers.items())
        self.checkpoint = SimpleNamespace(keys=lambda: self.keys, get_slice=lambda name: self.slice,
                                          get_tensor=lambda name: self.saved if name == candidate.LEGACY_BUFFER
                                          else self.saved_parameter)
        self.torch = SimpleNamespace(float32='float32', int64='int64',
                                     arange=lambda n, **kwargs: Tensor((n,), 'int64', list(range(n))),
                                     equal=lambda a, b: a.values == b.values)

    def verify(self):
        return candidate.validate_checkpoint(self.model, self.checkpoint, self.torch)

    def test_inventory_and_explicit_buffer_values(self):
        result = self.verify()
        self.assertEqual(result['learned_elements'], 184424451)
        self.assertEqual(result['verified_nonlearned_buffer'], candidate.LEGACY_BUFFER)
        self.assertTrue(result['all_loaded_parameters_equal_checkpoint'])

    def test_randomly_initialized_or_incorrect_loaded_values_are_rejected(self):
        self.parameter.values = ['random initialization']
        with self.assertRaisesRegex(ValueError, 'learned-weight values'):
            self.verify()

    def test_hidden_extra_or_missing_learned_weights_rejected(self):
        for keys in [[candidate.LEGACY_BUFFER], self.keys + ['position_embeddings.weight'],
                     ['classifier.weight']]:
            with self.subTest(keys=keys):
                self.keys = keys
                with self.assertRaises(ValueError):
                    self.verify()

    def test_wrong_shapes_dtype_count_and_nonlearned_value_rejected(self):
        self.slice.get_shape = lambda: [1]
        with self.assertRaises(ValueError):
            self.verify()
        self.slice.get_shape = lambda: [184424451]
        self.slice.get_dtype = lambda: 'F16'
        with self.assertRaises(ValueError):
            self.verify()
        self.slice.get_dtype = lambda: 'F32'
        self.parameter.numel = lambda: 1
        with self.assertRaises(ValueError):
            self.verify()
        self.parameter.numel = lambda: 184424451
        self.saved.values[0] = 99
        with self.assertRaisesRegex(ValueError, 'position_ids'):
            self.verify()
        self.saved.values = list(range(512))
        self.buffer.dtype = 'float32'
        with self.assertRaisesRegex(ValueError, 'position_ids'):
            self.verify()


class CliTests(unittest.TestCase):
    def invoke(self, raw, operation='inspect', backend=None):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.json'
            path.write_bytes(raw)
            stdout = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
            stderr = io.StringIO()
            with patch.object(candidate.sys, 'stdout', stdout), patch.object(candidate.sys, 'stderr', stderr), \
                    patch.object(candidate, 'LocalBackend', side_effect=backend or (lambda _: StubBackend())) as loader:
                code = candidate.main([operation, '--inputs', str(path), '--model-dir', str(Path(temp) / 'absent')])
                stdout.flush()
                return code, stdout.buffer.getvalue(), stderr.getvalue(), loader.call_count

    def test_single_bounded_json_stdout_and_no_backend_noise(self):
        def backend(_):
            print('synthetic optional-library notice')
            return StubBackend()
        code, raw, error, calls = self.invoke(candidate.schema.canonical_bytes(inputs()), backend=backend)
        self.assertEqual(code, 0)
        self.assertEqual(calls, 1)
        self.assertIn('synthetic optional-library notice', error)
        self.assertEqual(raw.count(b'\n'), 1)
        self.assertLessEqual(len(raw), candidate.schema.MAX_BYTES)
        self.assertEqual(json.loads(raw)['traces'][0]['reason'], 'three_class_argmax')
        code, raw, _, _ = self.invoke(candidate.schema.canonical_bytes(inputs()), operation='predict')
        self.assertEqual(code, 0)
        self.assertEqual(set(json.loads(raw)), {'protocol', 'input_sha256', 'predictions'})

    def test_invalid_json_and_input_fail_before_backend_load(self):
        for raw in [b'{"protocol":1,"protocol":1}', b'NaN', b'[]', b'\xff', b'{',
                    b'[' * 1500 + b']' * 1500, candidate.schema.canonical_bytes(inputs(129))]:
            with self.subTest(raw=raw[:30]):
                code, output, error, calls = self.invoke(raw)
                self.assertEqual(code, 2)
                self.assertEqual(output, b'')
                self.assertEqual(calls, 0)
                self.assertIn('DeBERTa experiment refused:', error)

    def test_missing_dependency_is_explicit_refusal_no_fallback(self):
        def absent(_):
            raise ImportError('synthetic unavailable dependency')
        code, raw, error, calls = self.invoke(candidate.schema.canonical_bytes(inputs()), backend=absent)
        self.assertEqual((code, raw, calls), (2, b'', 1))
        self.assertIn('unavailable dependency', error)


if __name__ == '__main__':
    unittest.main()
