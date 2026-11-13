"""Original synthetic lineage fixtures only; no translation/model execution."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jace.training import admit_dataset, dataset_review_digest, prepare_training

ROOT = Path(__file__).resolve().parents[1]


class TrainingProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('train.jsonl', 'evaluation.jsonl', 'manifest.json'):
            (self.root / name).write_bytes((ROOT / 'training/fixtures' / name).read_bytes())
        self.paths = tuple(self.root / name for name in ('train.jsonl', 'evaluation.jsonl', 'manifest.json'))
        self.manifest = json.loads(self.paths[2].read_bytes())
        self.key = 'train-alpha'

    def save(self, rebind=False):
        if rebind:
            self.manifest['review']['subject_sha256'] = dataset_review_digest(self.manifest)
        self.paths[2].write_bytes(json.dumps(self.manifest, ensure_ascii=False).encode('utf-8'))

    def admit(self):
        return admit_dataset(*self.paths)

    def test_original_fixture_admitted_without_execution(self):
        data = self.admit()
        self.assertEqual(len(data['train']), 3)
        self.assertEqual(len(data['evaluation']), 2)
        self.assertEqual(len(list(self.root.iterdir())), 3)

    def test_legacy_and_missing_provenance_rejected(self):
        original = copy.deepcopy(self.manifest)
        for field in ('provenance', 'review'):
            self.manifest = copy.deepcopy(original)
            del self.manifest[field]
            self.save()
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.admit()
        self.manifest = original
        self.manifest['schema_version'] = 1
        self.save()
        with self.assertRaises(ValueError):
            self.admit()

    def test_stale_metadata_review_rejected(self):
        self.manifest['provenance']['sources'][self.key]['attribution'] = 'Changed synthetic attribution'
        self.save()
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.admit()

    def test_changed_data_with_fresh_split_hash_still_requires_new_review(self):
        raw = self.paths[0].read_bytes().replace(b'Repeat alpha', b'State alpha')
        self.paths[0].write_bytes(raw)
        self.manifest['train_sha256'] = hashlib.sha256(raw).hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.admit()
        # Explicitly replacing a review declaration is possible, never authenticated consent.
        self.save(rebind=True)
        self.admit()

    def test_rights_kind_language_and_original_text_rejected_even_with_new_digest(self):
        original = copy.deepcopy(self.manifest)
        for updates in ({'rights_for_training': False}, {'rights_for_training': 1},
                        {'kind': 'religious_source'}, {'language': ''}, {'language': 'unknown_language'},
                        {'text': 'mismatched original'}, {'license': ''}, {'attribution': ''}):
            self.manifest = copy.deepcopy(original)
            self.manifest['provenance']['sources'][self.key].update(updates)
            self.save(rebind=True)
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                self.admit()

    def test_exact_record_coverage_required(self):
        original = copy.deepcopy(self.manifest)
        for change in ('missing', 'extra', 'unused_source'):
            self.manifest = copy.deepcopy(original)
            provenance = self.manifest['provenance']
            if change == 'missing':
                del provenance['records'][self.key]
            elif change == 'extra':
                provenance['records']['unknown'] = provenance['records'][self.key]
            else:
                provenance['sources']['unused'] = provenance['sources'][self.key]
            self.save(rebind=True)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.admit()

    def test_record_lineage_failures_cannot_be_bypassed_by_review_digest(self):
        original = copy.deepcopy(self.manifest)
        for updates in ({'split': 'evaluation'}, {'source_id': 'missing'}, {'source_id': []},
                        {'source_language': 'pra'}, {'target_language': 'gu'}, {'decision': 'pending'},
                        {'reviewer': ''}, {'kind': 'machine_translation'}, {'kind': 'human_reviewed_translation'},
                        {'unknown': True}):
            self.manifest = copy.deepcopy(original)
            self.manifest['provenance']['records'][self.key].update(updates)
            self.save(rebind=True)
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                self.admit()

    def translation(self, language, kind):
        # Invented arbitrary-color labels stand in for declared translation lineage.
        # No Prakrit text or claim of an actual reviewed translation is supplied.
        self.manifest['provenance']['sources'][self.key]['language'] = 'pra'
        self.manifest['provenance']['records'][self.key].update(
            source_language='pra', target_language=language, kind=kind,
            reviewer='Synthetic translation-review declaration only')

    def test_declared_prakrit_to_gujarati_hindi_english_lineage(self):
        for language in ('gu', 'hi', 'en'):
            self.translation(language, 'human_reviewed_translation')
            self.save(rebind=True)
            self.assertEqual(self.admit()['manifest']['provenance']['records'][self.key]['target_language'], language)

    def test_machine_translation_remains_rejected_with_approved_flags(self):
        self.translation('gu', 'machine_translation')
        self.save(rebind=True)
        with self.assertRaisesRegex(ValueError, 'unreviewed machine'):
            self.admit()

    def test_shared_original_cannot_leak_into_evaluation_as_translation(self):
        provenance = self.manifest['provenance']
        key = 'heldout-delta'
        del provenance['sources'][key]
        provenance['records'][key].update(source_id=self.key, target_language='gu',
                                           kind='human_reviewed_translation')
        self.save(rebind=True)
        with self.assertRaisesRegex(ValueError, 'cross train/evaluation'):
            self.admit()

    def test_policy_decision_purpose_and_review_identity_required(self):
        original = copy.deepcopy(self.manifest)
        for updates in ({'policy': 'obsolete'}, {'decision': 'pending'}, {'reviewer': ''}, {'subject_sha256': True}):
            self.manifest = copy.deepcopy(original)
            self.manifest['review'].update(updates)
            self.save()
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                self.admit()
        self.manifest = original
        self.manifest['provenance']['purpose'] = 'local_retrieval'
        self.save(rebind=True)
        with self.assertRaises(ValueError):
            self.admit()

    def test_duplicate_metadata_keys_rejected(self):
        self.paths[2].write_bytes(self.paths[2].read_bytes().replace(b'"schema_version": 2', b'"schema_version": 2, "schema_version": 2'))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.admit()

    def test_preflight_and_cli_reject_before_model_access(self):
        del self.manifest['review']
        self.save()
        model, model_manifest = self.root / 'absent-model', self.root / 'absent-model-manifest'
        with self.assertRaisesRegex(ValueError, 'schema 2'):
            prepare_training(*self.paths, model, model_manifest)
        result = subprocess.run([sys.executable, '-m', 'jace.training_cli', str(self.paths[0]),
                                 '--evaluation', str(self.paths[1]), '--dataset-manifest', str(self.paths[2]),
                                 '--model', str(model), '--model-manifest', str(model_manifest)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('schema 2', result.stderr)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
