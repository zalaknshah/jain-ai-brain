"""Invented fixture labels only; no real Prakrit books/translations or training."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jace import source_bundle as sb
from jace import training_review as tr
from jace.training import admit_dataset


@unittest.skipUnless(sys.platform == 'linux', 'descriptor-safe publication requires Linux')
class PrakritTrainingReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Large enough to exercise the worker's new >16KiB dataset manifest snapshot.
        self.raw = ('SYNTHETIC café α.\nSECOND invented note.\nUNAPPROVED fixture marker.\n' + 'filler ' * 3500).encode('utf-8')
        self.digest = hashlib.sha256(self.raw).hexdigest()
        self.book = self.root / 'invented.txt'
        self.book.write_bytes(self.raw)
        first_end = self.raw.index(b'\n')
        second_start = first_end + 1
        second_end = self.raw.index(b'\n', second_start)
        third_start = second_end + 1
        third_end = self.raw.index(b'\n', third_start)
        self.plan = {'books': {self.digest: {'path': str(self.book), 'work': 'Invented test work',
            'edition': 'Synthetic edition only', 'source': 'Original test author; no real book',
            'language': 'pra', 'license': 'Synthetic rights declaration', 'attribution': 'Original fixture author',
            'rights_evidence': 'Synthetic evidence reference; no actual rights clearance'}}, 'records': {}}
        for key, split, start, end, language, origin in [
            ('original', 'train', 0, first_end, 'pra', 'original'),
            ('heldout', 'evaluation', second_start, second_end, 'pra', 'original'),
            ('gujarati', 'train', 0, first_end, 'gu', 'machine_translation'),
            ('hindi', 'train', 0, first_end, 'hi', 'human_translation'),
            ('english', 'train', 0, first_end, 'en', 'human_translation'),
            ('blocked', 'train', third_start, third_end, 'pra', 'original')]:
            original = self.raw[start:end].decode('utf-8')
            translated = origin != 'original'
            self.plan['records'][key] = {'row': {'id': key, 'instruction': 'Invented unique fixture prompt ' + key,
                'response': 'Invented target label ' + language if translated else original},
                'split': split, 'book_sha256': self.digest, 'start': start, 'end': end, 'source_text': original,
                'target_language': language, 'origin': origin,
                **{name: 'Synthetic declaration only' if translated else '' for name in
                   ('translator', 'translation_license', 'translation_attribution', 'translation_rights_evidence')}}
        self.plan_path = self.root / 'plan.json'
        self.write(self.plan_path, self.plan)
        self.draft_dir, self.output = self.root / 'draft', self.root / 'admitted'

    def write(self, path, value):
        path.write_bytes(json.dumps(value, ensure_ascii=False).encode('utf-8'))

    def prepare(self):
        tr.prepare_review(self.plan_path, self.draft_dir, confirm_copy=True)
        self.draft = tr.read_json(self.draft_dir / 'draft.json')
        self.report = tr.read_json(self.draft_dir / 'decisions.json')

    def approve(self, decision, role):
        decision.update(decision='approved', reviewer='Synthetic human reviewer declaration', evidence='Synthetic evidence/rationale')
        decision['scopes' if role == 'rights' else 'qualified'] = list(tr.SCOPES) if role == 'rights' else True

    def approve_selected(self):
        for book in self.report['books'].values():
            self.approve(book['rights'], 'rights')
        for key, decision in self.report['records'].items():
            if key == 'blocked':
                continue
            for role in ('rights', 'content', 'translation'):
                if role != 'translation' or self.plan['records'][key]['origin'] != 'original':
                    self.approve(decision[role], role)

    def export(self, **changes):
        self.write(self.draft_dir / 'decisions.json', self.report)
        options = dict(confirm_export=True, declare_no_personal_data=True)
        options.update(changes)
        return tr.export_review(self.draft_dir / 'draft.json', self.draft_dir / 'decisions.json', self.output, **options)

    def admit(self):
        return admit_dataset(*(self.output / name for name in ('train.jsonl', 'evaluation.jsonl', 'manifest.json')))

    def test_pending_draft_and_decisions_are_not_admitted_or_exported(self):
        self.prepare()
        self.assertTrue(all(item['rights']['decision'] == 'pending' for item in self.report['books'].values()))
        with self.assertRaises(ValueError):
            admit_dataset(self.draft_dir / 'draft.json', self.draft_dir / 'decisions.json', self.draft_dir / 'draft.json')
        with self.assertRaisesRegex(ValueError, 'both train and evaluation'):
            self.export()
        self.assertFalse(self.output.exists())

    def test_whole_book_and_translation_approval_exports_only_selected_rows(self):
        self.prepare(); self.approve_selected()
        result = self.export()
        self.assertEqual((result['approved_records'], result['blocked_records']), (5, 1))
        self.assertFalse(result['training_started'])
        data = self.admit()
        self.assertEqual({row['id'] for row in data['train']}, {'original', 'gujarati', 'hindi', 'english'})
        self.assertEqual(len(data['evaluation']), 1)
        self.assertNotIn(b'UNAPPROVED', (self.output / 'train.jsonl').read_bytes())
        self.assertNotIn('blocked', data['manifest']['provenance']['records'])
        self.assertIn('UNAPPROVED', data['manifest']['provenance']['books'][self.digest]['text'])
        self.assertEqual(data['manifest']['provenance']['records']['gujarati']['origin'], 'machine_translation')
        self.assertGreater((self.output / 'manifest.json').stat().st_size, 16384)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        for path in self.output.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_confirmations_precede_reads(self):
        with patch.object(tr, 'read_json', side_effect=AssertionError('no read')):
            for value in (False, 1, 'true', None):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    tr.prepare_review('/absent', self.output, confirm_copy=value)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    tr.export_review('/absent', '/absent', self.output, confirm_export=value, declare_no_personal_data=True)
                with self.subTest(value=value), self.assertRaises(ValueError):
                    tr.export_review('/absent', '/absent', self.output, confirm_export=True, declare_no_personal_data=value)

    def test_missing_book_rights_blocks_every_translation(self):
        self.prepare(); self.approve_selected()
        self.report['books'][self.digest]['rights']['decision'] = 'pending'
        with self.assertRaisesRegex(ValueError, 'both train and evaluation'):
            self.export()
        self.assertFalse(self.output.exists())

    def test_translation_requires_rights_content_and_qualified_human_review(self):
        self.prepare(); self.approve_selected()
        original = copy.deepcopy(self.report)
        for role in ('rights', 'content', 'translation'):
            for state in ('pending', 'rejected'):
                self.report = copy.deepcopy(original)
                self.report['records']['gujarati'][role]['decision'] = state
                self.export()
                self.assertNotIn('gujarati', {row['id'] for row in self.admit()['train']})
                # Each iteration uses a distinct output; nothing is overwritten.
                self.output = self.root / ('out-' + role + '-' + state)
        self.report = original
        self.report['records']['hindi']['translation']['qualified'] = False
        with self.assertRaisesRegex(ValueError, 'qualified human'):
            self.export()

    def test_approval_requires_explicit_training_rights_and_evidence(self):
        self.prepare(); self.approve_selected()
        baseline = copy.deepcopy(self.report)
        for change in ({'scopes': ['local_retention']}, {'reviewer': ''}, {'evidence': ''}, {'scopes': tr.SCOPES + ['publish']}):
            self.report = copy.deepcopy(baseline)
            self.report['books'][self.digest]['rights'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.export()

    def test_stale_report_changed_translation_instruction_or_book_metadata(self):
        self.prepare(); self.approve_selected()
        baseline = copy.deepcopy(self.draft)
        for change in ('response', 'instruction', 'license', 'span'):
            draft = copy.deepcopy(baseline)
            p = draft['provenance']
            if change in ('response', 'instruction'):
                p['records']['gujarati']['row'][change] += ' changed'
            elif change == 'license':
                p['books'][self.digest]['license'] = 'Changed rights declaration'
            else:
                p['records']['gujarati']['start'] += 1
            self.write(self.draft_dir / 'draft.json', draft)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.export()

    def test_report_missing_extra_duplicate_or_obsolete_decisions(self):
        self.prepare(); self.approve_selected()
        baseline = copy.deepcopy(self.report)
        for change in ('missing', 'extra', 'policy', 'record_revision', 'book_revision'):
            self.report = copy.deepcopy(baseline)
            if change == 'missing':
                del self.report['records']['blocked']
            elif change == 'extra':
                self.report['records']['extra'] = self.report['records']['original']
            elif change == 'policy':
                self.report['policy'] = 'obsolete'
            elif change == 'record_revision':
                self.report['records']['original']['revision'] = '0' * 64
            else:
                self.report['books'][self.digest]['revision'] = '0' * 64
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.export()
        self.report = baseline
        path = self.draft_dir / 'decisions.json'
        raw = json.dumps(self.report).replace('"policy":', '"policy":"duplicate", "policy":')
        path.write_text(raw)
        with self.assertRaises(ValueError):
            tr.read_json(path)

    def test_exact_source_hash_span_language_and_split_checks(self):
        baseline = copy.deepcopy(self.plan)
        for change in ('hash', 'span', 'utf8', 'language', 'target', 'overlap', 'path'):
            self.plan = copy.deepcopy(baseline)
            record = self.plan['records']['gujarati']
            if change == 'hash':
                self.book.write_bytes(self.raw + b'changed')
            elif change == 'span':
                record['source_text'] += 'changed'
            elif change == 'utf8':
                record['start'] = self.raw.index('é'.encode('utf-8')) + 1
            elif change == 'language':
                self.plan['books'][self.digest]['language'] = 'en'
            elif change == 'target':
                record['target_language'] = 'fr'
            elif change == 'overlap':
                record['split'] = 'evaluation'
            else:
                self.plan['books'][self.digest]['path'] = '../invented.txt'
            self.write(self.plan_path, self.plan)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prepare()
            self.book.write_bytes(self.raw)

    def test_consumer_rejects_modified_report_book_and_rehashed_training_rows(self):
        self.prepare(); self.approve_selected(); self.export()
        path = self.output / 'manifest.json'
        baseline = json.loads(path.read_bytes())
        train = (self.output / 'train.jsonl').read_bytes()
        for change in ('pending', 'metadata', 'book', 'row'):
            manifest = copy.deepcopy(baseline)
            if change == 'pending':
                manifest['review']['records']['gujarati']['translation']['decision'] = 'pending'
            elif change == 'metadata':
                manifest['provenance']['records']['gujarati']['translation_license'] += 'changed'
            elif change == 'book':
                manifest['provenance']['books'][self.digest]['text'] += 'changed'
            else:
                raw = train.replace(b'Invented target label gu', b'Unreviewed changed output')
                (self.output / 'train.jsonl').write_bytes(raw)
                manifest['train_sha256'] = hashlib.sha256(raw).hexdigest()
            self.write(path, manifest)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.admit()
            (self.output / 'train.jsonl').write_bytes(train)

    def test_no_overwrite_symlink_and_failed_publication_cleanup(self):
        self.prepare(); self.approve_selected(); self.export()
        original = (self.output / 'manifest.json').read_bytes()
        with self.assertRaises(ValueError):
            self.export()
        self.assertEqual((self.output / 'manifest.json').read_bytes(), original)
        self.output = self.root / 'failed'
        with patch.object(sb, '_rename_noreplace', side_effect=ValueError('denied')):
            with self.assertRaisesRegex(ValueError, 'denied'):
                self.export()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.jace-training-review-*')), [])
        linked = self.root / 'linked.json'; linked.symlink_to(self.plan_path)
        with self.assertRaises(ValueError):
            tr.prepare_review(linked, self.root / 'unsafe', confirm_copy=True)

    def test_worker_large_snapshot_and_final_review_recheck_without_training(self):
        from test_training import OfflineTrainingTests
        from jace import training_worker
        fixture = OfflineTrainingTests()
        fixture.setUp(); self.addCleanup(fixture.tearDown)
        self.prepare(); self.approve_selected(); self.export()
        fixture.args = (*(self.output / name for name in ('train.jsonl', 'evaluation.jsonl', 'manifest.json')), fixture.model, fixture.root / 'model-manifest.json')
        def backend(plan, model, stage):
            self.assertEqual(plan['data']['manifest']['data_kind'], 'reviewed_prakrit')
            self.assertEqual(len(plan['data']['train']), 4)
            self.assertNotIn('blocked', {row['id'] for row in plan['data']['train']})
            manifest = json.loads((self.output / 'manifest.json').read_bytes())
            manifest['review']['records']['gujarati']['translation']['decision'] = 'rejected'
            self.write(self.output / 'manifest.json', manifest)
            return {'mock_only': True}
        with patch.object(training_worker, '_limits', return_value={}), patch.object(training_worker, '_train_qlora', side_effect=backend), patch.dict(os.environ, {}, clear=False):
            with self.assertRaisesRegex(ValueError, 'unapproved material'):
                training_worker.execute(fixture.job())
        self.assertFalse((fixture.root / 'run' / 'manifest.json').exists())
        self.assertTrue((fixture.root / 'run' / 'FAILED.json').exists())

    def test_cli_prepare_requires_consent_and_export_never_trains(self):
        result = subprocess.run([sys.executable, '-m', 'jace.training_review_cli', 'prepare', '--plan', '/absent', '--output', str(self.output)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('confirm_copy', result.stderr)
        self.assertFalse(self.output.exists())

    def test_cli_export_preflight_and_mocked_successful_worker(self):
        from test_training import OfflineTrainingTests
        from jace import training_worker
        fixture = OfflineTrainingTests()
        fixture.setUp(); self.addCleanup(fixture.tearDown)
        self.prepare(); self.approve_selected()
        self.write(self.draft_dir / 'decisions.json', self.report)
        result = subprocess.run([sys.executable, '-m', 'jace.training_review_cli', 'export',
            '--draft', str(self.draft_dir / 'draft.json'), '--decisions', str(self.draft_dir / 'decisions.json'),
            '--output', str(self.output), '--confirm-export', '--declare-no-personal-data'],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['training_started'])
        fixture.args = (*(self.output / name for name in ('train.jsonl', 'evaluation.jsonl', 'manifest.json')), fixture.model, fixture.root / 'model-manifest.json')
        result = subprocess.run([sys.executable, '-m', 'jace.training_cli', str(fixture.args[0]),
            '--evaluation', str(fixture.args[1]), '--dataset-manifest', str(fixture.args[2]),
            '--model', str(fixture.args[3]), '--model-manifest', str(fixture.args[4])],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['training_started'])
        def backend(plan, model, stage):
            (stage / 'adapter_model.safetensors').write_bytes(b'mock bytes only, no weights')
            (stage / 'adapter_config.json').write_text('{}')
            return {'mock_only': True}
        with patch.object(training_worker, '_limits', return_value={}), patch.object(training_worker, '_train_qlora', side_effect=backend), patch.object(training_worker, '_verify_export', return_value={'mock_only': True}), patch.dict(os.environ, {}, clear=False):
            report = training_worker.execute(fixture.job())
        self.assertEqual(report['dataset_kind'], 'reviewed_prakrit')
        self.assertEqual((report['train_records'], report['held_out_records']), (4, 1))
        self.assertTrue(report['metrics']['mock_only'])


class ExactPassageSplitTests(unittest.TestCase):
    """Pure synthetic provenance tests, including native platforms without safe IO."""
    def fixture(self, separate_book=True, translated=False, second_text=None):
        text = 'Invented café α fixture.'
        second_text = text if second_text is None else second_text
        originals = [text + '\nfirst edition', 'second edition\n' + second_text]
        if not separate_book:
            originals = [text + '\n' + second_text]
        books = {}
        for original in originals:
            digest = hashlib.sha256(original.encode()).hexdigest()
            books[digest] = dict(text=original, language='pra', **{key: 'Synthetic declaration'
                for key in ('work', 'edition', 'source', 'license', 'attribution', 'rights_evidence')})
        digests = list(books)
        records = {}
        for index, split in enumerate(('train', 'evaluation')):
            digest = digests[min(index, len(digests)-1)]
            raw = books[digest]['text'].encode()
            excerpt = text if index == 0 else second_text
            start = raw.index(excerpt.encode()) if index == 0 else raw.rindex(excerpt.encode())
            key = 'example' + str(index)
            records[key] = dict(row=dict(id=key, instruction='Distinct prompt ' + key,
                response=('Distinct translation ' + key) if translated else excerpt),
                split=split, book_sha256=digest, start=start, end=start+len(excerpt.encode()),
                source_text=excerpt, target_language=('gu' if index == 0 else 'hi') if translated else 'pra',
                origin='machine_translation' if translated else 'original',
                **{field: 'Synthetic declaration' if translated else '' for field in
                    ('translator', 'translation_license', 'translation_attribution', 'translation_rights_evidence')})
        return dict(purpose=tr.PURPOSE, books=books, records=records)

    def test_same_passage_in_different_editions_is_not_held_out(self):
        for translated in (False, True):
            for reverse in (False, True):
                with self.subTest(translated=translated, reverse=reverse):
                    value = self.fixture(translated=translated)
                    if reverse:
                        value['records'] = dict(reversed(list(value['records'].items())))
                    with self.assertRaisesRegex(ValueError, 'identical original passages'):
                        tr.review_template(value)

    def test_same_passage_at_disjoint_offsets_is_not_held_out(self):
        with self.assertRaisesRegex(ValueError, 'identical original passages'):
            tr.review_template(self.fixture(separate_book=False))

    def test_translations_of_same_passage_may_share_one_split(self):
        value = self.fixture(translated=True)
        value['records']['example1']['split'] = 'train'
        report = tr.review_template(value)
        self.assertEqual(len(report['records']), 2)
        self.assertTrue(all(item['content']['decision'] == 'pending' for item in report['records'].values()))

    def test_distinct_passages_and_unicode_variants_are_not_semantic_checks(self):
        for text in ('Different invented fixture.', 'Invented cafe\u0301 α fixture.'):
            tr.review_template(self.fixture(second_text=text))

    def test_training_consumer_rechecks_old_duplicate_exports_before_receipts(self):
        manifest = dict(schema_version=3, data_kind='reviewed_prakrit',
            rights_reviewed=True, content_reviewed=True, contains_personal_data=False,
            source='Synthetic', license='Synthetic', train_sha256='0'*64,
            evaluation_sha256='0'*64, provenance=self.fixture(translated=True), review={})
        with patch.object(tr, '_selected', side_effect=AssertionError('must reject before review receipts')):
            with self.assertRaisesRegex(ValueError, 'identical original passages'):
                tr.validate_admitted(manifest, [[], []])


class UnsupportedTrainingReviewTests(unittest.TestCase):
    def test_unsupported_platform_fails_before_private_reads(self):
        with patch.object(sb, '_safe_io_missing', return_value=['posix_os']), patch.object(tr, 'read_json', side_effect=AssertionError('no private read')):
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                tr.prepare_review('/absent', '/absent', confirm_copy=True)


if __name__ == '__main__':
    unittest.main()
