"""Stdlib-only tests with synthetic inputs. No challenge fixtures or model loads."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import predict_pretrained_support as nli


def seal(value):
    value['input_sha256'] = hashlib.sha256(nli.schema.canonical_bytes(
        {k: v for k, v in value.items() if k != 'input_sha256'})).hexdigest()
    return value


def inputs():
    return seal({'protocol': 1, 'dataset_sha256': 'a' * 64, 'cases': [{
        'id': 'synthetic', 'passages': [{'id': 'p', 'text': 'The door is red.'},
                                     {'id': 'q', 'text': 'The door is not blue.'}],
        'claim': 'The door is red.', 'citations': [{'passage_id': 'p', 'quote': 'red'}]}]})


class Stub:
    identity = {'backend': 'synthetic_stub_not_a_model'}

    def __init__(self, count=20, logits=None):
        self.count = count
        self.output = [[0., 1., 0.]] if logits is None else logits
        self.calls = 0
        self.pair = None

    def tokenize(self, premise, hypothesis):
        self.pair = (premise, hypothesis)
        return {'input_ids': [0] * self.count, 'attention_mask': [1] * self.count}

    def logits(self, encoded):
        self.calls += 1
        return self.output


class PretrainedBoundaryTests(unittest.TestCase):
    def test_exact_prediction_schema_and_full_context(self):
        backend = Stub()
        result = nli.run(inputs(), backend)
        self.assertEqual(backend.pair, ('The door is red.\n\nThe door is not blue.', 'The door is red.'))
        self.assertEqual(set(result['predictions']), {'protocol', 'input_sha256', 'predictions'})
        self.assertEqual(nli.schema.validate_predictions(result['predictions'], inputs()), {'synthetic': 'supported'})
        self.assertFalse(result['traces'][0]['truncation'])

    def test_frozen_mapping_and_tie(self):
        for logits, label in [([[9, 0, 0]], 'contradicted'), ([[0, 9, 0]], 'supported'),
                              ([[0, 0, 9]], 'not_established'), ([[1, 1, 1]], 'contradicted')]:
            self.assertEqual(nli.run(inputs(), Stub(logits=logits))['traces'][0]['label'], label)

    def test_overflow_before_inference_and_boundary(self):
        for count in (512, 513):
            stub = Stub(count=count)
            trace = nli.run(inputs(), stub)['traces'][0]
            self.assertEqual(stub.calls, int(count == 512))
            self.assertEqual(trace['token_count'], count)
            if count == 513:
                self.assertEqual(trace['reason'], 'pair_token_limit_exceeded')
                self.assertEqual(trace['label'], 'abstain')

    def test_malformed_and_nonfinite_logits(self):
        for raw in ([1, 2, 3], [], [[1, 2]], [[1, 2, 3, 4]], [[True, 1, 2]],
                    [[0, '1', 2]], [[0, float('nan'), 1]], [[float('inf'), 0, 1]], [[10**1000, 0, 1]]):
            trace = nli.run(inputs(), Stub(logits=raw))['traces'][0]
            self.assertEqual(trace['label'], 'abstain')
            self.assertIsNone(trace['raw_logits'])
            self.assertIn(trace['reason'], ('malformed_logits', 'nonfinite_logits'))
            json.dumps(trace, allow_nan=False)

    def test_backend_failures_abstain(self):
        stub = Stub()
        with patch.object(stub, 'logits', side_effect=RuntimeError('private details')):
            self.assertEqual(nli.run(inputs(), stub)['traces'][0]['reason'], 'inference_failed')
        with patch.object(stub, 'tokenize', return_value={'input_ids': [True]}):
            self.assertEqual(nli.run(inputs(), stub)['traces'][0]['reason'], 'tokenization_failed_or_malformed')

    def test_no_gold_group_rationale_or_unknown_fields(self):
        for key in ('label', 'rationale', 'group_id', 'phenomenon', 'extra'):
            data = inputs()
            data['cases'][0][key] = 'hidden'
            with self.assertRaises(ValueError):
                nli.validate_inputs(seal(data))
        data = inputs()
        data['label'] = 'supported'
        with self.assertRaises(ValueError):
            nli.validate_inputs(seal(data))

    def test_hash_count_id_citation_and_nested_schema(self):
        mutations = [lambda d: d['cases'][0].update(claim='changed'),
                     lambda d: d.update(protocol=True), lambda d: d.update(dataset_sha256='x'*64),
                     lambda d: d.update(cases=[]),
                     lambda d: d['cases'][0]['citations'][0].update(quote='absent'),
                     lambda d: d['cases'][0]['passages'][0].update(label='gold'),
                     lambda d: d['cases'].append(copy.deepcopy(d['cases'][0]))]
        for mutate in mutations:
            data = inputs()
            mutate(data)
            with self.assertRaises(ValueError):
                nli.validate_inputs(data if data['cases'] and data['cases'][0].get('claim') == 'changed' else seal(data))
        data = inputs()
        data['cases'] = [dict(copy.deepcopy(data['cases'][0]), id=f'c{i}') for i in range(128)]
        nli.validate_inputs(seal(data))
        data['cases'].append(dict(copy.deepcopy(data['cases'][0]), id='last'))
        with self.assertRaises(ValueError):
            nli.validate_inputs(seal(data))

    def test_duplicate_json_keys_and_nonfinite_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'input.json'
            for raw in ('{"a":1,"a":2}', '{"a":NaN}'):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    nli.schema.read_json(path)

    def test_manifest_fail_closed_before_optional_import(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                nli.LocalBackend(temp)
        self.assertEqual(nli.ARTIFACT_HASHES['model.safetensors'], nli.WEIGHTS_SHA256)

    def test_import_is_lazy(self):
        code = ('import sys; from scripts import predict_pretrained_support; '
                'assert "torch" not in sys.modules; assert "transformers" not in sys.modules')
        subprocess.run([sys.executable, '-B', '-c', code], check=True,
                       cwd=Path(__file__).resolve().parents[1])

    def test_loader_offline_flags_and_no_truncation(self):
        # Inspect the optional adapter without importing third-party dependencies.
        import inspect
        source = inspect.getsource(nli.LocalBackend)
        self.assertIn('os.environ.update(OFFLINE_ENV)', source)
        self.assertIn('local_files_only=True', source)
        self.assertIn('trust_remote_code=False', source)
        self.assertIn('use_safetensors=True', source)
        self.assertIn('truncation=False', source)
        self.assertIn('inference_mode()', source)
        self.assertIn('self.model.eval()', source)
        self.assertEqual(nli.OFFLINE_ENV['HF_HUB_OFFLINE'], '1')


if __name__ == '__main__':
    unittest.main()
