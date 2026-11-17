"""Synthetic files only; collision rejection is not corpus qualification."""
import json
import tempfile
import unittest
from pathlib import Path

from jace.canonical import CanonicalStore
from jace.corpus import ingest_files


class CorpusDuplicateIdentityTests(unittest.TestCase):
    def ingest(self, paths, output, **kwargs):
        return ingest_files(paths, output, work='Synthetic fixture', source='Synthetic fixture',
                            verified=True, license_name='CC0-1.0', **kwargs)

    def test_repeated_path_never_creates_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.txt'
            source.write_text('Synthetic passage only.', encoding='utf-8')
            output = root / 'new' / 'corpus.json'
            with self.assertRaisesRegex(ValueError, 'Duplicate corpus entry identity'):
                self.ingest([source, source], output)
            self.assertFalse(output.parent.exists())

    def test_distinct_paths_with_colliding_identity_preserve_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for name in ('one', 'two'):
                folder = root / name
                folder.mkdir()
                source = folder / 'source.txt'
                source.write_text('Synthetic passage only.', encoding='utf-8')
                paths.append(source)
            output = root / 'corpus.json'
            output.write_bytes(b'existing checkpoint\n')
            with self.assertRaisesRegex(ValueError, 'Duplicate corpus entry identity'):
                self.ingest(iter(paths), output)
            self.assertEqual(output.read_bytes(), b'existing checkpoint\n')

    def test_explicit_shared_location_collision_is_rejected_for_draft_too(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / 'one.txt', root / 'two.txt']
            for path in paths:
                path.write_text('Synthetic passage only.', encoding='utf-8')
            output = root / 'corpus.json'
            with self.assertRaisesRegex(ValueError, 'Duplicate corpus entry identity'):
                ingest_files(paths, output, work='Fixture', source='Fixture',
                             location='Shared location', draft=True)
            self.assertFalse(output.exists())

    def test_distinct_locations_are_preserved_not_silently_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / 'one.txt', root / 'two.txt']
            for path in paths:
                path.write_text('Synthetic passage only.', encoding='utf-8')
            output = root / 'corpus.json'
            self.assertEqual(self.ingest(paths, output), 2)
            entries = CanonicalStore(output).all()
            self.assertEqual(len({entry.entry_id for entry in entries}), 2)
            self.assertEqual({entry.location for entry in entries}, {'one.txt', 'two.txt'})
            previous = json.loads(output.read_text())
            self.ingest(paths, output)
            self.assertEqual(previous, json.loads(output.read_text()))
