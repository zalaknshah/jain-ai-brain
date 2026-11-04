import json
import tempfile
import unittest
from pathlib import Path

from jace.canonical import CanonicalStore
from jace.corpus import ingest_files


class CorpusAdmissionTests(unittest.TestCase):
    def test_unreviewed_or_unlicensed_ingestion_requires_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.txt'
            target = Path(directory) / 'corpus.json'
            source.write_text('A synthetic source passage.', encoding='utf8')
            for options in [{}, {'verified':True}, {'license_name':'CC0-1.0'}]:
                with self.subTest(options=options):
                    with self.assertRaises(ValueError):
                        ingest_files([source], target, work='Fixture', source='Synthetic fixture', **options)
                    self.assertFalse(target.exists())
            self.assertEqual(ingest_files([source], target, work='Fixture', source='Synthetic fixture', draft=True), 1)
            with self.assertRaises(ValueError):
                CanonicalStore(target)

    def test_reviewed_records_load_with_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.txt'
            target = Path(directory) / 'corpus.json'
            source.write_text('A synthetic source passage.', encoding='utf8')
            ingest_files([source], target, work='Fixture', source='Synthetic fixture',
                         verified=True, license_name='CC0-1.0', location='Fixture paragraph 1')
            record = CanonicalStore(target).all()[0]
            self.assertTrue(record.verified)
            self.assertEqual(record.location, 'Fixture paragraph 1')
            self.assertEqual(record.license, 'CC0-1.0')

    def test_hash_does_not_depend_on_checkout_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            ids=[]
            for name in ['one','two']:
                folder=Path(directory)/name
                folder.mkdir()
                source=folder/'source.txt'; target=folder/'corpus.json'
                source.write_text('A synthetic source passage.', encoding='utf8')
                ingest_files([source], target, work='Fixture', source='Synthetic fixture',
                             verified=True, license_name='CC0-1.0')
                ids.append(json.loads(target.read_text())[0]['entry_id'])
            self.assertEqual(ids[0],ids[1])

    def test_blank_external_path_uses_sample_and_empty_input_does_not_write(self):
        self.assertEqual(len(CanonicalStore('').all()), 6)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'empty.json'
            with self.assertRaises(ValueError):
                ingest_files([], target, work='Fixture', source='Synthetic fixture', draft=True)
            self.assertFalse(target.exists())

    def test_builtin_sample_is_available_but_not_claimed_verified(self):
        records=CanonicalStore().all()
        self.assertEqual(len(records),6)
        self.assertTrue(all(not record.verified for record in records))


if __name__ == '__main__':
    unittest.main()
