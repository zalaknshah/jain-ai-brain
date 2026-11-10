"""Independent synthetic review: stdlib only; never imports a real model runtime."""
import copy
import contextlib
import io
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from scripts import predict_pretrained_support as nli


def seal(data):
    data['input_sha256'] = hashlib.sha256(nli.schema.canonical_bytes(
        {k: v for k, v in data.items() if k != 'input_sha256'})).hexdigest()
    return data


def example():
    return seal({'protocol': 1, 'dataset_sha256': 'b'*64, 'cases': [{
        'id': 'arbitrary', 'claim': 'The lamp is green.',
        'passages': [{'id': 'first', 'text': 'The lamp is green.'},
                     {'id': 'second', 'text': 'Its shade is brass.'}],
        'citations': [{'passage_id': 'first', 'quote': 'green'}]}]})


class Recorder:
    identity = {'backend': 'independent-synthetic'}

    def __init__(self):
        self.pairs = []
        self.calls = 0

    def tokenize(self, premise, hypothesis):
        self.pairs.append((premise, hypothesis))
        return {'input_ids': [0, 4, 2, 2, 5, 2], 'attention_mask': [1]*6}

    def logits(self, encoded):
        self.calls += 1
        return [[-1, 2, 0]]


class IndependentBoundary(unittest.TestCase):
    def test_id_citation_dataset_hash_not_model_features(self):
        a = example()
        b = copy.deepcopy(a)
        b['dataset_sha256'] = 'c'*64
        b['cases'][0]['id'] = 'supported.not_established.contradicted'
        b['cases'][0]['passages'][0]['id'] = 'renamed'
        b['cases'][0]['citations'] = [{'passage_id': 'second', 'quote': 'brass'}]
        seal(b)
        x, y = Recorder(), Recorder()
        ra, rb = nli.run(a, x), nli.run(b, y)
        self.assertEqual(x.pairs, y.pairs)
        self.assertEqual(x.pairs, [('The lamp is green.\n\nIts shade is brass.', 'The lamp is green.')])
        self.assertEqual(ra['traces'][0]['raw_logits'], rb['traces'][0]['raw_logits'])
        self.assertNotEqual(ra['input_sha256'], rb['input_sha256'])

    def test_invalid_last_case_prevents_all_inference(self):
        data = example()
        data['cases'].append(dict(copy.deepcopy(data['cases'][0]), id='last', label='supported'))
        backend = Recorder()
        with self.assertRaises(ValueError):
            nli.run(seal(data), backend)
        self.assertEqual(backend.pairs, [])
        self.assertEqual(backend.calls, 0)

    def test_per_case_exception_preserves_later_case(self):
        data = example()
        data['cases'].append(dict(copy.deepcopy(data['cases'][0]), id='last'))
        backend = Recorder()
        with patch.object(backend, 'logits', side_effect=[RuntimeError('secret'), [[0, 0, 8]]]):
            result = nli.run(seal(data), backend)
        self.assertEqual([t['label'] for t in result['traces']], ['abstain', 'not_established'])
        self.assertNotIn('secret', json.dumps(result))

    def test_tokenization_shape_rejected_before_inference(self):
        for malformed in ({}, {'input_ids': []}, {'input_ids': [1], 'attention_mask': []},
                          {'input_ids': [[1]]}, {'input_ids': [-1]},
                          {'input_ids': [1], 'extra': [1]}, {'input_ids': [1.0]}):
            with self.subTest(malformed=malformed):
                backend = Recorder()
                with patch.object(backend, 'tokenize', return_value=malformed):
                    result = nli.run(example(), backend)
                self.assertEqual(backend.calls, 0)
                self.assertEqual(result['traces'][0]['label'], 'abstain')

    def test_boundaries_are_checked_on_combined_token_list(self):
        for length in [511, 512, 513, 4096]:
            backend = Recorder()
            with patch.object(backend, 'tokenize', return_value={'input_ids': [2]*length}):
                result = nli.run(example(), backend)
            self.assertEqual(backend.calls, int(length <= 512))
            self.assertEqual(result['traces'][0]['token_count'], length)

    def test_actual_adapter_offline_loader_and_inference_calls(self):
        # Mock modules, not source substring assertions. Never import torch/transformers.
        calls = []
        token = Mock(return_value={'input_ids': [0, 2], 'attention_mask': [1, 1]})
        output = Mock()
        output.detach.return_value.cpu.return_value.tolist.return_value = [[1, 2, 3]]
        model = Mock(config=SimpleNamespace(num_labels=3, model_type='roberta'))
        model.to.return_value = model
        model.return_value = SimpleNamespace(logits=output)
        def loader(kind, result):
            def load(path, **kwargs):
                self.assertEqual({k: os.environ.get(k) for k in nli.OFFLINE_ENV}, nli.OFFLINE_ENV)
                calls.append((kind, path, kwargs))
                return result
            return SimpleNamespace(from_pretrained=load)
        guard = Mock()
        guard.__enter__ = Mock()
        guard.__exit__ = Mock(return_value=False)
        torch = SimpleNamespace(__version__='stub', set_num_threads=Mock(),
                                manual_seed=Mock(), use_deterministic_algorithms=Mock(),
                                tensor=Mock(side_effect=lambda value, **kw: (value, kw)),
                                inference_mode=Mock(return_value=guard))
        transformers = SimpleNamespace(__version__='stub',
            AutoTokenizer=loader('tokenizer', token),
            RobertaForSequenceClassification=loader('model', model))
        with patch.dict(sys.modules, {'torch': torch, 'transformers': transformers}), \
             patch.dict(os.environ, {}, clear=False), \
             patch.object(nli, 'verify_artifacts', return_value=Path('/synthetic/model')), \
             patch.object(nli, 'version', return_value='stub'):
            backend = nli.LocalBackend('/synthetic/model')
            encoded = backend.tokenize('full premise', 'full hypothesis')
            self.assertEqual(backend.logits(encoded), [[1, 2, 3]])
        self.assertEqual(calls, [
            ('tokenizer', '/synthetic/model', {'local_files_only': True, 'trust_remote_code': False, 'use_fast': True}),
            ('model', '/synthetic/model', {'local_files_only': True, 'trust_remote_code': False, 'use_safetensors': True})])
        token.assert_called_once_with('full premise', 'full hypothesis', add_special_tokens=True,
                                      truncation=False, padding=False)
        torch.set_num_threads.assert_called_once_with(1)
        torch.manual_seed.assert_called_once_with(0)
        torch.use_deterministic_algorithms.assert_called_once_with(True)
        torch.inference_mode.assert_called_once_with()
        model.to.assert_called_once_with('cpu')
        model.eval.assert_called_once_with()
        self.assertEqual(backend.identity['runner_sha256'], hashlib.sha256(Path(nli.__file__).read_bytes()).hexdigest())
        self.assertEqual(backend.identity['schema_sha256'], hashlib.sha256(Path(nli.schema.__file__).read_bytes()).hexdigest())

    def test_deep_json_refuses_cleanly_before_loader(self):
        # RecursionError inherits RuntimeError and is caught by main.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'nested.json'
            path.write_text('['*2000 + '0' + ']'*2000)
            errors = io.StringIO()
            with patch.object(nli, 'LocalBackend') as loader, contextlib.redirect_stderr(errors):
                code = nli.main(['predict', '--inputs', str(path), '--model-dir', tmp])
            self.assertEqual(code, 2)
            loader.assert_not_called()
            self.assertIn('pretrained experiment refused:', errors.getvalue())
            self.assertNotIn('Traceback', errors.getvalue())

    def test_artifact_exact_set_hash_and_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'model'
            root.mkdir()
            contents = {'model.safetensors': b'inert synthetic weights', 'config.json': b'{}'}
            pins = {k: hashlib.sha256(v).hexdigest() for k, v in contents.items()}
            for name, data in contents.items():
                (root/name).write_bytes(data)
            with patch.object(nli, 'ARTIFACT_HASHES', pins), \
                 patch.object(nli, 'WEIGHTS_SHA256', pins['model.safetensors']):
                self.assertEqual(nli.verify_artifacts(root), root.resolve())
                (root/'extra').write_text('x')
                with self.assertRaises(ValueError): nli.verify_artifacts(root)
                (root/'extra').unlink()
                (root/'config.json').write_bytes(b'{ }')
                with self.assertRaises(ValueError): nli.verify_artifacts(root)
                (root/'config.json').unlink()
                target = Path(tmp)/'target'
                target.write_bytes(contents['config.json'])
                (root/'config.json').symlink_to(target)
                with self.assertRaises(ValueError): nli.verify_artifacts(root)
                link = Path(tmp)/'linked-model'
                link.symlink_to(root, target_is_directory=True)
                with self.assertRaises(ValueError): nli.verify_artifacts(link)


if __name__ == '__main__':
    unittest.main()
