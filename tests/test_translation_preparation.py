import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/prepare_translation_review.py'
spec = importlib.util.spec_from_file_location('translation_preparation', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TranslationPreparationTests(unittest.TestCase):
    def setUp(self):
        self.source = 'Synthetic header\r\nकरुणा કરુણા\r\n'.encode('utf-8')
        self.request = {'source_sha256': hashlib.sha256(self.source).hexdigest(),
                        'metadata': {field: 'Synthetic declared ' + field for field in module.METADATA},
                        'spans': [{'id': 'example', 'byte_start': 18, 'byte_end': len(self.source), 'locator': 'synthetic line 2'}]}

    def test_exact_source_and_blank_translations(self):
        packet = module.prepare(self.source, self.request)
        task = packet['tasks'][0]
        self.assertEqual(task['source_text'].encode('utf-8'), self.source[18:])
        self.assertEqual(set(task['translations']), {'gu', 'hi', 'en'})
        self.assertTrue(all(v['draft'] is None and v['review_status'] == 'pending' for v in task['translations'].values()))
        self.assertFalse(packet['training_admitted'])
        self.assertFalse(packet['runtime_admitted'])
        self.assertFalse(packet['public_release_approved'])

    def test_source_or_provenance_drift_changes_or_rejects_binding(self):
        first = module.prepare(self.source, self.request)['tasks'][0]['source_binding_sha256']
        changed = copy.deepcopy(self.request); changed['metadata']['edition'] += ' changed'
        self.assertNotEqual(first, module.prepare(self.source, changed)['tasks'][0]['source_binding_sha256'])
        with self.assertRaises(ValueError): module.prepare(self.source + b'x', self.request)

    def test_prepared_evidence_is_detached_from_caller_dictionaries(self):
        packet = module.prepare(self.source, self.request)
        before = json.dumps(packet, sort_keys=True)
        self.request['metadata']['edition'] = 'mutated'
        self.request['spans'][0]['byte_start'] = 0
        self.assertEqual(json.dumps(packet, sort_keys=True), before)

    def test_partial_utf8_rejected(self):
        changed = copy.deepcopy(self.request); changed['spans'][0]['byte_start'] = 19
        with self.assertRaises(ValueError): module.prepare(self.source, changed)

    def test_bounds_boolean_indices_and_duplicate_ids_rejected(self):
        for key, value in [('byte_start', True), ('byte_end', len(self.source)+1), ('byte_start', -1), ('id', '../escape')]:
            changed = copy.deepcopy(self.request); changed['spans'][0][key] = value
            with self.assertRaises(ValueError): module.prepare(self.source, changed)
        changed = copy.deepcopy(self.request); changed['spans'] *= 2
        with self.assertRaises(ValueError): module.prepare(self.source, changed)

    def test_extra_flags_cannot_authorize_training(self):
        for key in ('training_admitted', 'runtime_admitted', 'public_release_approved'):
            changed = copy.deepcopy(self.request); changed[key] = True
            with self.assertRaises(ValueError): module.prepare(self.source, changed)

    def test_required_rights_and_attribution_not_optional(self):
        for key in ('rights_basis', 'rights_notice', 'attribution', 'declared_source_language', 'text_role'):
            changed = copy.deepcopy(self.request); del changed['metadata'][key]
            with self.assertRaises(ValueError): module.prepare(self.source, changed)

    def test_cli_private_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source'; request = root/'request.json'; output = root/'packet.json'
            source.write_bytes(self.source); request.write_text(json.dumps(self.request), encoding='utf-8')
            command = [sys.executable, str(SCRIPT), str(source), str(request), str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['task_count'], 1)
            self.assertNotIn('करुणा', result.stdout + result.stderr)
            original = output.read_bytes()
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
            self.assertEqual(output.read_bytes(), original)

    def test_cli_duplicate_json_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source'; request = root/'request'; output = root/'output'
            source.write_bytes(self.source); request.write_text('{"spans":[],"spans":[]}', encoding='utf-8')
            result = subprocess.run([sys.executable, str(SCRIPT), str(source), str(request), str(output)], capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(output.exists())


class ScanLineageTests(unittest.TestCase):
    def setUp(self):
        self.source = b'Synthetic page one. Synthetic page two.'
        self.request = {'source_sha256': hashlib.sha256(self.source).hexdigest(),
                        'metadata': {k: 'Synthetic ' + k for k in module.METADATA},
                        'spans': [{'id': 'one', 'byte_start': 0, 'byte_end': 19, 'locator': 'page 1'},
                                  {'id': 'two', 'byte_start': 19, 'byte_end': len(self.source), 'locator': 'page 2'}]}
        self.scans = {'scan1': b'not an image: synthetic bytes', 'scan2': b'other synthetic bytes'}
        self.bindings = {key: {'scan_id': scan, 'sha256': hashlib.sha256(self.scans[scan]).hexdigest(),
                               'locator': key, 'source_url': 'https://example.invalid/' + key}
                         for key, scan in [('one', 'scan1'), ('two', 'scan2')]}

    def prepare(self):
        return module.prepare_with_scans(self.source, self.request, self.scans, self.bindings)

    def test_two_pages_remain_unreviewed(self):
        p = self.prepare()
        self.assertEqual(len(p['tasks']), 2)
        for t in p['tasks']:
            self.assertEqual(t['source_review']['scan_correspondence'], 'pending')
            self.assertEqual(t['scan_binding_sha256'], module.digest(t['scan_evidence']))
            self.assertTrue(all(x['draft'] is None for x in t['translations'].values()))
        for key in ('training_admitted', 'runtime_admitted', 'public_release_approved'):
            self.assertIs(p[key], False)

    def test_source_drift_rejected(self):
        self.source += b'x'
        with self.assertRaises(ValueError): self.prepare()

    def test_scan_drift_rejected(self):
        self.scans['scan1'] += b'x'
        with self.assertRaises(ValueError): self.prepare()

    def test_missing_extra_binding_or_scan_rejected(self):
        for where, key in [(self.bindings, 'one'), (self.scans, 'scan1')]:
            old = where.pop(key)
            with self.assertRaises(ValueError): self.prepare()
            where[key] = old
        self.scans['unused'] = b'x'
        with self.assertRaises(ValueError): self.prepare()

    def test_admission_injection_rejected(self):
        self.bindings['one']['training_admitted'] = True
        with self.assertRaises(ValueError): self.prepare()

    def test_scan_bounds(self):
        for value in (b'', bytearray(b'a'), b'x' * (8 * 1024 * 1024 + 1)):
            self.scans['scan1'] = value
            with self.assertRaises(ValueError): self.prepare()

    def test_aggregate_scan_limit(self):
        self.scans = {str(i): b'x' * (7 * 1024 * 1024) for i in range(5)}
        with self.assertRaises(ValueError): self.prepare()

    def test_unknown_and_extra_binding_rejected(self):
        self.bindings['one']['scan_id'] = 'unknown'
        with self.assertRaises(ValueError): self.prepare()
        self.bindings['one']['scan_id'] = 'scan1'
        self.bindings['extra'] = dict(self.bindings['one'])
        with self.assertRaises(ValueError): self.prepare()

    def test_detached_metadata_and_binding_drift(self):
        first = self.prepare(); before = json.dumps(first, sort_keys=True)
        self.bindings['one']['locator'] = 'changed'
        second = self.prepare()
        self.assertEqual(json.dumps(first, sort_keys=True), before)
        self.assertNotEqual(first['tasks'][0]['scan_binding_sha256'], second['tasks'][0]['scan_binding_sha256'])

    def test_same_scan_multiple_spans_allowed(self):
        self.bindings['two'] = dict(self.bindings['one'])
        del self.scans['scan2']
        self.assertEqual(len(self.prepare()['tasks']), 2)


if __name__ == '__main__': unittest.main()
