import dataclasses
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jace._fresh_study import preparation as f
from jace._fresh_study import consumer as c

SOURCE = b'''<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader/><text><body><p xml:id="TAS_1.1">Invented alpha.</p><p xml:id="SAS_1">Invented beta <hi>detail</hi>.</p><p xml:id="SAS_2">Invented context <note xml:id="note1">Invented note.</note></p><p xml:id="SAS_">Invented incomplete.</p><p xml:id="SAS_3">Invented final.</p></body></text></TEI>'''

class ConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bundle = Path(self.temp.name) / 'bundle'
        self.bundle.mkdir(mode=0o700)
        self.attr, self.acc = b'Synthetic attribution.', b'{"synthetic":true}'
        self.decl = f.Declaration(f.sha256(SOURCE), f.sha256(self.attr), f.sha256(self.acc), f.LICENSE, c.PURPOSE, True)
        prep = f.prepare(SOURCE, self.attr, self.acc, declaration=self.decl)
        self.raw = dict(zip(c.LIMITS, (SOURCE, self.attr, self.acc, f.CHANGE_NOTICE.encode(), prep.records_jsonl, prep.manifest_json)))
        for name, raw in self.raw.items():
            (self.bundle/name).write_bytes(raw)
            (self.bundle/name).chmod(0o600)
        self.pins = c.ExpectedPins(*(f.sha256(raw) for raw in self.raw.values()))
        self.study = c.StudyDeclaration(c.CONSUMER_VERSION, f.FORMAT, f.sha256(SOURCE), f.LICENSE, c.PURPOSE, True)

    def call(self, **kw):
        return c.consume(str(self.bundle), pins=self.pins, declaration=self.study, **kw)

    def test_inventory_has_no_source_text(self):
        result = self.call()
        self.assertNotIn('records', result)
        self.assertNotIn('Invented', str(result))
        self.assertTrue(all(v is False for v in result['safety'].values()))

    def test_exact_lookup_preserves_parts(self):
        result = self.call(operation='lookup', xml_id='SAS_1')
        record = result['records'][0]
        self.assertEqual(record['parsed_text'], 'Invented beta detail.')
        self.assertEqual(len(record['parsed_text_parts']), 3)
        self.assertIn('source_xml_path', record)
        self.assertEqual(result['attribution_notice'], self.attr.decode())

    def test_candidate_context(self):
        self.assertEqual(len(self.call(operation='lookup', xml_id='TAS_1.1', after=1)['records']), 2)

    def test_review_gate_for_target_and_context(self):
        for options in ({'xml_id':'note1'}, {'xml_id':'SAS_'}, {'xml_id':'SAS_2'}, {'xml_id':'SAS_1', 'after':1}):
            with self.subTest(options=options), self.assertRaises(c.ConsumerError):
                self.call(operation='lookup', **options)
            result = self.call(operation='lookup', reviewed_noncandidates=True, **options)
            self.assertGreaterEqual(len(result['records']), 1)

    def test_overlap_is_retained(self):
        r = self.call(operation='lookup', xml_id='note1', before=1, reviewed_noncandidates=True)['records']
        self.assertIn(r[0]['id'], r[1]['containing_record_ids'])

    def test_missing_exact_id(self):
        for identifier in ('missing', 'SAS', ' SAS_1', 'SAS_1 ', '', None):
            with self.subTest(identifier=identifier), self.assertRaises(c.ConsumerError):
                self.call(operation='lookup', xml_id=identifier)

    def test_bad_bounds_and_edges(self):
        for before, after in ((-1,0), (9,0), (True,0), (0,1.0), (1,0), (0,8)):
            with self.subTest(before=before, after=after), self.assertRaises(c.ConsumerError):
                self.call(operation='lookup', xml_id='TAS_1.1', before=before, after=after)

    def test_decl_and_pin_validation(self):
        for field, value in (('opted_in',1), ('purpose','training'), ('consumer_version','old'), ('preparation_version','old'), ('source_sha256','0'*64), ('accepted_license','other')):
            with self.subTest(field=field), self.assertRaises(c.ConsumerError):
                c.consume(str(self.bundle), pins=self.pins, declaration=dataclasses.replace(self.study, **{field:value}))
        with self.assertRaises(c.ConsumerError):
            c.consume(str(self.bundle), pins=None, declaration=self.study)

    def test_every_file_tamper_missing_empty_and_digest(self):
        for name in self.raw:
            path = self.bundle/name
            for raw in (b'', self.raw[name]+b' '):
                path.write_bytes(raw)
                with self.subTest(name=name), self.assertRaises(c.ConsumerError): self.call()
            path.unlink()
            with self.assertRaises(c.ConsumerError): self.call()
            path.write_bytes(self.raw[name]); path.chmod(0o600)

    def test_rehash_cannot_bypass_extraction(self):
        name = 'records.jsonl'
        raw = self.raw[name].replace(b'Invented alpha.', b'Altered content')
        (self.bundle/name).write_bytes(raw)
        self.pins = dataclasses.replace(self.pins, records_sha256=f.sha256(raw))
        with self.assertRaisesRegex(c.ConsumerError, 're-extraction'): self.call()

    def test_rehash_cannot_change_notice(self):
        raw = self.raw['CHANGES.txt'] + b'\n'
        (self.bundle/'CHANGES.txt').write_bytes(raw)
        self.pins = dataclasses.replace(self.pins, changes_sha256=f.sha256(raw))
        with self.assertRaisesRegex(c.ConsumerError, 'change notice'): self.call()

    def test_symlink_file_and_directory_components(self):
        for name in self.raw:
            path = self.bundle/name
            target = Path(self.temp.name)/'target'
            target.write_bytes(self.raw[name]); path.unlink(); path.symlink_to(target)
            with self.subTest(name=name), self.assertRaises(c.ConsumerError): self.call()
            path.unlink(); path.write_bytes(self.raw[name]); path.chmod(0o600)
        link = Path(self.temp.name)/'link'; link.symlink_to(self.bundle, target_is_directory=True)
        for path in (link, link/'child'):
            with self.assertRaises(c.ConsumerError):
                c.consume(str(path), pins=self.pins, declaration=self.study)

    def test_hardlink_and_fifo_rejected(self):
        path = self.bundle/'original.xml'; other = Path(self.temp.name)/'other'
        os.link(path, other)
        with self.assertRaises(c.ConsumerError): self.call()
        other.unlink(); path.unlink(); os.mkfifo(path)
        with self.assertRaises(c.ConsumerError): self.call()

    def test_changed_file_and_directory_during_verify(self):
        verify = f.verify
        def changed(*args, **kwargs):
            result = verify(*args, **kwargs)
            (self.bundle/'accession.json').write_bytes(self.acc + b' ')
            return result
        with patch.object(f, 'verify', changed), self.assertRaises(c.ConsumerError): self.call()
        (self.bundle/'accession.json').write_bytes(self.acc)
        def replaced(*args, **kwargs):
            result = verify(*args, **kwargs)
            self.bundle.rename(self.bundle.with_name('moved'))
            self.bundle.mkdir(mode=0o700)
            return result
        with patch.object(f, 'verify', replaced), self.assertRaises(c.ConsumerError): self.call()

    def test_oversize_is_rejected_before_read(self):
        with (self.bundle/'original.xml').open('wb') as stream: stream.truncate(f.MAX_SOURCE_BYTES+1)
        with self.assertRaises(c.ConsumerError): self.call()

    def test_private_modes_and_ownership(self):
        for path in (self.bundle, self.bundle/'original.xml'):
            mode = path.stat().st_mode & 0o777
            path.chmod(mode | 0o040)
            with self.assertRaisesRegex(c.ConsumerError, 'private ownership'): self.call()
            path.chmod(mode)
        with patch.object(c.os, 'geteuid', return_value=os.geteuid()+1):
            with self.assertRaisesRegex(c.ConsumerError, 'private ownership'): self.call()

    def test_invalid_paths_and_options(self):
        for path in ('relative', str(self.bundle) + '/', str(self.bundle) + '/../bundle'):
            with self.assertRaises(c.ConsumerError): c.consume(path, pins=self.pins, declaration=self.study)
        for options in ({'operation':'other'}, {'xml_id':'SAS_1'}, {'reviewed_noncandidates':True}, {'reviewed_noncandidates':1}):
            with self.assertRaises(c.ConsumerError): self.call(**options)

if __name__ == '__main__': unittest.main()
