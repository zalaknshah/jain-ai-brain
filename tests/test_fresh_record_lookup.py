import dataclasses,json,unittest
from unittest.mock import patch
import test_fresh_package_consumer as fixtures
from jace._fresh_study import consumer as c
from jace import fresh_study_request as request
class RecordLookupTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.ConsumerTests()
        with patch.object(fixtures,'SOURCE',fixtures.SOURCE.replace(b' xml:id="SAS_"',b'')):
            self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.rows=[json.loads(line) for line in self.f.raw['records.jsonl'].splitlines()]
        self.target=next(r for r in self.rows if r['source_xml_id'] is None)
    def test_queue_to_unidentified_record(self):
        queue=self.f.call(operation='review_queue',offset=0,limit=8,reviewed_noncandidates=True)
        item=next(r for r in queue['review_items'] if r['xml_id'] is None)
        out=self.f.call(operation='lookup_record',record_id=item['record_id'],reviewed_noncandidates=True)
        self.assertEqual(out['records'],[self.target]);self.assertEqual(out['target_record_id'],item['record_id'])
        self.assertEqual(out['identifier_semantics'],'preparation_local_record_id_not_scholarly_citation')
        self.assertTrue(all(value is False for value in out['safety'].values()))
    def test_noncandidate_not_admitted(self):
        with self.assertRaises(c.ConsumerError):self.f.call(operation='lookup_record',record_id=self.target['id'])
    def test_candidate_context(self):
        target=next(r for r in self.rows if r['source_xml_id']=='TAS_1.1')
        out=self.f.call(operation='lookup_record',record_id=target['id'],after=1)
        self.assertEqual(out['records'],self.rows[:2])
    def test_exact_id_missing(self):
        for identifier in [self.target['id']+'x','TAS_1.1','',None,True,'x'*257]:
            with self.subTest(identifier=identifier),self.assertRaises(c.ConsumerError):
                self.f.call(operation='lookup_record',record_id=identifier,reviewed_noncandidates=True)
    def test_option_separation(self):
        for options in [dict(xml_id='TAS_1.1'),dict(query='x'),dict(category='root_text_label'),dict(xml_ids=['a','b'])]:
            with self.subTest(options=options),self.assertRaises(c.ConsumerError):
                self.f.call(operation='lookup_record',record_id=self.target['id'],reviewed_noncandidates=True,**options)
        with self.assertRaises(c.ConsumerError):self.f.call(record_id=self.target['id'])
    def test_request_consent(self):
        req=dict(operation='lookup_record',record_id=self.target['id'],pins=dataclasses.asdict(self.f.pins),declaration=dataclasses.asdict(self.f.study))
        for disclosure,review in [(False,True),(True,False)]:
            with self.assertRaises(c.ConsumerError):request.run_request(json.dumps(req).encode(),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=disclosure,review_noncandidates=review)
        out=json.loads(request.run_request(json.dumps(req).encode(),bundle_directory=str(self.f.bundle),confirmed=True,allow_local_disclosure=True,review_noncandidates=True))
        self.assertEqual(out['records'],[self.target])
    def test_context_gate(self):
        target=next(r for r in self.rows if r['source_xml_id']=='SAS_1')
        with self.assertRaises(c.ConsumerError):self.f.call(operation='lookup_record',record_id=target['id'],after=1)
