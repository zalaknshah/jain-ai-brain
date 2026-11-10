"""Original synthetic regressions for mutually exclusive corpus admission modes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jace.canonical import CanonicalStore
from jace.corpus import ingest_files


ROOT = Path(__file__).resolve().parents[1]
METADATA = {'work': 'Original synthetic fixture', 'source': 'Test author',
            'language': 'en', 'edition': 'test-only', 'location': 'fixture section 1',
            'license_name': 'Original fixture permission'}


class CorpusDraftModeTests(unittest.TestCase):
    def test_conflicting_modes_rejected_before_path_iteration_read_or_write(self):
        def paths():
            raise AssertionError('paths must not be inspected')
            yield Path('/unused')
        with patch.object(Path, 'read_text', side_effect=AssertionError('No read')) as read, \
                patch.object(Path, 'write_text', side_effect=AssertionError('No write')) as write:
            with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
                ingest_files(paths(), '/unused/output.json', **METADATA, draft=True, verified=True)
            read.assert_not_called()
            write.assert_not_called()

    def test_conflict_leaves_an_existing_output_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'existing.json'
            output.write_bytes(b'Original sentinel, not corpus data')
            with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
                ingest_files([Path(directory)/'not-present.txt'], output,
                             **METADATA, draft=True, verified=True)
            self.assertEqual(output.read_bytes(), b'Original sentinel, not corpus data')

    def test_boolean_lookalikes_are_rejected_before_any_file_work(self):
        invalid = (0, 1, -1, 0.0, 1.0, None, '', 'false', 'true', [], {}, [True])
        with patch.object(Path, 'read_text', side_effect=AssertionError('No read')) as read, \
                patch.object(Path, 'write_text', side_effect=AssertionError('No write')) as write:
            for key in ('draft', 'verified'):
                for value in invalid:
                    with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, 'literal booleans'):
                        ingest_files(['/unused.txt'], '/unused.json', **METADATA,
                                     **{'draft': False, 'verified': False, key: value})
            read.assert_not_called()
            write.assert_not_called()

    def test_complete_metadata_cannot_make_a_draft_loadable(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'fixture.txt'
            output = Path(directory)/'draft.json'
            source.write_text('Synthetic first passage. Synthetic second passage.', encoding='utf-8')
            count = ingest_files([source], output, **METADATA, draft=True,
                                 chunk_size=3, overlap=1)
            records = json.loads(output.read_text())
            self.assertEqual(count, len(records))
            self.assertGreater(count, 1)
            self.assertTrue(all(record['verified'] is False for record in records))
            self.assertTrue(all(record['license'] == METADATA['license_name'] for record in records))
            with self.assertRaisesRegex(ValueError, 'review'):
                CanonicalStore(output)

    def test_reviewed_runtime_mode_still_loads_and_defaults_still_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'fixture.txt'
            output = Path(directory)/'runtime.json'
            source.write_text('Original synthetic source content.', encoding='utf-8')
            with self.assertRaises(ValueError):
                ingest_files([source], output, **METADATA)
            self.assertFalse(output.exists())
            count = ingest_files([source], output, **METADATA, verified=True)
            entries = CanonicalStore(output).all()
            self.assertEqual(count, 1)
            self.assertEqual(len(entries), 1)
            self.assertIs(entries[0].verified, True)
            self.assertEqual(entries[0].principle, 'Original synthetic source content.')

    def test_draft_output_without_license_stays_review_only(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'fixture.txt'
            output = Path(directory)/'draft.json'
            source.write_text('Original synthetic source content.', encoding='utf-8')
            ingest_files([source], output, **{**METADATA, 'license_name': None}, draft=True)
            self.assertIs(json.loads(output.read_text())[0]['verified'], False)
            with self.assertRaises(ValueError):
                CanonicalStore(output)


class CorpusDraftCliTests(unittest.TestCase):
    def call(self, source, output, *mode):
        env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR') if key in os.environ}
        return subprocess.run([sys.executable, str(ROOT/'scripts/ingest_corpus.py'), str(source),
            '--output', str(output), '--work', METADATA['work'], '--source', METADATA['source'],
            '--location', METADATA['location'], '--license', METADATA['license_name'], *mode],
            text=True, capture_output=True, env=env, timeout=5, check=False)

    def test_both_flag_orders_fail_without_reading_missing_input_or_touching_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'existing.json'
            output.write_bytes(b'Synthetic existing output sentinel')
            for modes in (('--draft', '--verified'), ('--verified', '--draft')):
                with self.subTest(modes=modes):
                    result = self.call(Path(directory)/'not-present.txt', output, *modes)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('not allowed with argument', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertEqual(result.stdout, '')
                    self.assertEqual(output.read_bytes(), b'Synthetic existing output sentinel')

    def test_cli_draft_is_rejected_by_runtime_and_verified_mode_remains_available(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'fixture.txt'
            source.write_text('Original synthetic source content.', encoding='utf-8')
            for mode in ('--draft', '--verified'):
                with self.subTest(mode=mode):
                    output = Path(directory)/(mode[2:]+'.json')
                    result = self.call(source, output, mode)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(output.read_text())[0]['verified'], mode == '--verified')
                    if mode == '--draft':
                        with self.assertRaises(ValueError):
                            CanonicalStore(output)
                    else:
                        self.assertEqual(len(CanonicalStore(output).all()), 1)


if __name__ == '__main__':
    unittest.main()
