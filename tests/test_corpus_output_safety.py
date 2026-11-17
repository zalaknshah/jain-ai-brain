"""Synthetic output preservation checks, not native Windows/crash qualification."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jace.canonical import CanonicalStore
from jace.corpus import ingest_files


class CorpusOutputSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'input.txt'
        self.original = b'Synthetic input passage.'
        self.source.write_bytes(self.original)
        self.output = self.root / 'output.json'
        self.previous = b'previous checkpoint'
        self.output.write_bytes(self.previous)

    def ingest(self, output=None, **kwargs):
        return ingest_files(iter([self.source]), output or self.output,
                            work='Fixture', source='Synthetic fixture',
                            verified=True, license_name='CC0-1.0', **kwargs)

    def assert_preserved(self):
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.output.read_bytes(), self.previous)
        self.assertEqual(list(self.root.glob('.jace-corpus-*')), [])

    def test_direct_source_alias_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'alias'):
            self.ingest(self.source)
        self.assert_preserved()

    def test_normalized_source_alias_is_refused(self):
        folder = self.root / 'sub'
        folder.mkdir()
        with self.assertRaisesRegex(ValueError, 'alias'):
            self.ingest(folder / '..' / self.source.name)
        self.assert_preserved()

    def test_symlink_source_alias_is_refused(self):
        alias = self.root / 'alias.json'
        try:
            alias.symlink_to(self.source)
        except (OSError, NotImplementedError):
            self.skipTest('symlink creation unavailable')
        with self.assertRaisesRegex(ValueError, 'alias'):
            self.ingest(alias)
        self.assertTrue(alias.is_symlink())
        self.assert_preserved()

    def test_hardlink_source_alias_is_refused(self):
        alias = self.root / 'alias.json'
        try:
            os.link(self.source, alias)
        except (OSError, NotImplementedError):
            self.skipTest('hardlink creation unavailable')
        with self.assertRaisesRegex(ValueError, 'alias'):
            self.ingest(alias)
        self.assertEqual(alias.read_bytes(), self.original)
        self.assert_preserved()

    def test_encoding_error_preserves_existing_output(self):
        with self.assertRaises(UnicodeEncodeError):
            self.ingest(tags=['\ud800'])
        self.assert_preserved()

    def test_encoding_error_creates_no_output_directory(self):
        output = self.root / 'new' / 'corpus.json'
        with self.assertRaises(UnicodeEncodeError):
            self.ingest(output, tags=['\ud800'])
        self.assertFalse(output.parent.exists())
        self.assert_preserved()

    def test_partial_staging_write_preserves_output_and_cleans_stage(self):
        original = tempfile.NamedTemporaryFile
        def broken(*args, **kwargs):
            stream = original(*args, **kwargs)
            def write(data):
                stream.file.write(data[:17])
                raise OSError('synthetic partial write')
            stream.write = write
            return stream
        with patch('jace.corpus.tempfile.NamedTemporaryFile', side_effect=broken):
            with self.assertRaisesRegex(OSError, 'partial write'):
                self.ingest()
        self.assert_preserved()

    def test_short_staging_write_is_not_reported_as_success(self):
        original = tempfile.NamedTemporaryFile
        def broken(*args, **kwargs):
            stream = original(*args, **kwargs)
            stream.write = lambda data: stream.file.write(data[:17])
            return stream
        with patch('jace.corpus.tempfile.NamedTemporaryFile', side_effect=broken):
            with self.assertRaisesRegex(OSError, 'Incomplete corpus staging write'):
                self.ingest()
        self.assert_preserved()

    def test_stage_creation_failure_preserves_output(self):
        with patch('jace.corpus.tempfile.NamedTemporaryFile', side_effect=OSError('synthetic creation')):
            with self.assertRaisesRegex(OSError, 'synthetic creation'):
                self.ingest()
        self.assert_preserved()

    def test_flush_failure_preserves_output_and_cleans_stage(self):
        original = tempfile.NamedTemporaryFile
        def broken(*args, **kwargs):
            stream = original(*args, **kwargs)
            stream.flush = lambda: (_ for _ in ()).throw(OSError('synthetic flush'))
            return stream
        with patch('jace.corpus.tempfile.NamedTemporaryFile', side_effect=broken):
            with self.assertRaisesRegex(OSError, 'synthetic flush'):
                self.ingest()
        self.assert_preserved()

    def test_replace_failure_preserves_output_and_cleans_stage(self):
        with patch('jace.corpus.os.replace', side_effect=OSError('synthetic replace')):
            with self.assertRaisesRegex(OSError, 'synthetic replace'):
                self.ingest()
        self.assert_preserved()

    def test_success_replaces_complete_output_without_changing_source(self):
        self.assertEqual(self.ingest(), 1)
        self.assertEqual(CanonicalStore(self.output).all()[0].principle,
                         self.original.decode())
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob('.jace-corpus-*')), [])

    def test_non_source_symlink_is_replaced_not_followed(self):
        target = self.root / 'other.txt'
        target.write_bytes(b'untouched')
        alias = self.root / 'alias.json'
        try:
            alias.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest('symlink creation unavailable')
        self.assertEqual(self.ingest(alias), 1)
        self.assertFalse(alias.is_symlink())
        self.assertEqual(target.read_bytes(), b'untouched')
        self.assertEqual(len(CanonicalStore(alias).all()), 1)
        self.assert_preserved()
